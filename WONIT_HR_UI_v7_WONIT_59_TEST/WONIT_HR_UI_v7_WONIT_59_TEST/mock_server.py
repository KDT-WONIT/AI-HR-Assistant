"""WONIT HR UI v7 — 채팅방별 이력 + 전처리 PDF 열람 통합 테스트 전용 가상 API 서버.

Python 표준 라이브러리만 사용합니다. 외부 직원 DB, 실제 기업 규정, LLM과 연결하지 않습니다.
웹 화면과 API를 동일한 127.0.0.1 포트에서 제공하므로 CORS 설정이 필요 없습니다.
운영환경에서 실행하거나 공개 포트/Cloudflare 터널에 노출하지 마세요.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'test_storage'
CONVERSATIONS_FILE = DATA_DIR / 'conversations.json'
LEGACY_HISTORY_FILE = DATA_DIR / 'history.json'
KST = timezone(timedelta(hours=9))

# 100% 가상 테스트 데이터 — 실제 조직/직원/규정의 확정 내용이 아닙니다.
EMPLOYEES = {
    'W-1001': {'employee_id': 'W-1001', 'name': '김민수', 'department': '생산기술팀', 'position': '사원', 'granted': 15, 'used': 6},
    'W-1002': {'employee_id': 'W-1002', 'name': '이지은', 'department': '경영지원팀', 'position': '대리', 'granted': 18, 'used': 8},
    'W-1003': {'employee_id': 'W-1003', 'name': '박준호', 'department': '품질관리팀', 'position': '과장', 'granted': 16, 'used': 4},
}
CONTACTS = {
    'leave': {'name': '박지현', 'department': '인사팀', 'position': '대리', 'duty': '휴가·근태', 'extension': '1234', 'email': 'hr-leave@example.test', 'image_url': '/assets/mock-hr-avatar.svg'},
    'travel': {'name': '김서연', 'department': '경영지원팀', 'position': '과장', 'duty': '출장·여비', 'extension': '1240', 'email': 'travel@example.test', 'image_url': '/assets/mock-hr-avatar.svg'},
    'welfare': {'name': '정우성', 'department': '인사팀', 'position': '대리', 'duty': '복리후생', 'extension': '1236', 'email': 'welfare@example.test', 'image_url': '/assets/mock-hr-avatar.svg'},
    'payroll': {'name': '조하늘', 'department': '급여팀', 'position': '과장', 'duty': '급여·수당', 'extension': '1260', 'email': 'payroll@example.test', 'image_url': '/assets/mock-hr-avatar.svg'},
    'hr_employment': {'name': '박지현', 'department': '인사팀', 'position': '대리', 'duty': '인사·고용', 'extension': '1234', 'email': 'hr-leave@example.test', 'image_url': '/assets/mock-hr-avatar.svg'},
    'other': {'name': '박지현', 'department': '인사팀', 'position': '대리', 'duty': '사내 인사 문의', 'extension': '1234', 'email': 'hr-leave@example.test', 'image_url': '/assets/mock-hr-avatar.svg'},
}
# '규정 출처'는 테스트용 예시 이름입니다. 실제 PDF의 특정 조항/페이지를 의미하지 않습니다.
LEAVE_SOURCE = {'document': '[테스트] 휴가·근무규정 (가상)', 'article': '테스트 근무일 계산 기준', 'version': 'MOCK-ONLY', 'source_id': 'TEST-LEAVE'}
TRAVEL_SOURCE = {'document': '[테스트] 출장·여비규정 (가상)', 'article': '테스트 일비·숙박비 가정', 'version': 'MOCK-ONLY', 'source_id': 'TEST-TRAVEL'}


def now_string():
    return datetime.now(KST).isoformat(timespec='seconds')


def safe_num(v, default=0):
    try:
        n = int(v)
        return n if 0 <= n <= 100000000 else default
    except (ValueError, TypeError):
        return default


def get_days(start, end):
    a = date.fromisoformat(str(start))
    b = date.fromisoformat(str(end))
    if b < a or (b-a).days > 365:
        raise ValueError('시작일/종료일을 확인해 주세요. (최대 365일)')
    days = [(a + timedelta(days=i)) for i in range((b-a).days+1)]
    return days


def contact_for_question(text, category=None):
    q = text or ''
    if '출장' in q or '여비' in q or category == 'travel':
        return CONTACTS['travel']
    if '급여' in q or '연봉' in q or '수당' in q:
        return CONTACTS['payroll']
    if '복리' in q or '학자금' in q or '사택' in q:
        return CONTACTS['welfare']
    return CONTACTS['leave']


class MockStore:
    """One persisted conversation object per session_id; each object owns an ordered turns array."""
    def __init__(self, persist=True):
        self.lock = threading.RLock()
        self.persist = persist
        self.sessions = {}
        self.conversations = {}
        if persist:
            DATA_DIR.mkdir(exist_ok=True)
            try:
                if CONVERSATIONS_FILE.is_file():
                    raw=json.loads(CONVERSATIONS_FILE.read_text(encoding='utf-8'))
                    rows=raw.get('conversations', []) if isinstance(raw,dict) else raw
                    for row in rows:
                        if isinstance(row,dict) and row.get('session_id'):
                            self.conversations[row['session_id']]=row
                elif LEGACY_HISTORY_FILE.is_file():
                    # v5 저장 파일이 있으면 첫 실행 때 같은 session_id로 묶어서 마이그레이션.
                    rows=json.loads(LEGACY_HISTORY_FILE.read_text(encoding='utf-8'))
                    for r in rows:
                        sid=r.get('session_id') or 'legacy-'+str(r.get('request_id') or uuid.uuid4().hex)
                        cv=self.conversations.setdefault(sid,{'session_id':sid,'employee_id':r.get('employee_id'),
                            'title':r.get('question','새 대화')[:65], 'category_id':r.get('category_id'),
                            'created_at':r.get('created_at') or now_string(),'updated_at':r.get('created_at') or now_string(), 'turns':[]})
                        cv['turns'].append(r)
                        cv['updated_at']=r.get('created_at') or now_string()
                    self.save()
            except (OSError,ValueError,TypeError) as e:
                print('[경고] 테스트 기록 로딩 실패:',e,flush=True)

    def save(self):
        if not self.persist: return
        DATA_DIR.mkdir(exist_ok=True)
        temp=CONVERSATIONS_FILE.with_suffix('.json.tmp')
        rows=list(self.conversations.values())
        temp.write_text(json.dumps({'schema_version':2,'conversations':rows},ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(CONVERSATIONS_FILE)

    def reset(self):
        with self.lock:
            self.conversations={}
            self.sessions={}
            self.save()

    def employee(self, eid):
        with self.lock:
            p = EMPLOYEES.get(str(eid).strip().upper())
            if not p:
                return {'found': False, 'employee': None, 'message': '등록된 테스트 사번이 아닙니다.'}
            return {'found': True, 'employee': {k: p[k] for k in ('employee_id', 'name', 'department', 'position')}}

    def get_session(self, sid, eid):
        if not sid or not isinstance(sid,str) or len(sid)>200:
            sid='session-'+uuid.uuid4().hex
        saved=self.conversations.get(sid)
        if saved and saved['employee_id'] != eid:
            raise PermissionError('다른 사번의 대화에 접근할 수 없습니다.')
        session=self.sessions.get(sid)
        if session and session['employee_id'] != eid:
            raise PermissionError('다른 사번의 대화 세션에는 접근할 수 없습니다.')
        if not session:
            session={'employee_id':eid,'intent':None,'remaining':None,'pending_kind':None,'requests':[],'planned_leave_days':None}
            if saved and saved.get('turns'):
                last=saved['turns'][-1]
                session['intent']=last.get('test_intent')
                session['remaining']=last.get('test_remaining')
                session['pending_kind']=last.get('test_pending_kind')
                session['planned_leave_days']=last.get('test_planned_leave_days')
                session['requests']=[t.get('request_id') for t in saved['turns'] if t.get('request_id')]
            self.sessions[sid]=session
        return sid,session

    def get_conversations(self, payload):
        eid=str(payload.get('employee_id') or '').strip().upper()
        if eid not in EMPLOYEES: raise PermissionError('미등록 테스트 사번입니다.')
        search=str(payload.get('search') or '').strip().casefold()
        with self.lock:
            rows=[]
            for cv in self.conversations.values():
                if cv.get('employee_id') != eid:continue
                turns=cv.get('turns') or []
                if not turns:continue
                hay=' '.join(str(t.get('question',''))+' '+str(t.get('answer','')) for t in turns).casefold()
                if search and search not in hay and search not in str(cv.get('title','')).casefold():continue
                last=turns[-1]
                rows.append({'session_id':cv['session_id'],'title':cv.get('title','새 대화'),
                    'category_id':cv.get('category_id'),'created_at':cv.get('created_at'),
                    'updated_at':cv.get('updated_at'),'turn_count':len(turns),
                    'message_count':len(turns)*2,'preview':last.get('answer','')[:100],
                    'last_status':last.get('status'), 'last_request_id':last.get('request_id')})
            rows.sort(key=lambda x:x['updated_at'] or '',reverse=True)
            return {'conversations':rows,'total':len(rows)}

    def get_conversation(self, payload):
        eid=str(payload.get('employee_id') or '').strip().upper()
        sid=str(payload.get('session_id') or '').strip()
        if eid not in EMPLOYEES:raise PermissionError('미등록 테스트 사번입니다.')
        with self.lock:
            cv=self.conversations.get(sid)
            if not cv:raise ValueError('해당 채팅을 찾을 수 없습니다.')
            if cv.get('employee_id')!=eid:raise PermissionError('다른 사번의 채팅을 열 수 없습니다.')
            turns=cv.get('turns') or []
            summary={'session_id':cv['session_id'],'title':cv['title'],'category_id':cv.get('category_id'),
                     'created_at':cv['created_at'],'updated_at':cv['updated_at'], 'turn_count':len(turns)}
            return {'conversation':summary,'turns':turns}

    def answer(self, payload):
        eid = str(payload.get('employee_id') or '').strip().upper()
        q = str(payload.get('question') or '').strip()[:1000]
        if eid not in EMPLOYEES:
            raise PermissionError('먼저 유효한 테스트 사번을 입력해 주세요.')
        if not q:
            raise ValueError('질문을 입력해 주세요.')
        if '오류 테스트' in q:
            raise RuntimeError('의도적으로 발생시킨 테스트 서버 오류입니다.')
        raw_data = payload.get('input_data') or {}
        inp = raw_data if isinstance(raw_data, dict) else {}
        with self.lock:
            sid, s = self.get_session(payload.get('session_id'), eid)
            p = EMPLOYEES[eid]
            basic_remaining = p['granted'] - p['used']
            request_id = 'T-' + uuid.uuid4().hex[:8].upper()
            res = {'request_id': request_id, 'session_id': sid, 'question': q,
                   'employee_id': eid, 'employee': {k:p[k] for k in ('employee_id','name','department','position')},
                   'status': 'answered', 'answer': '', 'sources': [], 'sections': [],
                   'calculation': None, 'contact': None, 'follow_up': None}
            task = str(inp.get('task') or '')
            # follow_up에 전송된 입력은 원래 질문의 상태와 연결합니다.
            if not task and inp:
                if s['pending_kind'] == 'leave_period':
                    task = 'leave_period'
                elif s['pending_kind'] == 'travel_estimate':
                    task = 'travel_estimate'

            travel_words = any(x in q for x in ('출장', '여비', '숙박비', '교통비'))
            leave_words = any(x in q for x in ('연차','휴가','휴직','쉬면','차감'))
            composite = travel_words and leave_words
            pending_date = ('월요일' in q or '수요일' in q or '언제' in q or '기간' in q or '며칠 차감' in q)
            is_special = ('특별휴가' in q or '규정에 없는' in q or '확인이 어려운' in q or '담당자' in q)
            has_leavelike = '연차' in q or '휴가' in q or '쉬면' in q
            leave_amount = re.search(r'([0-9]{1,3})\s*일\s*(?:더\s*)?(?:사용|쓰|차감|빼)', q)
            if not leave_amount:
                leave_amount = re.search(r'([0-9]{1,3})\s*일\s*더', q)

            if task == 'leave_period':
                start = inp.get('start_date')
                end = inp.get('end_date')
                if not start or not end:
                    res['status'] = 'needs_info'
                    res['answer'] = '휴가 계산을 위해 시작일과 종료일을 입력해 주세요.'
                    res['follow_up'] = {'fields': [
                        {'key':'start_date','label':'휴가 시작일','type':'date'},
                        {'key':'end_date','label':'휴가 종료일','type':'date'}]}
                    s['pending_kind'] = 'leave_period'
                else:
                    days = get_days(start,end)
                    weekdays = sum(d.weekday()<5 for d in days)
                    weekends = len(days)-weekdays
                    before = s['remaining'] if s['remaining'] is not None else basic_remaining
                    after = before-weekdays
                    res['answer'] = f'{p["name"]} 님, {start}부터 {end}까지의 테스트용 휴가 차감일은 {weekdays}일이며 예상 잔여 연차는 {after}일입니다.'
                    res['calculation'] = {'title':'휴가 기간 계산 · 가상 규칙', 'items': [
                        {'label':'조회 전 잔여 연차','value':f'{before}일'},
                        {'label':'전체 날짜','value':f'{len(days)}일'},
                        {'label':'토·일 제외','value':f'{weekends}일'},
                        {'label':'예상 차감','value':f'{weekdays}일'},
                        {'label':'예상 잔여 연차','value':f'{after}일'}],
                        'note':'테스트 계산: 토·일만 제외합니다. 공휴일·교대제·실제 규정은 적용되지 않습니다. 실제 잔여량은 변경되지 않습니다.'}
                    res['sources'] = [LEAVE_SOURCE]
                    s['remaining'] = after
                    s['planned_leave_days'] = basic_remaining-after
                    s['intent'] = 'leave_balance'
                    s['pending_kind'] = None

            elif task == 'travel_estimate':
                start,end = inp.get('start_date'),inp.get('end_date')
                dest = str(inp.get('destination') or '').strip()
                transport = str(inp.get('transport') or '').strip()
                if not (start and end and dest and transport):
                    res['status'] = 'needs_info'
                    res['answer'] = '출장비 테스트 계산에 필요한 출장지·기간·교통수단을 입력해 주세요.'
                    res['follow_up'] = {'fields': [
                        {'key':'destination','label':'출장지','type':'text'},
                        {'key':'start_date','label':'출장 시작일','type':'date'},
                        {'key':'end_date','label':'출장 종료일','type':'date'},
                        {'key':'transport','label':'교통수단','type':'select','options':['철도','버스','자가용','항공']},
                        {'key':'transport_fare_won','label':'교통비 예상 금액 (미입력 시 100000원)','type':'number','required':False}]}
                    s['pending_kind'] = 'travel_estimate'
                else:
                    days = get_days(start,end)
                    total_days = len(days)
                    nights = max(0,total_days-1)
                    perdiem = 30000 * total_days
                    lodging = 80000 * nights
                    fare = safe_num(inp.get('transport_fare_won'),100000) if inp.get('transport_fare_won') not in (None,'') else 100000
                    total = perdiem+lodging+fare
                    res['answer'] = f'{p["name"]} 님의 {dest} 출장({nights}박 {total_days}일) 예상 여비는 가상 기준으로 {total:,}원입니다.'
                    res['sources'] = [TRAVEL_SOURCE]
                    res['calculation'] = {'title':'출장비 예상 · 가상 기준', 'items': [
                        {'label':'출장일수','value':f'{total_days}일'},
                        {'label':'숙박일수','value':f'{nights}박'},
                        {'label':'일비 (30,000원 × 일수)','value':f'{perdiem:,}원'},
                        {'label':'숙박비 (80,000원 × 박수)','value':f'{lodging:,}원'},
                        {'label':'교통비 (입력액 또는 가상 100,000원)','value':f'{fare:,}원'},
                        {'label':'예상 합계','value':f'{total:,}원'}],
                        'note':'모든 단가는 테스트용 가상 값입니다. 실제 회사 규정/직급/영수증/식비·공휴일을 반영하지 않습니다.'}
                    s['intent'] = 'travel_estimate'
                    s['pending_kind'] = None

            elif composite:
                res['status'] = 'needs_review'
                res['answer'] = '출장과 휴가를 함께 묻는 복합 질문입니다. 테스트용 분류 결과를 항목별로 표시합니다. 실제 승인·지급 가능 여부는 판단하지 않습니다.'
                res['sections'] = [
                    {'title':'① 휴가 사용 조건', 'body':'휴가 규정 검토 및 승인 여부 확인이 필요합니다.', 'source_ids':['TEST-LEAVE']},
                    {'title':'② 출장 인정 기간', 'body':'휴가일의 출장 인정 여부는 담당자 확인이 필요합니다.', 'source_ids':['TEST-TRAVEL']},
                    {'title':'③ 숙박비 지급', 'body':'출장 일정·증빙 및 규정 확인이 필요한 항목입니다.', 'source_ids':['TEST-TRAVEL']}]
                res['sources'] = [LEAVE_SOURCE, TRAVEL_SOURCE]
                res['contact'] = CONTACTS['travel']
                s['intent'] = 'composite'
                s['pending_kind'] = None

            elif is_special:
                res['status'] = 'needs_review'
                res['answer'] = '현재 테스트 서버는 실제 특별휴가 승인 여부를 판단하지 않습니다. 담당자에게 확인할 수 있도록 연락처를 안내합니다.'
                res['contact'] = contact_for_question(q, payload.get('category_id'))
                s['intent'] = 'contact'
                s['pending_kind'] = None

            elif travel_words:
                res['status'] = 'needs_info'
                res['answer'] = '출장 여비 계산을 위해 출장지, 정확한 날짜, 교통수단을 알려주세요. 아래 입력창으로 이어서 질문할 수 있습니다.'
                res['follow_up'] = {'fields': [
                    {'key':'destination','label':'출장지','type':'text'},
                    {'key':'start_date','label':'출장 시작일','type':'date'},
                    {'key':'end_date','label':'출장 종료일','type':'date'},
                    {'key':'transport','label':'교통수단','type':'select','options':['철도','버스','자가용','항공']},
                    {'key':'transport_fare_won','label':'교통비 예상 금액 (미입력 시 100000원)','type':'number','required':False}]}
                s['intent'] = 'travel_estimate'
                s['pending_kind'] = 'travel_estimate'

            elif leave_words and (pending_date or ('월요일' in q and '수요일' in q)):
                res['status'] = 'needs_info'
                res['answer'] = '정확한 연·월·일이 필요합니다. 휴가 시작일과 종료일을 알려주시면 예상 차감일수를 계산합니다.'
                res['follow_up'] = {'fields': [
                    {'key':'start_date','label':'휴가 시작일','type':'date'},
                    {'key':'end_date','label':'휴가 종료일','type':'date'}]}
                s['pending_kind'] = 'leave_period'
                s['intent'] = 'leave_balance'

            elif s['intent']=='leave_balance' and any(w in q for w in ('안 쓰','안쓰','말고','줄이','변경','대신')) and re.search(r'(?:총\s*([0-9]{1,3})\s*일|([0-9]{1,3})\s*일만)',q):
                # 제한된 테스트 패턴 전용: 이전 가정의 '추가 차감'이 아니라 '전체 계획 변경'.
                match=re.search(r'(?:총\s*([0-9]{1,3})\s*일|([0-9]{1,3})\s*일만)',q)
                planned=safe_num(match.group(1) or match.group(2))
                projected=basic_remaining-planned
                s['planned_leave_days']=planned
                s['remaining']=projected
                res['answer']=f'기존 휴가 사용 계획을 총 {planned}일로 변경하는 가정입니다. {basic_remaining}일 - {planned}일 = 예상 잔여 연차 {projected}일입니다.'
                res['calculation']={'title':'휴가 계획 변경 · 가상 데이터','items':[{'label':'기본 잔여','value':f'{basic_remaining}일'}, {'label':'변경된 총 사용 계획','value':f'{planned}일'}, {'label':'예상 잔여','value':f'{projected}일'}], 'note':'기존 계획을 대체한 계산이며 실제 직원 연차 내역은 변경하지 않습니다.'}
                res['sources']=[LEAVE_SOURCE]
                s['pending_kind']=None

            elif has_leavelike and leave_amount and (s['intent']=='leave_balance' or '남' in q or '잔여' in q):
                day_count = safe_num(leave_amount.group(1),0)
                current = s['remaining'] if s['remaining'] is not None else basic_remaining
                projected = current-day_count
                s['remaining'] = projected
                s['planned_leave_days'] = basic_remaining-projected
                res['answer'] = f'앞선 대화를 이어서 가상 계산하면, {current}일 중 {day_count}일을 사용했을 때 예상 잔여 연차는 {projected}일입니다.'
                res['calculation'] = {'title':'대화 맥락 유지 테스트', 'items':[
                    {'label':'이전 예상 잔여','value':f'{current}일'},
                    {'label':'이번 가정 사용','value':f'{day_count}일'},
                    {'label':'새 예상 잔여','value':f'{projected}일'}],
                    'note':'대화 세션 내 가정 계산일 뿐 실제 휴가 DB를 변경하지 않습니다.'}
                res['sources'] = [LEAVE_SOURCE]
                s['intent'] = 'leave_balance'

            elif not leave_amount and (('남' in q and (has_leavelike or s['intent']=='leave_balance')) or ('연차' in q and any(x in q for x in ('몇','조회','잔여','있나요')))) :
                current = s['remaining'] if s['remaining'] is not None else basic_remaining
                res['answer'] = f'{p["name"]} 님의 가상 직원 데이터 기준 잔여 연차는 {current}일입니다.'
                res['calculation'] = {'title':'잔여 연차 조회 · 가상 데이터', 'items':[
                    {'label':'부여 연차','value':f'{p["granted"]}일'},
                    {'label':'기존 사용 연차','value':f'{p["used"]}일'},
                    {'label':'현재 가상 예상 잔여','value':f'{current}일'}],
                    'note':'실제 직원 DB 조회가 아니라 로컬 테스트 데이터입니다.'}
                res['sources'] = [LEAVE_SOURCE]
                s['intent'] = 'leave_balance'
                s['pending_kind'] = None

            elif s['intent']=='leave_balance' and leave_amount:
                day_count = safe_num(leave_amount.group(1),0)
                current = s['remaining'] if s['remaining'] is not None else basic_remaining
                projected = current-day_count
                s['remaining'] = projected
                s['planned_leave_days'] = basic_remaining-projected
                res['answer'] = f'이전 연차 질문과 연결해 계산하면, {day_count}일을 더 사용한 뒤 예상 잔여 연차는 {projected}일입니다.'
                res['calculation'] = {'title':'추가 질문', 'items':[{'label':'이전 예상 잔여','value':f'{current}일'},{'label':'추가 사용','value':f'{day_count}일'},{'label':'예상 잔여','value':f'{projected}일'}], 'note':'테스트 세션 한정 가상 계산입니다.'}
                res['sources'] = [LEAVE_SOURCE]

            else:
                # 일반 규정 질문은 실제 PDF 없이 권위 있는 규정 내용을 생성하지 않습니다.
                res['status'] = 'rag_unavailable'
                res['answer'] = ('전처리 규정 PDF 59개의 목록과 원문 열람 기능은 연결되어 있습니다. '
                                 '다만 현재 로컬 테스트 서버에는 규정 본문 RAG 검색·LLM Tool Calling이 없어 '
                                 '조항에 근거한 답변을 생성할 수 없습니다. '
                                 '사내 규정 메뉴에서 원문을 직접 확인하거나 실제 AI 백엔드 연동 후 다시 질문해 주세요.')
                s['intent'] = 'regulation'
                s['pending_kind'] = None

            s['requests'].append(request_id)
            record = {**res,'created_at':now_string(),'category_id':payload.get('category_id'),
                      'rating':None,'comment':None,'test_intent':s['intent'],
                      'test_remaining':s['remaining'],'test_pending_kind':s['pending_kind'],
                      'test_planned_leave_days':s.get('planned_leave_days')}
            cv=self.conversations.get(sid)
            if not cv:
                cv={'session_id':sid,'employee_id':eid,'title':q[:65],
                    'category_id':payload.get('category_id'), 'created_at':record['created_at'],
                    'updated_at':record['created_at'],'turns':[]}
                self.conversations[sid]=cv
            cv['turns'].append(record)
            cv['updated_at']=record['created_at']
            self.save()
            return res

    def get_history(self,payload):
        # v7에선 목록 UI에 질문별 records가 아니라 채팅방별 conversations만 반환.
        return self.get_conversations(payload)

    def feedback(self,payload):
        req=str(payload.get('request_id') or '')
        eid=str(payload.get('employee_id') or '').strip().upper()
        rating=safe_num(payload.get('rating'))
        if rating not in (1,2,3,4,5):raise ValueError('만족도는 1~5점이어야 합니다.')
        with self.lock:
            for cv in self.conversations.values():
                if cv.get('employee_id')!=eid:continue
                for turn in cv.get('turns',[]):
                    if turn.get('request_id')==req:
                        if turn.get('rating') is not None:raise ValueError('이미 평가를 제출한 문의입니다.')
                        turn['rating']=rating
                        turn['error_type']=str(payload.get('error_type') or '')[:100]
                        turn['comment']=str(payload.get('comment') or '')[:500]
                        turn['rating_submitted_at']=now_string()
                        self.save()
                        return {'success':True,'request_id':req,'session_id':cv['session_id'],'rating':rating}
        raise ValueError('해당 사번의 문의번호를 찾을 수 없습니다.')

    def contacts(self,payload):
        eid = str(payload.get('employee_id') or '').strip().upper()
        if eid not in EMPLOYEES:
            raise PermissionError('미등록 사번입니다.')
        key = str(payload.get('category_id') or 'other')
        return {'contacts': [CONTACTS.get(key, CONTACTS['other'])]}


MIME_OVERRIDES = {'.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8'}


def create_handler(store,delay=0.18):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'WONITLocalMock/3.0'
        protocol_version = 'HTTP/1.1'

        def log_message(self, fmt, *args):
            print('[API/WEB] '+fmt % args, flush=True)

        def headers_common(self, content_type, content_length=None):
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','SAMEORIGIN' if content_type.lower().startswith('application/pdf') else 'DENY')
            self.send_header('Referrer-Policy','no-referrer')
            if content_length is not None:
                self.send_header('Content-Length', str(content_length))
            self.send_header('Access-Control-Allow-Origin', f'http://127.0.0.1:{self.server.server_port}')

        def json_out(self,status,obj):
            b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.headers_common('application/json; charset=utf-8',len(b))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            route=unquote(urlparse(self.path).path)
            if route=='/api/health':
                return self.json_out(200, {'ok':True,'mode':'local_test','service':'WONIT HR Mock API','time':now_string()})
            if route.startswith('/api/'):
                return self.json_out(404, {'error':'지원하지 않는 API 주소입니다.'})
            if route.endswith('/'):
                route += 'index.html'
            path=(ROOT/route.lstrip('/')).resolve()
            try:
                path.relative_to(ROOT)
            except ValueError:
                return self.json_out(403, {'error':'접근할 수 없는 경로입니다.'})
            if not path.is_file() or 'test_storage' in path.parts or path.name=='mock_server.py' or 'tests' in path.parts:
                return self.json_out(404, {'error':'파일을 찾을 수 없습니다.'})
            content=path.read_bytes()
            content_type=MIME_OVERRIDES.get(path.suffix,mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.send_response(200)
            self.headers_common(content_type,len(content))
            # PDF preview within this app requires same-origin framing.
            # headers_common sends DENY by default; replace it per-content below.
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self):
            route=urlparse(self.path).path
            length=int(self.headers.get('Content-Length') or 0)
            if length>128_000 or length<1:
                return self.json_out(413, {'error':'요청 데이터가 너무 큽니다.'})
            try:
                payload=json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(payload,dict):
                    raise ValueError('JSON 객체가 필요합니다.')
            except (ValueError,UnicodeDecodeError) as e:
                return self.json_out(400,{'error':str(e)})
            try:
                if route=='/api/hr/employee':
                    result=store.employee(payload.get('employee_id'))
                elif route=='/api/hr/question':
                    result=store.answer(payload)
                elif route=='/api/hr/question/stream':
                    result=store.answer(payload)
                    return self.send_stream(result)
                elif route=='/api/hr/history':
                    result=store.get_history(payload)
                elif route=='/api/hr/conversation':
                    result=store.get_conversation(payload)
                elif route=='/api/hr/feedback':
                    result=store.feedback(payload)
                elif route=='/api/hr/contact':
                    result=store.contacts(payload)
                elif route=='/api/test/reset':
                    store.reset()
                    result={'success':True,'message':'테스트 문의 기록과 대화 세션 초기화 완료'}
                else:
                    return self.json_out(404, {'error':'등록되지 않은 API 주소입니다.'})
            except PermissionError as e:
                return self.json_out(403,{'error':str(e)})
            except ValueError as e:
                return self.json_out(400,{'error':str(e)})
            except Exception as e:
                return self.json_out(500,{'error':str(e)})
            if delay:
                time.sleep(delay)
            self.json_out(200, result)

        def send_stream(self,result):
            self.send_response(200)
            self.headers_common('text/event-stream; charset=utf-8')
            self.send_header('Connection','close')
            self.send_header('X-Accel-Buffering','no')
            self.end_headers()
            def event(typ,obj):
                data=json.dumps(obj,ensure_ascii=False)
                b=f'event: {typ}\ndata: {data}\n\n'.encode('utf-8')
                self.wfile.write(b)
                self.wfile.flush()
            try:
                text=result['answer']
                for i in range(0,len(text),7):
                    event('delta',{'text':text[i:i+7]})
                    if delay:
                        time.sleep(delay/4)
                event('final',result)
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection=True
    return Handler


def create_server(port=5510,persist=True,delay=0.18):
    store=MockStore(persist=persist)
    return ThreadingHTTPServer(('127.0.0.1',port),create_handler(store,delay=delay))


def main():
    arg=argparse.ArgumentParser(description='WONIT UI v7 채팅방 이력 + PDF 열람 모의 API + 웹서버')
    arg.add_argument('--port',type=int,default=5510)
    opts=arg.parse_args()
    try:
        server=create_server(port=opts.port)
    except OSError as e:
        print(f'\n[오류] 포트 {opts.port}을 열 수 없습니다: {e}\n이미 서버가 실행 중이라면 기존 창에서 Ctrl+C를 누르세요.',file=sys.stderr)
        raise SystemExit(1)
    print('\n'+'='*64)
    print(' WONIT Electronics HR Assistant v7 | 채팅방 이력 + 전처리 PDF 59개')
    print(' 직원 3명 · 채팅방 이력/복원 API · WONIT 전처리 PDF 59건 · SSE 채팅')
    print(' 테스트 데이터만 사용합니다. 회사 실제 규정 및 직원 정보가 아닙니다.')
    print(f' 접속 URL : http://127.0.0.1:{opts.port}')
    print(f' 상태 확인 : http://127.0.0.1:{opts.port}/api/health')
    print(' 종료 방법 : 이 터미널에서 Ctrl + C')
    print('='*64+'\n')
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        print('\n[종료] 로컬 테스트 서버를 종료합니다.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
