from pathlib import Path

from app.schemas import Source


def load_documents(directory: Path) -> list[Source]:
    """TODO: PDF 텍스트 추출. 문서명·페이지·조항·분야·버전 메타데이터 보존."""
    raise NotImplementedError("규정 문서 추출 구현 예정")


def split_documents(documents: list[Source]) -> list[Source]:
    """TODO: 조항 단위로 분할하고 출처 메타데이터를 유지합니다."""
    raise NotImplementedError("문서 분할 구현 예정")
