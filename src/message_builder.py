from __future__ import annotations

import logging
from pathlib import Path

from src.models import ProcessedProduct

logger = logging.getLogger(__name__)


class MessageBuilder:
    """템플릿 기반으로 상품 전송용 메시지를 생성한다.

    가격은 CSV의 selling_price를 사용하며,
    스크래핑한 도매가는 포함하지 않는다.
    """

    DEFAULT_TEMPLATE = (
        "☑️ {brand} {product_name}\n"
        "\n"
        "- 가격\n"
        "{selling_price}\n"
        "\n"
        "- 컬러\n"
        "{colors}\n"
        "\n"
        "- 사이즈\n"
        "{sizes}\n"
    )

    def __init__(self, template_path: str) -> None:
        path = Path(template_path)
        if path.exists():
            self._template = path.read_text(encoding="utf-8")
        else:
            logger.warning("Template not found at %s, using default", template_path)
            self._template = self.DEFAULT_TEMPLATE

    def build(self, product: ProcessedProduct) -> str:
        """상품 데이터를 기반으로 메시지 문자열을 생성한다."""
        sizes_str = ",".join(product.sizes) if product.sizes else ""
        colors_str = " ".join(product.colors) if product.colors else ""

        message = self._template.format(
            brand=product.brand,
            product_name=product.product_name,
            selling_price=product.selling_price,
            sizes=sizes_str,
            colors=colors_str,
        )

        result = message.strip()

        logger.info("Message built for %s (%d chars)", product.product_id, len(result))
        return result
