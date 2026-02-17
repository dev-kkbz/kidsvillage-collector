"""PyInstaller 번들 환경과 일반 실행 환경 모두에서 리소스 경로를 찾는 유틸리티."""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """PyInstaller로 빌드된 실행파일 내부인지 확인한다."""
    return getattr(sys, "frozen", False)


def resource_path(relative_path: str) -> Path:
    """번들 내부 리소스 또는 개발 환경의 상대 경로를 반환한다.

    PyInstaller --onefile 모드에서는 sys._MEIPASS 아래에 리소스가 풀린다.
    일반 실행에서는 프로젝트 루트 기준 상대 경로를 그대로 사용한다.
    """
    if is_frozen():
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(".")
    return base / relative_path
