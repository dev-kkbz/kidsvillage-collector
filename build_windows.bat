@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   키즈빌리지 상품 수집기 - Windows 빌드
echo ============================================
echo.

where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON=py -3.12"
) else (
    set "PYTHON=python"
)

%PYTHON% --version
if errorlevel 1 goto :error

if not exist ".venv" (
    echo [1/6] 가상환경 생성 중...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

call .venv\Scripts\activate.bat

echo [2/6] 의존성 설치 중...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :error

echo [3/6] 테스트 실행 중...
python -m unittest discover -s tests -v
if errorlevel 1 goto :error

echo [4/6] EXE 빌드 중...
python -m PyInstaller build.spec --distpath dist --workpath build_temp --clean -y
if errorlevel 1 goto :error

echo [5/6] 배포 폴더 생성 중...
if exist release rmdir /s /q release
mkdir release\KidsVillage_Collector
copy /y dist\KidsVillage_Collector.exe release\KidsVillage_Collector\ >nul
copy /y docs\USER_GUIDE.md release\KidsVillage_Collector\사용설명서.md >nul
copy /y input_example.csv release\KidsVillage_Collector\ >nul
copy /y .credentials.yaml.example release\KidsVillage_Collector\로그인설정_예시.yaml >nul

echo [6/6] ZIP 생성 중...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'release\KidsVillage_Collector\*' -DestinationPath 'release\KidsVillage_Collector_Windows.zip' -Force"
if errorlevel 1 goto :error

rmdir /s /q build_temp 2>nul

echo.
echo ============================================
echo   빌드 완료
echo   release\KidsVillage_Collector_Windows.zip
echo ============================================
pause
exit /b 0

:error
echo.
echo 빌드에 실패했습니다. 위 오류 내용을 확인하세요.
pause
exit /b 1
