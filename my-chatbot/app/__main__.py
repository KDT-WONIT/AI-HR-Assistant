"""웹 서버 실행: python -m app --reload"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="ABC Electronics AI HR Assistant 실행")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="개발 중 코드 변경 시 서버 재시작")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
