"""모델이 생성 중인 (아직 끝나지 않은) JSON에서 사용자에게 보여줄 문장만 뽑아 미리보기로 만듭니다.

답변 모델은 {coverage, summary, points[{text,...}]} 형태의 JSON을 생성합니다. 토큰이 도착하는 대로
summary와 각 point의 text를 읽어 `요약 + 확인된 내용` 형태로 보여주고, 생성이 끝나면 서버가 검증·정리한
최종 답변이 이 미리보기를 대체합니다(근거 검증을 통과하지 못한 문장이 최종본에 남지 않도록)."""

import re

KEY = re.compile(r'(?<!\\)"(summary|text)"\s*:\s*"')
ESCAPES = {'n': '\n', 't': '\t', 'r': '', '"': '"', '\\': '\\', '/': '/', 'b': '', 'f': ''}


def read_string(raw: str, start: int) -> tuple[str, bool]:
    """raw[start:]에서 JSON 문자열 값을 읽습니다. (값, 닫는 따옴표까지 도착했는지)."""
    out, index = [], start
    while index < len(raw):
        char = raw[index]
        if char == '"':
            return ''.join(out), True
        if char == '\\':
            if index + 1 >= len(raw):
                break  # 이스케이프가 중간에 끊김 — 다음 토큰을 기다립니다.
            nxt = raw[index + 1]
            if nxt == 'u':
                code = raw[index + 2:index + 6]
                if len(code) < 4:
                    break
                try:
                    out.append(chr(int(code, 16)))
                except ValueError:
                    pass
                index += 6
                continue
            out.append(ESCAPES.get(nxt, nxt))
            index += 2
            continue
        out.append(char)
        index += 1
    return ''.join(out), False


def extract_preview(partial_json: str) -> str:
    summary, points = '', []
    for match in KEY.finditer(partial_json or ''):
        value, _ = read_string(partial_json, match.end())
        value = re.sub(r'\s*[\[(][SE]\d+(?:\s*(?:참조|참고))?[\])]', '', value).strip()
        if not value:
            continue
        if match.group(1) == 'summary':
            summary = value
        else:
            points.append(value)
    parts = [summary] if summary else []
    if points:
        parts.append('확인된 내용\n' + '\n'.join('- ' + point for point in points))
    return '\n\n'.join(parts)
