from __future__ import annotations

import logging
from pathlib import Path

from src.models import ProcessedProduct

logger = logging.getLogger(__name__)


class MessageBuilder:
    """템플릿 기반으로 상품 전송용 메시지를 생성한다.

    가격은 도매가 + CSV margin으로 산출된 판매가를 사용한다.
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
        price_str = self._format_price(product.selling_price, product.option_prices)

        message = self._template.format(
            brand=product.brand,
            product_name=product.product_name,
            selling_price=price_str,
            sizes=sizes_str,
            colors=colors_str,
        )

        result = message.strip()

        logger.info("Message built for %s (%d chars)", product.product_id, len(result))
        return result

    @staticmethod
    def _format_price(selling_price: int, option_prices: list[int]) -> str:
        if not option_prices:
            return str(selling_price)
        extras = " / ".join(f"+{p}" for p in option_prices)
        return f"{selling_price} / {extras}"
