@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [WONIT HR Assistant v7 - 규정집·채팅방 이력 통합 테스트]
echo [안내] 서버가 켜지면 Chrome에서 http://127.0.0.1:5510 을 열어주세요.
py -3 mock_server.py --port 5510
if errorlevel 1 pause
