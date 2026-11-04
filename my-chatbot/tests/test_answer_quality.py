import unittest

from app.agent.answers import AnswerDraft, render_answer
from app.integrations.ollama import OllamaClient
from app.schemas import AnswerContext, Source


class AnswerQualityTests(unittest.TestCase):
    def context(self, text, question='연차휴가는 어떻게 신청하나요?'):
        return AnswerContext(employee_id='TEST',question=question,sources=[
            Source(document='취업규칙.pdf',page=7,text=text),
        ])

    def test_related_rules_are_provided_without_inventing_an_application_system(self):
        text='제20조(연차유급휴가) 80퍼센트 이상 출근한 직원에게 15일의 연차를 부여한다. 잔여 연차는 이월한다.'
        context=self.context(text)
        draft=AnswerDraft(coverage='direct',summary='연차는 ERP에서 3일 전에 신청하세요.',points=[
            {'text':'80퍼센트 이상 출근하면 15일을 부여합니다.','source_id':'S1','evidence_id':'E1'},
        ])
        answer=render_answer(context,draft,[])
        self.assertTrue(answer.startswith('신청에 참고할 수 있는 관련 규정은 다음과 같습니다.'))
        self.assertIn('15일',answer)
        self.assertNotIn('ERP',answer)
        self.assertNotIn('3일',answer)
        self.assertIn('담당 부서',answer)
        self.assertIn('취업규칙.pdf · 7쪽',answer)

    def test_known_how_to_is_paraphrased_and_cited(self):
        text='제20조(연차유급휴가) 직원은 연차휴가 신청서를 사용 3일 전까지 소속 부서장에게 제출한다.'
        context=self.context(text)
        draft=AnswerDraft(coverage='direct',summary='연차휴가 신청서를 사용 3일 전까지 부서장에게 제출하면 됩니다.',points=[
            {'text':'사용 3일 전까지 연차휴가 신청서를 부서장에게 제출해주세요.','source_id':'S1',
             'evidence_id':'E1'},
        ])
        answer=render_answer(context,draft,[])
        self.assertIn('확인된 내용\n- 사용 3일 전',answer)
        self.assertIn('[참고 문서]\n- 취업규칙.pdf · 7쪽 · 제20조(연차유급휴가)',answer)
        self.assertNotIn('직원은 연차휴가 신청서를',answer)

    def test_unrelated_leave_of_absence_procedure_is_not_annual_leave(self):
        context=self.context('제30조(휴직) 휴직 신청서를 담당자에게 제출한다.')
        draft=AnswerDraft(coverage='direct',summary='휴직 신청서를 제출하세요.',points=[
            {'text':'휴직 신청서를 담당자에게 제출하세요.','source_id':'S1','evidence_id':'E1'},
        ])
        self.assertIn('구체적인 신청 절차를 확인할 수 없습니다',render_answer(context,draft,[]))

    def test_each_point_must_match_its_own_evidence_numbers(self):
        context=self.context('교육비는 100만원까지 지원한다. 사택 보증금은 500만원이다.',question='교육비 지원 한도?')
        draft=AnswerDraft(coverage='direct',summary='교육비는 500만원까지 지원됩니다.',points=[
            {'text':'교육비는 500만원까지 지원됩니다.','source_id':'S1','evidence_id':'E1'},
        ])
        self.assertNotIn('500만원',render_answer(context,draft,[]))

    def test_unknown_source_id_and_reversed_exclusion_are_rejected(self):
        context=self.context('기숙사 비용은 지원 대상에서 제외한다.',question='기숙사 비용도 지원되나요?')
        for source_id,text in [('invented','기숙사 비용은 제외됩니다.'),('S1','기숙사 비용은 지원됩니다.')]:
            draft=AnswerDraft(coverage='direct',summary=text,points=[
                {'text':text,'source_id':source_id,'evidence_id':'E1'},
            ])
            self.assertNotIn(text,render_answer(context,draft,[]))

    def test_prompt_keeps_reference_ids_and_markdown_sections(self):
        context=self.context('제20조(연차유급휴가) 확인된 조항입니다.')
        text=OllamaClient.build_messages(context)[-1]['content']
        for title in ('## 사용자 정보','## 업무 조회 결과','## 참고 문서','### [S1] 취업규칙.pdf','## 현재 사용자 질문'):
            self.assertIn(title,text)
        self.assertEqual(text.count(context.question),1)
        self.assertEqual(text.count('확인된 조항입니다.'),1)

    def test_common_attendance_procedure_and_delegation_are_valid_annual_leave_references(self):
        context=self.context('제4조(근태계 제출) 각종 근태계의 제출은 전산시스템의 양식에 따라 전자결재를 통한 승인을 받는 방법으로 한다. '
                             '다만, 특별한 사정으로 인하여 본인이 직접 제출하지 못할 때에는 소속 부서원이 대리로 제출할 수 있다.')
        draft=AnswerDraft(coverage='partial',summary='신청 안내입니다.',points=[
            {'text':'전산시스템 양식으로 작성하고 전자결재 승인을 받으면 됩니다.','source_id':'S1','evidence_id':'E1'},
            {'text':'직접 제출하기 어려우면 소속 부서원이 대리 제출할 수 있습니다.','source_id':'S1','evidence_id':'E2'},
        ])
        answer=render_answer(context,draft,[])
        self.assertTrue(answer.startswith('공통 근태계 제출 기준에 따라'))
        self.assertIn('대리 제출',answer)
        self.assertIn('제4조(근태계 제출)',answer)
        self.assertNotIn('확인할 수 없습니다',answer)

    def test_mandatory_electronic_approval_is_not_lost_in_a_short_summary(self):
        context=self.context('제4조(근태계 제출) 각종 근태계의 제출은 전산시스템의 양식에 따라 전자결재를 통한 승인을 받는 방법으로 한다.')
        draft=AnswerDraft(coverage='partial',summary='전산시스템에서 진행합니다.',points=[
            {'text':'전산시스템의 양식을 사용합니다.','source_id':'S1','evidence_id':'E1'},
        ])
        answer=render_answer(context,draft,[])
        self.assertIn('전자결재 승인을 받으면 됩니다',answer)

    def test_unlimited_children_is_not_misread_as_an_exclusion(self):
        from app.agent.answers import is_supported
        self.assertTrue(is_supported('학자금은 무이자로 대부됩니다.',['학자금은 자녀 수 제한 없이 무이자로 대부한다.']))

    def test_domestic_rule_does_not_expand_to_overseas(self):
        context=self.context('제4조(국내대학교 학자금 대부) 국내대학교의 학자금은 자녀 수 제한 없이 무이자로 대부한다.',question='학자금은 무이자인가요?')
        draft=AnswerDraft(coverage='direct',summary='국내와 해외 모두 무이자입니다.',points=[
            {'text':'학자금은 무이자로 대부됩니다.','source_id':'S1','evidence_id':'E1'},
        ])
        answer=render_answer(context,draft,[])
        self.assertIn('국내대학교의 경우',answer)
        self.assertNotIn('해외',answer)

    def test_citation_does_not_pick_the_next_unrelated_article(self):
        from app.agent.answers import citation
        source=Source(document='규정.pdf',page=7,text='제20조(연차유급휴가) 연차휴가는 자유롭게 사용할 수 있다.\n제21조(특별유급휴가) 경조휴가를 준다.')
        self.assertIn('제20조(연차유급휴가)',citation(source,'연차휴가는 자유롭게 사용할 수 있다.'))
        self.assertNotIn('제21조',citation(source,'연차휴가는 자유롭게 사용할 수 있다.'))

    def test_special_leave_attachment_rule_is_not_annual_application_deadline(self):
        context=self.context('특별휴가, 헌혈휴가, 자녀돌봄휴가 증명서를 휴가신청시스템에 10일 이내 등록하며, 미등록 시 연차휴가로 변경한다.')
        draft=AnswerDraft(coverage='direct',summary='10일 이내 등록하세요.',points=[
            {'text':'증명서를 10일 이내 등록하고 미등록 시 연차휴가로 변경합니다.','source_id':'S1','evidence_id':'E1'},
        ])
        self.assertNotIn('10일',render_answer(context,draft,[]))


if __name__ == '__main__':
    unittest.main()
