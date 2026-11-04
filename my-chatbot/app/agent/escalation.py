"""규정 답변이 부족할 때 실제 DB의 관련 업무 담당자 후보를 안내합니다."""

import logging
import re
from dataclasses import dataclass, replace
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.errors import StorageUnavailable
from app.repositories.directory import EmployeeDirectoryRepository
from app.schemas import ContactEscalation, ContactRecommendation

logger = logging.getLogger(__name__)


class ContactTopic(BaseModel):
    label: str = ''
    keywords: list[Annotated[str,Field(min_length=2)]] = Field(min_length=1)
    phrases: list[Annotated[str,Field(min_length=2)]] = Field(default_factory=list)
    weak_keywords: list[Annotated[str,Field(min_length=2)]] = Field(default_factory=list)
    weak_exclusions: list[Annotated[str,Field(min_length=2)]] = Field(default_factory=list)
    department_terms: list[Annotated[str,Field(min_length=2)]] = Field(min_length=1)
    department_fallbacks: list[list[Annotated[str,Field(min_length=2)]]] = Field(default_factory=list)
    # 답변 단계에서 확인한 규정 문서명·선택 도구와 맞으면 모호한 질문의 주제 판단을 보강합니다.
    source_patterns: list[Annotated[str,Field(min_length=2)]] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)


class RoutingConfig(BaseModel):
    topics: list[ContactTopic]
    # 어떤 주제에도 맞지 않을 때 일반 문의 창구로 안내할 부서(우선순위 순서의 부서명/기능 키워드 묶음)
    default_departments: list[list[Annotated[str,Field(min_length=2)]]] = Field(default_factory=list)


def compact(value: str) -> str:
    return re.sub(r'\s+','',value).casefold()


def matching_terms(query: str, terms: list[str]) -> list[str]:
    """긴 표현부터 매칭하고 '계약 말고', '복지가 아니라' 등 부정한 주제는 제외합니다."""
    found = []
    for term in sorted(terms,key=lambda value:len(compact(value)),reverse=True):
        needle = compact(term)
        if len(needle) < 2 or any(needle in compact(previous) for previous in found):
            continue
        for match in re.finditer(re.escape(needle),query):
            tail = query[match.end():]
            if re.match(r'(?:(?:이|가|은|는|을|를|쪽|부서|담당자|담당|업무|문의|관련|에대한)){0,4}(?:말고|아니|제외)',tail):
                continue
            found.append(term)
            break
    return found


@dataclass(frozen=True)
class ContactHints:
    """답변 과정에서 얻은 보조 정보. 질문만으로 주제가 겹칠 때 어느 업무가 중심인지 판단합니다."""
    tool_id: str | None = None
    documents: tuple[str, ...] = ()


@dataclass(frozen=True)
class TopicEvidence:
    topic: ContactTopic
    score: float
    terms: list[str]
    position: int = 0  # 질문에서 이 주제가 처음 언급된 위치(공백 제거 기준)
    end: int = 0


CONTEXT_BONUS = 6
MULTI_MARKERS = ('둘다','모두','각각','동시에','함께','같이','그리고')
JOINERS = ('과','와','랑','하고','및',',','/','·')


def first_mention(query: str, terms: list[str]) -> tuple[int,int]:
    spots = [(query.find(compact(term)),len(compact(term))) for term in terms]
    spots = [item for item in spots if item[0] >= 0]
    return min(spots) if spots else (len(query),0)


def context_matches(topic: ContactTopic, hints: ContactHints | None) -> bool:
    if hints is None:
        return False
    if hints.tool_id and hints.tool_id in topic.tool_ids:
        return True
    return any(compact(pattern) in compact(document) for document in hints.documents for pattern in topic.source_patterns)


def asks_multiple(query: str, evidence: list[TopicEvidence]) -> bool:
    """'A와 B 둘 다'처럼 여러 업무를 함께 묻는지 확인합니다. 단어가 우연히 겹친 경우와 구분합니다."""
    if any(marker in query for marker in MULTI_MARKERS):
        return True
    ordered = sorted(evidence,key=lambda item:item.position)
    for first,second in zip(ordered,ordered[1:]):
        gap = query[first.end:second.position]
        if len(gap) <= 12 and any(joiner in gap for joiner in JOINERS):
            return True
    return False


def topic_evidence(question: str, topics: list[ContactTopic]) -> list[TopicEvidence]:
    query = compact(question)
    evidence = []
    for topic in topics:
        phrases = matching_terms(query,topic.phrases)
        keywords = matching_terms(query,topic.keywords)
        weak = [] if matching_terms(query,topic.weak_exclusions) else matching_terms(query,topic.weak_keywords)
        if phrases or keywords or weak:
            # 반복 단어나 동의어 개수로 주제가 뒤집히지 않도록 최대값을 사용합니다.
            score = 18 if phrases else 10 if keywords else 3
            terms = list(dict.fromkeys(phrases + keywords)) or weak
            position,length = first_mention(query,terms)
            evidence.append(TopicEvidence(topic,score,terms,position,position + length))
    return evidence


