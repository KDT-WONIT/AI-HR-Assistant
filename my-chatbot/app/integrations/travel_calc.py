"""출장비 계산기: 출장 일수·숙박 일수·교통비·1박 숙박비 4가지로 국내 출장 예상액을 계산합니다.

- 일비·식비는 여비규정의 직급별 정액(일비 25,000원·식비 30,000원, 임원 30,000원·60,000원)을 적용합니다.
- 교통비와 1박 숙박비는 사용자가 입력한 값을 그대로 쓰며 추정하지 않습니다.
- 4가지 중 하나라도 없으면 계산하지 않고 빠진 항목을 되물어 봅니다(숙박 0박이면 숙박비는 묻지 않음).
"""
import re
from decimal import Decimal

CALC_MARKER = '출장비 계산기'
REQUEST_WORDS = re.compile(r'계산|견적|예상|총액|산출|합계|얼마나\s*들|비용이?\s*얼마')
TRIP_WORDS = re.compile(r'출장|여비')
OVERSEAS_WORDS = re.compile(r'해외|국외|외국')
SOURCE = '여비규정(2025년도 07월 개정).pdf'
SOURCE_PAGES = '5·7·8·16쪽'
REGION_CAPS = (('서울', 100000), ('광역시', 90000), ('세종·제주', 80000), ('그 외 지역', 70000))

AMOUNT = re.compile(
    r'(?P<man>\d[\d,]*(?:\.\d+)?)\s*만\s*(?:(?P<cheon>\d[\d,]*)\s*천)?\s*원?'
    r'|(?P<c>\d[\d,]*(?:\.\d+)?)\s*천\s*원?'
    r'|(?P<won>\d[\d,]*)\s*원')
TRANSPORT_LABEL = re.compile(r'교통비|교통|차비|항공료|항공|비행기|KTX|SRT|기차|철도|버스|택시|렌트|통행료|톨게이트', re.I)
LODGING_LABEL = re.compile(r'숙박비|숙박|숙소|호텔|모텔|한\s*박|박당|\d+\s*박')


def _to_won(match) -> Decimal:
    def num(text):
        return Decimal(text.replace(',', ''))
    if match.group('man') is not None:
        return num(match.group('man')) * 10000 + (num(match.group('cheon')) * 1000 if match.group('cheon') else 0)
    if match.group('c') is not None:
        return num(match.group('c')) * 1000
    return num(match.group('won'))


def _last_label(window: str):
    """창 안에서 가장 가까운(마지막) 항목 이름을 찾습니다."""
    best = None
    for kind, pattern in (('transport', TRANSPORT_LABEL), ('lodging', LODGING_LABEL)):
        for found in pattern.finditer(window):
            if best is None or found.end() > best[1]:
                best = (kind, found.end(), found.start())
    return best


def extract_inputs(text: str) -> dict:
    """문장에서 days, nights, transport_cost, lodging_per_night(원)을 찾아 돌려줍니다. 없는 항목은 빠집니다."""
    found = {}
    amounts = list(AMOUNT.finditer(text))
    label_spans = []  # 금액의 이름으로 쓰인 'N박' 표현은 숙박 일수로 세지 않습니다.
    previous_end = 0
    for index, match in enumerate(amounts):
        before = text[max(previous_end, match.start() - 14):match.start()]
        after_limit = amounts[index + 1].start() if index + 1 < len(amounts) else len(text)
        after = text[match.end():min(match.end() + 8, after_limit)]
        label = _last_label(before)
        if label is None:
            label = _last_label(after)
            offset = match.end()
        else:
            offset = max(previous_end, match.start() - 14)
        if label is not None:
            kind = label[0]
            if kind == 'lodging':
                span = re.search(r'\d+\s*박\s*(?:당)?\s*$', before)
                if span:
                    label_spans.append((offset + span.start(), offset + span.end()))
            key = 'transport_cost' if kind == 'transport' else 'lodging_per_night'
            if key not in found:
                found[key] = float(_to_won(match))
        previous_end = match.end()
    rest = list(text)
    for match in amounts:
        for position in range(match.start(), match.end()):
            rest[position] = ' '
    for start, end in label_spans:
        for position in range(start, end):
            rest[position] = ' '
    plain = ''.join(rest)
    both = re.search(r'(\d+)\s*박\s*(\d+)\s*일', plain)
    if both:
        found['nights'], found['days'] = int(both[1]), int(both[2])
    else:
        nights = (re.search(r'숙박\s*(?:일수|기간)?\s*(?:은|는|:|이|가)?\s*(\d+)\s*(?:일|박|밤)', plain)
                  or re.search(r'(\d+)\s*(?:박|밤)(?!\s*(?:숙박|숙소|호텔|당|비|가격|요금))', plain))
        if nights:
            found['nights'] = int(nights[1])
            plain = plain[:nights.start()] + ' ' * (nights.end() - nights.start()) + plain[nights.end():]
        days = (re.search(r'(?:출장\s*(?:일수|기간)?\s*(?:은|는|:|이|가)?\s*)(\d+)\s*일', plain)
                or re.search(r'(?<!숙박)(?<!\d)(\d+)\s*일(?:간|\s*동안|\s*출장)?', plain))
        if days:
            found['days'] = int(days[1])
    if re.search(r'당일|하루|무박', plain):
        found.setdefault('days', 1)
        found.setdefault('nights', 0)
    if re.search(r'숙박\s*(?:은\s*)?(?:없|안\s*함|안\s*해|하지\s*않)', plain):
        found['nights'] = 0
    if re.search(r'(?:교통비|차비)\s*(?:는\s*)?(?:없|안\s*듦|무료)', plain):
        found.setdefault('transport_cost', 0.0)
    return found


