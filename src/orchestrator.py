from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.config_loader import SystemConfig
from src.image_manager import ImageManager
from src.message_builder import MessageBuilder
from src.models import CsvRow, ProcessedProduct, ProductResult, ProductStatus, make_dir_name
from src.scraper import ScrapeError, WholesaleScraper

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]


class ProductOrchestrator:
    """전체 파이프라인을 제어한다.

    CSV 로드 → 로그인 → 상품별 순차 처리 → summary 출력
    """

    def __init__(
        self,
        config: SystemConfig,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._config = config
        self._output_dir = Path(config.paths.output_dir)
        self._on_progress = on_progress

        self._scraper = WholesaleScraper(config.wholesale)
        self._image_mgr = ImageManager(
            config.paths.output_dir,
            session=self._scraper.session,
        )
        self._message_builder = MessageBuilder(config.paths.message_template)

        self._results: list[ProductResult] = []

    def run(self) -> list[ProductResult]:
        """전체 파이프라인을 실행한다."""
        rows = self._load_csv()
        if not rows:
            logger.warning("No products in CSV")
            return []

        logger.info("Loaded %d products from CSV", len(rows))

        if not self._scraper.login():
            logger.critical("Login failed, aborting")
            return []

        total = len(rows)
        for idx, row in enumerate(rows, start=1):
            logger.info("Processing %d/%d: %s", idx, total, row.url)

            if self._on_progress:
                self._on_progress(idx, total, row.product_id)

            result = self._process_single(row, seq=idx)
            self._results.append(result)

            status_icon = "OK" if result.status == ProductStatus.DONE else "FAIL"
            logger.info(
                "[%s] %s → %s", status_icon, result.product_id, result.status.value
            )

        self._write_summary()
        self._write_combined_messages()
        self._log_final_stats()

        return self._results

    def _process_single(self, row: CsvRow, *, seq: int = 0) -> ProductResult:
        """단일 상품을 처리한다."""
        product_id = row.product_id

        # Phase 1: 상품 정보 수집
        try:
            scraped = self._scraper.scrape_product(row.url)
        except ScrapeError as e:
            logger.error("Scrape failed for %s: %s", row.url, e.reason)
            return ProductResult(product_id, row.url, ProductStatus.FAILED_SCRAPE, str(e), seq=seq)
        except Exception as e:
            logger.error("Unexpected scrape error for %s: %s", row.url, e)
            return ProductResult(product_id, row.url, ProductStatus.FAILED_SCRAPE, str(e), seq=seq)

        dir_name = make_dir_name(scraped.brand, scraped.product_name, seq or None)
        wholesale_int = self._parse_price(scraped.wholesale_price)
        selling_price = wholesale_int + row.margin

        # Phase 2: 이미지 다운로드
        try:
            local_images = self._image_mgr.download_images(
                dir_name, scraped.image_urls
            )
        except Exception as e:
            logger.error("Image download failed for %s: %s", product_id, e)
            return ProductResult(
                product_id, row.url, ProductStatus.FAILED_IMAGE, str(e),
                brand=scraped.brand, product_name=scraped.product_name,
                wholesale_price=wholesale_int, selling_price=selling_price,
                seq=seq,
            )

        # Phase 3: 메시지 생성 + 파일 기록
        try:
            processed = ProcessedProduct(
                product_id=scraped.product_id,
                product_name=scraped.product_name,
                wholesale_price=scraped.wholesale_price,
                selling_price=selling_price,
                brand=scraped.brand,
                sizes=scraped.sizes,
                colors=scraped.colors,
                option_prices=scraped.option_prices,
                local_image_paths=local_images,
            )
            message = self._message_builder.build(processed)
            processed.message = message

            message_path = self._image_mgr.get_product_dir(dir_name) / "message.txt"
            message_path.write_text(message, encoding="utf-8")
            logger.info("Message saved to %s", message_path)
        except Exception as e:
            logger.error("Message build failed for %s: %s", product_id, e)
            return ProductResult(
                product_id, row.url, ProductStatus.FAILED_MESSAGE, str(e),
                brand=scraped.brand, product_name=scraped.product_name,
                wholesale_price=wholesale_int, selling_price=selling_price,
                seq=seq,
            )

        return ProductResult(
            product_id, row.url, ProductStatus.DONE,
            brand=scraped.brand, product_name=scraped.product_name,
            wholesale_price=wholesale_int, selling_price=selling_price,
            seq=seq,
        )

    @staticmethod
    def _parse_price(price_str: str) -> int:
        """가격 문자열에서 숫자만 추출하여 int로 변환한다."""
        digits = "".join(c for c in price_str if c.isdigit())
        return int(digits) if digits else 0

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
                margin_str = record.get("margin", "").strip()

                if not url:
                    logger.warning("Line %d: empty url, skipping", line_num)
                    continue
                try:
                    margin = int(margin_str)
                except (ValueError, TypeError):
                    logger.warning(
                        "Line %d: invalid margin '%s', skipping",
                        line_num, margin_str,
                    )
                    continue

                rows.append(CsvRow(url=url, margin=margin))

        return rows

    def _write_summary(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = self._output_dir / "summary.txt"

        succeeded = [r for r in self._results if r.status == ProductStatus.DONE]
        failed = [r for r in self._results if r.status != ProductStatus.DONE]

        lines = [
            "=" * 60,
            f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"  전체: {len(self._results)}건  |  성공: {len(succeeded)}건  |  실패: {len(failed)}건",
            "=" * 60,
            "",
        ]

        if succeeded:
            lines.append("[ 성공 ]")
            lines.append("-" * 60)
            for r in succeeded:
                lines.append(f"  {r.brand} {r.product_name}")
                lines.append(f"    폴더: {r.dir_name}")
                lines.append(
                    f"    도매가: {r.wholesale_price:,}원  →  판매가: {r.selling_price:,}원  |  마진: {r.margin:,}원"
                )
                lines.append("")

        if failed:
            lines.append("[ 실패 ]")
            lines.append("-" * 60)
            for r in failed:
                label = f"{r.brand} {r.product_name}".strip() or r.product_id
                lines.append(f"  {label}  [{r.status.value}]")
                lines.append(f"    URL: {r.url}")
                if r.error:
                    lines.append(f"    오류: {r.error}")
                lines.append("")

        summary_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Summary written to %s", summary_path)

    def _write_combined_messages(self) -> None:
        """성공한 상품들의 message.txt를 하나로 합쳐 messages.txt로 저장한다."""
        succeeded = [r for r in self._results if r.status == ProductStatus.DONE]
        if not succeeded:
            return

        sections: list[str] = []
        for r in succeeded:
            msg_path = self._image_mgr.get_product_dir(r.dir_name) / "message.txt"
            if not msg_path.exists():
                continue
            body = msg_path.read_text(encoding="utf-8").strip()
            header = f"{'=' * 40} [{r.seq:03d}]"
            sections.append(f"{header}\n\n{body}")

        if not sections:
            return

        combined_path = self._output_dir / "messages.txt"
        combined_path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
        logger.info("Combined messages written to %s", combined_path)

    def _log_final_stats(self) -> None:
        total = len(self._results)
        ok = sum(1 for r in self._results if r.status == ProductStatus.DONE)
        fail = total - ok
        logger.info("=== DONE: %d/%d succeeded, %d failed ===", ok, total, fail)
