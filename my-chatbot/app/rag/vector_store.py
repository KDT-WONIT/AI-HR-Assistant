import json
from functools import lru_cache

from app.schemas import Source
from app.config import settings
from app.errors import RagUnavailable


@lru_cache(maxsize=4)
def get_collection(directory: str, name: str):
    from pathlib import Path
    if not (Path(directory) / 'chroma.sqlite3').is_file():
        raise RagUnavailable('CHROMA_DIR에 기존 chroma.sqlite3가 없습니다. 새 빈 DB를 만들지 않습니다.')
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    client = chromadb.PersistentClient(path=directory, settings=ChromaSettings(anonymized_telemetry=False))
    return client.get_collection(name=name, embedding_function=None)


@lru_cache(maxsize=4)
def collection_sources(directory: str, name: str) -> tuple[str, ...]:
    collection = get_collection(directory, name)
    metadata = collection.get(include=['metadatas'])['metadatas']
    return tuple(sorted({item['source'] for item in metadata if item and item.get('source')}))


class ChromaVectorStore:
    def __init__(self):
        self.directory = settings.chroma_dir
        self.collection_name = settings.chroma_collection

    def fetch(self, ids: list[str]) -> dict[str, tuple[str, dict]]:
        """청크 ID로 본문과 메타데이터를 읽습니다(이웃 청크 이어 붙이기용, 읽기 전용)."""
        try:
            collection = get_collection(str(self.directory), self.collection_name)
            result = collection.get(ids=ids, include=['documents', 'metadatas'])
        except RagUnavailable:
            raise
        except Exception as exc:
            raise RagUnavailable('ChromaDB 이웃 조각 조회에 실패했습니다.') from exc
        return {identifier: (text or '', meta or {})
                for identifier, text, meta in zip(result['ids'], result['documents'], result['metadatas'])}

    def build(self, vectors: list[list[float]], documents: list[Source]) -> None:
        raise ValueError('기존 규정 인덱스는 검색 전용으로 사용합니다. 재적재는 별도 컬렉션으로 진행하세요.')

    def search(self, vector: list[float], patterns: list[str] | None, top_k: int = 5) -> list[Source]:
        """patterns가 None이면 전체 문서에서, 목록이면 이름에 그 문구가 들어간 문서에서만 검색합니다."""
        try:
            collection = get_collection(str(self.directory), self.collection_name)
            metadata = collection.metadata or {}
            if metadata.get('embedding_model') != settings.embedding_model:
                raise RagUnavailable('임베딩 모델이 기존 ChromaDB 메타데이터와 다릅니다.')
            if metadata.get('embedding_revision') and metadata['embedding_revision'] != settings.embedding_revision:
                raise RagUnavailable('임베딩 모델 리비전이 기존 ChromaDB와 다릅니다.')
            if metadata.get('embedding_dimension') and len(vector) != metadata['embedding_dimension']:
                raise RagUnavailable('질문 벡터와 기존 DB의 차원이 다릅니다.')
            if metadata.get('normalized_embeddings') is False:
                raise RagUnavailable('ChromaDB가 정규화 임베딩으로 생성되지 않았습니다.')
            where = None
            if patterns is not None:
                sources = [name for name in collection_sources(str(self.directory), self.collection_name)
                           if any(pattern in name for pattern in patterns)]
                if not sources:
                    return []
                where = {'source': {'$in': sources}}
            result = collection.query(query_embeddings=[vector], n_results=top_k,
                                      where=where, include=['documents', 'metadatas', 'distances'])
            output = []
            for identifier, text, meta, distance in zip(result['ids'][0], result['documents'][0], result['metadatas'][0], result['distances'][0]):
                if distance > settings.rag_max_distance or not text:
                    continue
                pages = json.loads(meta.get('pdf_pages_json', '[]'))
                pages = sorted({page for page in pages if isinstance(page, int) and page > 0})
                headings = json.loads(meta.get('headings_json', '[]'))
                output.append(Source(document=meta.get('source', '문서명 없음'), page=pages[0] if pages else None,
                                     pages=pages, section=' / '.join(str(item) for item in headings) or None,
                                     text=text[:5000], chunk_id=identifier, distance=float(distance)))
            return output
        except RagUnavailable:
            raise
        except Exception as exc:
            raise RagUnavailable('ChromaDB 검색에 실패했습니다. 경로·컬렉션·패키지 버전을 확인해주세요.') from exc
