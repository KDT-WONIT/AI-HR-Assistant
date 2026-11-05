"""제공받은 Tool의 순수 로직을 현재 프로필·대화·규정 DB에 연결합니다."""
import json
import re
from functools import lru_cache
from pathlib import Path

from app.config import settings
from app.rag.vector_store import get_collection
from app.repositories.factory import create_repository
from app.vendor.employee_tools.common import EmployeeContext
from app.vendor.employee_tools.inquiry_history_tool import search_inquiry_history
from app.vendor.employee_tools.travel_expense_tool import calculate_travel_expense,GRADES


def history_question(question):
    return bool(re.search(r'(이전|지난|과거|예전|최근|내).*(문의|질문|대화).*(이력|기록|내역|검색|찾|보여)|'
                          r'(문의|질문|대화)\s*(이력|기록|내역)',question))


def inquiry_history(request,arguments):
    context=EmployeeContext(request.employee_id,request.user_profile.model_dump(mode='json') if request.user_profile else {},create_repository())
    return search_inquiry_history(arguments.history_query or '',arguments.history_limit,context=context)


@lru_cache(maxsize=8)
def travel_policy_matches(directory,collection_name):
    """고정 계산 요율과 현재 규정 DB가 같은 원본 PDF인지 확인합니다."""
    basis=json.loads((Path(__file__).resolve().parents[1]/'vendor'/'employee_tools'/'policy_basis.json').read_text(encoding='utf-8'))
    evidence=basis['evidence']
    collection=get_collection(directory,collection_name)
    records=collection.get(ids=[item['chunk_id'] for item in evidence],include=['metadatas'])
    actual={identifier:meta for identifier,meta in zip(records['ids'],records['metadatas'])}
    return all(actual.get(item['chunk_id'],{}).get('source_sha256')==item['source_sha256'] for item in evidence)


DEFAULT_TRAVEL_GRADE='grade_3'
JOB_TITLE_GRADES=(('대표','executive'),('임원','executive'),('이사','executive'),('부장','grade_1'),('차장','grade_2'),
                  ('과장','grade_2'),('대리','grade_3'),('주임','grade_4_plus'),('사원','grade_4_plus'))


def resolve_travel_grade(profile,mapping):
    """직급 문자열이 매핑에 없어도 여비 등급을 정합니다. 반환: (등급, 가정 설명 또는 None)."""
    grade=(profile.grade if profile else None) or ''
    if isinstance(mapping,dict) and mapping.get(grade) in GRADES:
        return mapping[grade],None
    base=re.sub(r'\s*\(.*?\)\s*','',grade)
    if isinstance(mapping,dict) and mapping.get(base) in GRADES:
        return mapping[base],f'직급 "{grade}"은 "{base}" 기준의 여비 등급({mapping[base]})으로 적용했습니다.'
    number=re.search(r'(\d+)\s*직급',grade)
    if number:
        value=int(number.group(1))
        chosen='grade_4_plus' if value>=4 else f'grade_{max(value,1)}'
        return chosen,f'직급 "{grade}"에 등록된 여비 등급이 없어 {chosen}으로 가정했습니다.'
    title=(profile.job_title if profile else None) or ''
    for word,chosen in JOB_TITLE_GRADES:
        if word in title:
            return chosen,f'직급 정보가 없어 직책 "{title}"을 기준으로 여비 등급을 {chosen}으로 가정했습니다.'
    return DEFAULT_TRAVEL_GRADE,f'직급 정보가 없어 일반 직원 등급({DEFAULT_TRAVEL_GRADE})으로 가정했습니다.'


def travel_expense(request,arguments):
    if arguments.trip is None:
        return {'status':'error','error':{'message':'예상 여비 계산에는 출발일·복귀일·목적지와 국내/국외 구분이 필요합니다. 국내 출장은 왕복 거리·동일 시군 여부, 국외는 숙박 밤 수·식비 일수도 알려주세요.'}}
    try:
        mapping=json.loads(settings.travel_grade_mapping_path.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        mapping={}
    grade,grade_note=resolve_travel_grade(request.user_profile,mapping)
    if not travel_policy_matches(str(settings.chroma_dir),settings.chroma_collection):
        return {'status':'needs_review','message':'현재 규정 DB와 여비 계산 기준의 원본이 달라 요율 검토가 필요합니다.'}
    profile=request.user_profile.model_dump(mode='json') if request.user_profile else {}
    profile['travel_grade']=grade
    result=calculate_travel_expense(arguments.trip,context=EmployeeContext(request.employee_id,profile,None))
    if grade_note and isinstance(result,dict):
        result['assumptions']=[*result.get('assumptions',[]),grade_note]
    return result
