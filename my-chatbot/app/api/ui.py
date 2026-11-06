"""WONIT v7 화면의 계약을 기존 서비스에 연결합니다. 모의 답변은 만들지 않습니다."""
import json
import re
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID
from typing import Literal

from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse,StreamingResponse
from pydantic import Field,ValidationError,field_validator
from starlette.concurrency import run_in_threadpool

from app.api import routes as core
from app.config import settings
from app.schemas import RequestModel,ChatRequest,EndRequest,ToolArguments
from app.repositories.conversation_list import list_conversations

router=APIRouter(prefix='/hr',tags=['ui'])
ALIASES={'work_leave_labor':'work_labor','contracts_finance':'contracts_finance',
         'ethics_audit':'audit_ethics','organization':'organization_management',
         'research_quality':'rnd_quality','travel':'travel_expenses',
         'welfare':'pay_benefits','payroll':'pay_benefits','leave':'work_labor'}


class EmployeeRequest(RequestModel):
    employee_id: str = Field(min_length=1,max_length=50)

    @field_validator('employee_id')
    @classmethod
    def canonical_id(cls, value):
        from app.identity import canonical_employee_id
        return canonical_employee_id(value)


class SessionRequest(EmployeeRequest):
    session_id: UUID


class QuestionRequest(EmployeeRequest):
    session_id: UUID | None = None
    question: str = Field(min_length=1,max_length=4000)
    category_id: str | None = None
    previous_request_id: UUID | None = None
    input_data: dict = Field(default_factory=dict)


class HistoryRequest(EmployeeRequest):
    search: str = Field(default='',max_length=100)


class ContactRequest(RequestModel):
    """HR 담당자 조회: 사번은 선택입니다(입력하면 본인을 후보에서 제외)."""
    employee_id: str = Field(default='',max_length=50)
    category_id: str = Field(default='hr_employment',max_length=80)

    @field_validator('employee_id')
    @classmethod
    def canonical_optional_id(cls, value):
        if not value or not value.strip():
            return ''
        from app.identity import canonical_employee_id
        return canonical_employee_id(value)


class FeedbackRequest(SessionRequest):
    request_id: UUID
    rating: int = Field(ge=1,le=5)
    error_type: Literal['','incorrect_answer','wrong_source','calculation_error','technical_error'] = ''
    comment: str = Field(default='',max_length=1000)
    submitted_at: str | None = None


async def require_employee(employee_id):
    profile=await run_in_threadpool(core.service.users.get,employee_id)
    if profile is None:
        raise HTTPException(404,'등록된 사원번호를 확인해주세요.')
    return profile


async def owned_session(data):
    item=await core.get_conversation(data.session_id)
    if item.employee_id!=data.employee_id:
        raise HTTPException(403,'현재 사번의 대화만 조회할 수 있습니다.')
    return item


def person(profile,reason=''):
    return {**profile.model_dump(mode='json'),'position':profile.job_title,
            'extension':profile.extension_number,'email':profile.work_email,'duty':reason or ', '.join(profile.roles)}


def source_items(sources):
    return [{**source.model_dump(mode='json'),'article':source.section,
             'url':f'/api/hr/source/{source.chunk_id.split(":")[0]}'+(f'#page={source.page}' if source.page else '') if source.chunk_id else None}
            for source in sources]


def ui_result(response,question,employee_id):
    escalation=response.contact_escalation
    return dict(request_id=str(response.message_id),session_id=str(response.conversation_id),employee_id=employee_id,
        question=question,answer=response.answer,status='needs_info' if response.status=='needs_input' else response.status,
        sources=source_items(response.sources),sections=[],calculation=None,
        contact=[person(item.employee,item.reason) for item in escalation.contacts],
        contact_notice=escalation.message,created_at=datetime.now(timezone.utc).isoformat(),
        steps=[item.model_dump(mode='json') for item in response.steps],
        context=response.context.model_dump(mode='json'),tool_results=[item.model_dump(mode='json') for item in response.tool_results],
        webhook_events=[item.model_dump(mode='json') for item in response.webhook_events])


def chat_request(data):
    try:
        return validated_chat_request(data)
    except (ValidationError,TypeError) as exc:
        raise HTTPException(422,'입력한 계산 값의 형식과 범위를 확인해주세요.') from exc


def validated_chat_request(data):
    fields=dict(data.input_data)
    message=data.question
    task=fields.pop('task',None)
    arguments=None
    category=ALIASES.get(data.category_id,data.category_id)
    if task=='leave_period':
        requested=fields.get('requested_days')
        message+=f"\n사용 기간: {fields.get('start_date','')} ~ {fields.get('end_date','')}. "
        if requested is not None:
            arguments=ToolArguments(requested_days=requested)
            message+=f'{requested}일 사용하면 남은 연차를 알려주세요.'
        else:
            message+='공휴일·개인 근무일을 반영한 실제 차감일수는 아직 확인하지 못했습니다.'
        category='work_labor'
    elif task=='travel_estimate':
        arguments=ToolArguments(trip=fields)
        message+='\n출장 입력: '+json.dumps(fields,ensure_ascii=False)
        category='travel_expenses'
    elif fields:
        # 후속 입력은 사용자 데이터로만 전달하며 Tool 인자나 프로필을 덮어쓰지 않습니다.
        message+='\n추가 정보: '+json.dumps(fields,ensure_ascii=False)
    if len(message)>4000:
        raise HTTPException(422,'질문과 입력 정보가 너무 깁니다.')
    return ChatRequest(employee_id=data.employee_id,message=message,conversation_id=data.session_id,
                       tool_id=category,arguments=arguments)


