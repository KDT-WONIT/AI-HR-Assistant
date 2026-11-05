"""답변의 핵심 수치·조항을 **굵게** 표시합니다. 근거 검증이 끝난 최종 문장에만 적용합니다."""
import re

UNITS = r'(?:만\s?원|억\s?원|천\s?원|원|%|퍼센트|개월|시간|일|년|회|명|박|km|㎞|배|세|주|분기)'
KEY_PATTERN = re.compile(
    rf'(?<![\dA-Za-z*])(?!(?:19|20)\d\d\s?년)(\d[\d,]*(?:\.\d+)?\s?{UNITS})(?![A-Za-z0-9*])|(제\s?\d+\s?조(?:의\s?\d+)?)'
)
REFERENCE_HEADS = ('[참고 문서]', '참고 문서')
SECTION_HEADS = {'확인된 내용','확인 범위','참고 문서','검토한 문서 · 세부 답변 미확인',
                 '추가 안내','다음 단계','조회 근거','계산 근거','계산 결과','신청 방법','관련 담당자'}


def format_headings(text: str) -> str:
    """소제목 줄만 통일합니다. 일반 문장·목록·JSON 중괄호는 건드리지 않습니다."""
    lines=[]
    for line in text.split('\n'):
        title=line.strip().removeprefix('**').removesuffix('**').strip()
        markdown=bool(re.match(r'^#{1,4}\s+',title))
        title=re.sub(r'^#{1,4}\s+','',title)
        wrapped=(title.startswith('[') and title.endswith(']')) or (title.startswith('{') and title.endswith('}'))
        if wrapped:
            title=title[1:-1].strip()
        if title in SECTION_HEADS or ((markdown or wrapped) and len(title)<=45 and not re.search(r'["=:]',title)):
            lines.append('**{'+title+'}**')
        else:
            lines.append(line)
    return '\n'.join(lines)


# 계산기 답변의 표 형태 항목은 숫자마다 굵게 하지 않고, 서버가 직접 표시한 핵심 값만 굵게 둡니다.
PLAIN_SECTIONS = {'출장비 계산기', '계산 내역','적용 조건','관련 규정', '입력하신 조건', '확인 필요', '예정·결재 중', '최근 사용 내역', '사용 계획 반영'}


def emphasize(text: str) -> str:
    out, in_reference, plain = [], False, False
    for line in format_headings(text).split('\n'):
        stripped = line.strip()
        heading = re.fullmatch(r'\*\*\{(.+)\}\*\*', stripped)
        if heading:
            plain = heading[1] in PLAIN_SECTIONS
        elif not stripped:
            plain = False
        if plain:
            out.append(line)
            continue
        if stripped in REFERENCE_HEADS or stripped == '**{참고 문서}**':
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
