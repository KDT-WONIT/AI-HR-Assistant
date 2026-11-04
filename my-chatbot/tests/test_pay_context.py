"""연봉·급여 금액 질문: 표 복원, 사용자 직급 행 선택, 핵심 내용 출력."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from app.agent.answers import build_evidence
from app.agent.key_content import add_key_content, key_content_block
from app.integrations.ollama import OllamaClient
from app.rag.pipeline import RagService
from app.rag.retrieval import (RetrievalHints, focus_grades, pay_amount_question, personal_pay_question,
                               rank_sources, search_queries)
from app.rag.tables import decode_rows, expand_sources, is_table_fragment, render_row
from app.schemas import AnswerContext, Source, UserProfile

DOC = '직원연봉규정 시행세칙(2026년도 10월 7일 개정).pdf'
HEAD = '문서: 직원연봉규정 시행세칙(2026년도 10월 7일 개정)\n'
T = '부ᆞ팀장 (본사/특수 사업소)'
# 실제 인덱스의 구조를 그대로 옮긴 청크: 머리글이 있는 표(쪽 26) → 청크 경계에서 끊긴 행 → 꼬리 → 머리글 없이 이어진 표(쪽 27)
CHUNKS = {
    'doc:000001': (HEAD + '직무평가급 및 기타(제9조 관련)\n(금액 : 원, 월)', [26]),
    'doc:000002': (HEAD + '직무평가급 및 기타(제9조 관련)\n| - |\n| '
        f'{T}, 등 급 = 6. {T}, 직무급 = 1,345,000. {T}, 구 분 = 2직급 직위 가등급. '
        f'{T}, 등 급 = 7. {T}, 직무급 = 1,330,000. {T}, 구 분 = 1직급(나) 직위 마등급. '
        f'{T}, 등 급 = 8. {T}, 직무급 = 1,315,000. {T}, 구 분 = 2직급 직위 다등급. {T}, 등', [26]),
    'doc:000003': (HEAD + '직무평가급 및 기타(제9조 관련)\n| - |\n'
        f' 급 = 9. {T}, 직무급 = 1,300,000. {T}, 구 분 = 2직급 직위 라등급. '
        f'{T}, 등 급 = 10. {T}, 직무급 = 1,285,000. {T}, 구 분 = 2직급 직위', [26]),
    'doc:000004': (HEAD + '직무평가급 및 기타(제9조 관련)\n| - |\n 마등급 |', [26]),
    'doc:000005': (HEAD + '직원연봉규정 시행세칙\n개정번호, 1 = 43. 페 이 지, 1 = 23 / 29', [27]),
    'doc:000006': (HEAD + '직원연봉규정 시행세칙\n| - |\n| 16, 1 = 1,345,000. 16, 2 = 2직급 직위-지방사업소 가등급. '
        '17, 1 = 1,330,000. 17, 2 = 2직급 직위-지방사업소 나등급. 18, 1 = 1,050,000. 18, 2 = 3직급 직위-지방사업소. '
        '사업소장, 12, 1 = 1,405,000. 사업소장, 12, 2 = 1직급(나)', [27]),
    'doc:000007': (HEAD + '직원연봉규정 시행세칙\n| - |\n 직위-지방사업소 나등급. 지사장 13, 1 = 1,390,000. '
        '지사장 13, 2 = 1직급(나) 직위-지방사업소 다등급. 22, 1 = 1,220,000. 22, 2 = 사업소 부장 2직급 직위 |', [27]),
}


def fetch(ids):
    return {i: (CHUNKS[i][0], {'pdf_pages_json': json.dumps(CHUNKS[i][1])}) for i in ids if i in CHUNKS}


def source(identifier):
    text, pages = CHUNKS[identifier]
    return Source(document=DOC, page=pages[0], pages=pages, text=text, chunk_id=identifier, section='직원연봉규정 시행세칙')


class QuestionDetectionTests(unittest.TestCase):
    def test_amount_questions_are_detected_but_timing_and_other_topics_are_not(self):
        for question in ('나 연봉 얼마야', '내 월급이 얼마인지 알려줘', '성과급 얼마 받아?', '직원 연봉 구성이 어떻게 돼?'):
            with self.subTest(question=question):
                self.assertTrue(pay_amount_question(question))
        for question in ('나 연봉 언제 오르지', '학자금 지원 한도?', '연차휴가는 어떻게 신청하나요?'):
            with self.subTest(question=question):
                self.assertFalse(pay_amount_question(question))
        self.assertTrue(personal_pay_question('나 연봉 얼마야'))
        self.assertFalse(personal_pay_question('직원 연봉 구성이 어떻게 돼?'))

    def test_explicit_grade_in_question_beats_profile_grade(self):
        self.assertEqual(focus_grades('1직급 연봉 얼마야', '2직급'), ['1직급'])
        self.assertEqual(focus_grades('나 연봉 얼마야', '2직급'), ['2직급'])
        self.assertEqual(focus_grades('나 연봉 얼마야'), [])


class RetrievalTests(unittest.TestCase):
    def test_pay_question_is_expanded_with_the_users_grade(self):
        queries = search_queries('나 연봉 얼마야', RetrievalHints(grade='2직급'))
        self.assertEqual(queries[0], '나 연봉 얼마야')
        self.assertEqual(len(queries), 4)
        self.assertTrue(all('2직급' in item for item in queries[1:]))
        self.assertTrue(any('직무평가급' in item for item in queries))
        self.assertEqual(len(search_queries('나 연봉 얼마야')), 4)  # 프로필이 없어도 규정 표현으로 확장

    def test_amount_tables_beat_revision_history_and_executive_rules(self):
        history = Source(document=DOC, chunk_id='history', text='개정번호 개정일자 변 경 내 용 기본연봉 기준액 조정 직무급')
        table = Source(document=DOC, chunk_id='table', text='직무급 1,345,000 2직급 직위 가등급')
        executive = Source(document='임원연봉규정.pdf', chunk_id='exec', text='임원 직무급 3,000,000 2직급')
        ranked = rank_sources('나 연봉 얼마야', [[history, executive, table], [history, executive], [executive, history]], 5,
                              RetrievalHints(grade='2직급'))
        self.assertEqual(ranked[0].chunk_id, 'table')
        self.assertEqual(ranked[-1].chunk_id, 'history')


class TableRestorationTests(unittest.TestCase):
    def test_boundary_split_rows_are_joined_with_header_unit_and_tail(self):
        self.assertTrue(is_table_fragment(CHUNKS['doc:000003'][0]))
        result = expand_sources([source('doc:000003')], ['2직급'], fetch)
        self.assertEqual(len(result), 1)
        text = result[0].text
        self.assertIn('[표] 직무평가급 및 기타(제9조 관련) (금액 : 원, 월)', text)
        # 청크 2·3·4에 걸친 행이 모두 복원됩니다(`등` | `급 = 9`, `2직급 직위` | `마등급`).
        self.assertIn(f'{T} · 등급 9 · 직무급 1,300,000원 · 구분 2직급 직위 라등급', text)
        self.assertIn(f'{T} · 등급 10 · 직무급 1,285,000원 · 구분 2직급 직위 마등급', text)
        self.assertIn(f'{T} · 등급 6 · 직무급 1,345,000원 · 구분 2직급 직위 가등급', text)
        self.assertNotIn('1직급(나) 직위 마등급', text)  # 다른 직급 행은 제외
        self.assertEqual(len(result[0].highlights), 4)

    def test_neighbor_chunks_already_merged_are_not_duplicated(self):
        result = expand_sources([source('doc:000003'), source('doc:000002')], ['2직급'], fetch)
        self.assertEqual([item.chunk_id for item in result], ['doc:000003'])

    def test_table_continued_on_next_page_borrows_caption_and_decodes_numbered_rows(self):
        result = expand_sources([source('doc:000006')], ['2직급'], fetch)[0]
        self.assertIn('직무평가급 및 기타(제9조 관련) (이어지는 표)', result.caption)
        self.assertIn('(금액 : 원, 월)', result.caption)
        self.assertEqual(result.highlights, [
            '16번 행: 1,345,000원 · 2직급 직위-지방사업소 가등급',
            '17번 행: 1,330,000원 · 2직급 직위-지방사업소 나등급',
            '22번 행: 1,220,000원 · 사업소 부장 2직급 직위',  # 청크 7에서 이어 붙인 행
        ])
        self.assertNotIn('개정번호', result.text)
        self.assertNotIn('3직급', result.text)

    def test_without_focus_a_bounded_set_of_rows_is_shown_and_nothing_is_highlighted(self):
        result = expand_sources([source('doc:000006')], [], fetch)[0]
        self.assertEqual(result.highlights, [])
        self.assertIn('3직급 직위-지방사업소', result.text)

    def test_fetch_failure_keeps_the_original_source(self):
        def broken(ids):
            raise RuntimeError('chroma down')
        original = source('doc:000006')
        with self.assertLogs('app.rag.tables', level='WARNING'):
            result = expand_sources([original], ['2직급'], broken)
        self.assertEqual(result[0].text, original.text)

    def test_row_decoding_handles_values_with_periods_and_blank_labels(self):
        rows = decode_rows('1직급(가), 기본 연봉액.하한금액 = 72,278. 1직급(가), 기본 연봉액.상한금액 = 108,491. 7, 1 = 2000. 10. 18. 7, 2 = ')
        self.assertEqual(render_row(rows[0]), '1직급(가) · 기본 연봉액.하한금액 72,278 · 기본 연봉액.상한금액 108,491')
        self.assertEqual(render_row(rows[1]), '7번 행: 2000. 10. 18')

    def test_pipeline_restores_tables_with_the_users_grade_after_retrieval(self):
        hits = [[source('doc:000003')], [], [], []]
        with patch('app.rag.pipeline.EmbeddingService') as embedding, patch('app.rag.pipeline.ChromaVectorStore') as store:
            embedding.return_value.embed_documents.return_value = [[1], [2], [3], [4]]
            domain_hits = iter(hits)
            store.return_value.search.side_effect = lambda vector, patterns, count: next(domain_hits) if patterns is not None else []
            store.return_value.fetch.side_effect = fetch
            result = asyncio.run(RagService().search('나 연봉 얼마야', ['연봉규정'], hints=RetrievalHints(grade='2직급')))
        self.assertEqual(sum(call.args[1] is not None for call in store.return_value.search.call_args_list), 4)
        self.assertEqual(len(result[0].highlights), 4)
        self.assertTrue(all('2직급' in row for row in result[0].highlights))


class KeyContentTests(unittest.TestCase):
    def context(self, question='나 연봉 얼마야', coverage='unknown'):
        restored = expand_sources([source('doc:000003')], ['2직급'], fetch)
        return AnswerContext(question=question, employee_id='KDN0001', answer_coverage=coverage, sources=restored,
                             user_profile=UserProfile(employee_id='KDN0001', name='김서연', grade='2직급', department='인사부'),
                             user_profile_status='found')

    def test_block_lists_the_users_grade_rows_with_page_and_caution(self):
        block = key_content_block(self.context())
        self.assertIn('김서연님(2직급) 기준으로 규정에서 확인되는 지급 기준', block)
        self.assertIn('직원연봉규정 시행세칙(2026년도 10월 7일 개정) · 26쪽 · 직무평가급 및 기타(제9조 관련) (금액 : 원, 월)', block)
        self.assertIn('등급 6 · 직무급 1,345,000원 · 구분 2직급 직위 가등급', block)
        self.assertIn('확정 연봉액', block)
        self.assertIn('급여 담당 부서', block)
        self.assertNotIn('1직급(나)', block)

    def test_other_questions_get_no_block(self):
        self.assertEqual(key_content_block(self.context('나 연봉 언제 오르지')), '')

    def test_block_is_inserted_before_references_and_marks_partial(self):
        context = self.context(coverage='direct')
        answer = add_key_content(context, '연봉은 직위와 등급에 따라 결정됩니다.\n\n[참고 문서]\n- 직원연봉규정 시행세칙.pdf · 26쪽')
        parts = answer.split('\n\n')
        self.assertEqual(parts[0], '연봉은 직위와 등급에 따라 결정됩니다.')
        self.assertTrue(parts[1].startswith('김서연님(2직급)'))
        self.assertTrue(parts[2].startswith('[참고 문서]'))
        self.assertEqual(context.answer_coverage, 'partial')

    def test_generic_fallback_is_replaced_but_the_table_content_is_kept(self):
        context = self.context(coverage='missing')
        answer = add_key_content(context, '검색된 자료만으로는 질문에 대한 답변을 확실하게 정리하기 어렵습니다.\n\n다음 단계\n담당 부서에 확인해주세요.')
        self.assertTrue(answer.startswith('규정 문서에서 확인되는 핵심 내용을 정리했습니다.'))
        self.assertIn('직무급 1,300,000원', answer)
        self.assertIn('다음 단계', answer)
        self.assertEqual(context.answer_coverage, 'partial')

    def test_model_answer_stays_short_but_key_content_is_still_printed(self):
        """모델이 '직위에 따라 결정됩니다'만 답해도 표의 핵심 행이 출력됩니다(이번 개선의 목적)."""
        context = self.context()
        rows = [item for item in build_evidence(context) if '라등급' in item.text]
        self.assertTrue(rows and '1,300,000원' in rows[0].text)
        draft = {'coverage': 'partial', 'summary': '연봉은 직위와 사업소 등급에 따라 결정됩니다.',
                 'points': [{'text': '2직급 직위 라등급은 직무급이 월 1,300,000원입니다.', 'source_id': 'S1', 'evidence_id': rows[0].id}]}
        client = OllamaClient()
        client._chat = AsyncMock(return_value=json.dumps(draft, ensure_ascii=False))
        answer = asyncio.run(client.generate_answer(context))
        self.assertIn('1,300,000원', answer)
        self.assertIn('김서연님(2직급) 기준으로 규정에서 확인되는 지급 기준', answer)
        self.assertIn('등급 10 · 직무급 1,285,000원 · 구분 2직급 직위 마등급', answer)
        self.assertEqual(context.answer_coverage, 'partial')
        self.assertGreaterEqual(client._chat.await_args.kwargs['num_predict'], 2400)


if __name__ == '__main__':
    unittest.main()


class RichAnswerTests(unittest.TestCase):
    def test_short_model_answer_is_supplemented_with_related_source_sentences(self):
        from app.agent.answers import AnswerDraft, GroundedPoint, render_answer
        text = ('문서: 기록물관리지침\n제28조(보안관리)\n'
                '기록관의 전산실 및 보존서고는 외부인의 출입을 원칙적으로 금지하며, 허가를 받아야 한다. '
                '보존서고에는 보안 설비와 화재 방지 설비를 갖추어야 한다. '
                '기록물을 열람하려는 외부인은 기록관리부서장의 승인을 받아야 한다.')
        context = AnswerContext(employee_id='A', question='기록물 보안 관리는 어떻게 하나요?',
                                sources=[Source(document='기록물관리지침(2025년 07월 개정).pdf', page=9, text=text, section='제28조(보안관리)')])
        evidence = build_evidence(context)
        first = evidence[0]
        draft = AnswerDraft(coverage='direct', summary='기록물 보안은 출입을 통제해 관리합니다.',
                            points=[GroundedPoint(text=first.text, source_id=first.source_id, evidence_id=first.id)])
        answer = render_answer(context, draft, [])
        self.assertIn('보안 설비와 화재 방지 설비', answer)
        self.assertIn('기록관리부서장의 승인', answer)
        self.assertIn('[참고 문서]', answer)


class StreamingTests(unittest.TestCase):
    def test_preview_extracts_summary_then_points_from_partial_json(self):
        from app.agent.stream_preview import extract_preview
        self.assertEqual(extract_preview('{"coverage":"direct","summary":"기록물은 지침에 따라 관'), '기록물은 지침에 따라 관')
        partial = ('{"coverage":"direct","summary":"출입은 \\"허가\\"가 필요합니다.","points":[{"text":"외부인 출입 금지 [E1]",'
                   '"source_id":"S1","evidence_id":"E1"},{"text":"보존서고는 허')
        self.assertEqual(extract_preview(partial), '출입은 "허가"가 필요합니다.\n\n확인된 내용\n- 외부인 출입 금지\n- 보존서고는 허')
        self.assertEqual(extract_preview('{"coverage":"dir'), '')
        self.assertEqual(extract_preview('{"summary":"끊긴 이스케이프\\'), '끊긴 이스케이프')

    def test_stream_endpoint_sends_status_delta_and_final_then_final_replaces_preview(self):
        import json
        from unittest.mock import AsyncMock, patch
        from fastapi.testclient import TestClient
        from app.main import app
        from app.api import routes
        from app.schemas import ChatResponse, Step

        async def fake_reply(conversation, data, progress=None):
            await progress('status', '검색 중')
            await progress('delta', '미리보기')
            return ChatResponse(conversation_id=conversation.id, message_id=conversation.id, answer='최종 답변',
                                context=AnswerContext(question=data.message, employee_id=data.employee_id),
                                steps=[Step(key='a', label='a', detail='d', status='done')])

        with patch.object(routes.service, 'reply', side_effect=fake_reply), TestClient(app) as client:
            created = client.post('/api/conversations', json={'employee_id': 'KDN0001'}).json()
            with client.stream('POST', '/api/chat/stream', json={'employee_id': 'KDN0001', 'conversation_id': created['id'],
                                                                'message': '테스트'}) as response:
                body = ''.join(response.iter_text())
        events = [(block.split('\n')[0][7:], json.loads(block.split('\n')[1][6:])) for block in body.strip().split('\n\n')]
        self.assertEqual([name for name, _ in events], ['status', 'delta', 'final'])
        self.assertEqual(events[1][1], '미리보기')
        self.assertEqual(events[2][1]['answer'], '최종 답변')

    def test_ollama_stream_feeds_preview_and_returns_validated_answer(self):
        import threading
        from dataclasses import replace
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from app.config import settings

        text = ('문서: 기록물관리지침\n제28조(보안관리)\n기록관의 전산실 및 보존서고는 외부인의 출입을 원칙적으로 금지하며, 허가를 받아야 한다.')
        draft = json.dumps({'coverage': 'direct', 'summary': '외부인의 출입은 원칙적으로 금지되며 허가가 필요합니다.',
                            'points': [{'text': '전산실과 보존서고는 외부인 출입이 금지되며 허가를 받아야 합니다.', 'source_id': 'S1', 'evidence_id': 'E1'}]},
                           ensure_ascii=False)

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-ndjson')
                self.end_headers()
                for index in range(0, len(draft), 12):
                    self.wfile.write((json.dumps({'message': {'content': draft[index:index + 12]}, 'done': False}) + '\n').encode())
                    self.wfile.flush()
                self.wfile.write((json.dumps({'message': {'content': ''}, 'done': True, 'eval_count': 10, 'eval_duration': 10**9}) + '\n').encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        client = OllamaClient()
        client.base_url = f'http://127.0.0.1:{server.server_port}'
        client.answer_model = 'fake'
        previews = []

        async def on_preview(value):
            previews.append(value)

        context = AnswerContext(question='기록물 보안 관리는 어떻게 하나요?', employee_id='A', sources=[
            Source(document='기록물관리지침(2025년 07월 개정).pdf', page=9, text=text, section='제28조(보안관리)')])
        with patch('app.integrations.ollama.settings', replace(settings, answer_provider='ollama', ollama_model='fake')):
            answer = asyncio.run(client.generate_answer(context, on_preview=on_preview))
        self.assertGreater(len(previews), 2)  # 토큰이 오는 동안 여러 번 갱신됩니다.
        self.assertTrue(previews[-1].startswith('외부인의 출입은 원칙적으로 금지되며'))
        self.assertIn('[참고 문서]', answer)  # 최종본은 검증·정리된 형식입니다.


class RemoteTimingTests(unittest.TestCase):
    def test_timings_from_the_tool_process_are_merged_and_not_sent_to_the_model(self):
        from app import timing
        from app.schemas import ToolResult
        result = ToolResult(tool_id='x', status='ok', message='', data={'_timings': {'items': {'임베딩': 0.4, '벡터 검색': 0.2}, 'notes': {'임베딩': '질문 1개'}}})
        timings = timing.start('t')
        remote = result.data.pop('_timings')
        for label, seconds in remote['items'].items():
            timing.record(label, seconds, remote['notes'].get(label, ''))
        self.assertEqual(timings.items, {'임베딩': 0.4, '벡터 검색': 0.2})
        self.assertNotIn('_timings', result.data)
