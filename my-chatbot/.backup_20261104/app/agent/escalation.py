"""규정 답변이 부족할 때 실제 DB의 관련 업무 담당자 후보를 안내합니다."""

import logging
import re
from dataclasses import dataclass
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


class RoutingConfig(BaseModel):
    topics: list[ContactTopic]


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
class TopicEvidence:
    topic: ContactTopic
    score: float
    terms: list[str]


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
            evidence.append(TopicEvidence(topic,score,list(dict.fromkeys(phrases + keywords)) or weak))
    return evidence


def is_followup(question: str) -> bool:
    query = compact(question)
    if re.match(r'^(다른질문|다른얘기|다른업무|새질문|별개로|주제를바꿔|그건됐고)',query):
        return False
    return bool(re.match(r'^(그럼|그러면|그거|그것|그건|이거|이것|해당|위내용|누구|어디|관련담당자|담당자|문의할|추가로)',query)
                and re.search(r'어디|누구|담당|문의|연락|건의|제안|도입|구매도|해도|가능|신청|방법|절차',query))


def resolve_topics(question: str, topics: list[ContactTopic], history: list[dict] | None) -> list[TopicEvidence]:
    evidence = topic_evidence(question,topics)
    if not any(item.score >= 10 for item in evidence) and is_followup(question):
        for item in reversed(history or []):
            if item.get('role') != 'user':
                continue
            previous = topic_evidence(item.get('content',''),topics)
            if previous:
                evidence.extend(TopicEvidence(hit.topic,hit.score * 0.85,hit.terms) for hit in previous)
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
    return [item for item in evidence if item.score >= strongest * 0.75]


def department_scores(question, departments, topics, *, history=None):
    query = compact(question)
    evidence = resolve_topics(question,topics,history)
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
                score,terms = candidate_score,list(item.terms)
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
            output[department.dept_id] = (score,list(dict.fromkeys(terms)),department)
    return output


class ContactRecommender:
    def __init__(self, directory=None):
        self.directory = directory if directory is not None else EmployeeDirectoryRepository()

    def recommend(self, question: str, employee_id: str, history: list[dict] | None = None) -> ContactEscalation:
        try:
            config = RoutingConfig.model_validate_json(settings.contact_routing_path.read_text(encoding='utf-8'))
            departments = self.directory.departments()
            scored = department_scores(question,departments,config.topics,history=history)
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
                score,terms,department = scored[profile.dept_id]
                ranking.append((score,role_score,profile.employee_id,candidate,terms,department))
            ranking.sort(key=lambda item:(-item[0],-item[1],item[2]))
            if ranking:
                # 주 담당 부서에 연락처가 없을 때만 관련 부서의 다음 우선순위를 사용합니다.
                ranking = [item for item in ranking if item[0] >= ranking[0][0] * 0.7]
                # 서로 다른 업무를 함께 물었다면 한 부서 직원만으로 후보를 채우지 않습니다.
                first_by_department,extras,seen = [],[],set()
                for item in ranking:
                    dept_id = item[3]['profile'].dept_id
                    if dept_id in seen:
                        extras.append(item)
                    else:
                        first_by_department.append(item)
                        seen.add(dept_id)
                ranking = first_by_department + extras
            contacts = []
            for _,_,_,candidate,terms,department in ranking[:settings.contact_recommendation_limit]:
                profile = candidate['profile']
                role_text = ', '.join(profile.roles) or profile.job_title or '역할 정보 없음'
                duty = department.dept_function or ''
                contacts.append(ContactRecommendation(
                    employee=profile,matched_terms=terms,duty_description=duty,
                    reason=f'문의 주제: {", ".join(terms)} · {department.dept_name} 담당 업무: {duty or "업무 기능 미등록"} · 업무 역할: {role_text}',
                ))
            if not contacts:
                return ContactEscalation(status='not_found',message='관련 부서는 찾았지만 본인 이외에 안내 가능한 담당자 연락처가 등록되어 있지 않습니다.')
            return ContactEscalation(status='recommended',message='질문의 핵심 업무와 대화 맥락, 부서의 담당 업무를 기준으로 찾은 문의 후보입니다.',contacts=contacts)
        except (StorageUnavailable,OSError,ValueError,ValidationError):
            logger.warning('담당자 추천 데이터를 확인하지 못했습니다.',exc_info=True)
            return ContactEscalation(status='unavailable',message='담당자 정보를 조회하지 못했습니다. 잠시 후 다시 확인해주세요.')
