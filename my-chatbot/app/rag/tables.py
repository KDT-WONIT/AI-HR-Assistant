"""평탄화된 표 청크를 읽기 쉬운 행으로 복원합니다.

규정 PDF의 표는 인덱스에서 `키, 열 = 값.` 형태로 이어 붙어 있고, 청크 경계에서 행이 끊기거나
(`등 급` | `= 8.`) 다음 쪽으로 이어진 표는 머리글이 사라집니다. 그래서 검색된 조각만으로는
"몇 등급이 얼마인지"를 알 수 없습니다. 이 모듈은 이웃 청크를 이어 붙여 행을 복원하고,
사용자의 직급 같은 관심어가 들어간 행만 골라 답변 근거와 '핵심 내용'으로 쓸 수 있게 합니다.

인덱스를 다시 만들지 않으며 ChromaDB에서 이웃 청크를 읽기만 합니다.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable

from app.schemas import Source

logger = logging.getLogger(__name__)

CHUNK_ID = re.compile(r'^(?P<prefix>.+):(?P<number>\d+)$')
ATOM_SPLIT = re.compile(r'\.\s+')
ATOM = re.compile(r'^(?P<left>.*?\S)\s*=\s*(?P<value>.*)$', re.S)
FLAT_CELL = re.compile(r'\S,\s[^=.]{1,40}\s=\s')
UNIT = re.compile(r'\(\s*금액\s*:[^)]*\)')
MONEY = re.compile(r'^\d{1,3}(?:,\d{3})+$')
SKIP_ROW_KEYS = re.compile(r'^(?:개정\s*번호|페\s*이\s*지)$')

# 이웃 청크를 이어 붙이는 범위(표 본문) / 머리글·단위를 찾는 범위(앞쪽)
BODY_SPAN, CAPTION_SPAN = 3, 8


@dataclass(frozen=True)
class Row:
    key: str
    cells: tuple[tuple[str, str], ...]

    @property
    def numeric_columns(self) -> bool:
        return all(re.fullmatch(r'\d+', column) for column, _ in self.cells)


@dataclass
class TableView:
    caption: str = ''
    unit: str = ''
    rows: list[Row] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)


def is_table_fragment(text: str) -> bool:
    return len(FLAT_CELL.findall(text or '')) >= 3


def split_chunk(text: str) -> tuple[str, str]:
    """(제목 줄, 본문). 청크는 `문서: 이름` / 제목 / 본문 순서입니다."""
    lines = (text or '').split('\n')
    if lines and lines[0].startswith('문서:'):
        lines = lines[1:]
    title = lines[0].strip() if lines else ''
    return title, '\n'.join(lines[1:])


def clean_body(body: str) -> str:
    """표 테두리(`| - |`, 행 구분 `|`)를 제거하되 청크 경계의 공백은 보존합니다."""
    body = re.sub(r'(?m)^[ \t]*\|[ \t]*-+[ \t]*\|[ \t]*\n?', '', body)
    body = re.sub(r'[ \t]*\|[ \t]*\n[ \t]*\|[ \t]*', ' ', body)
    body = re.sub(r'^\|[ \t]?', '', body)
    return re.sub(r'[ \t]?\|[ \t]*\n?$', '', body)


def decode_rows(text: str) -> list[Row]:
    """`키, 열 = 값` 조각을 행으로 묶습니다. `.`+공백으로 나눈 뒤 `=`이 없는 조각은 앞 값에 이어 붙입니다."""
    atoms: list[list[str]] = []
    for piece in ATOM_SPLIT.split(text):
        piece = piece.strip().rstrip('.')
        match = ATOM.match(piece) if piece else None
        if match:
            left, value = match.group('left'), match.group('value').strip()
            key, _, column = left.rpartition(',')
            if not key:
                key, column = left, ''
            atoms.append([key.strip(), column.strip(), value])
        elif atoms and piece:
            atoms[-1][2] = f'{atoms[-1][2]}. {piece}'
        # 청크 경계에서 잘린 첫 조각은 의미를 알 수 없어 버립니다.
    rows: list[Row] = []
    for key, column, value in atoms:
        if rows and rows[-1].key == key and all(column != existing for existing, _ in rows[-1].cells):
            rows[-1] = Row(key, rows[-1].cells + ((column, value),))
        else:
            rows.append(Row(key, ((column, value),)))
    return [row for row in rows if not SKIP_ROW_KEYS.match(row.key)]


def normalize_column(column: str) -> str:
    return re.sub(r'(?<=[가-힣])\s+(?=[가-힣])', '', column) if len(column) <= 8 else column


def render_row(row: Row, unit: str = '') -> str:
    won = '원' in unit
    values = [(normalize_column(column), value.strip()) for column, value in row.cells if value.strip()]
    values = [(column, value + '원' if won and MONEY.match(value) else value) for column, value in values]
    if row.numeric_columns:
        return f'{row.key}번 행: ' + ' · '.join(value for _, value in values)
    return row.key + ' · ' + ' · '.join(f'{column} {value}' if column else value for column, value in values)


def neighbor_ids(chunk_id: str, before: int, after: int) -> dict[int, str]:
    match = CHUNK_ID.match(chunk_id or '')
    if not match:
        return {}
    width, number = len(match.group('number')), int(match.group('number'))
    return {n: f"{match.group('prefix')}:{n:0{width}d}" for n in range(max(1, number - before), number + after + 1)}


def pages_of(meta: dict) -> list[int]:
    try:
        return [page for page in json.loads(meta.get('pdf_pages_json', '[]')) if isinstance(page, int) and page > 0]
    except (TypeError, ValueError):
        return []


def table_view(source: Source, fetch: Callable[[list[str]], dict[str, tuple[str, dict]]]) -> TableView | None:
    """표 조각 하나를 같은 표의 앞뒤 청크와 이어 붙여 행과 머리글(제목·단위)을 복원합니다."""
    match = CHUNK_ID.match(source.chunk_id or '')
    if not match:
        return None
    number = int(match.group('number'))
    ids = neighbor_ids(source.chunk_id, CAPTION_SPAN, BODY_SPAN)
    found = fetch(list(ids.values()))
    chunks = {n: found[chunk_id] for n, chunk_id in ids.items() if chunk_id in found}
    chunks[number] = (source.text, chunks.get(number, ('', {}))[1])  # 검색된 조각을 기준으로 삼습니다.
    document_title = source.document.split('(')[0].removesuffix('.pdf').strip()
    own_title = split_chunk(source.text)[0]

    def same_table(n: int) -> bool:
        text = chunks.get(n, ('', {}))[0]
        return bool(text) and is_table_fragment(text) and split_chunk(text)[0] == own_title

    def remnant(n: int) -> bool:
        """표의 마지막 행이 청크 경계에서 잘려 짧은 꼬리만 다음 청크에 남은 경우(예: '마등급 |')"""
        text = chunks.get(n, ('', {}))[0]
        if not text or split_chunk(text)[0] != own_title:
            return False
        body = clean_body(split_chunk(text)[1]).strip()
        return 0 < len(body) <= 40 and '=' not in body and '금액' not in body

    first = last = number
    while first - 1 >= number - BODY_SPAN and same_table(first - 1):
        first -= 1
    while last + 1 <= number + BODY_SPAN and same_table(last + 1):
        last += 1
    if last + 1 <= number + BODY_SPAN and remnant(last + 1):
        last += 1
    stitched = ''.join(clean_body(split_chunk(chunks[n][0])[1]) for n in range(first, last + 1))

    # 머리글: 표 자신의 제목, 없으면(쪽을 넘어 이어진 표) 앞쪽 청크의 가장 가까운 구체적인 제목
    caption = own_title if own_title and own_title != document_title else ''
    borrowed = False
    unit = ''
    for n in range(first - 1, number - CAPTION_SPAN - 1, -1):
        if n not in chunks:
            continue
        title, body = split_chunk(chunks[n][0])
        if not caption and title and title != document_title:
            caption, borrowed = title, True
        found_unit = UNIT.findall(body) or UNIT.findall(title)
        if found_unit and not unit:
            unit = found_unit[-1]
        if caption and unit:
            break
    if borrowed:
        caption += ' (이어지는 표)'
    pages = sorted({page for n in range(first, last + 1) for page in pages_of(chunks[n][1])} | set(source.pages or [])
                   | ({source.page} if source.page else set()))
    return TableView(caption=caption, unit=unit, rows=decode_rows(stitched), pages=pages,
                     chunk_ids=[ids[n] for n in range(first, last + 1) if n in ids])


def expand_sources(sources: list[Source], focus: list[str], fetch, *, max_rows: int = 14,
                   max_highlights: int = 10) -> list[Source]:
    """표 조각 출처를 복원된 행으로 바꾸고, 관심어(직급 등)가 들어간 행은 highlights로 따로 담습니다."""
    consumed: set[str] = set()
    output: list[Source] = []
    for source in sources:
        if source.chunk_id and source.chunk_id in consumed:
            continue  # 앞선 표 복원에 이미 포함된 이웃 조각입니다.
        if not is_table_fragment(source.text):
            output.append(source)
            continue
        try:
            view = table_view(source, fetch)
        except Exception:  # 이웃 조회 실패로 검색 자체를 막지 않습니다.
            logger.warning('표 복원에 실패해 원본 조각을 사용합니다: %s', source.chunk_id, exc_info=True)
            view = None
        if view is None or not view.rows:
            output.append(source)
            continue
        consumed.update(view.chunk_ids)
        rendered = [render_row(row, view.unit) for row in view.rows]
        matched = [line for line in rendered if any(term in line for term in focus)] if focus else []
        chosen = matched[:max_rows] or rendered[:max_rows]
        title = ' '.join(part for part in (view.caption, view.unit) if part)
        text = '\n'.join([f"문서: {source.document.removesuffix('.pdf')}", *(['[표] ' + title] if title else []),
                          *('- ' + line for line in chosen)])
        pages = view.pages or source.pages
        output.append(source.model_copy(update={
            'text': text, 'pages': pages, 'page': pages[0] if pages else source.page,
            'caption': title, 'highlights': matched[:max_highlights],
        }))
    return output
