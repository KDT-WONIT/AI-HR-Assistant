"""모델 인자 중 명시적인 사용자 값과 충돌하는 항목을 바로잡습니다. 요율은 계산 Tool의 책임입니다."""
import re


def normalize_arguments(current, contextual, arguments):
    args = arguments.model_copy(deep=True)
    if not re.search(r'(?:\d+(?:\.\d+)?\s*일).{0,8}(?:쓰|사용)', current):
        args.requested_days = None
    if not re.search(r'계산|예상|견적|얼마|총액|대략', current) or re.search(r'언제|지급일|입금일|지급\s*예정일', current):
        args.trip = None
        return args
    if args.trip is None:
        return args
    trip = args.trip
    if re.search(r'KTX|SRT|철도|기차|버스', contextual, re.I):
        trip['transport_mode'] = 'public_transport'
    distance = re.search(r'왕복\s*([\d,.]+)\s*km', contextual, re.I)
    if distance:
        trip['distance_km'] = float(distance[1].replace(',', ''))
    if re.search(r'(?:다른|다른\s*시군|별도)\s*시[·ㆍ\s]?군|본사와\s*다른\s*시군', contextual):
        trip['same_city'] = False
    elif re.search(r'근무지와\s*(?:같은|동일)\s*시[·ㆍ\s]?군', contextual):
        trip['same_city'] = True
    # 도시 구분은 지리 정보이며 규정 요율은 이곳에 두지 않습니다.
    city = trip.get('destination_city', '')
    if any(name in city for name in ('부산','대구','인천','광주','대전','울산')):
        trip['domestic_region_type'] = 'metropolitan_city'
    elif '서울' in city:
        trip['domestic_region_type'] = 'special_city'
    elif any(name in city for name in ('세종','제주')):
        trip['domestic_region_type'] = 'special_autonomous'
    nights = re.search(r'(\d+)\s*박\s*(\d+)\s*일', contextual)
    if nights:
        trip['lodging_nights'] = int(nights[1])
    meals = re.search(r'식비\s*(?:지급\s*대상은?|는?)?\s*(\d+)\s*일', contextual)
    if meals:
        trip['meal_days'] = int(meals[1])
    if trip.get('trip_type') == 'domestic':
        for key in ('destination_country','exchange_rate_krw_per_usd','approval_date','exchange_rate_date','exchange_rate_basis'):
            trip.pop(key, None)
    return args
