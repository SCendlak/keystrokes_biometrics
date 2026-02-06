@echo off
setlocal EnableDelayedExpansion

REM Katalog projektu (tam gdzie jest docker-compose.yml)
cd /d "%~dp0"

set "FRONTEND_URL=http://localhost:5173"
set "DOCKER_DOWNLOAD_URL=https://docs.docker.com/get-docker/"

REM --- Sprawdzenie Dockera ---
where docker >nul 2>&1
if errorlevel 1 (
  echo Docker nie jest zainstalowany lub nie jest w PATH.
  echo Pobierz i zainstaluj Docker: %DOCKER_DOWNLOAD_URL%
  start "" "%DOCKER_DOWNLOAD_URL%"
  exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
  echo Docker jest zainstalowany, ale nie dziala - np. Docker Desktop nie jest uruchomiony.
  echo Uruchom Docker Desktop i uruchom ten skrypt ponownie.
  exit /b 1
)

docker compose version >nul 2>&1
if errorlevel 1 (
  docker-compose version >nul 2>&1
  if errorlevel 1 (
    echo Docker Compose nie jest dostepny. Zainstaluj Docker Desktop z Docker Compose.
    echo Dokumentacja: %DOCKER_DOWNLOAD_URL%
    start "" "%DOCKER_DOWNLOAD_URL%"
    exit /b 1
  )
)

REM --- Budowanie i uruchamianie ---
echo Budowanie i uruchamianie kontenerow...
docker compose up --build -d 2>nul || docker-compose up --build -d
if errorlevel 1 (
  echo Blad uruchamiania kontenerow.
  exit /b 1
)

REM --- Krotkie odczekanie (pierwszy build moze trwac kilka minut - w razie pustej strony odswiez pozniej) ---
echo Oczekiwanie 30 s na start uslug...
timeout /t 30 /nobreak >nul
REM --- Otwarcie przeglądarki ---
echo Otwieranie przegladarki: %FRONTEND_URL%
start "" "%FRONTEND_URL%"

echo.
echo Gotowe. Aplikacja: %FRONTEND_URL% ^(backend: http://localhost:8000^)
echo Zatrzymanie: w tym katalogu uruchom: docker compose down
exit /b 0
