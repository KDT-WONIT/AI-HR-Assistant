# v7 로컬 자동 테스트

Windows PowerShell / PyCharm Terminal에서 프로젝트 루트 기준:

```powershell
py -m unittest discover -s tests -p "test_local_api.py" -v
```

16개 테스트: 사번 조회, 대화 맥락, 채팅방 이력/검색, PDF 59개, 질문 목록 132개, 출처 URL, SSE, 연락처, 만족도 등.

테스트는 휘발성 Store를 사용하여 사용자가 저장한 `test_storage/conversations.json`을 변경하지 않습니다.