def is_followup(question: str) -> bool:
    query = compact(question)
    if re.match(r'^(다른질문|다른얘기|다른업무|새질문|별개로|주제를바꿔|그건됐고)',query):
        return False
    return bool(re.match(r'^(그럼|그러면|그거|그것|그건|이거|이것|해당|위내용|누구|어디|관련담당자|담당자|문의할|추가로)',query)
                and re.search(r'어디|누구|담당|문의|연락|건의|제안|도입|구매도|해도|가능|신청|방법|절차',query))


def resolve_topics(question: str, topics: list[ContactTopic], history: list[dict] | None,
                   hints: ContactHints | None = None) -> list[TopicEvidence]:
    evidence = topic_evidence(question,topics)
    if not any(item.score >= 10 for item in evidence) and is_followup(question):
        for item in reversed(history or []):
            if item.get('role') != 'user':
                continue
            previous = topic_evidence(item.get('content',''),topics)
            if previous:
                evidence.extend(TopicEvidence(hit.topic,hit.score * 0.85,hit.terms,10**6,10**6) for hit in previous)
                break
            # 직전의 다른 주제를 건너뛰어 오래된 업무 맥락으로 돌아가지 않습니다.
            if not is_followup(item.get('content','')):
                break
    if not evidence:
        return []
    strongest = max(item.score for item in evidence)
    # '구매를 건의'처럼 대상 업무가 모호하면 계약 담당자로 단정하지 않습니다.
    if strongest <= 3 and re.search(r'건의|제안|도입|개선',question):
        return []
    # 검색된 규정 문서·선택된 업무 분야와 맞는 주제를 우선합니다(예: 복리후생 질문에 섞인 '구매계약').
    multiple = asks_multiple(compact(question),[item for item in evidence if item.score >= strongest * 0.75])
    if not multiple:
        evidence = [replace(item,score=item.score + CONTEXT_BONUS) if item.score >= 10 and context_matches(item.topic,hints) else item
                    for item in evidence]
    strongest = max(item.score for item in evidence)
    selected = [item for item in evidence if item.score >= strongest * 0.75]
    # 여러 업무를 함께 묻지 않았다면 질문의 중심 업무(가장 점수가 높고 먼저 언급된 주제) 하나만 사용합니다.
    if len(selected) > 1 and not multiple:
        selected = [max(selected,key=lambda item:(item.score,-item.position))]
    return selected


def department_scores(question, departments, topics, *, history=None, hints=None):
    query = compact(question)
    evidence = resolve_topics(question,topics,history,hints)
    department_tiers = {}
    for item in evidence:
        tiers = {}
        for department in departments:
            searchable = compact(department.dept_name + ' ' + (department.dept_function or ''))
            for tier,terms in enumerate([item.topic.department_terms,*item.topic.department_fallbacks]):
                if matching_terms(searchable,terms):
                    tiers[department.dept_id] = tier
                    break
        department_tiers[id(item.topic)] = tiers
    output = {}
    for department in departments:
        terms = []
        score = 0
        fallback = ''
        if matching_terms(query,[department.dept_name]):
            score = 24
            terms.append(department.dept_name)
        for item in evidence:
            tiers = department_tiers[id(item.topic)]
            if department.dept_id not in tiers:
                continue
            # 전담 복지부서가 없으면 실제 존재하는 급여/인사 부서 중 우선순위를 정합니다.
            candidate_score = item.score * (0.65 ** (tiers[department.dept_id] - min(tiers.values())))
            if candidate_score > score:
                # 전담 부서가 아닌 대체 부서로 연결된 경우 안내 문구에 그 사실을 밝힙니다.
                score,terms,fallback = candidate_score,list(item.terms),(item.topic.label or '해당 업무') if tiers[department.dept_id] > 0 else ''
            elif candidate_score == score:
                terms.extend(item.terms)
        # 새 전문 업무는 실제 부서 기능에서 찾되 구매 같은 일반 행동어를 중복 가산하지 않습니다.
        if not evidence:
            generic = {'업무','운영','관리','대응','개발','지원','처리','및','구매','계약','건의','제안'}
            generic.update(compact(term) for topic in topics for term in topic.weak_keywords)
            for term in re.split(r'[,·/\s]+',department.dept_function or ''):
                if len(term) >= 2 and compact(term) not in generic and matching_terms(query,[term]):
                    score = max(score,8)
                    terms.append(term)
        if score:
            output[department.dept_id] = (score,list(dict.fromkeys(terms)),department,fallback)
    return output


DEFAULT_LABEL = '__default__'


