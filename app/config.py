from pathlib import Path
import os
from dotenv import load_dotenv

# Project directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"

# Magic Comprehensive Rules
RULES_PDF_PATH = DATA_DIR / "MagicCompRules 20260417.pdf"
RULES_VERSION = "2026-04-17"

# Local embeddings
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
EMBEDDING_MODEL = "qwen3-embedding:0.6b"
EMBEDDING_DIMENSIONS = 1024
EMBEDDING_BATCH_SIZE = 8

EMBEDDING_QUERY_INSTRUCTION = (
    "Retrieve relevant official Magic: The Gathering "
    "rules and glossary definitions that help answer "
    "the user's question."
)

# Local vector database
CHROMA_DIR = DATA_DIR / "chroma"
CHROMA_COLLECTION = "mtgsage_knowledge"

# Gemini generative model
load_dotenv(PROJECT_ROOT / ".env", override=False)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")