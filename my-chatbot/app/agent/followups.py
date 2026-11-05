"""생략된 대상에 필요한 사용자 발언만 원문으로 연결합니다. 규정이나 답은 만들지 않습니다."""
import re


def contextual_question(question: str, history: list[dict]) -> str:
    if len(question) > 2400:
        return question
    if not re.search(r'그\s*(?:휴가|출장|경조|지원|비용)|그럼|이\s*경우|아까|연달아|이어서|경조사', question):
        return question
    statements = [item['content'] for item in history if item.get('role') == 'user']
    if re.search(r'출장비|여비|그\s*출장', question):
        # 날짜·금액이 있는 출장 조건을 보존합니다. 최근 5턴 밖의 조건도 같은 세션에서 찾습니다.
        facts = [text for text in statements if '출장' in text and re.search(r'\d+\s*(?:km|만원)|\d{4}년', text)]
    elif re.search(r'휴가|경조|지원금', question):
        births = [text for text in statements if '배우자' in text and '출산' in text]
        # 구체적인 출산 조건 발언이 일반적인 '사용하려고 해'보다 우선입니다.
        facts = [text for text in births if re.search(r'예정|둘째|첫째|단태|다태|쌍둥', text)] or births[-1:]
        if not facts:
            facts = [text for text in statements if any(word in text for word in ('휴가', '경조'))][-1:]
    else:
        facts = statements[-1:]
    facts = list(dict.fromkeys(text for text in facts[-3:] if text != question))
    if not facts:
        return question
    return question + '\n\n[생략된 대상 이해용 · 같은 세션 사용자의 발언, 규정 근거 아님]\n' + '\n'.join(facts)[:1500]


def current_question(question: str) -> str:
    return question.split('\n\n[생략된 대상 이해용', 1)[0]


def situation_statement(question: str) -> bool:
    text = current_question(question)
    return bool(re.search(r'출장\s*중|출산할\s*예정', text)) and not re.search(
        r'\?|어떻게|언제|얼마|며칠|가능|될까|되나요|알려|계산|궁금|문의|방법|절차', text)
