FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
# OJO: las apps de Coolify de este repo **no** se construyen con este
# Dockerfile: usan NIXPACKS (build_pack = nixpacks), que genera su propio
# Dockerfile y corre `pip install .`, sin extras. Por eso el driver de Flexxus
# esta en las dependencias base de `pyproject.toml` y no solo en el extra
# `flexxus`: con el driver solo en el extra, la imagen de produccion salia sin
# el y el modulo de repuestos degradaba a texto libre sin avisar.
#
# Este Dockerfile queda para los builds manuales (`docker build`).
RUN pip install --no-cache-dir .[dev,flexxus]
COPY . .
CMD ["sh","-c","alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
