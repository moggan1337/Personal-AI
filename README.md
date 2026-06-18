# Personal AI Twin Platform

> Train an AI version of yourself.

A **twin** learns your **writing style**, **decision-making**, **knowledge**, and
**personality** from samples you provide, then works *as you* across four
applications: **consulting**, **coaching**, **customer support**, and **content
creation**.

Built on the Anthropic API with `claude-opus-4-8`. Pure Python backend (FastAPI +
SQLite) and a dependency-free single-page frontend — no build step, no Node, no
framework.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [How it works](#how-it-works)
  - [The four learning dimensions](#the-four-learning-dimensions)
  - [The five application modes](#the-five-application-modes)
  - [Why persona synthesis instead of fine-tuning](#why-persona-synthesis-instead-of-fine-tuning)
- [Feature tour](#feature-tour)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Using the app](#using-the-app)
- [Project structure](#project-structure)
- [Data model](#data-model)
- [The persona profile](#the-persona-profile)
- [API reference](#api-reference)
- [Testing](#testing)
- [Design decisions & FAQ](#design-decisions--faq)
- [Troubleshooting](#troubleshooting)
- [Privacy & data](#privacy--data)
- [Limitations & roadmap](#limitations--roadmap)

---

## Why this exists

People accumulate a distinctive way of writing, deciding, and explaining — and
then spend hours re-applying it: answering the same support questions, drafting
posts in their own voice, giving the same advice. A personal twin captures that
style once and lets it scale, while staying transparent and fully under your
control.

This project is a complete, runnable reference implementation of that idea: data
ingestion, persona modeling, multi-mode deployment, persistence, and sharing.

---

## How it works

```
  1. TRAIN                     2. SYNTHESIZE                 3. DEPLOY
 ┌──────────────────┐        ┌────────────────────┐        ┌───────────────────┐
 │ writing samples  │        │  Claude reads every │        │ Chat as the twin  │
 │ decisions        │  ───▶  │  sample and distils │  ───▶  │ in 5 modes, with  │
 │ knowledge        │        │  a structured       │        │ the persona as    │
 │ personality      │        │  persona profile    │        │ the system prompt │
 └──────────────────┘        └────────────────────┘        └───────────────────┘
        │                              │                             │
   TrainingSample              persona_json (JSON)            Conversation +
   rows in SQLite              stored on the Twin             Message rows
```

1. **Train** — you add short, authentic samples in four categories.
2. **Synthesize** — Claude analyzes all the samples and produces a **structured
   persona profile** (validated against a JSON schema), stored on the twin.
3. **Deploy** — when you chat, that profile is rendered into a system prompt and
   the chosen application mode reshapes behavior. Replies stream back token by
   token and are saved as conversations.

### The four learning dimensions

| Dimension     | What a good sample looks like | What Claude extracts |
|---------------|-------------------------------|----------------------|
| `writing`     | Emails, messages, posts, notes you actually wrote | tone, formality, sentence structure, vocabulary, signature phrases, quirks |
| `decisions`   | A choice you made and the reasoning behind it | approach, core values, risk tolerance, mental models |
| `knowledge`   | Facts, expertise, and strong opinions you hold | domains, strong opinions, key facts |
| `personality` | How you come across to others | traits, communication style, humor, motivations |

You don't need many samples to start — a handful of genuine examples per
dimension produces a recognizable twin. More variety makes it more convincing.

### The five application modes

The same persona, reframed for the job at hand. Mode only changes *how* the twin
operates — never its voice.

| Mode | Behavior |
|------|----------|
| `conversation` | Natural one-on-one chat. The default. |
| `consulting`   | Sharp, opinionated, actionable advice; asks clarifying questions. |
| `coaching`     | Supportive but honest; reflective questions over hand-fed answers. |
| `support`      | Patient, clear issue resolution; admits when it doesn't know. |
| `content`      | Publish-ready writing that matches your style precisely. |

### Why persona synthesis instead of fine-tuning

Rather than fine-tuning a model on your data, the platform synthesizes a
**structured persona profile** and injects it as the system prompt at inference
time. That choice buys a lot:

- **Cheap & instant** — no training jobs; a twin exists the moment you synthesize.
- **Updatable** — add samples and re-synthesize to refine; no retraining pipeline.
- **Inspectable** — the profile is plain JSON you can read in the *Persona* tab.
  You can see exactly what the twin "learned," and correct it by editing samples.
- **Portable** — a twin is just data, so it exports and imports as a JSON file.

---

## Feature tour

- **Twin management** — create, list, inspect, and delete twins.
- **Four-dimension training** — add and remove samples per category.
- **Persona synthesis** — one click turns samples into a structured profile using
  Claude with structured outputs and adaptive thinking.
- **Persona inspector** — read the full profile, rendered as readable sections.
- **Five-mode streaming chat** — talk to your twin; replies stream in real time.
- **Seed personas** — three ready-made example twins (a growth advisor, a stoic
  coach, a support specialist), each pre-loaded with authentic training data, so
  you can try the entire flow without writing anything.
- **Conversation history** — every chat is saved per twin and per mode; reopen,
  continue, or delete past threads from the sidebar.
- **Export / import** — download a trained twin (persona + training data) as a
  shareable `.json`, and import one to recreate it instantly.

---

## Quick start

### Prerequisites

- Python 3.10+
- An Anthropic API key — get one at <https://console.anthropic.com/>

### 1. Add your API key

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
```

### 2. Run it

```bash
./run.sh
```

Then open <http://localhost:8000>.

`run.sh` creates a virtualenv, installs dependencies, warns if `.env` is missing,
and starts the server with auto-reload.

### Run manually instead

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

> **No API key yet?** The app still boots and you can create twins and add
> training data — only **synthesis** and **chat** require the key, and they
> return a clear `503` until it's set.

---

## Configuration

Configuration is read from the environment (and from `.env`, which is loaded
automatically). See `.env.example`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | _(required for AI features)_ | Your Anthropic API key. |
| `TWIN_MODEL` | `claude-opus-4-8` | The model that powers synthesis and chat. |
| `DATABASE_URL` | `sqlite:///./data/twins.db` | SQLAlchemy database URL. |

The database file and its parent `data/` directory are created automatically on
first run.

---

## Using the app

1. **Create a twin** — click **+ New twin**, give it a name and optional tagline.
   Or pick a **ready-made example** from the same dialog to start with training
   data already loaded.
2. **Train** — under the **Train** tab, add samples in each of the four
   dimensions. Remove any with the **×**.
3. **Synthesize the persona** — click **Synthesize / re-train persona**. Claude
   analyzes the samples and produces the structured profile, visible under the
   **Persona** tab. Re-run this any time you add or change samples.
4. **Chat** — open the **Chat** tab, pick an application **mode**, and talk to
   your twin. Replies stream in real time. Use **+ New chat** to start a fresh
   thread; past threads appear in the sidebar to reopen or delete.
5. **Share** — **Export** downloads the twin as JSON; **Import** (top bar)
   recreates a twin from such a file.

---

## Project structure

```
Personal-AI/
├── backend/
│   └── app/
│       ├── config.py        Environment config: model id, categories, modes, paths
│       ├── database.py       SQLAlchemy engine + models (Twin, TrainingSample,
│       │                     Conversation, Message)
│       ├── schemas.py        Pydantic request/response models
│       ├── seeds.py          Built-in example twins with training data
│       ├── twin_engine.py    Anthropic integration: persona synthesis + streaming chat
│       └── main.py           FastAPI routes; serves the frontend
├── frontend/
│   ├── index.html            Single-page UI
│   ├── styles.css            Styling (dark theme)
│   └── app.js                Vanilla JS: training, persona view, streaming chat,
│                             conversations, seeds, export/import
├── tests/
│   └── test_api.py           API tests (no API key required)
├── data/                     SQLite database lives here (gitignored)
├── requirements.txt
├── run.sh                    One-command setup + launch
└── .env.example
```

### Tech stack

- **Backend:** FastAPI, SQLAlchemy 2.0 (SQLite), Anthropic Python SDK, Pydantic
- **Model:** `claude-opus-4-8` — adaptive thinking for synthesis, streaming for chat
- **Frontend:** dependency-free HTML/CSS/JS (no build step)

---

## Data model

```
Twin ──┬──< TrainingSample      (category ∈ writing|decisions|knowledge|personality)
       └──< Conversation ──< Message   (role ∈ user|assistant)
```

| Table | Key fields |
|-------|------------|
| `twins` | `name`, `owner`, `tagline`, `persona_json`, `persona_updated_at` |
| `training_samples` | `twin_id`, `category`, `content` |
| `conversations` | `twin_id`, `title`, `mode`, `updated_at` |
| `messages` | `conversation_id`, `role`, `content` |

Deleting a twin cascades to its samples and conversations; deleting a
conversation cascades to its messages.

---

## The persona profile

Synthesis produces a JSON object validated against a fixed schema
(`twin_engine.PERSONA_SCHEMA`). Shape:

```jsonc
{
  "summary": "A 2-3 sentence portrait of who this person is.",
  "writing_style": {
    "tone": "...", "formality": "...", "sentence_structure": "...",
    "vocabulary": "...", "signature_phrases": ["..."], "quirks": ["..."]
  },
  "decision_making": {
    "approach": "...", "core_values": ["..."],
    "risk_tolerance": "...", "mental_models": ["..."]
  },
  "knowledge": {
    "domains": ["..."], "strong_opinions": ["..."], "key_facts": ["..."]
  },
  "personality": {
    "traits": ["..."], "communication_style": "...",
    "humor": "...", "motivations": ["..."]
  }
}
```

At chat time this is rendered into a first-person system prompt and combined with
the mode instruction. The twin is told to stay in character, never reveal that
it's an AI, and not fabricate facts about your life — if asked something outside
its knowledge it reasons in your style and says so honestly.

---

## API reference

Base URL: `http://localhost:8000`. All payloads are JSON.

### Metadata

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/meta` | Available categories, modes, and the active model. |

### Twins

| Method | Path | Description |
|--------|------|-------------|
| `GET`    | `/api/twins` | List twins (summaries). |
| `POST`   | `/api/twins` | Create a twin. Body: `{name, owner?, tagline?}`. |
| `GET`    | `/api/twins/{id}` | Twin detail: samples grouped by category + persona. |
| `DELETE` | `/api/twins/{id}` | Delete a twin and all its data. |

### Training & synthesis

| Method | Path | Description |
|--------|------|-------------|
| `POST`   | `/api/twins/{id}/samples` | Add a sample. Body: `{category, content}`. |
| `DELETE` | `/api/twins/{id}/samples/{sid}` | Remove a sample. |
| `POST`   | `/api/twins/{id}/train` | Synthesize the persona from all samples. |

### Chat (persisted, streaming)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/twins/{id}/chat` | Stream a reply as `text/plain`. |

Request body:

```json
{ "mode": "consulting", "content": "How should I price this?", "conversation_id": null }
```

- `conversation_id` is optional. Omit (or `null`) to start a new thread.
- The response is a streamed `text/plain` body. The thread id is returned in the
  **`X-Conversation-Id`** response header — pass it back as `conversation_id` to
  continue the same thread. Both the user turn and the assistant reply are
  persisted.

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| `GET`    | `/api/twins/{id}/conversations` | List a twin's saved conversations. |
| `GET`    | `/api/conversations/{cid}` | A conversation with its full message list. |
| `DELETE` | `/api/conversations/{cid}` | Delete a conversation. |

### Seeds

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/seeds` | List ready-made example twins. |
| `POST` | `/api/seeds/{key}/instantiate` | Create a twin pre-loaded from a seed. |

### Export / import

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/twins/{id}/export` | Export a twin (persona + samples) as JSON. |
| `POST` | `/api/twins/import` | Recreate a twin from exported JSON. |

### Example: end-to-end with `curl`

```bash
BASE=http://localhost:8000

# Instantiate a ready-made twin, capture its id
TID=$(curl -s -X POST $BASE/api/seeds/growth-advisor/instantiate | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Synthesize the persona (requires ANTHROPIC_API_KEY)
curl -s -X POST $BASE/api/twins/$TID/train > /dev/null

# Chat — stream a reply and capture the conversation id from the header
curl -s -D - -o /tmp/reply.txt -X POST $BASE/api/twins/$TID/chat \
  -H 'Content-Type: application/json' \
  -d '{"mode":"consulting","content":"How do I lower my CAC?"}' | grep -i x-conversation-id
cat /tmp/reply.txt

# Export the twin to a shareable file
curl -s $BASE/api/twins/$TID/export -o my-twin.json
```

---

## Testing

```bash
pip install pytest
pytest -q
```

The suite (`tests/test_api.py`) covers the twin lifecycle, validation, guardrails
(can't chat before training, can't train with no samples), seeds, the
export/import round-trip, and the conversation endpoints. **None of it requires
an API key** — the AI calls aren't exercised, so tests are fast and deterministic.

---

## Design decisions & FAQ

**Why a structured persona instead of fine-tuning?**
See [Why persona synthesis instead of fine-tuning](#why-persona-synthesis-instead-of-fine-tuning).
In short: cheaper, instantly updatable, inspectable, and portable.

**Why is the server the source of truth for chat history?**
The chat endpoint rebuilds the conversation from the database on every turn and
only takes the new message plus a `conversation_id`. This keeps the client thin,
makes history durable, and means a refresh never loses a thread.

**Why sync SQLAlchemy with a streaming endpoint?**
FastAPI runs sync endpoints in a threadpool and keeps the request-scoped DB
session open until the streamed response finishes, so the assistant reply can be
persisted in the stream's `finally` block. This avoids mixing async and sync DB
access for a small, single-node app.

**Why no frontend framework?**
The UI is small and self-contained. Vanilla HTML/CSS/JS means zero build
tooling, zero `node_modules`, and a frontend anyone can read top to bottom.

**Can I change the model?**
Yes — set `TWIN_MODEL`. It defaults to `claude-opus-4-8`, the most capable model
and the right fit for nuanced persona work.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| Synthesis or chat returns `503` | `ANTHROPIC_API_KEY` not set. Add it to `.env`. |
| Synthesis returns `502 Synthesis failed: ...` | An API error (bad key, rate limit, network). The detail message is surfaced verbatim. |
| `400 This twin hasn't been trained yet` | Synthesize the persona before chatting. |
| `400 Add at least one training sample before training` | Add samples before clicking train. |
| Chat reply ends with `[error: ...]` | The model stream failed mid-response; the partial reply (if any) is still saved. Retry. |
| Port already in use | Change the port: `uvicorn backend.app.main:app --port 8001`. |

---

## Privacy & data

- All data lives **locally** in `data/twins.db` (gitignored). Nothing is sent
  anywhere except to the Anthropic API during synthesis and chat.
- Training samples and chat content are sent to Anthropic as part of those calls,
  subject to Anthropic's API data policies.
- Exported twin files contain the persona and all training samples in plaintext —
  treat them as you would the underlying personal data.

---

## Limitations & roadmap

Current scope is a single-node reference implementation:

- No authentication or multi-user isolation — intended for local/personal use.
- Synthesis includes all samples in one prompt; very large corpora would benefit
  from chunking or retrieval.
- Conversation context is sent in full each turn (no server-side compaction yet).

Natural next steps: cross-conversation search, per-message regenerate, seeding
twins as already-trained, retrieval over large knowledge bases, and user accounts.
