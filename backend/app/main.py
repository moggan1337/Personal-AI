"""FastAPI application: auth, twin management, training, synthesis, chat, search."""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import auth, seeds, twin_engine
from .config import APPLICATION_MODES, TRAINING_CATEGORIES
from .database import (
    AuthSession,
    Conversation,
    Message,
    SessionLocal,
    TrainingSample,
    Twin,
    User,
    init_db,
)
from .schemas import (
    ChatRequest,
    ConversationDetail,
    ConversationSummary,
    Credentials,
    MessageOut,
    SampleCreate,
    SampleOut,
    SearchHit,
    SeedInfo,
    TwinCreate,
    TwinDetail,
    TwinImport,
    TwinSummary,
    UserOut,
)

app = FastAPI(title="Personal AI Twin Platform", version="2.0.0")

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


def current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """The authenticated user, or None for anonymous access."""
    return auth.user_from_request(request, db)


def _uid(user: Optional[User]) -> Optional[int]:
    return user.id if user else None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _load_twin(db: Session, twin_id: int, user: Optional[User]) -> Twin:
    """Load a twin the caller is allowed to see.

    Logged-in users see only their own twins; anonymous callers see only
    unowned (user_id IS NULL) twins. A mismatch returns 404 to avoid leaking
    existence.
    """
    twin = db.get(Twin, twin_id)
    if twin is None or twin.user_id != _uid(user):
        raise HTTPException(status_code=404, detail="Twin not found")
    return twin


def _load_conversation(db: Session, conv_id: int, user: Optional[User]) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Authorize via the owning twin.
    _load_twin(db, conv.twin_id, user)
    return conv


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


def _conversation_summary(conv: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conv.id,
        twin_id=conv.twin_id,
        title=conv.title,
        mode=conv.mode,
        message_count=len(conv.messages),
        updated_at=conv.updated_at,
        created_at=conv.created_at,
    )


