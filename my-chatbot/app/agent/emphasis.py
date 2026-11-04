"""답변의 핵심 수치·조항을 **굵게** 표시합니다. 근거 검증이 끝난 최종 문장에만 적용합니다."""
import re

UNITS = r'(?:만\s?원|억\s?원|천\s?원|원|%|퍼센트|개월|시간|일|년|회|명|박|km|㎞|배|세|주|분기)'
KEY_PATTERN = re.compile(
    rf'(?<![\dA-Za-z*])(?!(?:19|20)\d\d\s?년)(\d[\d,]*(?:\.\d+)?\s?{UNITS})(?![A-Za-z0-9*])|(제\s?\d+\s?조(?:의\s?\d+)?)'
)
REFERENCE_HEADS = ('[참고 문서]', '참고 문서')


def emphasize(text: str) -> str:
    out, in_reference = [], False
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped in REFERENCE_HEADS:
            in_reference = True
        elif not stripped:
            in_reference = False
        if in_reference or '**' in line or '|' in line:
            out.append(line)
            continue
        out.append(KEY_PATTERN.sub(lambda m: f'**{m.group(0)}**', line))
    return '\n'.join(out)


def strip_emphasis(text: str) -> str:
    """시트·로그에 저장할 때는 강조 표시를 제거합니다."""
    return text.replace('**', '')
