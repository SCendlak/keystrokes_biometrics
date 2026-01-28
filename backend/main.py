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

# Load environment variables
load_dotenv()

# Database configuration
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL environment variable")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ============================================================================
# DATABASE MODELS
# ============================================================================

class SessionDB(Base):
    """
  Represents a single typing session for biometric enrollment or verification.
  Each session contains metadata and a collection of keystroke timing data.
  """
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True)
    text = Column(Text)  # The text that was typed
    created_at = Column(DateTime, default=datetime.utcnow)

    # One-to-many relationship: one session has many keystrokes
    keystrokes = relationship(
        "KeystrokeDB",
        back_populates="session",
        cascade="all, delete-orphan",  # Delete keystrokes when session is deleted
    )


class KeystrokeDB(Base):
    """
  Stores individual keystroke biometric data.
  Each keystroke contains timing information used for behavioral analysis.
  """
    __tablename__ = "keystrokes"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)

    # Keystroke identification
    key = Column(String)  # Character pressed (e.g., "a", "Space", "Enter")
    key_code = Column(String)  # Numeric key code

    # Timing data (in milliseconds from session start)
    press_time = Column(Integer)  # When key was pressed
    release_time = Column(Integer)  # When key was released

    # Biometric features
    dwell_time = Column(Integer)  # How long key was held (release - press)
    flight_time = Column(Integer)  # Time since previous key release

    # Relationship back to session
    session = relationship("SessionDB", back_populates="keystrokes")


# Create all tables
Base.metadata.create_all(bind=engine)


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

