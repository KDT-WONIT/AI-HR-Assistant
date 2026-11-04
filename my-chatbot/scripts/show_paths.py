"""현재 적용되는 경로만 출력합니다. 비밀번호·웹훅 URL 등은 출력하지 않습니다."""

import json

from app.config import settings

def main():
    print(json.dumps(settings.paths(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
