"""실제 Ollama·MCP·Chroma로 발표 흐름을 별도 DB에서 재현합니다. 외부 n8n 전송은 하지 않습니다."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]

QUESTIONS=[
    '현재 본사에서 부산으로 동일 지역 20박 21일 국내출장 중이야. 출장 기간은 2026년 10월 19일부터 11월 8일까지이고, 본사와 다른 시군이며 왕복 600km야. KTX 왕복 교통비는 10만원, 숙박은 20박에 1박 8만원이고, 식비 지급 대상은 21일이야. 회사 제공 숙소나 식사는 없어.',
    '출장이 끝나는 날과 비슷한 11월 9일에 배우자가 둘째 아이 한 명을 출산할 예정이야.',
    '출장을 마치면 바로 근무지로 복귀하지 않고 배우자 출산전후휴가를 사용하려고 해. 이렇게 해도 될까?',
    '이 경우 경조사 지원금은 얼마 받을 수 있어?',
    '그럼 경조사 휴가는 며칠 쓸 수 있어?',
    '그 휴가는 어떻게 신청해야 해?',
    '장기 출장으로 피로도 쌓였고 배우자 보필도 해야 해서, 경조사 휴가에 이어 남은 연차도 소진하려고 해. 연달아 사용할 수 있을까?',
    '내 잔여 연차는 며칠이야?',
    '아까 말한 20박 21일 국내출장의 대략적인 출장비도 계산해줘.',
    '그 출장비는 언제 지급돼?',
]


async def run(phase):
    from app.config import settings
    from app.agent.service import ChatService
    from app.mcp.client import MCPToolGateway
    from app.repositories.sqlite import SQLiteConversationRepository
    from app.integrations.sqlite import connection_scope
    from app.schemas import ChatRequest,EndRequest

    # 기존 원본 DB는 읽지 않고 테스트 원장 한 행만 독립 DB에 넣습니다.
    with connection_scope(write=True) as c:
        c.execute("INSERT OR IGNORE INTO employees(employee_id,name,created_at) VALUES(?,?,?)",('WON0002','이준호',datetime.now(timezone.utc).isoformat()))
        c.execute('INSERT INTO leave_balances(employee_id,balance_year,granted_days,used_days,updated_at) VALUES(?,?,?,?,?)',
                  ('WON0002',2026,23,8,datetime.now(timezone.utc).isoformat()))
    repository=SQLiteConversationRepository()
    gateway=MCPToolGateway()
    output={'phase':phase,'employee_id':'WON0002','assumptions':{'trip':'2026-10-19~2026-11-08 / 부산 / 20박21일','transport_krw':100000,'lodging_per_night_krw':80000,'child':'둘째 단태아','leave_granted':23,'leave_used':8},'steps':[]}
    output_path=settings.logs_dir/f'presentation-{phase}.json'
    def save():
        output_path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    async with gateway.connect():
        service=ChatService(repository,tools=gateway)
        call=service.ollama._chat
        async def traced_chat(*args, **kwargs):
            result=await call(*args, **kwargs)
            if kwargs.get('label') in {'후속 질문 맥락 정리','도구 선택(툴콜링)'}:
                with (settings.logs_dir/f'presentation-{phase}-routing.jsonl').open('a',encoding='utf-8') as f:
                    f.write(json.dumps({'stage':kwargs['label'],'output':result},ensure_ascii=False)+'\n')
            return result
        service.ollama._chat=traced_chat
        conversation=await service.start_conversation('WON0002')
        output['session_id']=str(conversation.id);save()
        for number,question in enumerate(QUESTIONS,1):
            started=asyncio.get_running_loop().time()
            try:
                response=await service.reply(repository.get(conversation.id,include_messages=False),ChatRequest(employee_id='WON0002',conversation_id=conversation.id,message=question))
                record={'number':number,'question':question,'seconds':round(asyncio.get_running_loop().time()-started,2),**response.model_dump(mode='json')}
                output['steps'].append(record);save()
                print(f"STEP {number} | {response.status} | {','.join(response.tools_used)} | {response.answer[:140]}",flush=True)
            except Exception as exc:
                output['steps'].append({'number':number,'question':question,'error':str(exc),'error_type':type(exc).__name__});save()
                print(f'STEP {number} | ERROR | {type(exc).__name__}: {exc}',flush=True)
        # 11번 종료 버튼은 UI에서 평가 창을 열 뿐, 12번 제출 전에는 닫지 않습니다.
        current=repository.get(conversation.id)
        output['steps'].append({'number':11,'action':'대화 종료 버튼: 평가 입력 전','session_status':current.status})
        ended=await service.end(current,EndRequest(rating='helpful',score=5,comment='발표 시나리오 로컬 검증'))
        output['steps'].append({'number':12,'action':'만족도 제출','result':ended.model_dump(mode='json')})
        restored=repository.get(conversation.id)
        output['final_state']={'status':restored.status,'message_count':len(restored.messages),'score':restored.end_result.score}
        save()
        await service.flush();await service.n8n.aclose()
    print('REPORT',output_path,flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',default='baseline')
    args=parser.parse_args()
    import re
    if not re.fullmatch(r'[a-z0-9-]{1,30}', args.phase):
        parser.error('phase는 영문 소문자, 숫자, 하이픈만 사용하세요.')
    target=ROOT/'logs'/f'presentation-{args.phase}.sqlite3'
    if target.exists():
        parser.error(f'기존 테스트 기록을 덮어쓰지 않습니다: {target}')
    os.environ.update(N8N_WEBHOOK_URL='',WARM_UP='false',OLLAMA_UNLOAD_ON_EXIT='false',
                      SQLITE_PATH=str(target),N8N_ASYNC='false')
    asyncio.run(run(args.phase))


if __name__=='__main__':main()
