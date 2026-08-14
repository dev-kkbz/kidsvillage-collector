from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.scraper import BROWSER_USER_AGENT

logger = logging.getLogger(__name__)


class ImageDownloadError(RuntimeError):
    """상품 이미지가 한 장도 저장되지 않았을 때 발생한다."""


class ImageManager:
    """상품 이미지를 브라우저와 유사한 요청으로 내려받아 정리한다."""

    MIN_IMAGE_BYTES = 128

    def __init__(self, output_base_dir: str, session: requests.Session | None = None) -> None:
        self._base_dir = Path(output_base_dir)
        self._session = session or requests.Session()

    def get_product_dir(self, dir_name: str) -> Path:
        return self._base_dir / dir_name

    def download_images(
        self,
        dir_name: str,
        image_urls: list[str],
        *,
        referer_url: str,
    ) -> list[str]:
        """이미지 목록을 다운로드한다.

        - 정확한 상품 상세 URL을 Referer로 전송
        - 루트 Referer 및 Referer 없는 요청까지 순차 재시도
        - HTTP 성공이어도 HTML/오류 페이지면 이미지로 저장하지 않음
        - 한 장도 성공하지 못하면 ImageDownloadError 발생
        """
        if not image_urls:
            raise ImageDownloadError("상세 페이지에서 이미지 URL을 찾지 못했습니다.")

        product_dir = self.get_product_dir(dir_name)
        product_dir.mkdir(parents=True, exist_ok=True)

        existing = self._existing_images(product_dir)
        if existing and len(existing) >= len(image_urls):
            logger.info("[%s] Images already exist (%d), skipping download", dir_name, len(existing))
            return [str(p) for p in existing[:len(image_urls)]]

        result: list[str] = []
        failures: list[str] = []

        for idx, url in enumerate(image_urls, start=1):
            try:
                saved = self._download_one(
                    url=url,
                    product_dir=product_dir,
                    index=idx,
                    referer_url=referer_url,
                )
                result.append(str(saved))
                logger.info("[%s] Image %d saved: %s", dir_name, idx, saved.name)
            except Exception as e:
                reason = self._friendly_error(e)
                failures.append(f"{idx}: {url} -> {reason}")
                logger.warning("[%s] Failed image %d (%s): %s", dir_name, idx, url, reason)

        logger.info("[%s] Downloaded %d/%d images", dir_name, len(result), len(image_urls))

        if not result:
            details = " | ".join(failures[:3])
            if len(failures) > 3:
                details += f" | 외 {len(failures) - 3}건"
            raise ImageDownloadError(
                f"이미지 {len(image_urls)}개를 찾았지만 모두 다운로드에 실패했습니다. {details}"
            )

        if failures:
            logger.warning("[%s] Partial image failure: %d/%d failed", dir_name, len(failures), len(image_urls))

        return result

    def _download_one(
        self,
        *,
        url: str,
        product_dir: Path,
        index: int,
        referer_url: str,
    ) -> Path:
        referers = self._referer_candidates(referer_url)
        errors: list[str] = []

        for referer in referers:
            headers = {
                "User-Agent": BROWSER_USER_AGENT,
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
            }
            if referer:
                headers["Referer"] = referer

            try:
                with self._session.get(
                    url,
                    headers=headers,
                    timeout=(12, 60),
                    stream=True,
                    allow_redirects=True,
                ) as resp:
                    if resp.status_code >= 400:
                        snippet = self._response_snippet(resp)
                        raise requests.HTTPError(
                            f"HTTP {resp.status_code}; type={resp.headers.get('Content-Type', '')}; body={snippet}",
                            response=resp,
                        )

                    temp_path = product_dir / f".{index:02d}.part"
                    total = 0
                    prefix = bytearray()
                    try:
                        with open(temp_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=64 * 1024):
                                if not chunk:
                                    continue
                                if len(prefix) < 64:
                                    prefix.extend(chunk[: 64 - len(prefix)])
                                f.write(chunk)
                                total += len(chunk)
                    except Exception:
                        temp_path.unlink(missing_ok=True)
                        raise

                    extension = self._detect_extension(bytes(prefix), resp.headers.get("Content-Type", ""), url)
                    if total < self.MIN_IMAGE_BYTES or extension is None:
                        temp_path.unlink(missing_ok=True)
                        content_type = resp.headers.get("Content-Type", "")
                        preview = bytes(prefix).decode("utf-8", errors="replace")[:80]
                        raise ValueError(
                            f"이미지 응답이 아님: bytes={total}, type={content_type}, preview={preview!r}"
                        )

                    self._remove_index_variants(product_dir, index)
                    destination = product_dir / f"{index:02d}.{extension}"
                    os.replace(temp_path, destination)
                    return destination
            except Exception as e:
                label = referer or "<Referer 없음>"
                errors.append(f"Referer={label}: {e}")

        raise ImageDownloadError(" / ".join(errors))

    @staticmethod
    def _referer_candidates(referer_url: str) -> list[str]:
        candidates = [
            referer_url,
            "https://www.kidsvillage.co.kr/",
            "https://kidsvillage.co.kr/",
            "",
        ]
        result: list[str] = []
        for item in candidates:
            if item not in result:
                result.append(item)
        return result

    @staticmethod
    def _response_snippet(resp: requests.Response) -> str:
        try:
            data = resp.content[:160]
            return data.decode(resp.encoding or "utf-8", errors="replace").replace("\n", " ")
        except Exception:
            return ""

    @staticmethod
    def _detect_extension(prefix: bytes, content_type: str, url: str) -> str | None:
        if prefix.startswith(b"\xff\xd8\xff"):
            return "jpg"
        if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if prefix.startswith((b"GIF87a", b"GIF89a")):
            return "gif"
        if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
            return "webp"
        if prefix.startswith(b"BM"):
            return "bmp"
        if len(prefix) >= 12 and prefix[4:12] in {b"ftypavif", b"ftypavis"}:
            return "avif"

        normalized = content_type.split(";", 1)[0].strip().lower()
        by_type = {
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/webp": "webp",
            "image/bmp": "bmp",
            "image/avif": "avif",
        }
        if normalized in by_type and len(prefix) >= 8:
            return by_type[normalized]

        suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
        if normalized.startswith("image/") and suffix in {"jpg", "jpeg", "png", "gif", "webp", "bmp", "avif"}:
            return "jpg" if suffix == "jpeg" else suffix
        return None

    @staticmethod
    def _remove_index_variants(product_dir: Path, index: int) -> None:
        for ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp", "avif"):
            (product_dir / f"{index:02d}.{ext}").unlink(missing_ok=True)

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc)
        lower = text.lower()
        if any(token in lower for token in ("nameresolutionerror", "getaddrinfo failed", "failed to resolve")):
            return (
                "DNS 조회 실패. Windows DNS를 1.1.1.1 또는 8.8.8.8로 변경한 뒤 다시 실행하세요. "
                f"원문: {text}"
            )
        if "certificate_verify_failed" in lower or "sslcertverificationerror" in lower:
            return f"SSL 인증서 확인 실패. Windows 날짜/시간과 인증서 업데이트를 확인하세요. 원문: {text}"
        return text

    @classmethod
    def _existing_images(cls, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}
        files: list[Path] = []
        for file in directory.iterdir():
            if not file.is_file() or file.suffix.lower() not in image_exts:
                continue
            if file.stat().st_size < cls.MIN_IMAGE_BYTES:
                continue
            try:
                prefix = file.read_bytes()[:64]
            except OSError:
                continue
            if cls._detect_extension(prefix, "", str(file)) is None:
                logger.warning("Invalid existing image ignored: %s", file)
                continue
            files.append(file)
        return sorted(files, key=lambda p: (int(p.stem) if p.stem.isdigit() else 999999, p.name))
