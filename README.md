# Personal AI Twin Platform

Train an AI version of yourself. A twin learns your **writing style**,
**decision-making**, **knowledge**, and **personality** from samples you provide,
then works *as you* across four applications: **consulting**, **coaching**,
**customer support**, and **content creation**.

Built on the Anthropic API (`claude-opus-4-8`).

---

## How it works

```
  Training samples            Persona synthesis              Deployment
 ┌──────────────────┐       ┌────────────────────┐       ┌──────────────────┐
 │ writing          │       │  Claude reads all  │       │  Chat as the twin │
 │ decisions        │  ───▶ │  samples and builds │ ───▶ │  in 5 modes, with │
 │ knowledge        │       │  a structured       │       │  the persona as   │
 │ personality      │       │  persona profile    │       │  the system prompt│
 └──────────────────┘       └────────────────────┘       └──────────────────┘
```

Rather than fine-tuning a model, the platform **synthesizes a structured persona
profile** from your samples (using Claude with structured outputs), then injects
that profile as the system prompt at chat time. This makes a twin cheap to
create, instantly updatable (just re-train), and fully inspectable — you can read
exactly what your twin "learned."

### The four learning dimensions

| Dimension     | What it captures |
|---------------|------------------|
| `writing`     | tone, formality, sentence structure, vocabulary, signature phrases, quirks |
| `decisions`   | approach, core values, risk tolerance, mental models |
| `knowledge`   | domains, strong opinions, key facts |
| `personality` | traits, communication style, humor, motivations |

### The five application modes

`conversation` · `consulting` · `coaching` · `support` · `content` — each
reframes how the twin behaves while staying in the same voice.

### Also included

- **Seed personas** — three ready-made example twins (a growth advisor, a stoic
  coach, a support specialist), each pre-loaded with authentic training data so
  you can try the full flow in one click.
- **Conversation history** — every chat is saved per twin and per mode; reopen,
  continue, or delete past threads from the sidebar.
- **Export / import** — download a trained twin (persona + training data) as a
  shareable `.json` file, and import one to recreate it instantly.

---

## Quick start

**1. Add your API key**

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
```

**2. Run it**

```bash
./run.sh
```

Then open <http://localhost:8000>.

`run.sh` creates a virtualenv, installs dependencies, and starts the server. To
run manually instead:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

---

## Using the app

1. **Create a twin** — give it a name and optional tagline.
2. **Train** — under the *Train* tab, add samples in each of the four dimensions.
   A few authentic examples per dimension is enough to start; more variety yields
   a more convincing twin.
3. **Synthesize the persona** — click *Synthesize / re-train persona*. Claude
   analyzes the samples and produces the structured profile, visible under the
   *Persona* tab.
4. **Chat** — pick an application mode and talk to your twin. Responses stream in
   real time. Add more samples and re-train at any point to refine it.

---

## Architecture

```
backend/app/
  config.py        Environment config, model id, categories, modes
  database.py      SQLAlchemy models (Twin, TrainingSample, Conversation, Message)
  schemas.py       Pydantic request/response models
  seeds.py         Built-in example twins with training data
  twin_engine.py   Anthropic calls: persona synthesis + streaming chat
  main.py          FastAPI routes; serves the frontend
frontend/
  index.html       Single-page UI
  styles.css
  app.js           Vanilla JS: training, persona view, streaming chat
tests/
  test_api.py      API tests (no API key required)
```

### API

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/meta` | Categories, modes, model |
| `GET`  | `/api/twins` | List twins |
| `POST` | `/api/twins` | Create a twin |
| `GET`  | `/api/twins/{id}` | Twin detail (samples + persona) |
| `DELETE` | `/api/twins/{id}` | Delete a twin |
| `POST` | `/api/twins/{id}/samples` | Add a training sample |
| `DELETE` | `/api/twins/{id}/samples/{sid}` | Remove a sample |
| `POST` | `/api/twins/{id}/train` | Synthesize the persona profile |
| `POST` | `/api/twins/{id}/chat` | Stream a reply (`text/plain`); persists the turn |
| `GET`  | `/api/seeds` | List ready-made example twins |
| `POST` | `/api/seeds/{key}/instantiate` | Create a twin from a seed |
| `GET`  | `/api/twins/{id}/export` | Export a twin as shareable JSON |
| `POST` | `/api/twins/import` | Import a twin from JSON |
| `GET`  | `/api/twins/{id}/conversations` | List saved conversations |
| `GET`  | `/api/conversations/{cid}` | Conversation with its messages |
| `DELETE` | `/api/conversations/{cid}` | Delete a conversation |

The chat endpoint returns the thread id in the `X-Conversation-Id` response
header; pass it back as `conversation_id` to continue a thread.

### Tech

- **Backend:** FastAPI, SQLAlchemy (SQLite), Anthropic Python SDK
- **Model:** `claude-opus-4-8` with adaptive thinking for synthesis and streaming
  for chat
- **Frontend:** dependency-free HTML/CSS/JS

---

## Testing

```bash
pip install pytest
pytest -q
```

The suite covers twin lifecycle, validation, and the guardrails (can't chat
before training, can't train with no samples) — none of it requires an API key.

---

## Notes

- Data is stored locally in `data/twins.db` (gitignored).
- Persona profiles are stored as JSON and are fully readable in the *Persona* tab.
- The twin is instructed to stay in character and not fabricate facts about your
  life — if asked something outside its knowledge, it reasons in your style and
  says so honestly.
