@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [WONIT - 테스트 기록 초기화]
powershell -NoProfile -Command "Invoke-RestMethod -Uri 'http://127.0.0.1:5510/api/test/reset' -Method Post -ContentType 'application/json' -Body '{}' | ConvertTo-Json -Depth 4"
if errorlevel 1 echo [오류] 먼저 py mock_server.py 를 실행하세요.
pause
