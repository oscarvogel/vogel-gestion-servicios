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

    # --- Flexxus: ERP de Suevos, Firebird 3050 (#114) ---
    # Credenciales de **plataforma**, no de la empresa: Flexxus es un ERP
    # unico de la plataforma. La habilitacion por tenant va en el parametro de
    # empresa `flexxus.enabled`; aca solo vive el secreto y la direccion.
    #
    # La "base" es la ruta del `.gdb` vista DESDE EL SERVIDER Firebird, no una
    # ruta local del backend: el backend no tiene el archivo.
    flexxus_host: str = "suevos.ddns.net"
    flexxus_port: int = 3050
    flexxus_user: str = "ELECTROTR"
    flexxus_password: str | None = None
    flexxus_charset: str = "ISO8859_1"
    flexxus_database: str = r"C:\FLEXXUS\DB\ETR\DB-ETR.gdb"
    flexxus_timeout_seconds: float = 10.0

    # --- Modulo IA (#44) ---
    # La API key vive solo en el backend. Sin ella el sistema sigue andando: la IA
    # queda 'no disponible' y el resto de la app no se enteran.
    ai_provider: str = "minimax"
    minimax_api_key: str | None = None
    minimax_base_url: str = "https://api.minimax.io/v1"
    # El nombre del modelo es case-sensitive en MiniMax: MiniMax-M3, con las dos M.
    minimax_model: str = "MiniMax-M3"
    ai_timeout_seconds: float = 30.0
    ai_max_tokens: int = 1024
    ai_fallback_model: str = "simulado"
    # Precios por millon de tokens, para estimar el costo del adicional. Es estimacion:
    # el precio real es el de la factura del proveedor.
    ai_price_input_per_million_usd: float = 0.30
    ai_price_output_per_million_usd: float = 1.20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
