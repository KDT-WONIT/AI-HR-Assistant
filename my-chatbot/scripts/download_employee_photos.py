"""사원 DB의 photo_url에서 사진을 내려받아 assets/photos/{사번}.jpg로 저장합니다.

인터넷이 되는 PC에서 한 번 실행하면 이후에는 외부 접속 없이 로컬 파일로 사진이 표시됩니다.

    python -m scripts.download_employee_photos            # 없는 사진만 내려받기
    python -m scripts.download_employee_photos --force    # 모두 다시 내려받기
    python -m scripts.download_employee_photos --limit 5  # 처음 5명만 시험

사원 DB는 읽기 전용으로만 열며 수정하지 않습니다. 사진은 가상 직원용 스톡 사진(Pexels)이므로
화면에는 "실제 직원 아님" 안내(photo_alt)가 함께 표시됩니다.
"""

import argparse
import io
import sqlite3
import sys
import time
from urllib.parse import urlsplit

import httpx

from app.config import settings
from app.repositories.directory import REMOTE_PHOTO_HOSTS

MIN_BYTES, MAX_BYTES = 2_500, 8_000_000


def photo_rows():
    path = settings.employee_directory_db.resolve()
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        return connection.execute('SELECT employee_id,photo_url FROM employee_contacts '
                                  "WHERE photo_url IS NOT NULL AND photo_url<>'' ORDER BY employee_id").fetchall()
    finally:
        connection.close()


def normalize(content: bytes) -> bytes:
    """JPEG 여부를 확인하고, Pillow가 있으면 650px 이내 JPEG로 줄입니다."""
    try:
        from PIL import Image
    except ImportError:
        if content[:3] != b'\xff\xd8\xff':
            raise ValueError('JPEG 파일이 아닙니다.')
        return content
    with Image.open(io.BytesIO(content)) as image:
        image = image.convert('RGB')
        image.thumbnail((650, 650))
        output = io.BytesIO()
        image.save(output, 'JPEG', quality=85, optimize=True)
        return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--force', action='store_true', help='이미 있는 사진도 다시 내려받습니다.')
    parser.add_argument('--limit', type=int, default=0, help='처리할 최대 인원(0이면 전체)')
    args = parser.parse_args()
    target = settings.employee_directory_dir / 'assets' / 'photos'
    target.mkdir(parents=True, exist_ok=True)
    rows = photo_rows()
    if args.limit > 0:
        rows = rows[:args.limit]
    done = skipped = failed = 0
    headers = {'User-Agent': 'Mozilla/5.0 (classroom demo; employee photo cache)'}
    with httpx.Client(timeout=25, follow_redirects=True, headers=headers, trust_env=True) as client:
        for index, (employee_id, url) in enumerate(rows, 1):
            destination = target / f'{employee_id}.jpg'
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or parsed.hostname not in REMOTE_PHOTO_HOSTS:
                print(f'[{index:03}/{len(rows)}] {employee_id} 건너뜀: 허용되지 않은 주소')
                failed += 1
                continue
            if destination.is_file() and not args.force:
                skipped += 1
                continue
            for attempt in range(3):
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    content = response.content
                    if not response.headers.get('content-type', '').lower().startswith('image/'):
                        raise ValueError('이미지 응답이 아닙니다.')
                    if not MIN_BYTES <= len(content) <= MAX_BYTES:
                        raise ValueError('이미지 크기가 올바르지 않습니다.')
                    temporary = destination.with_suffix('.tmp')
                    temporary.write_bytes(normalize(content))
                    temporary.replace(destination)
                    done += 1
                    print(f'[{index:03}/{len(rows)}] {employee_id} 저장 ({destination.stat().st_size:,} bytes)')
                    break
                except (httpx.HTTPError, ValueError, OSError) as error:
                    if attempt == 2:
                        failed += 1
                        print(f'[{index:03}/{len(rows)}] {employee_id} 실패: {str(error)[:80]}')
                    else:
                        time.sleep(1.2)
    print(f'완료 {done}명 · 기존 파일 {skipped}명 · 실패 {failed}명 · 위치 {target}')
    return 1 if failed and not (done or skipped) else 0


if __name__ == '__main__':
    sys.exit(main())
