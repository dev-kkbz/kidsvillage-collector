from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class ProductStatus(Enum):
    INIT = "INIT"
    SCRAPED = "SCRAPED"
    IMAGES_SAVED = "IMAGES_SAVED"
    MESSAGE_BUILT = "MESSAGE_BUILT"
    DONE = "DONE"
    FAILED_SCRAPE = "FAILED_SCRAPE"
    FAILED_IMAGE = "FAILED_IMAGE"
    FAILED_MESSAGE = "FAILED_MESSAGE"


@dataclass
class CsvRow:
    url: str
    selling_price: int

    @property
    def product_id(self) -> str:
        """URL에서 상품 식별자를 추출한다.

        URL 쿼리 파라미터 중 it_id, product_no 등을 우선 사용하고,
        없으면 URL 경로의 마지막 세그먼트를 사용한다.
        """
        parsed = urlparse(self.url)
        qs = parse_qs(parsed.query)
        for key in ("it_id", "product_no", "id"):
            if key in qs:
                return qs[key][0]
        path_parts = Path(parsed.path).parts
        if path_parts:
            stem = Path(path_parts[-1]).stem
            if stem:
                return stem
        return str(abs(hash(self.url)))


@dataclass
class ScrapedProduct:
    product_id: str
    product_name: str
    wholesale_price: str
    brand: str = ""
    sizes: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)


@dataclass
class ProcessedProduct:
    product_id: str
    product_name: str
    wholesale_price: str
    selling_price: int
    brand: str = ""
    sizes: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    local_image_paths: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class ProductResult:
    product_id: str
    url: str
    status: ProductStatus
    error: str = ""
