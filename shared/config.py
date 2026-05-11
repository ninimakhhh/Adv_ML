import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# --- LLM keys ---
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")

if not DEEPSEEK_API_KEY:
    raise EnvironmentError(
        "DEEPSEEK_API_KEY is not set. "
        "Add it to your .env file — see .env.example for the required variables."
    )

# --- Model defaults ---
DEFAULT_DEEPSEEK_MODEL = DEEPSEEK_MODEL
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"

# --- Paths ---
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
CHROMADB_DIR = ROOT_DIR / "chromadb_store"

# --- RAG ---
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K_RETRIEVAL = 5
