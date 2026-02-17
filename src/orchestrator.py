from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from src.config_loader import SystemConfig
from src.image_manager import ImageManager
from src.message_builder import MessageBuilder
from src.models import CsvRow, ProcessedProduct, ProductResult, ProductStatus
from src.scraper import ScrapeError, WholesaleScraper

logger = logging.getLogger(__name__)


class ProductOrchestrator:
    """전체 파이프라인을 제어한다.

    CSV 로드 → 로그인 → 상품별 순차 처리 → summary 출력
    """

    def __init__(self, config: SystemConfig) -> None:
        self._config = config
        self._output_dir = Path(config.paths.output_dir)

        self._scraper = WholesaleScraper(config.wholesale)
        self._image_mgr = ImageManager(config.paths.output_dir)
        self._message_builder = MessageBuilder(config.paths.message_template)

        self._results: list[ProductResult] = []

    def run(self) -> list[ProductResult]:
        """전체 파이프라인을 실행한다."""
        rows = self._load_csv()
        if not rows:
            logger.warning("No products in CSV")
            return []

        logger.info("Loaded %d products from CSV", len(rows))

        self._scraper.start()
        try:
            if not self._scraper.login():
                logger.critical("Login failed, aborting")
                return []

            for idx, row in enumerate(rows, start=1):
                logger.info("Processing %d/%d: %s", idx, len(rows), row.url)
                result = self._process_single(row)
                self._results.append(result)

                status_icon = "OK" if result.status == ProductStatus.DONE else "FAIL"
                logger.info(
                    "[%s] %s → %s", status_icon, result.product_id, result.status.value
                )
        finally:
            self._scraper.close()

        self._write_summary()
        self._log_final_stats()

        return self._results

    def _process_single(self, row: CsvRow) -> ProductResult:
        """단일 상품을 처리한다."""
        product_id = row.product_id

        # Phase 1: 상품 정보 수집
        try:
            scraped = self._scraper.scrape_product(row.url)
        except ScrapeError as e:
            logger.error("Scrape failed for %s: %s", row.url, e.reason)
            return ProductResult(product_id, row.url, ProductStatus.FAILED_SCRAPE, str(e))
        except Exception as e:
            logger.error("Unexpected scrape error for %s: %s", row.url, e)
            return ProductResult(product_id, row.url, ProductStatus.FAILED_SCRAPE, str(e))

        # Phase 2: 이미지 다운로드
        try:
            cookies = self._scraper.get_cookies_dict()
            local_images = self._image_mgr.download_images(
                product_id, scraped.image_urls, cookies
            )
        except Exception as e:
            logger.error("Image download failed for %s: %s", product_id, e)
            return ProductResult(product_id, row.url, ProductStatus.FAILED_IMAGE, str(e))

        # Phase 3: 메시지 생성 + 파일 기록
        try:
            processed = ProcessedProduct(
                product_id=scraped.product_id,
                product_name=scraped.product_name,
                wholesale_price=scraped.wholesale_price,
                selling_price=row.selling_price,
                brand=scraped.brand,
                sizes=scraped.sizes,
                colors=scraped.colors,
                local_image_paths=local_images,
            )
            message = self._message_builder.build(processed)
            processed.message = message

            message_path = self._image_mgr.get_product_dir(product_id) / "message.txt"
            message_path.write_text(message, encoding="utf-8")
            logger.info("Message saved to %s", message_path)
        except Exception as e:
            logger.error("Message build failed for %s: %s", product_id, e)
            return ProductResult(product_id, row.url, ProductStatus.FAILED_MESSAGE, str(e))

        return ProductResult(product_id, row.url, ProductStatus.DONE)

    def _load_csv(self) -> list[CsvRow]:
        csv_path = Path(self._config.paths.input_csv)
        if not csv_path.exists():
            logger.error("CSV file not found: %s", csv_path)
            return []

        rows: list[CsvRow] = []
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for line_num, record in enumerate(reader, start=2):
                url = record.get("url", "").strip()
                price_str = record.get("selling_price", "").strip()

                if not url:
                    logger.warning("Line %d: empty url, skipping", line_num)
                    continue
                try:
                    selling_price = int(price_str)
                except (ValueError, TypeError):
                    logger.warning(
                        "Line %d: invalid selling_price '%s', skipping", line_num, price_str
                    )
                    continue

                rows.append(CsvRow(url=url, selling_price=selling_price))

        return rows

    def _write_summary(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = self._output_dir / "summary.txt"

        succeeded = [r for r in self._results if r.status == ProductStatus.DONE]
        failed = [r for r in self._results if r.status != ProductStatus.DONE]

        lines = [
            f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"전체: {len(self._results)}  성공: {len(succeeded)}  실패: {len(failed)}",
            "",
            "--- 성공 ---",
        ]
        for r in succeeded:
            lines.append(f"  {r.product_id} ({r.url})")

        if failed:
            lines.append("")
            lines.append("--- 실패 ---")
            for r in failed:
                lines.append(f"  {r.product_id} [{r.status.value}] {r.error}")
                lines.append(f"    URL: {r.url}")

        summary_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Summary written to %s", summary_path)

    def _log_final_stats(self) -> None:
        total = len(self._results)
        ok = sum(1 for r in self._results if r.status == ProductStatus.DONE)
        fail = total - ok
        logger.info("=== DONE: %d/%d succeeded, %d failed ===", ok, total, fail)
