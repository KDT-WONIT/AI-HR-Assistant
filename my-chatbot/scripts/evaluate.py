"""질문 세트를 챗봇에 실제로 보내 품질을 점검하고 결과를 파일로 저장합니다.

    python -m scripts.evaluate                      # 서버 없이 앱을 직접 실행(기본). n8n 전송은 끕니다.
    python -m scripts.evaluate --base-url http://127.0.0.1:8000   # 이미 떠 있는 서버에 요청
    python -m scripts.evaluate --only pay-salary --only leave-days
    python -m scripts.evaluate --employee WON0002 --cases data/eval/cases.json

각 질문은 새 대화로 보내므로 앞선 질문이 영향을 주지 않습니다. 실제 Ollama·Chroma를 사용하므로 Ollama를 먼저 켜두세요.
결과는 data/eval/results_<시각>.md / .csv 로 저장됩니다. 기대 조건은 data/eval/cases.json 에서 고칠 수 있습니다.

조건 종류: expect_any(그룹마다 하나 이상 포함), expect_sources(출처 문서명에 하나 이상 포함), forbid(포함되면 실패),
expect_contact_depts / forbid_contact_depts(추천 담당자 부서), min_contacts, min_answer_chars, max_seconds.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / 'data' / 'eval' / 'cases.json'


def check(case: dict, result: dict) -> list[str]:
    """실패 사유 목록(비어 있으면 통과)."""
    problems = []
    answer = result['answer']
    if result.get('error'):
        return [f"요청 실패: {result['error']}"]
    for group in case.get('expect_any', []):
        if not any(term in answer for term in group):
            problems.append('답변에 없음: ' + ' / '.join(group))
    for term in case.get('forbid', []):
        if term in answer:
            problems.append(f'답변에 있으면 안 됨: {term}')
    wanted = case.get('expect_sources')
    if wanted and not any(term in source for term in wanted for source in result['sources']):
        problems.append('출처 문서에 없음: ' + ' / '.join(wanted))
    depts = result['contact_depts']
    if case.get('expect_contact_depts') and not any(dept in depts for dept in case['expect_contact_depts']):
        problems.append(f"담당자 부서가 기대와 다름: {depts or '없음'} (기대: {' / '.join(case['expect_contact_depts'])})")
    for dept in case.get('forbid_contact_depts', []):
        if dept in depts:
            problems.append(f'있으면 안 되는 담당자 부서: {dept}')
    if len(depts) < case.get('min_contacts', 0):
        problems.append(f"담당자 안내가 {case['min_contacts']}명 미만")
    if len(answer) < case.get('min_answer_chars', 0):
        problems.append(f"답변이 너무 짧음({len(answer)}자 < {case['min_answer_chars']}자)")
    if result['seconds'] > case.get('max_seconds', 90):
        problems.append(f"응답이 느림({result['seconds']:.0f}초)")
    return problems


def summarize(payload: dict, seconds: float) -> dict:
    contacts = payload.get('contact_escalation', {}).get('contacts', [])
    return {
        'answer': payload.get('answer', ''), 'status': payload.get('status', ''),
        'sources': [f"{item.get('document', '')} {item.get('page') or ''}쪽".strip() for item in payload.get('sources', [])],
        'contact_depts': [item['employee'].get('department') or '' for item in contacts],
        'contact_names': [item['employee'].get('name') or '' for item in contacts],
        'seconds': seconds, 'error': None,
    }


def make_client(base_url: str | None):
    import httpx
    if base_url:
        return httpx.Client(base_url=base_url, timeout=300), None
    # 서버 없이 앱을 직접 실행합니다. 평가 질문이 n8n 시트에 쌓이지 않도록 웹훅 주소를 비웁니다.
    os.environ['N8N_WEBHOOK_URL'] = ''
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from app.main import app
    context = TestClient(app, base_url='http://eval')
    return context.__enter__(), context


def ask(client, employee: str, question: str) -> dict:
    started = time.monotonic()
    try:
        created = client.post('/api/conversations', json={'employee_id': employee})
        created.raise_for_status()
        conversation_id = created.json()['id']
        response = client.post('/api/chat', json={'employee_id': employee, 'conversation_id': conversation_id,
                                                  'message': question})
        seconds = time.monotonic() - started
        if response.status_code != 200:
            detail = response.json().get('detail', response.text) if response.headers.get('content-type', '').startswith('application/json') else response.text
            return {'answer': '', 'status': '', 'sources': [], 'contact_depts': [], 'contact_names': [],
                    'seconds': seconds, 'error': f'HTTP {response.status_code}: {detail}'}
        return summarize(response.json(), seconds)
    except Exception as exc:  # 서버 연결 실패 등
        return {'answer': '', 'status': '', 'sources': [], 'contact_depts': [], 'contact_names': [],
                'seconds': time.monotonic() - started, 'error': f'{type(exc).__name__}: {exc}'}


def write_reports(rows: list[dict], directory: Path) -> tuple[Path, Path]:
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    directory.mkdir(parents=True, exist_ok=True)
    csv_path, md_path = directory / f'results_{stamp}.csv', directory / f'results_{stamp}.md'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['id', '결과', '질문', '답변', '상태', '출처', '추천 담당자', '초', '실패 사유'])
        for row in rows:
            writer.writerow([row['id'], row['verdict'], row['question'], row['answer'], row['status'], ' | '.join(row['sources']),
                             ' | '.join(f'{d} {n}' for d, n in zip(row['contact_depts'], row['contact_names'])),
                             f"{row['seconds']:.1f}", ' ; '.join(row['problems'])])
    passed = sum(row['verdict'] == 'PASS' for row in rows)
    lines = [f'# 챗봇 평가 결과 ({stamp})', '', f'통과 {passed} / {len(rows)}', '']
    for row in rows:
        lines += [f"## [{row['verdict']}] {row['id']} — {row['question']}", f"- 소요 {row['seconds']:.1f}초 · 상태 {row['status'] or '-'}",
                  f"- 출처: {', '.join(row['sources']) or '없음'}",
                  f"- 추천 담당자: {', '.join(f'{d} {n}' for d, n in zip(row['contact_depts'], row['contact_names'])) or '없음'}"]
        if row['problems']:
            lines.append('- 실패 사유: ' + ' ; '.join(row['problems']))
        lines += ['', '```', row['answer'] or '(답변 없음)', '```', '']
    md_path.write_text('\n'.join(lines), encoding='utf-8')
    return csv_path, md_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='챗봇 답변 품질 평가')
    parser.add_argument('--cases', type=Path, default=DEFAULT_CASES)
    parser.add_argument('--base-url', help='이미 실행 중인 서버 주소. 생략하면 서버 없이 앱을 직접 실행합니다.')
    parser.add_argument('--employee', help='질문할 사번(기본: cases.json의 employee_id)')
    parser.add_argument('--only', action='append', help='이 id의 질문만 실행(여러 번 지정 가능)')
    args = parser.parse_args(argv)

    spec = json.loads(args.cases.read_text(encoding='utf-8'))
    employee = args.employee or spec.get('employee_id', 'WON0001')
    cases = [case for case in spec['cases'] if not args.only or case['id'] in args.only]
    if not cases:
        print('실행할 질문이 없습니다. --only 값과 cases.json의 id를 확인하세요.')
        return 2
    client, context = make_client(args.base_url)
    rows = []
    try:
        for number, case in enumerate(cases, 1):
            result = ask(client, case.get('employee_id', employee), case['question'])
            problems = check(case, result)
            row = {'id': case['id'], 'question': case['question'], 'verdict': 'FAIL' if problems else 'PASS',
                   'problems': problems, **result}
            rows.append(row)
            print(f"[{number}/{len(cases)}] {row['verdict']} {case['id']} ({result['seconds']:.1f}초)"
                  + ('' if not problems else '\n    - ' + '\n    - '.join(problems)), flush=True)
    finally:
        if context is not None:
            context.__exit__(None, None, None)
        else:
            client.close()
    csv_path, md_path = write_reports(rows, args.cases.parent)
    passed = sum(row['verdict'] == 'PASS' for row in rows)
    average = sum(row['seconds'] for row in rows) / len(rows)
    print(f'\n통과 {passed}/{len(rows)} · 평균 {average:.1f}초\n결과: {md_path}\n      {csv_path}')
    return 0 if passed == len(rows) else 1


if __name__ == '__main__':
    sys.exit(main())
