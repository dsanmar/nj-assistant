from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Project root = backend/
    BASE_DIR: Path = Path(__file__).resolve().parents[2]

    DATA_DIR: Path = BASE_DIR / "data"
    PDF_DIR: Path = DATA_DIR / "pdfs"
    DB_PATH: Path = DATA_DIR / "njdot_knowledgehub.sqlite3"
    INDEX_DIR: Path = DATA_DIR / "indexes"
    BM25_PATH: Path = INDEX_DIR / "bm25.pkl"
    FAISS_INDEX_PATH: Path = INDEX_DIR / "faiss.index"
    FAISS_META_PATH: Path = INDEX_DIR / "faiss_meta.pkl"
    EMBED_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()