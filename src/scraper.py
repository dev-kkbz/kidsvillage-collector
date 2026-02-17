from __future__ import annotations

import logging
import time
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

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

    Selenium으로 로그인 후 상품 페이지에서 정보와 이미지 URL을 추출한다.
    """

    def __init__(self, config: WholesaleConfig) -> None:
        self._config = config
        self._driver: webdriver.Chrome | None = None

    def start(self) -> None:
        options = Options()
        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=options)
        self._driver.implicitly_wait(5)
        logger.info("Browser started")

    def login(self) -> bool:
        """그누보드 기반 로그인."""
        if not self._driver:
            raise RuntimeError("Browser not started")

        login_url = self._config.login_url
        if not login_url:
            logger.warning("login_url not configured, skipping")
            return True

        form = self._config.login_form
        try:
            self._driver.get(login_url)
            wait = WebDriverWait(self._driver, 10)

            id_input = wait.until(EC.presence_of_element_located((By.NAME, form.id_field)))
            id_input.clear()
            id_input.send_keys(self._config.username)

            pw_input = self._driver.find_element(By.NAME, form.pw_field)
            pw_input.clear()
            pw_input.send_keys(self._config.password)
            pw_input.submit()
            time.sleep(2)

            if "login" in self._driver.current_url.lower():
                logger.error("Login failed - still on login page")
                return False

            logger.info("Login OK → %s", self._driver.current_url)
            return True
        except Exception as e:
            logger.error("Login failed: %s", e)
            return False

    def scrape_product(self, url: str) -> ScrapedProduct:
        """상품 페이지에서 정보 + 이미지 URL을 수집한다."""
        if not self._driver:
            raise RuntimeError("Browser not started")

        product_id = self._extract_product_id(url)

        try:
            self._driver.get(url)
            time.sleep(self._config.request_delay_seconds)

            sel = self._config.selectors

            # 상품명: <strong id="sit_title">마인드후드남방</strong>
            product_name = self._get_text(sel.product_name, "상품명 없음")

            # 도매가: <input type="hidden" id="it_price" value="21000">
            wholesale_price = self._get_attr(sel.price, "value", "0")

            # 브랜드 / 색상 / 사이즈: 상품 정보 테이블 <th>→<td> 에서 추출
            brand = self._get_table_value("브랜드")
            colors = self._get_table_list("색상")
            sizes = self._get_table_list("사이즈")

            # 이미지: #sit_inf_explan img의 src
            image_urls = self._get_image_urls(sel.detail_images)

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

    def get_cookies_dict(self) -> dict[str, str]:
        """현재 Selenium 세션의 쿠키를 requests 호환 dict로 반환한다."""
        if not self._driver:
            return {}
        return {c["name"]: c["value"] for c in self._driver.get_cookies()}

    def close(self) -> None:
        if self._driver:
            self._driver.quit()
            self._driver = None
            logger.info("Browser closed")

    # ─── 요소 추출 헬퍼 ─────────────────────────────────

    def _get_text(self, selector: str, default: str = "") -> str:
        if not selector or not self._driver:
            return default
        try:
            el = self._driver.find_element(By.CSS_SELECTOR, selector)
            text = el.text.strip()
            if text:
                logger.debug("  %s → '%s'", selector, text)
                return text
            logger.warning("  %s → element found but empty", selector)
            return default
        except Exception:
            logger.warning("  %s → NOT FOUND", selector)
            return default

    def _get_attr(self, selector: str, attr: str, default: str = "") -> str:
        """hidden input 등에서 attribute 값을 추출한다."""
        if not selector or not self._driver:
            return default
        try:
            el = self._driver.find_element(By.CSS_SELECTOR, selector)
            val = el.get_attribute(attr)
            if val:
                logger.debug("  %s[%s] → '%s'", selector, attr, val)
                return val.strip()
            logger.warning("  %s[%s] → empty", selector, attr)
            return default
        except Exception:
            logger.warning("  %s → NOT FOUND", selector)
            return default

    def _get_table_value(self, header_text: str, default: str = "") -> str:
        """테이블에서 <th>가 header_text인 행의 <td> 텍스트를 추출한다."""
        if not self._driver:
            return default
        try:
            xpath = f"//th[contains(text(),'{header_text}')]/following-sibling::td[1]"
            el = self._driver.find_element(By.XPATH, xpath)
            text = el.text.strip()
            if text:
                logger.debug("  th[%s] → '%s'", header_text, text)
                return text
            logger.warning("  th[%s] → element found but empty", header_text)
            return default
        except Exception:
            logger.warning("  th[%s] → NOT FOUND", header_text)
            return default

    def _get_table_list(self, header_text: str) -> list[str]:
        """테이블에서 <th>가 header_text인 행의 <td> 텍스트를 ' / ' 로 분리하여 리스트로 반환한다."""
        raw = self._get_table_value(header_text)
        if not raw:
            return []
        items = [v.strip() for v in raw.split("/") if v.strip()]
        logger.debug("  th[%s] list → %s", header_text, items)
        return items

    def _get_image_urls(self, selector: str) -> list[str]:
        """상세 설명 영역의 이미지 src를 추출한다."""
        if not selector or not self._driver:
            return []
        try:
            imgs = self._driver.find_elements(By.CSS_SELECTOR, selector)
            base_url = self._config.base_url
            urls: list[str] = []
            for img in imgs:
                src = img.get_attribute("src")
                if src:
                    full_url = urljoin(base_url, src) if not src.startswith("http") else src
                    urls.append(full_url)
            logger.debug("  %s → %d images found", selector, len(urls))
            return urls
        except Exception:
            logger.warning("  %s → images NOT FOUND", selector)
            return []

    @staticmethod
    def _extract_product_id(url: str) -> str:
        from src.models import CsvRow
        return CsvRow(url=url, selling_price=0).product_id