def default_scores(departments, groups):
    """주제를 판단하지 못한 질문도 최소 한 명은 안내하도록, 설정된 일반 문의 부서를 낮은 점수로 돌려줍니다."""
    for terms in groups:
        matched = [department for department in departments
                   if matching_terms(compact(department.dept_name + ' ' + (department.dept_function or '')),terms)]
        if matched:
            return {department.dept_id:(1,[],department,DEFAULT_LABEL) for department in matched}
    return {}


class ContactRecommender:
    def __init__(self, directory=None):
        self.directory = directory if directory is not None else EmployeeDirectoryRepository()

    def recommend(self, question: str, employee_id: str, history: list[dict] | None = None,
                  hints: ContactHints | None = None, use_default: bool = True) -> ContactEscalation:
        try:
            config = RoutingConfig.model_validate_json(settings.contact_routing_path.read_text(encoding='utf-8'))
            departments = self.directory.departments()
            scored = department_scores(question,departments,config.topics,history=history,hints=hints)
            if not scored and not use_default:
                return ContactEscalation()
            if not scored:
                scored = default_scores(departments,config.default_departments)
            if not scored:
                return ContactEscalation(status='not_found',message='질문과 연결되는 담당 업무를 찾지 못했습니다. 문의할 업무나 부서를 조금 더 구체적으로 알려주세요.')
            ordered = sorted(scored,key=lambda key:scored[key][0],reverse=True)
            candidates = self.directory.contact_candidates(ordered)
            ranking = []
            weights = {'PROCESSOR':3,'BACKUP':2,'MANAGER':1,'APPROVER':0.5,'EMPLOYEE':0}
            for candidate in candidates:
                profile = candidate['profile']
                if profile.employee_id == employee_id or not (profile.work_email or profile.extension_number):
                    continue
                role_score = max((weights.get(item['role_category'],0) for item in candidate['role_details']),default=0)
                score,terms,department,fallback = scored[profile.dept_id]
                ranking.append((score,role_score,profile.employee_id,candidate,terms,department,fallback))
            ranking.sort(key=lambda item:(-item[0],-item[1],item[2]))
            if ranking:
                # 주 담당 부서에 연락처가 없을 때만 관련 부서의 다음 우선순위를 사용합니다.
                ranking = [item for item in ranking if item[0] >= ranking[0][0] * 0.7]
                # 업무(주제)별로 묶어 부서가 겹치지 않게 고른 뒤, 주제를 번갈아 배치합니다.
                # 서로 다른 업무를 함께 물었다면 한 주제나 한 부서 직원만으로 후보를 채우지 않습니다.
                groups = {}
                for item in ranking:
                    groups.setdefault(tuple(item[4]),[]).append(item)
                ordered_groups = []
                for group in groups.values():
                    first_by_department,extras,seen = [],[],set()
                    for item in group:
                        dept_id = item[3]['profile'].dept_id
                        if dept_id in seen:
                            extras.append(item)
                        else:
                            first_by_department.append(item)
                            seen.add(dept_id)
                    ordered_groups.append(first_by_department + extras)
                ranking,picked = [],set()
                for position in range(max(len(group) for group in ordered_groups)):
                    for group in ordered_groups:
                        if position < len(group) and group[position][2] not in picked:
                            ranking.append(group[position])
                            picked.add(group[position][2])
            contacts = []
            for _,_,_,candidate,terms,department,fallback in ranking[:settings.contact_recommendation_limit]:
                profile = candidate['profile']
                role_text = ', '.join(profile.roles) or profile.job_title or '역할 정보 없음'
                duty = department.dept_function or ''
                contacts.append(ContactRecommendation(
                    employee=profile,matched_terms=terms,duty_description=duty,
                    reason=('질문과 정확히 맞는 담당 업무를 찾지 못해 일반 문의 창구로 안내합니다 · ' if fallback == DEFAULT_LABEL
                            else f'{fallback} 전담 부서가 없어 관련 업무 부서로 안내합니다 · ' if fallback else '')
                           + (f'문의 주제: {", ".join(terms)} · ' if terms else '') + f'{department.dept_name} 담당 업무: {duty or "업무 기능 미등록"} · 업무 역할: {role_text}',
                ))
            if not contacts:
                return ContactEscalation(status='not_found',message='관련 부서는 찾았지만 본인 이외에 안내 가능한 담당자 연락처가 등록되어 있지 않습니다.')
            return ContactEscalation(status='recommended',message='질문의 핵심 업무와 대화 맥락, 부서의 담당 업무를 기준으로 찾은 문의 후보입니다.',contacts=contacts)
        except (StorageUnavailable,OSError,ValueError,ValidationError):
            logger.warning('담당자 추천 데이터를 확인하지 못했습니다.',exc_info=True)
            return ContactEscalation(status='unavailable',message='담당자 정보를 조회하지 못했습니다. 잠시 후 다시 확인해주세요.')
