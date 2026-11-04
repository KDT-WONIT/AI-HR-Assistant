"""Pydantic/FastAPI 계약을 docs/openapi.json으로 내보냅니다."""

import json

from app.config import PROJECT_ROOT
from app.main import app

def main():
    (PROJECT_ROOT / "docs" / "openapi.json").write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print("docs/openapi.json 생성 완료")


if __name__ == "__main__":
    main()
