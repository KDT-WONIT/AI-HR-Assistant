"""질문 하나를 처리하는 동안 단계별 소요 시간을 모아 한 줄씩 보기 좋게 출력합니다.

요청 단위로 `Timings`를 만들어 ContextVar에 두므로, 검색·모델 호출 같은 깊은 코드에서도 `record()`만 부르면 됩니다
(활성 요청이 없으면 아무 일도 하지 않습니다)."""

import logging
import time
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger('uvicorn.error')


def width(text: str) -> int:
    """한글처럼 폭이 2칸인 글자를 고려한 표시 폭."""
    return sum(2 if unicodedata.east_asian_width(char) in 'WF' else 1 for char in text)


def pad(text: str, size: int) -> str:
    return text + ' ' * max(0, size - width(text))


class Timings:
    def __init__(self, title: str = ''):
        self.title = title
        self.items: dict[str, float] = {}
        self.notes: dict[str, str] = {}
        self.started = time.monotonic()

    def add(self, label: str, seconds: float, note: str = '') -> None:
        self.items[label] = self.items.get(label, 0.0) + seconds
        if note:
            self.notes[label] = note

    def note(self, label: str, note: str) -> None:
        self.notes[label] = note

    def lines(self, order: list[str] | None = None) -> list[str]:
        labels = [label for label in (order or []) if label in self.items] + [label for label in self.items if label not in (order or [])]
        label_width = max([width(label) for label in labels] + [12])
        out = [f'━━ 응답 시간 · {self.title} ' + '━' * 10]
        for label in labels:
            note = self.notes.get(label)
            out.append(f'  {pad(label, label_width)} {self.items[label]:6.1f}초' + (f'   {note}' if note else ''))
        out.append(f'  {"─" * (label_width + 9)}')
        out.append(f'  {pad("합계", label_width)} {time.monotonic() - self.started:6.1f}초')
        return out

    def log(self, order: list[str] | None = None) -> None:
        for line in self.lines(order):
            logger.info(line)


current: ContextVar[Timings | None] = ContextVar('current_timings', default=None)


def start(title: str = '') -> Timings:
    timings = Timings(title)
    current.set(timings)
    return timings


def record(label: str, seconds: float, note: str = '') -> None:
    timings = current.get()
    if timings is not None:
        timings.add(label, seconds, note)


def note(label: str, text: str) -> None:
    timings = current.get()
    if timings is not None:
        timings.note(label, text)


@contextmanager
def measure(label: str):
    began = time.monotonic()
    try:
        yield
    finally:
        record(label, time.monotonic() - began)