@router.post('/employee')
async def employee(data: EmployeeRequest):
    return {'found':True,'employee':person(await require_employee(data.employee_id))}


@router.post('/question')
async def question(data: QuestionRequest):
    await require_employee(data.employee_id)
    request=chat_request(data)
    response=await core.chat(request)
    return ui_result(response,data.question,data.employee_id)


@router.post('/question/stream')
async def question_stream(data: QuestionRequest):
    await require_employee(data.employee_id)
    # 기존 SSE 경로가 세션·종료·도구 검증과 연결 중단 후 저장까지 담당합니다.
    stream=await core.chat_stream(chat_request(data))
    async def events():
        async for block in stream.body_iterator:
            if isinstance(block,bytes):
                block=block.decode('utf-8')
            event_line,payload_line,*_=block.split('\n')
            event=event_line.removeprefix('event: ')
            payload=json.loads(payload_line.removeprefix('data: '))
            if event=='final':
                from app.schemas import ChatResponse
                payload=ui_result(ChatResponse.model_validate(payload),data.question,data.employee_id)
            elif event=='delta':
                payload={'text':payload if isinstance(payload,str) else payload.get('text',''),'replace':True}
            elif event=='status':
                payload={'text':payload if isinstance(payload,str) else str(payload)}
            elif event=='error':
                payload={**payload,'error':payload.get('detail','답변 처리 오류')}
            yield f'event: {event}\ndata: {json.dumps(payload,ensure_ascii=False)}\n\n'
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@router.post('/history')
async def history(data: HistoryRequest):
    await require_employee(data.employee_id)
    return {'conversations':await run_in_threadpool(list_conversations,core.repository,data.employee_id,data.search)}


@router.post('/conversation')
async def conversation(data: SessionRequest):
    item=await owned_session(data)
    turns=[]
    for q,a in zip(item.messages,item.messages[1:]):
        if q.role!='user' or a.role!='assistant':
            continue
        turns.append(dict(request_id=str(a.id),session_id=str(item.id),employee_id=item.employee_id,
            question=q.content,answer=a.content,status='needs_info' if a.processing_status=='needs_input' else a.processing_status,
            sources=source_items(a.sources),contact=[person(p.employee,p.reason) for p in a.contact_escalation.contacts],
            created_at=a.created_at.isoformat(),rating=item.end_result.score if item.end_result and a==item.messages[-1] else None))
    return {'conversation':{'session_id':str(item.id),'status':item.status,'title':turns[0]['question'][:70] if turns else '새 대화',
                             'end_result':item.end_result.model_dump(mode='json') if item.end_result else None},'turns':turns}


@router.post('/contact')
async def contacts(data: ContactRequest):
    if data.employee_id:
        await require_employee(data.employee_id)
    topics={'leave':'연차 근태','travel':'출장 여비','welfare':'복리후생','payroll':'급여 연봉','hr_employment':'인사 채용','other':'인사'}
    result=await run_in_threadpool(core.service.contacts.recommend,topics.get(data.category_id,data.category_id),data.employee_id)
    return {'contacts':[person(p.employee,p.reason) for p in result.contacts],'message':result.message}


@router.post('/feedback')
async def feedback(data: FeedbackRequest):
    item=await owned_session(data)
    index=next((i for i,message in enumerate(item.messages) if message.role=='assistant' and message.id==data.request_id),None)
    if index is None:
        raise HTTPException(404,'평가할 답변이 이 대화에 없습니다.')
    request=EndRequest(rating='helpful' if data.rating>=4 else 'neutral' if data.rating==3 else 'unhelpful',
                      score=data.rating,error_type=data.error_type,comment=data.comment,
                      message_id=item.messages[index-1].id if index else None)
    result=await core.service.end(item,request)
    return {'success':True,**result.model_dump(mode='json')}


@router.post('/retry')
async def retry(data: SessionRequest):
    await owned_session(data)
    return (await core.service.deliver_end_event(data.session_id)).model_dump(mode='json')


@router.get('/source/{document_id}')
async def source_pdf(document_id: str):
    if not re.fullmatch(r'[a-f0-9]{24}',document_id):
        raise HTTPException(404,'문서를 찾을 수 없습니다.')
    # 검색 DB의 ID를 원본 목록과 대조하며 요청 경로를 직접 파일명으로 사용하지 않습니다.
    root=settings.chroma_dir.parent
    manifest=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    record=next((item for item in manifest.get('documents',[]) if item.get('document_id')==document_id),None)
    if record is None:
        raise HTTPException(404,'등록된 문서를 찾을 수 없습니다.')
    relative=Path(record['source'])
    for base in (root/'input_pdfs',root.parent/'WONIT_Electronics_59'):
        candidate=(base/relative).resolve()
        if candidate.is_relative_to(base.resolve()) and candidate.is_file() and candidate.suffix.lower()=='.pdf':
            return FileResponse(candidate,media_type='application/pdf',headers={'X-Content-Type-Options':'nosniff'})
    raise HTTPException(404,'원본 PDF 파일을 찾을 수 없습니다.')
