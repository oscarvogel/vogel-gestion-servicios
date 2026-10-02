import secrets

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///./dev.db"
    jwt_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    cors_origins: str = "http://localhost:5173"

    # --- Avisos al cliente (#45) ---
    # La autenticacion es de plataforma, nunca por empresa: en la base solo queda que
    # instancia de la gateway y que remitente se muestra. El aislamiento por empresa lo
    # resuelven la gateway (403 si el instanceId no es de la empresa de la key) y el
    # company_id de cada fila de la cola.
    whatsapp_base_url: str = "https://whatsapp.vogelconsultoria.com.ar"
    whatsapp_api_key: str | None = None
    whatsapp_default_instance: str | None = None
    whatsapp_timeout_seconds: float = 15.0
    whatsapp_source_app: str = "vogel-gestion"

    # Clave maestra para cifrar las credenciales por empresa (API key de la gateway).
    # Sin esta variable NO se guardan credenciales: se prefiere fallar a guardar en claro.
    credentials_encryption_key: str | None = None

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = 20.0
    # Remitente por defecto de la plataforma cuando la empresa no define el suyo.
    email_from_address: str | None = None
    email_from_name: str = "Vogel Gestión de Servicios"

    # Cuántos intentos como máximo antes de dejar una notificación en FAILED para
    # revisión manual. El drenaje nunca reintenta en caliente sin límite.
    notification_max_attempts: int = 5

    # --- Archivos de equipo (#43) ---
    # El dominio habla con una interfaz de storage; aca se elige el backend. La
    # implementacion por defecto es el sistema de archivos sobre un volumen persistente,
    # igual que la multimedia de la gateway de WhatsApp. Un backend desconocido falla
    # en vez de caer al disco en silencio.
    storage_backend: str = "filesystem"
    storage_local_root: str = "./data/equipment-documents"
    # Tope de tamaño por archivo, en MB. Se valida antes de leer, no despues.
    storage_max_file_mb: int = 25

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