def get_db():
    """Provides database session for each request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# PYDANTIC MODELS (API Request/Response)
# ============================================================================

class KeystrokeData(BaseModel):
    """
  Keystroke data from frontend.
  Matches the structure sent by App.jsx handleKeyUp function.
  """
    dwellTime: int
    flightTime: int
    key: str
    keyCode: str
    pressTime: int
    releaseTime: int


class SessionCreate(BaseModel):
    """
  Request payload for creating a training session or verification attempt.
  Matches the payload structure sent by App.jsx submitData function.
  """
    userId: str
    text: str
    startedAt: Optional[str] = None
    keystrokes: List[KeystrokeData]


class SessionOut(BaseModel):
    """Response model for session creation."""
    id: str
    userId: str
    text: str
    createdAt: str
    keystrokesCount: int


class UserStats(BaseModel):
    """Response model for user statistics."""
    userId: str
    sessionCount: int


class VerificationMatch(BaseModel):
    """Individual match result in verification matrix."""
    userId: str
    score: float
    confidence: float
    isMatch: bool


class VerificationResponse(BaseModel):
    """Response model for verification endpoint."""
    claimedUser: str
    inputStats: dict
    matrix: List[VerificationMatch]
    verified: bool


# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="Keystroke Biometrics API",
    description="Behavioral biometric authentication using keystroke dynamics",
    version="1.0.0"
)

# CORS configuration for frontend
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API router with prefix
api = APIRouter(prefix="/api", tags=["api"])


# ============================================================================
# BIOMETRIC ANALYSIS FUNCTIONS
# ============================================================================

def calculate_session_stats(keystrokes: List[KeystrokeData]):
    """
  Calculates average Dwell Time and Flight Time for a single session.

  These metrics form the biometric signature:
  - Dwell Time: How long keys are held down
  - Flight Time: Time between releasing one key and pressing the next

  Args:
      keystrokes: List of keystroke data from a typing session

  Returns:
      Tuple of (avg_dwell, avg_flight) in milliseconds
  """
    if not keystrokes:
        return 0.0, 0.0

    # Extract all dwell times
    dwells = [k.dwellTime for k in keystrokes]

    # Extract flight times (excluding first keystroke which has flight_time=0)
    flights = [k.flightTime for k in keystrokes if k.flightTime != 0]

    # Calculate averages
    avg_dwell = sum(dwells) / len(dwells) if dwells else 0.0
    avg_flight = sum(flights) / len(flights) if flights else 0.0

    return avg_dwell, avg_flight


def get_user_profile_stats(db: Session, user_id: str):
    """
  Fetches the historical typing profile for a user.

  Queries all previous training sessions and calculates average
  biometric characteristics across all keystrokes.

  Args:
      db: Database session
      user_id: Username to look up

  Returns:
      Tuple of (avg_dwell, avg_flight) or None if user has no history
  """
    # Join sessions and keystrokes tables, filter by user_id
    query = db.query(
        func.avg(KeystrokeDB.dwell_time),
        func.avg(KeystrokeDB.flight_time)
    ).join(SessionDB).filter(SessionDB.user_id == user_id)

    result = query.first()

    # Handle case where user has no training data
    if not result or result[0] is None:
        return None

    return float(result[0]), float(result[1]), query.count()


# ============================================================================
# API ENDPOINTS
# ============================================================================

@api.get("/")
def health_check():
    """Health check endpoint."""
    return {
        "ok": True,
        "service": "keystroke-biometrics-api",
        "version": "1.0.0"
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

    # Step A: Calculate stats for CURRENT session
    cur_dwell, cur_flight = calculate_session_stats(payload.keystrokes)

    # Step B: Fetch HISTORICAL stats (user's established baseline)
    history = get_user_profile_stats(db, payload.userId)

    # Step C: Anti-Poisoning Check
    if history:
        hist_dwell, hist_flight, count = history

        # Calculate Manhattan distance (sum of absolute differences)
        dwell_diff = abs(cur_dwell - hist_dwell)
        flight_diff = abs(cur_flight - hist_flight)

        # Threshold for acceptable deviation (milliseconds)
        # Adjust this based on real-world usage and accuracy requirements
        MAX_DEVIATION = 60.0
        MIN_COUNT = 2

        # Reject session if deviation is too large
        if count > MIN_COUNT:
            if dwell_diff > MAX_DEVIATION or flight_diff > MAX_DEVIATION:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Inconsistent typing pattern detected. "
                        f"Deviation: Dwell {dwell_diff:.1f}ms, Flight {flight_diff:.1f}ms. "
                        f"This session differs significantly from your established profile. "
                        f"Please try again or ensure you're typing on your usual keyboard."
                    )
                )

    # Step D: Save to database (only if validation passes or first session)
    session_id = str(uuid4())
    session_row = SessionDB(
        id=session_id,
        user_id=payload.userId,
        text=payload.text,
        created_at=datetime.utcnow()
    )

    # Add all keystrokes to the session
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

    # Return session details
    return SessionOut(
        id=session_id,
        userId=payload.userId,
        text=payload.text,
        createdAt=session_row.created_at.isoformat(),
        keystrokesCount=len(payload.keystrokes)
    )


@api.get("/users/{user_id}/stats", response_model=UserStats)
def get_user_stats(user_id: str, db: Session = Depends(get_db)):
    """
  Get training statistics for a user.

  Called by frontend to display training progress (e.g., "2 / 3 sessions").

  Args:
      user_id: Username to query
      db: Database session (injected)

  Returns:
      UserStats with session count
  """
    count = db.query(SessionDB).filter(SessionDB.user_id == user_id).count()

    return UserStats(
        userId=user_id,
        sessionCount=count
    )


@api.post("/verify", response_model=VerificationResponse)
def verify_user(payload: SessionCreate, db: Session = Depends(get_db)):
    """
  VERIFICATION ENDPOINT - Authenticate user by typing pattern

  This endpoint compares the user's current typing pattern against all
  enrolled users in the database. It returns a verification matrix showing
  similarity scores for all users.

  Process Flow:
  1. Calculate biometric stats from input keystrokes
  2. Retrieve all users' established profiles from database
  3. Calculate similarity scores (Manhattan distance)
  4. Convert distances to confidence percentages
  5. Sort by best match and return top 5

  Similarity Metric:
  - Uses Manhattan distance: |Dwell₁ - Dwell₂| + |Flight₁ - Flight₂|
  - Lower distance = more similar typing patterns
  - Confidence = max(0, 100 - distance)

  Args:
      payload: Typing session data (userId is the claimed identity)
      db: Database session (injected)

  Returns:
      VerificationResponse with matrix of matches and verification result
  """

    # Step 1: Calculate biometric profile from input
    in_dwell, in_flight = calculate_session_stats(payload.keystrokes)

    # Step 2: Get ALL users' established profiles
    # This query groups by user_id and calculates avg stats for each
    user_stats = db.query(
        SessionDB.user_id,
        func.avg(KeystrokeDB.dwell_time).label('avg_dwell'),
        func.avg(KeystrokeDB.flight_time).label('avg_flight')
    ).join(KeystrokeDB).group_by(SessionDB.user_id).all()

    # Step 3 & 4: Calculate similarity scores for all users
    results = []

    for u_id, u_dwell, u_flight in user_stats:
        # Skip users with no valid data
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

    # Take top 5 matches for the verification matrix
    top_matches = results[:5]

    # Convert to Pydantic models
    matrix = [
        VerificationMatch(
            userId=m["userId"],
            score=m["score"],
            confidence=m["confidence"],
            isMatch=m["isMatch"]
        )
        for m in top_matches
    ]

    # Determine if verification succeeded
    # True if the best match (lowest score) is the claimed user
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


# Include API router in main app
app.include_router(api)

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # Run the server
    # Default: http://127.0.0.1:8000
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True  # Auto-reload on code changes (development only)
    )