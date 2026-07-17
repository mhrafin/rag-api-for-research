FROM python:3.12-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY . /code

WORKDIR /code

# This uv sync does create .venv in the container. So we would either need to use uv run or set path for the .venv
RUN uv sync --locked

CMD ["uv","run","fastapi", "run", "src/main.py", "--port", "8000"]
