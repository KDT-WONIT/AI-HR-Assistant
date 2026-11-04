"""TODO: 문서 적재 진입점. 현재 파일을 읽거나 인덱스를 생성하지 않습니다.

실행 예정: python -m scripts.ingest --domain work_labor
구현 순서: 원본 PDF → 텍스트 추출 → 조항 분할 → 임베딩 → ChromaDB 저장.
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="규정 문서 적재 인터페이스 (구현 전)")
    parser.add_argument("--domain", required=True, help="app/tools/registry.py에 등록된 분야 ID")
    args = parser.parse_args()
    parser.exit(1, f"[{args.domain}] 적재 로직은 아직 구현되지 않았습니다. app/rag/를 먼저 구현해주세요.\n")


if __name__ == "__main__":
    main()
