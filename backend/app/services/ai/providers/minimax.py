"""Adaptador de MiniMax.

Contrato verificado en la documentacion de MiniMax:
- Base OpenAI-compatible: ``https://api.minimax.io/v1`` (host internacional; el de China
  es api.minimaxi.com)
- ``POST /v1/chat/completions`` con ``Authorization: Bearer <key>``
- El limite se llama ``max_completion_tokens``; ``max_tokens`` esta deprecado en esta
  interfaz y da error
- El nombre del modelo es **case-sensitive**: ``MiniMax-M3`` con las dos M mayusculas
- Solo acepta roles ``system`` / ``user`` / ``assistant``

La clave vive solo en el backend: sale de la configuracion y nunca se loguea ni se
devuelve en una respuesta de la API.
"""
from __future__ import annotations

import time

import httpx

from app.core.config import settings
from app.services.ai.providers.base import ALLOWED_ROLES, LlmMessage, LlmResponse, ProviderError


class MinimaxProvider:
    name = "minimax"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        self._api_key = (api_key if api_key is not None else settings.minimax_api_key or "").strip()
        self._base_url = (base_url or settings.minimax_base_url).rstrip("/")
        self._model = model or settings.minimax_model
        self._timeout = timeout if timeout is not None else settings.ai_timeout_seconds

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def model_id(self) -> str:
        return self._model

    def complete(self, messages: list[LlmMessage], max_tokens: int = 1024) -> LlmResponse:
        if not self._api_key:
            raise ProviderError("MiniMax no tiene API key cargada en la plataforma.")
        payload_messages = [m.as_dict() for m in messages if m.role in ALLOWED_ROLES]
        if not payload_messages:
            raise ProviderError("No hay mensajes válidos para enviar al proveedor.")

        body = {
            "model": self._model,
            "messages": payload_messages,
            # En esta interfaz el limite es max_completion_tokens, no max_tokens.
            "max_completion_tokens": max_tokens,
            # Sin razonamiento expuesto: sale mas barato y la respuesta al usuario es limpia.
            "thinking": {"type": "disabled"},
        }
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(f"MiniMax no respondio en {self._timeout:g}s.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"No se pudo contactar a MiniMax: {type(exc).__name__}.") from exc

        if response.status_code in (401, 403):
            raise ProviderError("MiniMax rechazo la API key (401/403). Revisar la credencial en la plataforma.")
        if response.status_code == 429:
            raise ProviderError("MiniMax replied que se alcanzo el limite de peticiones o de tokens (429).")
        if response.status_code >= 400:
            raise ProviderError(f"MiniMax respondio {response.status_code}: {response.text[:200]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("MiniMax devolvio una respuesta que no es JSON.") from exc

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("MiniMax no devolvio ninguna respuesta.")
        message = choices[0].get("message") or {}
        text = (message.get("content") or "").strip()
        if not text:
            # Puede pasar si el modelo solo devuelve razonamiento y lo pedimos off.
            raise ProviderError("MiniMax devolvio una respuesta vacia.")
        usage = data.get("usage") or {}
        return LlmResponse(
            text=text,
            model=data.get("model") or self._model,
            provider=self.name,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            finish_reason=choices[0].get("finish_reason"),
            raw={"duration_ms": int((time.perf_counter() - started) * 1000)},
        )
