@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [WONIT HR Assistant v7 - 로컬 테스트 서버]
echo.
py -3 mock_server.py --port 5510
if errorlevel 1 (
  echo.
  echo [실행 오류] Python이 설치되어 있는지, 이미 포트 5510을 사용 중인지 확인하세요.
  pause
)
