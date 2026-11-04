# 프로젝트 내부 임베딩 모델

최초 한 번, 프로젝트 최상위 폴더에서 다음을 실행하세요.

```powershell
.\.venv\Scripts\python.exe -m employee_tools.prepare_model
```

규정 DB와 같은 BGE-M3 개정본을 `models/bge-m3`에 내려받습니다.
최초 다운로드에는 인터넷 연결이 필요합니다. 이후에는 내부 모델 파일만 사용합니다.
다운로드 후에는 이 models 폴더도 함께 옮기면 다시 받을 필요가 없습니다.
