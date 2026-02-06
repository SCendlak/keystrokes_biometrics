FROM python:3.11-slim

WORKDIR /app

# Instalacja uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Zaleznosci z lockfile (lepsza powtarzalnosc niz requirements.txt)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Reszta aplikacji
COPY . .

# Uvicorn jest w zaleznosciach fastapi[standard]; uruchamiamy z venv uv
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
