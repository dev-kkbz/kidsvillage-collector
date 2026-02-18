#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# tkinter 의존성 확인
if ! python3 -c "import tkinter" 2>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo "❌ tkinter가 설치되어 있지 않습니다."
    echo "   다음 명령어로 설치해주세요:"
    echo ""
    echo "   brew install python-tk@${PY_VER}"
    echo ""
    exit 1
fi

# 가상환경 생성 (최초 1회)
if [ ! -d ".venv" ]; then
    echo "📦 가상환경 생성 중..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# 의존성 설치 (최초 1회)
if [ ! -f ".venv/.deps_installed" ]; then
    echo "📦 의존성 설치 중..."
    pip install -q -r requirements.txt
    touch .venv/.deps_installed
fi

python3 run.py
