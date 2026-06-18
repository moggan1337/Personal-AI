"""FastAPI application: twin management, training, persona synthesis, and chat."""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import twin_engine
from .config import APPLICATION_MODES, TRAINING_CATEGORIES
from .database import SessionLocal, TrainingSample, Twin, init_db
from .schemas import (
    ChatRequest,
    SampleCreate,
    SampleOut,
    TwinCreate,
    TwinDetail,
    TwinSummary,
)

app = FastAPI(title="Personal AI Twin Platform", version="1.0.0")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# Ensure tables exist as soon as the app module is imported (works under uvicorn
# and under TestClient, which doesn't fire startup events).
init_db()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _load_twin(db: Session, twin_id: int) -> Twin:
    twin = db.get(Twin, twin_id)
    if twin is None:
        raise HTTPException(status_code=404, detail="Twin not found")
    return twin


def _summary(twin: Twin) -> TwinSummary:
    return TwinSummary(
        id=twin.id,
        name=twin.name,
        owner=twin.owner,
        tagline=twin.tagline,
        sample_count=len(twin.samples),
        trained=bool(twin.persona_json),
        persona_updated_at=twin.persona_updated_at,
        created_at=twin.created_at,
    )


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
@app.get("/api/meta")
def meta() -> dict:
    return {
        "categories": list(TRAINING_CATEGORIES),
        "modes": list(APPLICATION_MODES),
        "model": twin_engine.TWIN_MODEL,
    }


# --------------------------------------------------------------------------- #
# Twins
# --------------------------------------------------------------------------- #
@app.get("/api/twins", response_model=list[TwinSummary])
def list_twins(db: Session = Depends(get_db)) -> list[TwinSummary]:
    twins = db.query(Twin).order_by(Twin.created_at.desc()).all()
    return [_summary(t) for t in twins]


@app.post("/api/twins", response_model=TwinSummary, status_code=201)
def create_twin(payload: TwinCreate, db: Session = Depends(get_db)) -> TwinSummary:
    twin = Twin(name=payload.name, owner=payload.owner, tagline=payload.tagline)
    db.add(twin)
    db.commit()
    db.refresh(twin)
    return _summary(twin)


@app.get("/api/twins/{twin_id}", response_model=TwinDetail)
def get_twin(twin_id: int, db: Session = Depends(get_db)) -> TwinDetail:
    twin = _load_twin(db, twin_id)
    by_category: dict[str, list[SampleOut]] = defaultdict(list)
    for sample in twin.samples:
        by_category[sample.category].append(SampleOut.model_validate(sample))

    persona = json.loads(twin.persona_json) if twin.persona_json else None
    summary = _summary(twin)
    return TwinDetail(
        **summary.model_dump(),
        persona=persona,
        samples_by_category={c: by_category.get(c, []) for c in TRAINING_CATEGORIES},
    )


@app.delete("/api/twins/{twin_id}", status_code=204)
def delete_twin(twin_id: int, db: Session = Depends(get_db)) -> None:
    twin = _load_twin(db, twin_id)
    db.delete(twin)
    db.commit()


# --------------------------------------------------------------------------- #
# Training data
# --------------------------------------------------------------------------- #
@app.post("/api/twins/{twin_id}/samples", response_model=SampleOut, status_code=201)
def add_sample(
    twin_id: int, payload: SampleCreate, db: Session = Depends(get_db)
) -> SampleOut:
    try:
        payload.validate_category()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    twin = _load_twin(db, twin_id)
    sample = TrainingSample(
        twin_id=twin.id, category=payload.category, content=payload.content.strip()
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return SampleOut.model_validate(sample)


@app.delete("/api/twins/{twin_id}/samples/{sample_id}", status_code=204)
def delete_sample(twin_id: int, sample_id: int, db: Session = Depends(get_db)) -> None:
    sample = db.get(TrainingSample, sample_id)
    if sample is None or sample.twin_id != twin_id:
        raise HTTPException(status_code=404, detail="Sample not found")
    db.delete(sample)
    db.commit()


# --------------------------------------------------------------------------- #
# Training (persona synthesis)
# --------------------------------------------------------------------------- #
@app.post("/api/twins/{twin_id}/train", response_model=TwinDetail)
def train_twin(twin_id: int, db: Session = Depends(get_db)) -> TwinDetail:
    twin = _load_twin(db, twin_id)
    if not twin.samples:
        raise HTTPException(
            status_code=400, detail="Add at least one training sample before training."
        )

    by_category: dict[str, list[str]] = defaultdict(list)
    for sample in twin.samples:
        by_category[sample.category].append(sample.content)

    try:
        persona = twin_engine.synthesize_persona(twin.name, dict(by_category))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # surface Anthropic/API errors cleanly
        raise HTTPException(status_code=502, detail=f"Synthesis failed: {exc}")

    twin.persona_json = json.dumps(persona)
    twin.persona_updated_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    db.refresh(twin)
    return get_twin(twin_id, db)


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #
@app.post("/api/twins/{twin_id}/chat")
def chat(twin_id: int, payload: ChatRequest, db: Session = Depends(get_db)):
    try:
        payload.validate_mode()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    twin = _load_twin(db, twin_id)
    if not twin.persona_json:
        raise HTTPException(
            status_code=400, detail="This twin hasn't been trained yet. Train it first."
        )
    if not payload.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty.")

    persona = json.loads(twin.persona_json)
    messages = [{"role": m.role, "content": m.content} for m in payload.messages]
    name = twin.name

    def token_stream():
        try:
            for chunk in twin_engine.stream_reply(name, persona, payload.mode, messages):
                yield chunk
        except RuntimeError as exc:
            yield f"\n\n[error: {exc}]"
        except Exception as exc:  # pragma: no cover - defensive
            yield f"\n\n[error talking to model: {exc}]"

    return StreamingResponse(token_stream(), media_type="text/plain; charset=utf-8")


# --------------------------------------------------------------------------- #
# Frontend (mounted last so it doesn't shadow /api routes)
# --------------------------------------------------------------------------- #
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
