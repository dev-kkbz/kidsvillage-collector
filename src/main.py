from __future__ import annotations

import argparse
import logging
import sys

from src.config_loader import load_config
from src.models import ProductStatus
from src.orchestrator import ProductOrchestrator


def main() -> int:
    args = _parse_args()
    _setup_logging(args.log_level)

    logger = logging.getLogger(__name__)
    logger.info("Starting product-manager")

    config = load_config(args.config, args.credentials)
    orchestrator = ProductOrchestrator(config)
    results = orchestrator.run()

    if not results:
        return 2

    all_ok = all(r.status == ProductStatus.DONE for r in results)
    return 0 if all_ok else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="product-manager",
        description="도매 사이트 상품 수집 및 메시지 생성",
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="설정 파일 경로 (기본: config/settings.yaml)",
    )
    parser.add_argument(
        "--credentials",
        default="config/credentials.yaml",
        help="인증 정보 파일 경로 (기본: config/credentials.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="로그 레벨 (기본: INFO)",
    )
    return parser.parse_args()


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


if __name__ == "__main__":
    sys.exit(main())
