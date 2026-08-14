"""PyInstaller 번들 환경과 일반 실행 환경의 경로 유틸리티."""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """PyInstaller로 빌드된 실행 파일 내부인지 확인한다."""
    return bool(getattr(sys, "frozen", False))


def application_dir() -> Path:
    """사용자가 보는 프로그램 폴더를 반환한다.

    - EXE: 실행 파일이 있는 폴더
    - 소스 실행: 프로젝트 루트
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(relative_path: str) -> Path:
    """번들 내부 리소스 또는 프로젝트 루트의 리소스 경로를 반환한다."""
    if is_frozen():
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = application_dir()
    return base / relative_path
