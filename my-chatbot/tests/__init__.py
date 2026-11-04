"""테스트 패키지. 전체: python -m tests / 개별: python -m unittest tests.test_api -v"""
import os

# 테스트가 프로젝트 .env의 실제 외부 웹훅으로 데이터를 보내지 않도록 차단합니다.
# 웹훅 통합 검사는 임시 로컬 수신기 주소로 settings를 명시적으로 교체합니다.
os.environ['N8N_WEBHOOK_URL'] = ''
# 기존 검사는 전송 결과(sent/failed)를 바로 확인하므로 동기 전송으로 고정합니다. 비동기 전송은 별도 검사에서 켭니다.
os.environ['N8N_ASYNC'] = 'false'
