from __future__ import annotations

import logging
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.config_loader import WholesaleConfig
from src.models import ScrapedProduct

logger = logging.getLogger(__name__)


class ScrapeError(Exception):
    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Scrape failed for {url}: {reason}")


class WholesaleScraper:
    """키즈빌리지 도매 사이트 스크래퍼.

    requests.Session으로 로그인 후 BeautifulSoup로 상품 정보를 추출한다.
    """

    def __init__(self, config: WholesaleConfig) -> None:
        self._config = config
        self._session = requests.Session()

    @property
    def session(self) -> requests.Session:
        return self._session

    def login(self) -> bool:
        """그누보드 기반 로그인 (login_check.php POST)."""
        login_url = self._config.login_url
        if not login_url:
            logger.warning("login_url not configured, skipping")
            return True

        form = self._config.login_form
        try:
            # Gnuboard login_check.php 엔드포인트로 POST
            check_url = login_url.replace("/login.php", "/login_check.php")
            payload = {
                form.id_field: self._config.username,
                form.pw_field: self._config.password,
                "url": "/shop/",
            }
            resp = self._session.post(check_url, data=payload, timeout=15)
            resp.raise_for_status()

            # 로그인 성공 여부: 상품 페이지 접근하여 로그인 상태 확인
            test_resp = self._session.get(
                self._config.base_url + "/shop/", timeout=15
            )
            if "login.php" in test_resp.url:
                logger.error("Login failed - still redirected to login page")
                return False

            logger.info("Login OK")
            return True
        except Exception as e:
            logger.error("Login failed: %s", e)
            return False

    def scrape_product(self, url: str) -> ScrapedProduct:
        """상품 페이지에서 정보 + 이미지 URL을 수집한다."""
        product_id = self._extract_product_id(url)

        try:
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            time.sleep(self._config.request_delay_seconds)

            # 로그인 페이지로 리다이렉트되었는지 확인
            if "login.php" in resp.url:
                raise ScrapeError(url, "Not logged in - redirected to login page")

            soup = BeautifulSoup(resp.text, "lxml")
            sel = self._config.selectors

            product_name = self._get_text(soup, sel.product_name)
            wholesale_price = self._get_attr(soup, sel.price, "value")
            brand = self._get_table_value(soup, "브랜드")
            colors = self._get_table_list(soup, "색상")
            sizes = self._get_table_list(soup, "사이즈")
            image_urls = self._get_image_urls(soup, sel.detail_images)

            logger.info(
                "Scraped %s: brand=%s, name=%s, price=%s원, %d sizes, %d colors, %d images",
                product_id, brand, product_name, wholesale_price,
                len(sizes), len(colors), len(image_urls),
            )

            return ScrapedProduct(
                product_id=product_id,
                product_name=product_name,
                wholesale_price=wholesale_price,
                brand=brand,
                sizes=sizes,
                colors=colors,
                image_urls=image_urls,
            )
        except ScrapeError:
            raise
        except Exception as e:
            raise ScrapeError(url, str(e)) from e

    # ─── BS4 추출 헬퍼 ──────────────────────────────────

    @staticmethod
    def _get_text(soup: BeautifulSoup, selector: str) -> str:
        if not selector:
            return ""
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
        logger.warning("  %s → NOT FOUND or empty", selector)
        return ""

    @staticmethod
    def _get_attr(soup: BeautifulSoup, selector: str, attr: str) -> str:
        if not selector:
            return ""
        el = soup.select_one(selector)
        if el:
            val = el.get(attr, "")
            if val:
                return str(val).strip()
        logger.warning("  %s[%s] → NOT FOUND or empty", selector, attr)
        return ""

    @staticmethod
    def _find_th(soup: BeautifulSoup, header_text: str):
        """<th> 중 header_text를 포함하는 첫 번째 요소를 찾는다."""
        for th in soup.find_all("th"):
            if header_text in th.get_text():
                return th
        return None

    @classmethod
    def _get_table_value(cls, soup: BeautifulSoup, header_text: str) -> str:
        th = cls._find_th(soup, header_text)
        if th:
            td = th.find_next_sibling("td")
            if td:
                text = td.get_text(strip=True)
                if text:
                    return text
        logger.warning("  th[%s] → NOT FOUND or empty", header_text)
        return ""

    @classmethod
    def _get_table_list(cls, soup: BeautifulSoup, header_text: str) -> list[str]:
        th = cls._find_th(soup, header_text)
        if th:
            td = th.find_next_sibling("td")
            if td:
                raw = td.get_text(strip=True)
                if raw:
                    return [v.strip() for v in raw.split("/") if v.strip()]
        logger.warning("  th[%s] list → NOT FOUND or empty", header_text)
        return []

    def _get_image_urls(self, soup: BeautifulSoup, selector: str) -> list[str]:
        if not selector:
            return []
        imgs = soup.select(selector)
        base_url = self._config.base_url
        urls: list[str] = []
        for img in imgs:
            src = img.get("src", "")
            if src:
                full_url = urljoin(base_url, src) if not src.startswith("http") else src
                urls.append(full_url)
        return urls

    @staticmethod
    def _extract_product_id(url: str) -> str:
        from src.models import CsvRow
        return CsvRow(url=url).product_id
