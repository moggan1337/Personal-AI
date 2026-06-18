"""Application configuration loaded from the environment."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Root of the repository (two levels up from this file: app/ -> backend/ -> repo).
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# The Anthropic model that powers every twin. Opus 4.8 is the most capable
# model and the right default for nuanced persona work.
TWIN_MODEL = os.environ.get("TWIN_MODEL", "claude-opus-4-8")

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'twins.db'}")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# The four dimensions a twin learns about its owner.
TRAINING_CATEGORIES = ("writing", "decisions", "knowledge", "personality")

# Application modes the twin can be deployed in.
APPLICATION_MODES = ("conversation", "consulting", "coaching", "support", "content")
