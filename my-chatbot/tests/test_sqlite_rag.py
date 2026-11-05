import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.config import settings
from app.errors import ConversationConflict, ModelUnavailable, RagUnavailable, StorageUnavailable
from app.integrations.ollama import OllamaClient
from app.integrations.sqlite import connection_scope
from app.repositories.sqlite import SQLiteConversationRepository
from app.repositories.users import SQLiteUserRepository
from app.schemas import AnswerContext, EndResponse, Message, ToolDefinition, ToolInput
from app.tools.execution import business_data


class SQLiteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = replace(settings, sqlite_path=Path(self.directory.name)/'app.sqlite3', storage_backend='sqlite')
        item = patch('app.integrations.sqlite.settings', self.config)
        item.start(); self.addCleanup(item.stop)
        item = patch('scripts.import_leave_balances.settings',replace(self.config,user_data_source='sqlite'))
        item.start(); self.addCleanup(item.stop)
        self.repository = SQLiteConversationRepository()

    def pair(self, text):
        now = datetime.now(timezone.utc)
        return [Message(id=uuid4(), role='user', content=text, created_at=now),
                Message(id=uuid4(), role='assistant', content='답변 '+text, created_at=now)]

    def test_history_persistence_and_isolation(self):
        first, other = self.repository.create('A'), self.repository.create('A')
        context = AnswerContext(employee_id='A', question='질문')
        self.repository.append_turn(other.id, self.pair('다른 세션'), context, None)
        last = None
        for index in range(7):
            pair = self.pair(str(index)); self.repository.append_turn(first.id, pair, context, last); last=pair[-1].id
        fresh = SQLiteConversationRepository()
        recent = fresh.recent_messages(first.id, 10)
        self.assertEqual([m.content for m in recent if m.role=='user'], ['2','3','4','5','6'])
        self.assertEqual(len(fresh.get(first.id).messages), 14)
        self.assertNotIn('다른 세션', str(recent))
        facts = fresh.user_messages(first.id)
        self.assertEqual([m.content for m in facts], [str(n) for n in range(7)])
        self.assertTrue(all(m.role == 'user' for m in facts))
        self.assertEqual([m.content for m in fresh.user_messages(other.id)], ['다른 세션'])

    def test_atomic_turn_close_and_duplicate_end(self):
        conversation=self.repository.create('A'); context=AnswerContext(employee_id='A',question='q')
        pair=self.pair('first'); self.repository.append_turn(conversation.id,pair,context,None)
        broken=self.pair('rollback'); broken[-1].id=pair[-1].id
        with self.assertRaises(StorageUnavailable): self.repository.append_turn(conversation.id,broken,context,pair[-1].id)
        self.assertEqual(len(self.repository.get(conversation.id).messages),2)
        with self.assertRaises(ConversationConflict): self.repository.append_turn(conversation.id,self.pair('stale'),context,None)
        result=EndResponse(conversation_id=conversation.id,ended_at=datetime.now(timezone.utc),rating='helpful',comment='',event_id=uuid4(),webhook_status='not_configured',message='closed')
        self.repository.close(conversation.id,result,{})
        self.assertEqual(self.repository.close(conversation.id,result.model_copy(update={'event_id':uuid4()}),{}),result)
        with self.assertRaises(ConversationConflict): self.repository.append_turn(conversation.id,self.pair('closed'),context,pair[-1].id)

    def test_user_profile_seed_and_leave_projection(self):
        from scripts.seed_employees import insert_sqlite_dataset
        tables={'employees':[dict(employee_id='A',employee_name='테스트',grade='2직급',hire_date='2020-01-01',employment_type='정규직',employment_status='재직')]}
        self.assertEqual(insert_sqlite_dataset(tables)['employees'],1)
        self.assertEqual(insert_sqlite_dataset(tables)['employees'],0)
        self.assertEqual(SQLiteUserRepository().get('A').grade,'2직급')
        with connection_scope(write=True) as connection:
            connection.execute('INSERT INTO leave_balances VALUES(?,?,?,?,?)',('A',2026,16,3,'2026-11-04'))
        request=ToolInput(question='남은 휴가 중 3.5일을 사용하면?',employee_id='A',conversation_id=uuid4(),arguments={'year':2026,'requested_days':3.5})
        data,missing=business_data('work_labor',request)
        self.assertIsNone(missing)
        self.assertEqual(data['leave_projection']['projected_remaining_days'],9.5)
        with connection_scope() as connection: self.assertEqual(connection.execute('SELECT used_days FROM leave_balances').fetchone()[0],3)
        request.employee_id='UNKNOWN'
        self.assertIn('데이터가 없습니다',business_data('work_labor',request)[1])

    def test_balance_csv_validation_and_transaction(self):
        from scripts.import_leave_balances import import_balances
        with connection_scope(write=True) as connection:
            connection.execute('INSERT INTO employees(employee_id,name,created_at) VALUES(?,?,?)',('A','사용자','2026-01-01'))
        path=Path(self.directory.name)/'leave.csv'
        path.write_text('employee_id,year,granted_days,used_days\nA,2026,15,2.5\n',encoding='utf-8')
        self.assertEqual(import_balances(path),1)
        path.write_text('employee_id,year,granted_days,used_days\nA,2026,15,3\nA,2027,1,2\n',encoding='utf-8')
        with self.assertRaises(ValueError): import_balances(path)
        with connection_scope() as connection:
            self.assertEqual(connection.execute('SELECT used_days FROM leave_balances WHERE balance_year=2026').fetchone()[0],2.5)