def _twin_detail(twin: Twin) -> TwinDetail:
    by_category: dict[str, list[SampleOut]] = defaultdict(list)
    for sample in twin.samples:
        by_category[sample.category].append(SampleOut.model_validate(sample))
    persona = json.loads(twin.persona_json) if twin.persona_json else None
    return TwinDetail(
        **_summary(twin).model_dump(),
        persona=persona,
        samples_by_category={c: by_category.get(c, []) for c in TRAINING_CATEGORIES},
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
# Authentication
# --------------------------------------------------------------------------- #
@app.post("/api/auth/register", response_model=UserOut, status_code=201)
def register(
    creds: Credentials, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    username = creds.username.strip().lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    salt, pw_hash = auth.hash_password(creds.password)
    user = User(username=username, salt=salt, password_hash=pw_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = auth.create_session(db, user)
    response.set_cookie(auth.COOKIE_NAME, token, httponly=True, samesite="lax")
    return UserOut(id=user.id, username=user.username)


@app.post("/api/auth/login", response_model=UserOut)
def login(
    creds: Credentials, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    username = creds.username.strip().lower()
    user = db.query(User).filter(User.username == username).first()
    if user is None or not auth.verify_password(creds.password, user.salt, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = auth.create_session(db, user)
    response.set_cookie(auth.COOKIE_NAME, token, httponly=True, samesite="lax")
    return UserOut(id=user.id, username=user.username)


@app.post("/api/auth/logout", status_code=204)
def logout(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> None:
    token = request.cookies.get(auth.COOKIE_NAME)
    if token:
        auth.destroy_session(db, token)
    response.delete_cookie(auth.COOKIE_NAME)


@app.get("/api/auth/me", response_model=Optional[UserOut])
def me(user: Optional[User] = Depends(current_user)) -> Optional[UserOut]:
    return UserOut(id=user.id, username=user.username) if user else None


# --------------------------------------------------------------------------- #
# Twins
# --------------------------------------------------------------------------- #
@app.get("/api/twins", response_model=list[TwinSummary])
def list_twins(
    db: Session = Depends(get_db), user: Optional[User] = Depends(current_user)
) -> list[TwinSummary]:
    twins = (
        db.query(Twin)
        .filter(Twin.user_id == _uid(user))
        .order_by(Twin.created_at.desc())
        .all()
    )
    return [_summary(t) for t in twins]


@app.post("/api/twins", response_model=TwinSummary, status_code=201)
def create_twin(
    payload: TwinCreate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> TwinSummary:
    twin = Twin(
        user_id=_uid(user),
        name=payload.name,
        owner=payload.owner,
        tagline=payload.tagline,
    )
    db.add(twin)
    db.commit()
    db.refresh(twin)
    return _summary(twin)


@app.get("/api/twins/{twin_id}", response_model=TwinDetail)
def get_twin(
    twin_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> TwinDetail:
    return _twin_detail(_load_twin(db, twin_id, user))


@app.delete("/api/twins/{twin_id}", status_code=204)
def delete_twin(
    twin_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> None:
    db.delete(_load_twin(db, twin_id, user))
    db.commit()


# --------------------------------------------------------------------------- #
# Training data
# --------------------------------------------------------------------------- #
@app.post("/api/twins/{twin_id}/samples", response_model=SampleOut, status_code=201)
def add_sample(
    twin_id: int,
    payload: SampleCreate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> SampleOut:
    try:
        payload.validate_category()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    twin = _load_twin(db, twin_id, user)
    sample = TrainingSample(
        twin_id=twin.id, category=payload.category, content=payload.content.strip()
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return SampleOut.model_validate(sample)


@app.delete("/api/twins/{twin_id}/samples/{sample_id}", status_code=204)
def delete_sample(
    twin_id: int,
    sample_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> None:
    _load_twin(db, twin_id, user)
    sample = db.get(TrainingSample, sample_id)
    if sample is None or sample.twin_id != twin_id:
        raise HTTPException(status_code=404, detail="Sample not found")
    db.delete(sample)
    db.commit()


# --------------------------------------------------------------------------- #
# Training (persona synthesis)
# --------------------------------------------------------------------------- #
@app.post("/api/twins/{twin_id}/train", response_model=TwinDetail)
def train_twin(
    twin_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> TwinDetail:
    twin = _load_twin(db, twin_id, user)
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
    return _twin_detail(twin)


# --------------------------------------------------------------------------- #
# Seeds (ready-made example twins)
# --------------------------------------------------------------------------- #
@app.get("/api/seeds", response_model=list[SeedInfo])
def list_seeds() -> list[SeedInfo]:
    return [
        SeedInfo(
            key=s["key"],
            name=s["name"],
            tagline=s["tagline"],
            pretrained=bool(s.get("persona")),
        )
        for s in seeds.SEED_TWINS
    ]


@app.post("/api/seeds/{key}/instantiate", response_model=TwinSummary, status_code=201)
def instantiate_seed(
    key: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> TwinSummary:
    seed = seeds.get_seed(key)
    if seed is None:
        raise HTTPException(status_code=404, detail="Seed not found")

    twin = Twin(
        user_id=_uid(user),
        name=seed["name"],
        owner=seed.get("owner", ""),
        tagline=seed["tagline"],
    )
    if seed.get("persona"):  # ship already-trained
        twin.persona_json = json.dumps(seed["persona"])
        twin.persona_updated_at = dt.datetime.now(dt.timezone.utc)
    db.add(twin)
    db.flush()
    for category, items in seed["samples"].items():
        for content in items:
            db.add(TrainingSample(twin_id=twin.id, category=category, content=content))
    db.commit()
    db.refresh(twin)
    return _summary(twin)


# --------------------------------------------------------------------------- #
# Export / import (share a twin)
# --------------------------------------------------------------------------- #
@app.get("/api/twins/{twin_id}/export")
def export_twin(
    twin_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> dict:
    twin = _load_twin(db, twin_id, user)
    by_category: dict[str, list[str]] = {c: [] for c in TRAINING_CATEGORIES}
    for sample in twin.samples:
        by_category.setdefault(sample.category, []).append(sample.content)
    return {
        "format": "personal-ai-twin",
        "version": 1,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "name": twin.name,
        "owner": twin.owner,
        "tagline": twin.tagline,
        "persona": json.loads(twin.persona_json) if twin.persona_json else None,
        "samples_by_category": by_category,
    }


@app.post("/api/twins/import", response_model=TwinSummary, status_code=201)
def import_twin(
    payload: TwinImport,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> TwinSummary:
    twin = Twin(
        user_id=_uid(user),
        name=payload.name,
        owner=payload.owner,
        tagline=payload.tagline,
    )
    if payload.persona:
        twin.persona_json = json.dumps(payload.persona)
        twin.persona_updated_at = dt.datetime.now(dt.timezone.utc)
    db.add(twin)
    db.flush()
    for category, items in payload.samples_by_category.items():
        if category not in TRAINING_CATEGORIES:
            continue
        for content in items:
            if content and content.strip():
                db.add(
                    TrainingSample(
                        twin_id=twin.id, category=category, content=content.strip()
                    )
                )
    db.commit()
    db.refresh(twin)
    return _summary(twin)


# --------------------------------------------------------------------------- #
# Conversations & search
# --------------------------------------------------------------------------- #
@app.get("/api/twins/{twin_id}/conversations", response_model=list[ConversationSummary])
def list_conversations(
    twin_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> list[ConversationSummary]:
    _load_twin(db, twin_id, user)
    convs = (
        db.query(Conversation)
        .filter(Conversation.twin_id == twin_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [_conversation_summary(c) for c in convs]


@app.get("/api/twins/{twin_id}/search", response_model=list[SearchHit])
def search_conversations(
    twin_id: int,
    q: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> list[SearchHit]:
    _load_twin(db, twin_id, user)
    query = q.strip()
    if not query:
        return []
    rows = (
        db.query(Message, Conversation)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Conversation.twin_id == twin_id)
        .filter(Message.content.ilike(f"%{query}%"))
        .order_by(Message.id.desc())
        .limit(50)
        .all()
    )
    hits = []
    for msg, conv in rows:
        hits.append(
            SearchHit(
                conversation_id=conv.id,
                conversation_title=conv.title,
                mode=conv.mode,
                message_id=msg.id,
                role=msg.role,
                snippet=_snippet(msg.content, query),
                created_at=msg.created_at,
            )
        )
    return hits


def _snippet(content: str, query: str, width: int = 160) -> str:
    idx = content.lower().find(query.lower())
    if idx < 0:
        return content[:width]
    start = max(0, idx - width // 2)
    end = min(len(content), start + width)
    snippet = content[start:end]
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(content) else "")


@app.get("/api/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> ConversationDetail:
    conv = _load_conversation(db, conv_id, user)
    summary = _conversation_summary(conv)
    return ConversationDetail(
        **summary.model_dump(),
        messages=[MessageOut.model_validate(m) for m in conv.messages],
    )


@app.delete("/api/conversations/{conv_id}", status_code=204)
def delete_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
) -> None:
    conv = _load_conversation(db, conv_id, user)
    db.delete(conv)
    db.commit()


# --------------------------------------------------------------------------- #
# Chat (persisted + streaming, with retrieval)
# --------------------------------------------------------------------------- #
def _twin_memories(twin: Twin, query: str) -> list[dict]:
    """Retrieve the training samples most relevant to the current message."""
    samples = [{"category": s.category, "content": s.content} for s in twin.samples]
    return twin_engine.retrieve_relevant(query, samples)


def _stream_and_persist(
    db: Session,
    *,
    name: str,
    persona: dict,
    mode: str,
    history: list[dict],
    memories: list[dict],
    conv_id: int,
) -> StreamingResponse:
    """Shared streaming body used by both chat and regenerate."""

    def token_stream():
        collected: list[str] = []
        try:
            for chunk in twin_engine.stream_reply(name, persona, mode, history, memories):
                collected.append(chunk)
                yield chunk
        except RuntimeError as exc:
            yield f"\n\n[error: {exc}]"
        except Exception as exc:  # pragma: no cover - defensive
            yield f"\n\n[error talking to model: {exc}]"
        finally:
            reply = "".join(collected).strip()
            if reply:
                db.add(Message(conversation_id=conv_id, role="assistant", content=reply))
                target = db.get(Conversation, conv_id)
                if target is not None:
                    target.updated_at = dt.datetime.now(dt.timezone.utc)
                db.commit()

    return StreamingResponse(
        token_stream(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Conversation-Id": str(conv_id)},
    )


@app.post("/api/twins/{twin_id}/chat")
def chat(
    twin_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    try:
        payload.validate_mode()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    twin = _load_twin(db, twin_id, user)
    if not twin.persona_json:
        raise HTTPException(
            status_code=400, detail="This twin hasn't been trained yet. Train it first."
        )

    # Resolve the conversation: reuse an existing one or start a new thread.
    if payload.conversation_id is not None:
        conv = db.get(Conversation, payload.conversation_id)
        if conv is None or conv.twin_id != twin.id:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = Conversation(twin_id=twin.id, mode=payload.mode, title="New conversation")
        db.add(conv)
        db.flush()

    # The DB is the source of truth for history; append the new user turn.
    history = [{"role": m.role, "content": m.content} for m in conv.messages]
    history.append({"role": "user", "content": payload.content})

    db.add(Message(conversation_id=conv.id, role="user", content=payload.content))
    if not conv.messages:  # first turn → derive a title
        conv.title = payload.content[:60] + ("…" if len(payload.content) > 60 else "")
    conv.mode = payload.mode
    conv.updated_at = dt.datetime.now(dt.timezone.utc)
    memories = _twin_memories(twin, payload.content)
    db.commit()

    return _stream_and_persist(
        db,
        name=twin.name,
        persona=json.loads(twin.persona_json),
        mode=payload.mode,
        history=history,
        memories=memories,
        conv_id=conv.id,
    )


@app.post("/api/conversations/{conv_id}/regenerate")
def regenerate(
    conv_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    conv = _load_conversation(db, conv_id, user)
    twin = _load_twin(db, conv.twin_id, user)
    if not twin.persona_json:
        raise HTTPException(status_code=400, detail="This twin hasn't been trained yet.")
    if not conv.messages:
        raise HTTPException(status_code=400, detail="Nothing to regenerate.")

    # Drop the trailing assistant message (if present) so we can produce a new one.
    if conv.messages[-1].role == "assistant":
        db.delete(conv.messages[-1])
        db.flush()
        db.refresh(conv)
    if not conv.messages or conv.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="No user message to respond to.")

    history = [{"role": m.role, "content": m.content} for m in conv.messages]
    last_user = history[-1]["content"]
    memories = _twin_memories(twin, last_user)
    conv.updated_at = dt.datetime.now(dt.timezone.utc)
    db.commit()

    return _stream_and_persist(
        db,
        name=twin.name,
        persona=json.loads(twin.persona_json),
        mode=conv.mode,
        history=history,
        memories=memories,
        conv_id=conv.id,
    )


# --------------------------------------------------------------------------- #
# Frontend (mounted last so it doesn't shadow /api routes)
# --------------------------------------------------------------------------- #
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
