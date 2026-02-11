from __future__ import annotations
from functools import lru_cache
import numpy as np
from sentence_transformers import SentenceTransformer
from app.core.config import settings

@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.EMBED_MODEL_NAME)

def embed_texts(texts: list[str]) -> np.ndarray:
    model = get_model()
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype="float32")