class RoutingAndSearchTests(unittest.TestCase):
    def test_unverified_claim_is_not_replaced_with_raw_document(self):
        from app.schemas import Source
        context = AnswerContext(question='지원?', employee_id='A', sources=[Source(document='규정.pdf',page=4,text='교육비는 100만원까지 지원한다.')])
        client = OllamaClient()
        client._chat = AsyncMock(return_value=json.dumps({'coverage':'direct','summary':'500만원 지원됩니다.','points':[
            {'text':'500만원 지원됩니다.','source_id':'S1','evidence_id':'E1'},
        ]}))
        answer = asyncio.run(client.generate_answer(context))
        self.assertNotIn('500만원',answer)  # 검증되지 않은 모델 주장은 쓰지 않고,
        self.assertIn('교육비는 100만원까지 지원한다.',answer)  # 질문과 맞는 원문 문장을 그대로 정리해 '모르겠다'로 끝내지 않습니다.
        self.assertIn('규정.pdf · 4쪽',answer)

    def test_broken_answer_json_is_a_readable_limit_notice(self):
        from app.schemas import Source
        context=AnswerContext(question='규정?',employee_id='A',sources=[Source(document='규정.pdf',page=2,text='확인된 원문입니다.')])
        client=OllamaClient(); client._chat=AsyncMock(return_value='{"summary":"잘린 응답')
        answer=asyncio.run(client.generate_answer(context))
        self.assertIn('확실하게 정리하기 어렵습니다',answer)
        self.assertNotIn('확인된 원문입니다.',answer)
        self.assertIn('규정.pdf · 2쪽',answer)

    def test_supported_explanation_is_rendered_with_verified_citation(self):
        from app.schemas import Source
        context=AnswerContext(question='지원?',employee_id='A',sources=[Source(document='복지.pdf',page=3,text='교육비는 100만원까지 지원한다.')])
        client=OllamaClient()
        client._chat=AsyncMock(return_value=json.dumps({'coverage':'direct','summary':'교육비는 100만원까지 지원됩니다.','points':[
            {'text':'교육비는 100만원까지 지원됩니다.','source_id':'S1','evidence_id':'E1'}]}))
        answer=asyncio.run(client.generate_answer(context))
        self.assertIn('교육비는 100만원까지 지원됩니다.',answer)
        self.assertIn('[참고 문서]\n- 복지.pdf · 3쪽',answer)
        self.assertFalse(client.explanation_is_supported('500만원 지원됩니다.',['100만원까지 지원한다.'],[]))
        self.assertFalse(client.explanation_is_supported('모두 지원됩니다.',['지원 대상에서 제외한다.'],[]))

    def test_model_context_deduplicates_tool_sources(self):
        from app.schemas import Source, ToolResult
        source=Source(document='복지.pdf',text='중복 없이 전달할 근거')
        context=AnswerContext(question='질문',employee_id='A',sources=[source],tool_results=[ToolResult(tool_id='benefits',status='ok',message='검색 완료',sources=[source])])
        messages=OllamaClient.build_messages(context)
        self.assertEqual(messages[-1]['content'].count('중복 없이 전달할 근거'),1)
        self.assertIn('S1',messages[-1]['content'])
    def test_generated_quotes_must_exist_verbatim_in_source(self):
        from app.schemas import Source
        context=AnswerContext(question='지원 기준?',employee_id='A',sources=[Source(document='복지.pdf',page=3,text='다음 비용은 지원 대상에서 제외한다.')])
        client=OllamaClient()
        draft={'coverage':'direct','summary':'해당 비용은 지원에서 제외됩니다.','points':[
            {'text':'해당 비용은 지원에서 제외됩니다.','source_id':'S1','evidence_id':'E999'}]}
        client._chat=AsyncMock(return_value=json.dumps(draft))
        answer=asyncio.run(client.generate_answer(context))
        self.assertNotIn('해당 비용은 지원에서 제외됩니다.',answer)
        draft['points'][0]['evidence_id']='E1'
        client._chat.return_value=json.dumps(draft)
        answer=asyncio.run(client.generate_answer(context))
        self.assertIn('해당 비용은 지원에서 제외됩니다.',answer)
        self.assertNotIn('다음 비용은 지원 대상에서 제외한다.',answer)
        self.assertIn('복지.pdf · 3쪽',answer)

    def test_tool_schema_adapts_to_any_number_and_rejects_unknown_id(self):
        tools=[ToolDefinition(id=f'custom_{i}',name=f'분야{i}',description='규정 검색',data_path='') for i in range(12)]
        client=OllamaClient(); client._chat=AsyncMock(return_value=json.dumps({'tool_id':'custom_11','arguments':{}}))
        result=asyncio.run(client.choose_tools('질문',tools))
        self.assertEqual(result.tool_id,'custom_11')
        self.assertEqual(client._chat.call_args.kwargs['schema']['properties']['tool_id']['enum'],[t.id for t in tools]+['general'])
        client._chat.return_value='{"tool_id":"invented","arguments":{}}'
        with self.assertRaises(ModelUnavailable): asyncio.run(client.choose_tools('질문',tools))

    def test_new_module_is_discovered_without_editing_list(self):
        from app.tools.base import Tool
        from app.tools.registry import discover_tools
        import app.tools.registry as registry
        tool=Tool(ToolDefinition(id='new_domain',name='새 분야',description='검색',data_path=''),AsyncMock())
        with patch.object(registry, 'settings',replace(settings,enabled_tools=())), \
             patch.object(registry.pkgutil, 'iter_modules',return_value=[SimpleNamespace(name='new_domain')]), \
             patch.object(registry.importlib, 'import_module',return_value=SimpleNamespace(tool=tool)):
            self.assertEqual(list(discover_tools()),['new_domain'])

    def test_chroma_filter_threshold_and_provenance(self):
        from app.rag.vector_store import ChromaVectorStore
        collection=Mock(metadata={'embedding_model':settings.embedding_model,'embedding_revision':settings.embedding_revision,'embedding_dimension':2})
        collection.query.return_value={'ids':[['a','b']],'documents':[['규정','관련 없음']],
            'metadatas':[[{'source':'취업규칙.pdf','pdf_pages_json':'[3,4]','headings_json':'["연차"]'},{'source':'취업규칙.pdf'}]],'distances':[[0.2,0.95]]}
        with patch('app.rag.vector_store.get_collection',return_value=collection), \
             patch('app.rag.vector_store.collection_sources',return_value=('취업규칙.pdf','여비규정.pdf')):
            sources=ChromaVectorStore().search([1,0],['취업'],5)
            self.assertEqual(len(sources),1)
            self.assertEqual(sources[0].pages,[3,4])
            self.assertEqual(sources[0].chunk_id,'a')
            self.assertEqual(collection.query.call_args.kwargs['where'],{'source':{'$in':['취업규칙.pdf']}})
            with self.assertRaises(RagUnavailable): ChromaVectorStore().search([1],['취업'],5)

    def test_missing_index_does_not_create_database(self):
        from app.rag.vector_store import get_collection
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RagUnavailable): get_collection(directory,'missing')
            self.assertEqual(list(Path(directory).iterdir()),[])
