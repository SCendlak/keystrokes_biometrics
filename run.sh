#!/usr/bin/env bash
set -e

# Katalog projektu (tam gdzie jest docker-compose.yml)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

FRONTEND_URL="http://localhost:5173"
DOCKER_DOWNLOAD_URL="https://docs.docker.com/get-docker/"

# --- Sprawdzenie Dockera ---
check_docker() {
  if ! command -v docker &>/dev/null; then
    echo "Docker nie jest zainstalowany lub nie jest w PATH."
    echo "Pobierz i zainstaluj Docker: $DOCKER_DOWNLOAD_URL"
    if [[ "$(uname)" == "Darwin" ]]; then
      open "$DOCKER_DOWNLOAD_URL" 2>/dev/null || true
    elif command -v xdg-open &>/dev/null; then
      xdg-open "$DOCKER_DOWNLOAD_URL" 2>/dev/null || true
    fi
    exit 1
  fi

  if ! docker info &>/dev/null; then
    echo "Docker jest zainstalowany, ale nie działa (np. Docker Desktop nie jest uruchomiony)."
    echo "Uruchom Docker Desktop i uruchom ten skrypt ponownie."
    exit 1
  fi

  if ! docker compose version &>/dev/null && ! docker-compose version &>/dev/null; then
    echo "Docker Compose nie jest dostępny. Zainstaluj plugin 'docker compose' lub 'docker-compose'."
    echo "Dokumentacja: $DOCKER_DOWNLOAD_URL"
    exit 1
  fi
}

# --- Budowanie i uruchamianie ---
run_compose() {
  echo "Budowanie i uruchamianie kontenerów..."
  if docker compose version &>/dev/null; then
    docker compose up --build -d
  else
    docker-compose up --build -d
  fi
}

# --- Oczekiwanie na frontend ---
wait_for_frontend() {
  echo "Oczekiwanie na uruchomienie frontendu (max 120 s)..."
  for i in $(seq 1 120); do
    if curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" 2>/dev/null | grep -q "200\|301\|302"; then
      echo "Frontend jest gotowy."
      return 0
    fi
    sleep 1
  done
  echo "Timeout: frontend nie odpowiedział w 120 s. Sprawdź: docker compose logs frontend"
  return 1
}

# --- Otwarcie przeglądarki ---
open_browser() {
  echo "Otwieranie przeglądarki: $FRONTEND_URL"
  if [[ "$(uname)" == "Darwin" ]]; then
    open "$FRONTEND_URL"
  elif command -v xdg-open &>/dev/null; then
    xdg-open "$FRONTEND_URL"
  else
    echo "Otwórz w przeglądarce: $FRONTEND_URL"
  fi
}

# --- Wykonanie ---
check_docker
run_compose
wait_for_frontend && open_browser

echo "Gotowe. Aplikacja: $FRONTEND_URL (backend: http://localhost:8000)"
echo "Zatrzymanie: w tym katalogu uruchom: docker compose down"
