"""The Anthropic-powered brain of a twin.

Two responsibilities:

1. ``synthesize_persona`` — read a person's training samples and distil them into
   a structured persona profile (writing style, decision-making, knowledge,
   personality). This is the "learning" step.
2. ``stream_reply`` — speak *as* the person in a chat, grounded in that persona
   profile and shaped by the chosen application mode.
"""
from __future__ import annotations

import json
from typing import Iterator, Optional

import anthropic

from .config import ANTHROPIC_API_KEY, TWIN_MODEL

# A single shared client. anthropic.Anthropic() also reads ANTHROPIC_API_KEY from
# the environment; we pass it explicitly so a clear error surfaces when missing.
_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


# JSON schema for the persona profile. Used with structured outputs so the model
# always returns a parseable object with exactly these fields.
PERSONA_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "A 2-3 sentence portrait of who this person is.",
        },
        "writing_style": {
            "type": "object",
            "properties": {
                "tone": {"type": "string"},
                "formality": {"type": "string"},
                "sentence_structure": {"type": "string"},
                "vocabulary": {"type": "string"},
                "signature_phrases": {"type": "array", "items": {"type": "string"}},
                "quirks": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "tone",
                "formality",
                "sentence_structure",
                "vocabulary",
                "signature_phrases",
                "quirks",
            ],
            "additionalProperties": False,
        },
        "decision_making": {
            "type": "object",
            "properties": {
                "approach": {"type": "string"},
                "core_values": {"type": "array", "items": {"type": "string"}},
                "risk_tolerance": {"type": "string"},
                "mental_models": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["approach", "core_values", "risk_tolerance", "mental_models"],
            "additionalProperties": False,
        },
        "knowledge": {
            "type": "object",
            "properties": {
                "domains": {"type": "array", "items": {"type": "string"}},
                "strong_opinions": {"type": "array", "items": {"type": "string"}},
                "key_facts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["domains", "strong_opinions", "key_facts"],
            "additionalProperties": False,
        },
        "personality": {
            "type": "object",
            "properties": {
                "traits": {"type": "array", "items": {"type": "string"}},
                "communication_style": {"type": "string"},
                "humor": {"type": "string"},
                "motivations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["traits", "communication_style", "humor", "motivations"],
            "additionalProperties": False,
        },
    },
    "required": ["summary", "writing_style", "decision_making", "knowledge", "personality"],
    "additionalProperties": False,
}

_SYNTH_SYSTEM = """You are an expert behavioural analyst building a faithful \
psychological and stylistic profile of a person from samples of their writing, \
decisions, knowledge, and personality.

Infer only what the evidence supports. Where a dimension is thinly covered, keep \
that part of the profile modest and general rather than inventing detail. Capture \
the person's actual voice and judgement — not an idealised version. The profile \
will be used to let an AI speak and decide convincingly as this person, so be \
concrete and specific."""


def _format_samples(samples_by_category: dict[str, list[str]]) -> str:
    blocks = []
    for category, items in samples_by_category.items():
        if not items:
            continue
        joined = "\n\n".join(f"  [{i + 1}] {text}" for i, text in enumerate(items))
        blocks.append(f"### {category.upper()} SAMPLES\n{joined}")
    return "\n\n".join(blocks) if blocks else "(no samples provided)"


def synthesize_persona(name: str, samples_by_category: dict[str, list[str]]) -> dict:
    """Distil training samples into a structured persona profile."""
    client = get_client()
    samples_text = _format_samples(samples_by_category)

    user_prompt = (
        f"Build the persona profile for a person named {name}.\n\n"
        f"Here is everything we know about them:\n\n{samples_text}\n\n"
        "Analyse these samples and produce the structured profile."
    )

    response = client.messages.create(
        model=TWIN_MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=_SYNTH_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
        output_config={"format": {"type": "json_schema", "schema": PERSONA_SCHEMA}},
    )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise RuntimeError("Persona synthesis returned no text content.")
    return json.loads(text)


# How each application mode reframes the twin's behaviour.
_MODE_INSTRUCTIONS = {
    "conversation": (
        "You are chatting one-on-one. Be yourself, naturally and conversationally."
    ),
    "consulting": (
        "You are acting as a paid consultant in your areas of expertise. Give "
        "sharp, opinionated, actionable advice grounded in how you actually think. "
        "Ask clarifying questions when the problem is underspecified."
    ),
    "coaching": (
        "You are coaching this person. Be supportive but honest. Draw on your own "
        "values and mental models, ask reflective questions, and help them reach "
        "their own conclusions rather than just handing over answers."
    ),
    "support": (
        "You are handling customer support on your own behalf or your work's behalf. "
        "Be helpful, patient, and clear. Resolve the issue using what you know; if "
        "you genuinely don't know something, say so and suggest a next step."
    ),
    "content": (
        "You are creating written content (posts, drafts, replies) in your own "
        "voice. Match your writing style precisely — tone, structure, phrasing, and "
        "quirks. Produce publish-ready text unless asked to brainstorm."
    ),
}


def _persona_to_prompt(name: str, persona: dict) -> str:
    """Render the structured persona into readable system-prompt guidance."""
    return (
        f"You ARE {name}. You are not an assistant playing {name}; you respond as "
        f"{name} would, in the first person, drawing on the profile below.\n\n"
        f"=== WHO YOU ARE ===\n{persona.get('summary', '')}\n\n"
        f"=== HOW YOU WRITE AND SPEAK ===\n{json.dumps(persona.get('writing_style', {}), indent=2)}\n\n"
        f"=== HOW YOU MAKE DECISIONS ===\n{json.dumps(persona.get('decision_making', {}), indent=2)}\n\n"
        f"=== WHAT YOU KNOW AND BELIEVE ===\n{json.dumps(persona.get('knowledge', {}), indent=2)}\n\n"
        f"=== YOUR PERSONALITY ===\n{json.dumps(persona.get('personality', {}), indent=2)}\n\n"
        "Stay in character. Never break the fourth wall or mention that you are an AI, "
        "a model, or a persona profile. If asked something genuinely outside your "
        f"knowledge, respond the way {name} honestly would — don't fabricate facts "
        "about your life, but do reason in your own style."
    )


def build_system_prompt(name: str, persona: dict, mode: str) -> str:
    mode_text = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS["conversation"])
    return f"{_persona_to_prompt(name, persona)}\n\n=== CURRENT MODE ===\n{mode_text}"


def stream_reply(
    name: str,
    persona: dict,
    mode: str,
    messages: list[dict],
) -> Iterator[str]:
    """Stream the twin's reply token by token."""
    client = get_client()
    system_prompt = build_system_prompt(name, persona, mode)

    with client.messages.stream(
        model=TWIN_MODEL,
        max_tokens=4000,
        system=system_prompt,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text
