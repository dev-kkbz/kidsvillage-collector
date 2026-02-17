from __future__ import annotations

import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class ImageManager:
    """상품 이미지를 URL에서 다운로드하여 상품 폴더에 정리한다."""

    def __init__(self, output_base_dir: str) -> None:
        self._base_dir = Path(output_base_dir)

    def get_product_dir(self, product_id: str) -> Path:
        return self._base_dir / product_id

    def download_images(
        self,
        product_id: str,
        image_urls: list[str],
        cookies: dict[str, str] | None = None,
    ) -> list[str]:
        """이미지 URL 리스트를 다운로드하여 상품 폴더에 저장한다.

        이미 같은 수의 이미지가 있으면 스킵한다.
        Returns: 로컬 파일 경로 리스트
        """
        product_dir = self.get_product_dir(product_id)
        product_dir.mkdir(parents=True, exist_ok=True)

        existing = self._existing_images(product_dir)
        if existing and len(existing) >= len(image_urls):
            logger.info("[%s] Images already exist (%d), skipping download", product_id, len(existing))
            return [str(p) for p in existing]

        session = requests.Session()
        if cookies:
            session.cookies.update(cookies)

        result: list[str] = []
        for idx, url in enumerate(image_urls, start=1):
            dest = product_dir / f"{idx:02d}.jpg"
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                result.append(str(dest))
                logger.debug("[%s] Downloaded %02d: %s", product_id, idx, url)
            except Exception as e:
                logger.warning("[%s] Failed to download image %d (%s): %s", product_id, idx, url, e)

        logger.info("[%s] Downloaded %d/%d images", product_id, len(result), len(image_urls))
        return result

    def has_images(self, product_id: str) -> bool:
        product_dir = self.get_product_dir(product_id)
        return bool(self._existing_images(product_dir))

    @staticmethod
    def _existing_images(directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
        return sorted(
            f for f in directory.iterdir()
            if f.is_file() and f.suffix.lower() in image_exts
        )
