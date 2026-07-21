FROM python:3.12-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

WORKDIR /code

COPY pyproject.toml uv.lock ./
RUN uv sync --locked

COPY . .

CMD ["uv", "run", "fastapi", "run", "src/main.py", "--port", "8000", "--host", "0.0.0.0"]
