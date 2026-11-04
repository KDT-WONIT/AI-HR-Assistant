from functools import lru_cache

from app.config import settings
from app.errors import RagUnavailable


@lru_cache(maxsize=2)
def load_model(name: str, revision: str, directory: str, device: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(name, revision=revision or None, cache_folder=directory, device=device)


class EmbeddingService:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            model = load_model(settings.embedding_model, settings.embedding_revision,
                               str(settings.embedding_cache_dir), settings.embedding_device)
            return model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
        except Exception as exc:
            raise RagUnavailable('질문 임베딩에 실패했습니다. 기존 DB와 동일한 임베딩 모델/리비전을 확인해주세요.') from exc

    def embed_query(self, question: str) -> list[float]:
        return self.embed_documents([question])[0]
