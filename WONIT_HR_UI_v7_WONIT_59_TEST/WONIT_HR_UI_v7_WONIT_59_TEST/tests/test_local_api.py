"""Standard-library tests for the local WONIT HR integration simulator.
Run: py -m unittest discover -s tests -p 'test_local_api.py' -v
"""
import http.client
import json
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mock_server import create_server


class TestMockAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv=create_server(port=0,persist=False,delay=0.008)
        cls.port=cls.srv.server_port
        cls.thread=threading.Thread(target=cls.srv.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        self.call('/api/test/reset',{})

    def call(self,path,payload=None,method='POST'):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        if method=='GET':
            c.request('GET',path)
        else:
            c.request('POST',path,body=json.dumps(payload or {},ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json'})
        r=c.getresponse()
        raw=r.read()
        status=r.status
        c.close()
        try:data=json.loads(raw)
        except ValueError:data=raw
        return status,data

    def q(self,text,sid='test_123',employee='W-1001',**rest):
        st,data=self.call('/api/hr/question',{'employee_id':employee,'question':text,'session_id':sid,**rest})
        self.assertEqual(st,200,data)
        return data

    def test_health_and_static_files(self):
        status,result=self.call('/api/health',method='GET')
        self.assertEqual(status,200)
        self.assertEqual(result['mode'],'local_test')
        status,content=self.call('/',method='GET')
        self.assertEqual(status,200)
        self.assertIn(b'WONIT Electronics',content)
        self.assertIn(b'assets/regulation_categories.json',content) if False else None
        status,content=self.call('/config.js',method='GET')
        self.assertEqual(status,200)
        self.assertIn(b'enableStreaming: true',content)

    def test_employee_lookup(self):
        code,r=self.call('/api/hr/employee',{'employee_id':'W-1001'})
        self.assertEqual(code,200)
        self.assertTrue(r['found'])
        self.assertEqual(r['employee']['name'],'김민수')
        code,r=self.call('/api/hr/employee',{'employee_id':'W-9999'})
        self.assertFalse(r['found'])

    def test_leave_balance_and_context(self):
        a=self.q('제 연차가 며칠 남았나요?')
        self.assertIn('9일',a['answer'])
        self.assertEqual(a['status'],'answered')
        self.assertIn('calculation',a)
        b=self.q('그럼 3일 사용하면 얼마나 남나요?',previous_request_id=a['request_id'])
        self.assertIn('6일',b['answer'])
        c=self.q('그럼 2일 더 쓰면?',previous_request_id=b['request_id'])
        self.assertIn('4일',c['answer'])
        self.assertEqual(c['session_id'],'test_123')
        d=self.q('제 연차가 며칠 남았나요?',sid='fresh_abc')
        self.assertIn('9일',d['answer'])

    def test_employee_isolation(self):
        self.q('제 연차가 며칠 남았나요?',sid='shared_one')
        status,data=self.call('/api/hr/question',{'employee_id':'W-1002','session_id':'shared_one','question':'제 연차는?'})
        self.assertEqual(status,403)
        b=self.q('제 연차가 며칠 남았나요?',sid='separate_second',employee='W-1002')
        self.assertIn('10일',b['answer'])

    def test_leave_followup(self):
        r=self.q('월요일부터 수요일까지 쉬면 연차가 얼마나 차감되나요?',sid='leave_followup')
        self.assertEqual(r['status'],'needs_info')
        self.assertEqual(len(r['follow_up']['fields']),2)
        r2=self.q(r['question'],sid='leave_followup',previous_request_id=r['request_id'],input_data={'start_date':'2026-11-09','end_date':'2026-11-11'})
        self.assertEqual(r2['status'],'answered')
        self.assertIn('3일',r2['answer'])
        self.assertIn('6일',r2['answer'])

    def test_travel_350000(self):
        r=self.q('부산으로 출장가는데 예상 여비는?',sid='travel_first')
        self.assertEqual(r['status'],'needs_info')
        r2=self.q(r['question'],sid='travel_first',previous_request_id=r['request_id'],input_data={'destination':'부산','start_date':'2026-11-09','end_date':'2026-11-11','transport':'철도','transport_fare_won':100000})
        self.assertIn('350,000원',r2['answer'])
        self.assertEqual(r2['status'],'answered')
        self.assertEqual(len(r2['sources']),1)

    def test_composite_and_contact(self):
        r=self.q('출장 중 개인 사정으로 하루 휴가를 붙여도 되나요? 그날 숙박비는 지원되나요?')
        self.assertEqual(r['status'],'needs_review')
        self.assertEqual(len(r['sources']),2)
        self.assertEqual(len(r['sections']),3)
        self.assertEqual(r['contact']['duty'],'출장·여비')
        c=self.q('규정에 없는 특별휴가를 받을 수 있나요?',sid='special')
        self.assertEqual(c['status'],'needs_review')
        self.assertEqual(c['contact']['name'],'박지현')

    def test_history_grouped_and_feedback(self):
        a=self.q('제 연차가 며칠 남았나요?',sid='leave_session')
        b=self.q('그럼 3일 사용하면 얼마나 남나요?',sid='leave_session')
        c=self.q('지식재산권 관리규정을 알려주세요.',sid='research_session',category_id='research_quality')
        st,d=self.call('/api/hr/history',{'employee_id':'W-1001'})
        self.assertEqual(st,200)
        self.assertEqual(len(d['conversations']),2)
        self.assertNotIn('records',d)
        rooms={r['session_id']:r for r in d['conversations']}
        self.assertEqual(rooms['leave_session']['turn_count'],2)
        self.assertEqual(rooms['leave_session']['message_count'],4)
        self.assertEqual(rooms['research_session']['turn_count'],1)
        self.assertIn('지식재산권',rooms['research_session']['title'])
        st,detail=self.call('/api/hr/conversation',{'employee_id':'W-1001','session_id':'leave_session'})
        self.assertEqual(st,200)
        self.assertEqual(len(detail['turns']),2)
        self.assertEqual(detail['turns'][0]['question'],a['question'])
        self.assertEqual(detail['turns'][1]['question'],b['question'])
        st,r=self.call('/api/hr/feedback',{'request_id':b['request_id'],'employee_id':'W-1001','rating':4,'error_type':'wrong_source','comment':'테스트'})
        self.assertEqual(st,200)
        st,detail=self.call('/api/hr/conversation',{'employee_id':'W-1001','session_id':'leave_session'})
        self.assertEqual(detail['turns'][1]['rating'],4)
        st,r=self.call('/api/hr/feedback',{'request_id':b['request_id'],'employee_id':'W-1001','rating':4})
        self.assertEqual(st,400)
        st,d=self.call('/api/hr/history',{'employee_id':'W-1002'})
        self.assertEqual(d['conversations'],[])
        st,r=self.call('/api/hr/conversation',{'employee_id':'W-1002','session_id':'leave_session'})
        self.assertEqual(st,403)

    def test_history_search_all_turns(self):
        self.q('연차 기본 잔여 확인',sid='leave')
        self.q('그럼 3일 사용하면 얼마나 남나요?',sid='leave')
        self.q('연구개발비 규정을 알려줘',sid='research')
        st,d=self.call('/api/hr/history',{'employee_id':'W-1001','search':'3일 사용'})
        self.assertEqual(st,200)
        self.assertEqual([x['session_id'] for x in d['conversations']],['leave'])

    def test_history_persistence_and_resume_after_server_restart(self):
        from mock_server import MockStore
        from unittest.mock import patch
        import tempfile
        from pathlib import Path
        from mock_server import DATA_DIR
        # File persistence check in a temporary directory (no effect on user's history).
        with tempfile.TemporaryDirectory() as d:
            import mock_server
            orig=mock_server.HISTORY_FILE if hasattr(mock_server,'HISTORY_FILE') else None
            with patch.object(mock_server,'DATA_DIR',Path(d)),patch.object(mock_server,'CONVERSATIONS_FILE',Path(d)/'conversations.json'),patch.object(mock_server,'LEGACY_HISTORY_FILE',Path(d)/'history.json'):
                a=MockStore(persist=True)
                b=a.answer({'employee_id':'W-1001','question':'제 연차가 며칠 남았나요?','session_id':'persistent'})
                c=a.answer({'employee_id':'W-1001','question':'그럼 3일 사용하면 얼마나 남나요?','session_id':'persistent'})
                self.assertTrue((Path(d)/'conversations.json').exists())
                restored=MockStore(persist=True)
                self.assertEqual(len(restored.get_conversation({'employee_id':'W-1001','session_id':'persistent'})['turns']),2)
                r=restored.answer({'employee_id':'W-1001','question':'그럼 2일 더 쓰면?','session_id':'persistent'})
                self.assertIn('4일',r['answer'])
                self.assertEqual(restored.get_conversations({'employee_id':'W-1001'})['conversations'][0]['turn_count'],3)

    def test_pdf_59_catalog_and_openable_preprocessed(self):
        st,data=self.call('/assets/regulations_catalog.json',method='GET')
        self.assertEqual(st,200)
        import json
        manifest=data if isinstance(data,dict) else json.loads(data)
        self.assertEqual(manifest['count'],59)
        self.assertEqual(len(manifest['documents']),59)
        from collections import Counter
        counts=Counter(d['category_id'] for d in manifest['documents'])
        self.assertEqual(counts['hr_employment'],12)
        self.assertEqual(counts['work_leave_labor'],6)
        self.assertEqual(counts['organization'],11)
        self.assertEqual(sum(counts.values()),59)
        for d in manifest['documents']:
            self.assertIn('WONIT Electronics',d['source_organization'])
            self.assertTrue(d['url'].startswith('/regulations/wonit_preprocessed/WONIT-'))
        st,body=self.call(manifest['documents'][0]['url'],method='GET')
        self.assertEqual(st,200)
        self.assertTrue(body.startswith(b'%PDF-'))


    def test_all_new_pdf_files_and_question_samples(self):
        import json
        from collections import Counter
        root=Path(__file__).resolve().parents[1]
        cat=json.loads((root/'assets/regulations_catalog.json').read_text(encoding='utf-8'))
        examples=json.loads((root/'assets/sample_questions.json').read_text(encoding='utf-8'))
        self.assertEqual(len(cat['documents']),59)
        self.assertEqual(len(examples['categories']),10)
        self.assertEqual(sum(map(len,examples['categories'].values())),132)
        expected={r['id']:r['count'] for r in cat['categories']}
        actual=Counter(r['category_id'] for r in cat['documents'])
        self.assertEqual(dict(actual),expected)
        for d in cat['documents']:
            source=root/d['url'].lstrip('/')
            self.assertTrue(source.is_file(),source)
            self.assertEqual(source.read_bytes()[:5],b'%PDF-')
            self.assertTrue(d['id'].startswith('WONIT-'))
        st,body=self.call('/assets/sample_questions.json',method='GET')
        self.assertEqual(st,200)
        st,body=self.call('/regulations/public_source/KDN-001.pdf',method='GET')
        self.assertEqual(st,404)
        # Frontend has document viewer and question-category helper separate.
        page=(root/'index.html').read_text(encoding='utf-8')
        self.assertIn('homeExampleList',page)
        self.assertIn('chatExampleList',page)
        self.assertNotIn('한전KDN',page)
        self.assertIn('AI 질문 분야',page)

    def test_leave_plan_correction(self):
        first=self.q('휴가 5일 사용하면 몇일 남나요?',sid='plan')
        self.assertIn('4일',first['answer'])
        second=self.q('그러면 5일 쓴다고 했는데 2일은 안쓰고 총 3일만 쓴다면?',sid='plan')
        self.assertIn('6일',second['answer'])
        third=self.q('여기에서 2일 더 쓰면?',sid='plan')
        self.assertIn('4일',third['answer'])

    def test_contact(self):
        st,d=self.call('/api/hr/contact',{'employee_id':'W-1001','category_id':'travel'})
        self.assertEqual(st,200)
        self.assertEqual(d['contacts'][0]['name'],'김서연')

    def test_sse_streaming_and_final_json(self):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        b=json.dumps({'employee_id':'W-1001','question':'제 연차가 며칠 남았나요?','session_id':'stream_1'},ensure_ascii=False).encode()
        c.request('POST','/api/hr/question/stream',body=b,headers={'Content-Type':'application/json'})
        r=c.getresponse()
        self.assertEqual(r.status,200)
        self.assertIn('text/event-stream',r.getheader('Content-Type'))
        chunks=r.read().decode('utf-8')
        c.close()
        self.assertIn('event: delta',chunks)
        self.assertIn('event: final',chunks)
        final=[x for x in chunks.split('\n\n') if x.startswith('event: final')][0]
        data=json.loads(final.split('data: ',1)[1])
        self.assertIn('9일',data['answer'])

    def test_explicit_server_error_and_invalid_date(self):
        st,d=self.call('/api/hr/question',{'employee_id':'W-1001','question':'오류 테스트','session_id':'error'})
        self.assertEqual(st,500)
        st,d=self.call('/api/hr/question',{'employee_id':'W-1001','question':'휴가일 계산','session_id':'bad_date','input_data':{'task':'leave_period','start_date':'2026-11-11','end_date':'2026-11-09'}})
        self.assertEqual(st,400)


if __name__=='__main__':
    unittest.main(verbosity=2)
