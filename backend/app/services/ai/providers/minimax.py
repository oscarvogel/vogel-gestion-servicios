"""Adaptador de MiniMax.

Contrato verificado en la documentacion de MiniMax:
- Base OpenAI-compatible: ``https://api.minimax.io/v1`` (host internacional; el de China
  es api.minimaxi.com)
- ``POST /v1/chat/completions`` con ``Authorization: Bearer <key>``
- El limite se llama ``max_completion_tokens``; ``max_tokens`` esta deprecado en esta
  interfaz y da error
- El nombre del modelo es **case-sensitive**: ``MiniMax-M3`` con las dos M mayusculas
- Acepta los roles ``system`` / ``user`` / ``assistant`` y tambien ``tool``

Tool calling, verificado contra la API real el 2026-10-03 con el modelo M3:
- Acepta ``tools`` con la forma de OpenAI: ``{"type": "function", "function": {name,
  description, parameters}}``, donde ``parameters`` es JSON Schema.
- Cuando pide una herramienta, la respuesta llega con ``finish_reason: "tool_calls"`` y
  ``message.tool_calls[]`` con ``{id, type, function: {name, arguments}}``. **``arguments``
  viene como string JSON**, hay que parsearlo.
- ``message.content`` puede traer texto ademas de las llamadas: no implica que no haya
  herramientas que ejecutar.
- El round trip funciona: assistant con ``tool_calls`` + ``tool`` con ``tool_call_id`` y el
  contenido del resultado, y el modelo responde usando ese resultado. (``role: "developer"``
  si da 400.)

La clave vive solo en el backend: sale de la configuracion y nunca se loguea ni se
devuelve en una respuesta de la API.
"""
from __future__ import annotations

import json
import time

import httpx

from app.core.config import settings
from app.services.ai.providers.base import (
    ALLOWED_ROLES,
    LlmMessage,
    LlmResponse,
    LlmToolCall,
    ProviderError,
)


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

    def complete(
        self,
        messages: list[LlmMessage],
        max_tokens: int = 1024,
        tools: list[dict] | None = None,
    ) -> LlmResponse:
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
        if tools:
            body["tools"] = tools
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
        tool_calls = _parse_tool_calls(message.get("tool_calls"))
        if not text and not tool_calls:
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
            tool_calls=tool_calls,
            raw={"duration_ms": int((time.perf_counter() - started) * 1000)},
        )


def _parse_tool_calls(raw: object) -> list[LlmToolCall]:
    """``tool_calls`` de la respuesta, con ``arguments`` ya parseado.

    Si el modelo manda argumentos que no son JSON no es motivo para perder la respuesta: la
    llamada se descarta y el resto de la conversacion sigue. Un ``arguments`` ilegible es un
    error del modelo, no una caida del sistema.
    """
    if not isinstance(raw, list):
        return []
    calls: list[LlmToolCall] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fn = item.get("function") or {}
        name = fn.get("name")
        if not name:
            continue
        arguments_raw = fn.get("arguments")
        if isinstance(arguments_raw, dict):
            arguments = arguments_raw
        else:
            try:
                arguments = json.loads(arguments_raw or "{}")
            except (TypeError, ValueError):
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append(
            LlmToolCall(id=str(item.get("id") or f"call_{len(calls) + 1}"), name=str(name), arguments=arguments)
        )
    return calls
