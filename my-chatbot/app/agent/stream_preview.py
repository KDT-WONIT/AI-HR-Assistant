"""모델이 생성 중인 (아직 끝나지 않은) JSON에서 사용자에게 보여줄 문장만 뽑아 미리보기로 만듭니다.

답변 모델은 {coverage, summary, points[{text,...}]} 형태의 JSON을 생성합니다. 토큰이 도착하는 대로
summary와 각 point의 text를 읽어 `요약 + 확인된 내용` 형태로 보여주고, 생성이 끝나면 서버가 검증·정리한
최종 답변이 이 미리보기를 대체합니다(근거 검증을 통과하지 못한 문장이 최종본에 남지 않도록)."""

import re
import json

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


def complete_draft(raw: str):
    """완성된 point 객체만 복구합니다. 끊긴 문장이나 출처 ID 없는 문장은 보여주지 않습니다."""
    from app.agent.answers import AnswerDraft, GroundedPoint
    summary=''; points=[]
    match=re.search(r'"summary"\s*:\s*"',raw)
    if match:
        value, complete=read_string(raw,match.end())
        if complete:
            summary=value
    match=re.search(r'"points"\s*:\s*\[',raw)
    if not match:
        return None
    decoder=json.JSONDecoder(); offset=match.end()
    while offset<len(raw):
        while offset<len(raw) and raw[offset] in ' \r\n\t,': offset+=1
        if offset>=len(raw) or raw[offset]!='{': break
        try:
            value,length=decoder.raw_decode(raw[offset:]); offset+=length
            points.append(GroundedPoint.model_validate(value))
        except ValueError:
            break
    if not summary or not points:
        return None
    coverage=re.search(r'"coverage"\s*:\s*"(direct|partial|missing)"',raw)
    return AnswerDraft(summary=summary,points=points[:6],coverage=coverage[1] if coverage else 'partial')


def validated_preview(raw, context, facts):
    from app.agent.answers import render_answer
    draft=complete_draft(raw)
    if draft is None:
        return ''
    preview_context=context.model_copy(deep=True)
    answer=render_answer(preview_context,draft,facts)
    return answer if preview_context.answer_coverage!='missing' else ''
