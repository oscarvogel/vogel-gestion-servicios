FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
# El extra `flexxus` trae el driver firebirdsql. Sin el, el modulo de
# repuestos degrada a texto libre en produccion sin avisar: es mejor que
# falle el build.
RUN pip install --no-cache-dir .[dev,flexxus]
COPY . .
CMD ["sh","-c","alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
