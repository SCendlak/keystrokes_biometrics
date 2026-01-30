import decimal

from dotenv import load_dotenv
import os
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import FastAPI, APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy import (
    create_engine, Column, String, Integer, DateTime, ForeignKey, Text, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL environment variable")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SessionDB(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True)
    text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    keystrokes = relationship(
        "KeystrokeDB",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class KeystrokeDB(Base):
    __tablename__ = "keystrokes"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)

    key = Column(String)
    key_code = Column(String)

    press_time = Column(Integer)
    release_time = Column(Integer)

    dwell_time = Column(Integer)  # Jak długo przycisk był trzymany (puszczenie - czas_naciśniecia)
    flight_time = Column(Integer) # Czas od ostatniego przycisku (lot palca)

    session = relationship("SessionDB", back_populates="keystrokes")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class KeystrokeData(BaseModel):
    dwellTime: int
    flightTime: int
    key: str
    keyCode: str
    pressTime: int
    releaseTime: int


class SessionCreate(BaseModel):
    userId: str
    text: str
    startedAt: Optional[str] = None
    keystrokes: List[KeystrokeData]


class SessionOut(BaseModel):
    id: str
    userId: str
    text: str
    createdAt: str
    keystrokesCount: int


class UserStats(BaseModel):
    userId: str
    sessionCount: int


class VerificationMatch(BaseModel):
    userId: str
    score: float
    confidence: float
    isMatch: bool


class VerificationResponse(BaseModel):
    claimedUser: str
    inputStats: dict
    matrix: List[VerificationMatch]
    verified: bool

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api", tags=["api"])

def calculate_session_stats(keystrokes: List[KeystrokeData]):
    if not keystrokes:
        return 0.0, 0.0
    dwells = [k.dwellTime for k in keystrokes]
    flights = [k.flightTime for k in keystrokes if k.flightTime != 0]
    avg_dwell = sum(dwells) / len(dwells) if dwells else 0.0
    avg_flight = sum(flights) / len(flights) if flights else 0.0

    return avg_dwell, avg_flight


def get_user_profile_stats(db: Session, user_id: str):
    query = db.query(
        func.avg(KeystrokeDB.dwell_time),
        func.avg(KeystrokeDB.flight_time)
    ).join(SessionDB).filter(SessionDB.user_id == user_id)
    # mało efektywnie TODO: zoptymalizować
    result = query.first()
    if not result or result[0] is None:
        return None

    return float(result[0]), float(result[1]), query.count()
@api.get("/")
def hello_world():
    return {
        "ok": True,
        "service": "dziala",
        "status": "ok",
    }


@api.post("/sessions", response_model=SessionOut)
def create_training_session(payload: SessionCreate, db: Session = Depends(get_db)):
    """
  TRAINING ENDPOINT - Enroll a new typing session

  This endpoint is called during the training phase when users type the
  fixed training text. It implements anti-poisoning protection to prevent
  profile corruption.

  Process Flow:
  1. Calculate biometric stats for current session
  2. Fetch user's historical profile (if exists)
  3. Check for consistency (anti-poisoning)
  4. Save to database if validation passes
  5. Return session details

  Anti-Poisoning Logic:
  - Compares current session against established baseline
  - Rejects sessions that deviate by more than MAX_DEVIATION (40ms)
  - Prevents impostor attacks and accidental profile corruption

  Args:
      payload: Session data from frontend (userId, text, keystrokes)
      db: Database session (injected)

  Returns:
      SessionOut with session details

  Raises:
      HTTPException 400: If typing pattern is inconsistent with profile
  """
    cur_dwell, cur_flight = calculate_session_stats(payload.keystrokes)
    history = get_user_profile_stats(db, payload.userId)
    if history:
        hist_dwell, hist_flight, count = history

        dwell_diff = abs(cur_dwell - hist_dwell)
        flight_diff = abs(cur_flight - hist_flight)
        MAX_DEVIATION = 60.0
        MIN_COUNT = 2

        #TODO: check czy 3 jest niezbyt efektywny powinien być przed wyliczaniem manhatanu
        if count > MIN_COUNT:
            if dwell_diff > MAX_DEVIATION or flight_diff > MAX_DEVIATION:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Wykryto zbyt zróżnicowany wzorzec. "
                        f"Odchylenie: Pomiedzy przyciskami {dwell_diff:.1f}ms, Czas lotu {flight_diff:.1f}ms. "
                        f"Ta sesja odskakuje zbytnio od twojego typu pisania. "
                        f"Spróbuj ponownie na swoim profilu lub użyj tej samej klawiatury."
                    )
                )

    session_id = str(uuid4())
    session_row = SessionDB(
        id=session_id,
        user_id=payload.userId,
        text=payload.text,
        created_at=datetime.utcnow()
    )

    for k in payload.keystrokes:
        session_row.keystrokes.append(
            KeystrokeDB(
                id=str(uuid4()),
                session_id=session_id,
                key=k.key,
                key_code=k.keyCode,
                press_time=k.pressTime,
                release_time=k.releaseTime,
                dwell_time=k.dwellTime,
                flight_time=k.flightTime,
            )
        )

    db.add(session_row)
    db.commit()
    db.refresh(session_row)

    return SessionOut(
        id=session_id,
        userId=payload.userId,
        text=payload.text,
        createdAt=session_row.created_at.isoformat(),
        keystrokesCount=len(payload.keystrokes)
    )


@api.get("/users/{user_id}/stats", response_model=UserStats)
def get_user_stats(user_id: str, db: Session = Depends(get_db)):
    count = db.query(SessionDB).filter(SessionDB.user_id == user_id).count()

    return UserStats(
        userId=user_id,
        sessionCount=count
    )


@api.post("/verify", response_model=VerificationResponse)
def verify_user(payload: SessionCreate, db: Session = Depends(get_db)):
    in_dwell, in_flight = calculate_session_stats(payload.keystrokes)

    user_stats = db.query(
        SessionDB.user_id,
        func.avg(KeystrokeDB.dwell_time).label('avg_dwell'),
        func.avg(KeystrokeDB.flight_time).label('avg_flight')
    ).join(KeystrokeDB).group_by(SessionDB.user_id).all()

    results = []

    for u_id, u_dwell, u_flight in user_stats:
        if u_dwell is None or u_flight is None:
            continue
        #Manhatann
        dist = abs(decimal.Decimal(in_dwell) - u_dwell) + abs(decimal.Decimal(in_flight) - u_flight)

        confidence = max(0, 100 - dist)

        results.append({
            "userId": u_id,
            "score": round(dist, 2),
            "confidence": round(confidence, 1),
            "isMatch": u_id == payload.userId
        })

    results.sort(key=lambda x: x["score"])
    top_matches = results[:5] #TODO: niezbyt optymalne lepiej ograniczyć querry zamiast filtrowac na endpointcie

    matrix = [
        VerificationMatch(
            userId=m["userId"],
            score=m["score"],
            confidence=m["confidence"],
            isMatch=m["isMatch"]
        )
        for m in top_matches
    ]

    verified = (
            len(results) > 0 and
            results[0]["userId"] == payload.userId
    )

    return VerificationResponse(
        claimedUser=payload.userId,
        inputStats={
            "dwell": round(in_dwell, 1),
            "flight": round(in_flight, 1)
        },
        matrix=matrix,
        verified=verified
    )

app.include_router(api)

#TODO: Kilka metod sprawdzających i trenujących, potencjalnie model SVC, potrzeba by przeksztalcic dane

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True  #dev mode
    )