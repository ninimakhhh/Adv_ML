import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# --- LLM keys ---
DEEPSEEK_API_KEY: str | None = os.getenv("DEEPSEEK_API_KEY")
#GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
#ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
#OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")

# --- Model defaults ---
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"

# --- RAG ---
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K_RETRIEVAL = 5
