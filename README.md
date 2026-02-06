# Keystrokes Dynamics

Aplikacja do analizy biometrii pisania na klawiaturze: rejestracja sesji treningowych (wzorce naciśnięć) i weryfikacja użytkownika metodą odległości Manhattan.

---

## Infrastruktura

Projekt składa się z trzech usług uruchamianych w Dockerze:

```
┌─────────────────────────────────────────────────────────────────┐
│  Przeglądarka (użytkownik)                                        │
│  http://localhost:5173  ← frontend (React + Vite)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP (API_BASE = http://127.0.0.1:8000)
                             ▼
┌────────────────────────────┬────────────────────────────────────┐
│  Backend (FastAPI)          │  Baza danych (PostgreSQL)           │
│  http://localhost:8000     │  localhost:5432                     │
│  • /api/sessions           │  • baza: keystrokes                  │
│  • /api/users/{id}/stats   │  • użytkownik/hasło z docker-compose│
│  • /api/verify             │                                      │
└────────────────────────────┴────────────────────────────────────┘
```


| Usługa       | Port | Opis                                                                                          |
| ------------ | ---- | --------------------------------------------------------------------------------------------- |
| **frontend** | 5173 | Aplikacja React (Vite). Zbiera dane o naciśnięciach klawiszy i wysyła je do backendu.         |
| **backend**  | 8000 | API FastAPI. Zapisuje sesje i keystrokes do bazy, liczy statystyki i weryfikację (Manhattan). |
| **db**       | 5432 | PostgreSQL. Tabele `sessions` i `keystrokes`.                                                 |


---

## Jak współpracują backend i frontend

1. **Frontend (React)**
  Użytkownik wybiera tryb (trening / weryfikacja), wpisuje nazwę użytkownika i pisze podany tekst. Aplikacja mierzy czasy naciśnięć i zwolnień klawiszy (dwell time, flight time) i wysyła je do backendu.
2. **Backend (FastAPI)**
  - **Trening:** `POST /api/sessions` — zapisuje sesję i listę keystrokes do bazy (SQLAlchemy → PostgreSQL).  
  - **Statystyki:** `GET /api/users/{user_id}/stats` — zwraca liczbę sesji treningowych użytkownika.  
  - **Weryfikacja:** `POST /api/verify` — porównuje nową sesję z zapisanymi wzorcami użytkownika (odległość Manhattan), zwraca wynik weryfikacji i macierz porównań.
3. **Przepływ danych**
  Frontend wywołuje `http://127.0.0.1:8000` (w Dockerze port 8000 jest mapowany na backend). Backend czyta/zapisuje dane w PostgreSQL (kontener `db`). CORS jest skonfigurowany tak, aby żądania z `http://localhost:5173` były dozwolone.

---

## Instalacja i uruchomienie

### Wymagania

- **Docker** (oraz **Docker Compose**).  
Jeśli Docker nie jest zainstalowany: [Pobierz Docker](https://docs.docker.com/get-docker/).

### Uruchomienie jednym skryptem (zalecane)

W katalogu głównym projektu:

- **macOS / Linux:**  
`./run.sh`
- **Windows:**  
`run.bat` (dwuklik lub z CMD).

Skrypt sprawdza obecność Dockera, buduje obrazy, uruchamia kontenery (`docker compose up --build -d`) i otwiera przeglądarkę na stronie frontendu. Przy pierwszym uruchomieniu build może zająć kilka minut.

### Ręczne uruchomienie (Docker Compose)

```bash
cd /ścieżka/do/KeystrokesDynamics
docker compose up --build -d
```

Następnie otwórz w przeglądarce: **[http://localhost:5173](http://localhost:5173)**.

### Zatrzymanie

W katalogu projektu:

```bash
docker compose down
```

---

## Uruchomienie bez Dockera (opcjonalnie)

- **Backend:** Python 3.11+, `uv` (lub pip). W katalogu `backend`: ustaw `DATABASE_URL` w pliku `.env`, potem `uv sync` i `uvicorn main:app --reload --port 8000`.
- **Frontend:** Node 18+. W katalogu `frontend`: `npm install`, `npm run dev`.
- **Baza:** Lokalna instancja PostgreSQL z bazą i użytkownikiem zgodnym z `DATABASE_URL`.

W takim przypadku frontend nadal łączy się z backendem pod adresem `http://127.0.0.1:8000` (wartość `API_BASE` w `frontend/src/App.jsx`).

---

## Przydatne adresy


| Zasób                      | URL                                                      |
| -------------------------- | -------------------------------------------------------- |
| Aplikacja Fron             | [http://localhost:5173](http://localhost:5173)           |
| API backend                | [http://localhost:8000](http://localhost:8000)           |
| Dokumentacja API (Swagger) | [http://localhost:8000/docs](http://localhost:8000/docs) |


