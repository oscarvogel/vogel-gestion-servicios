# Vogel Gestión de Servicios

Plataforma web multiempresa para gestión de servicios técnicos, órdenes de trabajo y posventa.

## Fundación implementada

- FastAPI + API v1
- Vue 3 + Vite + Pinia
- MySQL 8
- SQLAlchemy 2 + Alembic
- JWT access/refresh
- empresas, usuarios y membresías
- selección y validación de empresa activa
- test inicial de aislamiento tenant
- Docker Compose
- CI backend/frontend
- adaptadores separados para PortalVogel y WhatsApp

## Desarrollo local

1. Copiar `.env.example` a `.env`.
2. Ejecutar `docker compose up --build`.
3. Backend: `http://localhost:8000`.
4. Health: `http://localhost:8000/health`.
5. Frontend: `http://localhost:5173`.

La regla central es que el tenant efectivo se obtiene de una empresa activa autorizada para el usuario; no se confía en un `company_id` arbitrario enviado por el frontend.

## API de foundation

- `GET /health` devuelve `{"status":"ok"}`.
- `POST /api/v1/auth/login` emite access y refresh tokens sin empresa activa.
- `POST /api/v1/auth/refresh` emite un nuevo access token desde un refresh token.
- `POST /api/v1/auth/select-company` valida empresa activa y membresía antes de fijar el tenant.
- `GET /api/v1/companies/current` requiere un tenant válido en el access token.

Después de ejecutar `alembic upgrade head`, el seed de staging se ejecuta únicamente de forma explícita:

```powershell
python backend/scripts/seed_staging.py
```

Las contraseñas del seed se leen desde `STAGING_*_PASSWORD` o se generan de forma segura; no se almacenan en el repositorio.
