import unittest

from app.agent.emphasis import emphasize, strip_emphasis


class EmphasisTests(unittest.TestCase):
    def test_bolds_amounts_periods_and_articles(self):
        text = emphasize('일비는 1일 50,000원이며 제19조에 따라 30일간 전액 지급합니다.')
        self.assertIn('**50,000원**', text)
        self.assertIn('**제19조**', text)
        self.assertIn('**30일**', text)

    def test_skips_references_tables_years_and_existing_bold(self):
        text = '요약 2025년 개정\n\n[참고 문서]\n- 여비규정.pdf · 5쪽 · 제5조\n\n| 직급 | 3,000원 |\n이미 **10일** 5일'
        out = emphasize(text)
        self.assertNotIn('**2025', out)
        self.assertIn('- 여비규정.pdf · 5쪽 · 제5조', out)
        self.assertIn('| 직급 | 3,000원 |', out)
        self.assertNotIn('**5일**', out)

    def test_strip_and_idempotent(self):
        once = emphasize('휴가는 15일입니다.')
        self.assertEqual(emphasize(once), once)
        self.assertEqual(strip_emphasis(once), '휴가는 15일입니다.')

    def test_section_titles_are_unified_as_bold_braces(self):
        out = emphasize('요약입니다.\n\n확인된 내용\n- 항목\n\n[참고 문서]\n- a.pdf · 1쪽\n\n추가 안내\n문의하세요.\n\n다음 단계\n확인하세요.')
        for title in ('확인된 내용', '참고 문서', '추가 안내', '다음 단계'):
            self.assertIn('**{' + title + '}**', out)
        self.assertEqual(emphasize(out), out)


if __name__ == '__main__':
    unittest.main()
