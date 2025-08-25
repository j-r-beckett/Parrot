FROM python:3.13-slim AS builder
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

FROM python:3.13-slim
RUN pip install uv
COPY --from=builder /.venv /.venv
COPY . .
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
