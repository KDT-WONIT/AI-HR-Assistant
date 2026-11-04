"""n8n Execute Command 등에서 사용하는 1회 JSON 입출력 진입점."""
import argparse
import json
import sys

from .common import ToolError
from .tool_registry import EmployeeTools


def main():
    parser = argparse.ArgumentParser(description="접속 사원의 Tool 1회 실행")
    parser.add_argument("--employee-id", required=True, help="서버에서 확인한 접속 사원번호")
    args = parser.parse_args()
    try:
        request = json.load(sys.stdin)
        # 사원번호는 AI가 생성한 JSON 인자가 아니라 접속 서버에서 전달합니다.
        result = EmployeeTools(args.employee_id).execute_tool(request)
    except (ToolError, ValueError, OSError) as exc:
        result = {"status": "error", "error": {"code": getattr(exc, "code", "INPUT_ERROR"), "message": str(exc)}}
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