def is_calc_request(question: str) -> bool:
    return bool(TRIP_WORDS.search(question) and REQUEST_WORDS.search(question)) and not OVERSEAS_WORDS.search(question)


def pending(last_assistant: str) -> bool:
    return CALC_MARKER in (last_assistant or '')


def merge_inputs(question: str, previous_user_messages: list[str]) -> dict:
    """같은 대화에서 앞서 알려준 값도 이어 받고, 최근 입력이 우선합니다."""
    merged = {}
    for text in [*previous_user_messages[-4:], question]:
        merged.update(extract_inputs(text))
    return merged


def should_run(question: str, previous_user_messages: list[str], last_assistant: str) -> bool:
    if OVERSEAS_WORDS.search(question):
        return False
    if is_calc_request(question):
        return True
    return pending(last_assistant) and bool(extract_inputs(question))


LABELS = (('days', '출장 일수', lambda v: f'{int(v)}일'), ('nights', '숙박 일수', lambda v: f'{int(v)}박'),
          ('transport_cost', '교통비(왕복 합계)', lambda v: f'{int(v):,}원'),
          ('lodging_per_night', '1박 숙박비', lambda v: f'{int(v):,}원'))


def missing_items(inputs: dict) -> list[str]:
    need = ['days', 'nights', 'transport_cost']
    if inputs.get('nights') != 0:
        need.append('lodging_per_night')
    return [key for key in need if key not in inputs]


def request_message(inputs: dict, problem: str = '') -> str:
    lines = [f'**{{{CALC_MARKER}}}**',
             '출장비를 계산하려면 아래 4가지 정보가 모두 필요합니다. 빠진 항목을 알려주세요.', '']
    for key, label, fmt in LABELS:
        if key == 'lodging_per_night' and inputs.get('nights') == 0:
            lines.append(f'- {label}: 숙박 없음이라 필요하지 않습니다')
        else:
            lines.append(f'- {label}: ' + (fmt(inputs[key]) if key in inputs else '(입력 필요)'))
    if problem:
        lines.extend(['', problem])
    lines.extend(['', '예) 3일 출장, 2박, 교통비 10만원, 1박 숙박비 8만원', '이미 알려주신 항목은 기억하고 있으니 빠진 것만 말씀하셔도 됩니다.'])
    return '\n'.join(lines)


def validate(inputs: dict) -> str:
    days, nights = int(inputs['days']), int(inputs['nights'])
    if not 1 <= days <= 366:
        return f'출장 일수({days}일)는 1~366일이어야 합니다.'
    if nights > days - 1:
        return f'숙박 일수({nights}박)는 출장 일수({days}일)보다 하루 적어야 합니다. {days}일 출장이면 최대 {days - 1}박입니다.'
    return ''


def calculate(inputs: dict, travel_grade: str | None) -> dict:
    days, nights = int(inputs['days']), int(inputs['nights'])
    transport = Decimal(str(inputs['transport_cost']))
    per_night = Decimal(str(inputs.get('lodging_per_night', 0)))
    executive = travel_grade == 'executive'
    daily_rate, meal_rate = (30000, 60000) if executive else (25000, 30000)
    after_arrival = days - 1  # 도착 다음 날부터 30일 전액, 이후 30일 90%, 60일 초과 80%
    units = (Decimal(1 + min(after_arrival, 30)) + Decimal(min(max(after_arrival - 30, 0), 30)) * Decimal('0.9')
             + Decimal(max(after_arrival - 60, 0)) * Decimal('0.8'))
    allowance = Decimal(daily_rate) * units
    meals = Decimal(meal_rate) * days
    meal_note = ''
    if days == 1 and nights == 0:
        meals = meals * 2 / 3
        meal_note = '숙박 없는 1일 출장은 식비의 3분의 2'
    lodging = per_night * nights
    total = allowance + meals + lodging + transport
    capped = travel_grade not in {'executive', 'grade_1'}
    lodging_note = ''
    if nights and capped and per_night > 70000:
        lodging_note = ('입력하신 1박 숙박비가 지역별 상한(서울 100,000원·광역시 90,000원·세종/제주 80,000원·그 외 70,000원)을 '
                        '넘을 수 있습니다. 상한을 넘는 금액은 지급되지 않을 수 있으니 지역별 상한을 확인해주세요.')
    return dict(days=days, nights=nights, transport_cost=int(transport), lodging_per_night=int(per_night),
                daily_rate=daily_rate, daily_units=float(units), allowance=int(allowance),
                meal_rate=meal_rate, meals=int(meals.quantize(Decimal(1))), meal_note=meal_note,
                lodging=int(lodging), total=int(total.quantize(Decimal(1))), travel_grade=travel_grade,
                lodging_note=lodging_note, source=SOURCE, source_pages=SOURCE_PAGES)
