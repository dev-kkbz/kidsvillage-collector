@echo off
chcp 65001 >nul
echo ============================================
echo   키즈빌리지 상품 수집기 - Windows 빌드
echo ============================================
echo.

REM Python 가상환경 생성 + 의존성 설치
if not exist ".venv" (
    echo [1/4] 가상환경 생성 중...
    python -m venv .venv
)

echo [2/4] 의존성 설치 중...
call .venv\Scripts\activate.bat
pip install -r requirements.txt pyinstaller >nul 2>&1

echo [3/4] 실행파일 빌드 중...
pyinstaller build.spec --distpath dist --workpath build_temp --clean -y

echo [4/4] 정리 중...
rmdir /s /q build_temp 2>nul

echo.
echo ============================================
echo   빌드 완료: dist\KidsVillage_Collector.exe
echo ============================================
pause
