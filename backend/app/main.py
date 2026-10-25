from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_router
from app.core.build_info import build_info
from app.core.config import settings

app = FastAPI(title="Vogel Gestión de Servicios")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | None]:
    # Incluye version y commit para poder preguntar "¿que build esta vivo?" sin login.
    return {"status": "ok", **build_info()}


app.include_router(api_router, prefix="/api/v1")
