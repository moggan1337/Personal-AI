"""API tests that don't require an Anthropic API key.

Run with:  pytest -q
"""
import os
import sys
import tempfile

# Use a throwaway database so tests never touch real data.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402

client = TestClient(app)


def _make_twin():
    return client.post("/api/twins", json={"name": "Test Twin"}).json()


def test_meta():
    body = client.get("/api/meta").json()
    assert set(body["categories"]) == {"writing", "decisions", "knowledge", "personality"}
    assert "consulting" in body["modes"]
    assert body["model"]


def test_twin_lifecycle():
    twin = _make_twin()
    assert twin["trained"] is False and twin["sample_count"] == 0

    r = client.post(
        f"/api/twins/{twin['id']}/samples",
        json={"category": "writing", "content": "Hello world."},
    )
    assert r.status_code == 201

    detail = client.get(f"/api/twins/{twin['id']}").json()
    assert detail["sample_count"] == 1
    assert len(detail["samples_by_category"]["writing"]) == 1

    assert client.delete(f"/api/twins/{twin['id']}").status_code == 204
    assert client.get(f"/api/twins/{twin['id']}").status_code == 404


def test_invalid_category_rejected():
    twin = _make_twin()
    r = client.post(
        f"/api/twins/{twin['id']}/samples",
        json={"category": "invalid", "content": "x"},
    )
    assert r.status_code == 422


def test_invalid_mode_rejected():
    twin = _make_twin()
    r = client.post(
        f"/api/twins/{twin['id']}/chat",
        json={"mode": "bogus", "content": "hi"},
    )
    assert r.status_code == 422


def test_chat_requires_training():
    twin = _make_twin()
    r = client.post(
        f"/api/twins/{twin['id']}/chat",
        json={"mode": "conversation", "content": "hi"},
    )
    assert r.status_code == 400


def test_train_requires_samples():
    twin = _make_twin()
    r = client.post(f"/api/twins/{twin['id']}/train")
    assert r.status_code == 400


def test_seeds_listed_and_instantiated():
    seeds = client.get("/api/seeds").json()
    assert len(seeds) >= 1
    key = seeds[0]["key"]

    created = client.post(f"/api/seeds/{key}/instantiate").json()
    assert created["sample_count"] > 0

    detail = client.get(f"/api/twins/{created['id']}").json()
    # Seed twins ship with samples in every dimension.
    assert all(detail["samples_by_category"][c] for c in detail["samples_by_category"])

    assert client.post("/api/seeds/does-not-exist/instantiate").status_code == 404


def test_export_and_import_roundtrip():
    twin = _make_twin()
    client.post(
        f"/api/twins/{twin['id']}/samples",
        json={"category": "knowledge", "content": "Caching beats fine-tuning here."},
    )
    exported = client.get(f"/api/twins/{twin['id']}/export").json()
    assert exported["format"] == "personal-ai-twin"
    assert exported["samples_by_category"]["knowledge"]

    imported = client.post("/api/twins/import", json=exported).json()
    assert imported["id"] != twin["id"]
    detail = client.get(f"/api/twins/{imported['id']}").json()
    assert detail["samples_by_category"]["knowledge"]


def test_conversation_listing_empty_and_404():
    twin = _make_twin()
    assert client.get(f"/api/twins/{twin['id']}/conversations").json() == []
    assert client.get("/api/conversations/999999").status_code == 404
