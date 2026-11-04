"""프로젝트 루트에서 python -m tests [-v]로 전체 테스트를 실행합니다."""

import sys
import unittest
from pathlib import Path


def main():
    directory = Path(__file__).resolve().parent
    unittest.main(
        module=None,
        argv=[sys.argv[0], "discover", "-s", str(directory), "-t", str(directory.parent), *sys.argv[1:]],
    )


if __name__ == "__main__":
    main()
