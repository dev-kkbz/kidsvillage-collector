from __future__ import annotations

import logging
import re
import time
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config_loader import WholesaleConfig
from src.models import ScrapedProduct

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)


class ScrapeError(Exception):
    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Scrape failed for {url}: {reason}")


class WholesaleScraper:
    """키즈빌리지 로그인 및 상품 정보 수집기."""

    def __init__(self, config: WholesaleConfig) -> None:
        self._config = config
        self._session = requests.Session()
        self._configure_session()

    @property
    def session(self) -> requests.Session:
        return self._session

    def _configure_session(self) -> None:
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.update({
            "User-Agent": BROWSER_USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        })

    def login(self) -> bool:
        """그누보드 로그인 후 실제 로그인 상태를 확인한다."""
        login_url = self._config.login_url
        if not login_url:
            logger.warning("login_url not configured, skipping login")
            return True

        form = self._config.login_form
        try:
            check_url = login_url.replace("/login.php", "/login_check.php").split("?", 1)[0]
            payload = {
                form.id_field: self._config.username,
                form.pw_field: self._config.password,
                "url": "/shop/",
            }
            resp = self._session.post(
                check_url,
                data=payload,
                headers={"Referer": login_url},
                timeout=(10, 30),
                allow_redirects=True,
            )
            resp.raise_for_status()

            test_url = self._config.base_url.rstrip("/") + "/shop/"
            test_resp = self._session.get(test_url, timeout=(10, 30), allow_redirects=True)
            test_resp.raise_for_status()

            if self._looks_like_login_page(test_resp):
                logger.error("Login failed - login page/form was returned")
                return False

            logger.info("Login OK (%s)", test_resp.url)
            return True
        except Exception as e:
            logger.exception("Login failed: %s", e)
            return False

    def scrape_product(self, url: str) -> ScrapedProduct:
        """상품 페이지에서 정보와 상세 이미지 URL을 수집한다."""
        request_url = self._normalize_site_url(url)
        product_id = self._extract_product_id(request_url)

        try:
            resp = self._session.get(
                request_url,
                headers={"Referer": self._config.base_url.rstrip("/") + "/shop/"},
                timeout=(10, 40),
                allow_redirects=True,
            )
            resp.raise_for_status()
            time.sleep(self._config.request_delay_seconds)

            if self._looks_like_login_page(resp):
                raise ScrapeError(url, "로그인 상태가 풀렸거나 로그인 페이지로 이동했습니다.")

            if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding or "utf-8"

            soup = BeautifulSoup(resp.text, "lxml")
            sel = self._config.selectors

            product_name = self._get_text(soup, sel.product_name)
            wholesale_price = self._get_attr(soup, sel.price, "value")
            brand = self._get_table_value(soup, "브랜드")
            colors = self._get_table_list(soup, "색상")
            sizes = self._get_table_list(soup, "사이즈")
            option_prices = self._get_option_prices(soup, resp.url)
            image_urls = self._get_image_urls(soup, sel.detail_images, resp.url)

            if not product_name:
                raise ScrapeError(url, "상품명을 찾지 못했습니다. 사이트 구조 변경 가능성이 있습니다.")
            if not image_urls:
                raise ScrapeError(url, "상세 이미지 URL을 찾지 못했습니다. 사이트 구조 변경 가능성이 있습니다.")

            logger.info(
                "Scraped %s: brand=%s, name=%s, price=%s원, %d sizes, %d colors, "
                "%d option_prices, %d images",
                product_id,
                brand,
                product_name,
                wholesale_price,
                len(sizes),
                len(colors),
                len(option_prices),
                len(image_urls),
            )

            return ScrapedProduct(
                product_id=product_id,
                product_name=product_name,
                wholesale_price=wholesale_price,
                brand=brand,
                sizes=sizes,
                colors=colors,
                image_urls=image_urls,
                option_prices=option_prices,
            )
        except ScrapeError:
            raise
        except Exception as e:
            raise ScrapeError(url, self._friendly_network_error(e)) from e

    def _normalize_site_url(self, url: str) -> str:
        """www 유무가 달라도 로그인 쿠키가 유지되도록 설정의 호스트로 통일한다."""
        parsed = urlparse(url)
        base = urlparse(self._config.base_url)
        if parsed.hostname in {"kidsvillage.co.kr", "www.kidsvillage.co.kr"} and base.netloc:
            return urlunparse((base.scheme or "https", base.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        return url

    @staticmethod
    def _looks_like_login_page(resp: requests.Response) -> bool:
        if "login.php" in resp.url.lower():
            return True
        text = resp.text[:200_000]
        return bool(
            re.search(r'name=["\']mb_id["\']', text, re.I)
            and re.search(r'name=["\']mb_password["\']', text, re.I)
        )

    @staticmethod
    def _get_text(soup: BeautifulSoup, selector: str) -> str:
        if not selector:
            return ""
        el = soup.select_one(selector)
        if el:
            text = el.get_text(" ", strip=True)
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
                text = td.get_text(" ", strip=True)
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
                raw = td.get_text(" ", strip=True)
                if raw:
                    return [v.strip() for v in re.split(r"\s*/\s*", raw) if v.strip()]
        logger.warning("  th[%s] list → NOT FOUND or empty", header_text)
        return []

    def _get_option_prices(self, soup: BeautifulSoup, product_url: str) -> list[int]:
        option_selects = soup.select("select.it_option")
        if len(option_selects) < 2:
            return []

        first_select = option_selects[0]
        option_values = [
            opt.get("value", "").strip()
            for opt in first_select.find_all("option")
            if opt.get("value", "").strip()
        ]
        if not option_values:
            return []

        it_id = parse_qs(urlparse(product_url).query).get("it_id", [""])[0]
        if not it_id:
            return []

        g5_shop_url = self._config.base_url.rstrip("/") + "/shop"
        for script in soup.find_all("script"):
            text = script.string or ""
            match = re.search(r'g5_shop_url\s*=\s*["\']([^"\']+)', text)
            if match:
                g5_shop_url = match.group(1)
                break

        post_url = urljoin(product_url, g5_shop_url.rstrip("/") + "/itemoption.php")
        sel_count = len(option_selects)
        first_option = first_select.find("option")
        op_title = first_option.get_text(strip=True) if first_option else "선택"

        all_prices: set[int] = set()
        for opt_val in option_values:
            try:
                resp = self._session.post(
                    post_url,
                    data={
                        "it_id": it_id,
                        "opt_id": opt_val,
                        "idx": "0",
                        "sel_count": str(sel_count),
                        "op_title": op_title,
                    },
                    headers={"Referer": product_url},
                    timeout=(10, 20),
                )
                if resp.status_code == 200 and resp.text.strip():
                    all_prices.update(self._parse_itemoption_response(resp.text))
            except Exception as e:
                logger.debug("  [옵션] opt_id=%s 호출 실패: %s", opt_val, e)

        return sorted(all_prices)

    @staticmethod
    def _parse_itemoption_response(html: str) -> list[int]:
        prices: set[int] = set()
        option_soup = BeautifulSoup(html, "lxml")
        for opt in option_soup.find_all("option"):
            val = opt.get("value", "").strip()
            if not val:
                continue
            parts = val.split(",")
            if len(parts) >= 2:
                try:
                    price = int(parts[1])
                    if price:
                        prices.add(price)
                except (ValueError, IndexError):
                    pass
        return sorted(prices)

    def _get_image_urls(self, soup: BeautifulSoup, selector: str, page_url: str) -> list[str]:
        """src뿐 아니라 lazy-load 속성과 이미지 링크도 수집한다."""
        nodes: list[Tag] = list(soup.select(selector)) if selector else []
        scope = soup.select_one("#sit_inf_explan")

        if not nodes and scope:
            nodes = list(scope.select("img"))

        raw_urls: list[str] = []
        for img in nodes:
            # 원본 이미지 링크가 있으면 썸네일 src보다 우선한다.
            parent = img.find_parent("a", href=True)
            if parent:
                href = str(parent.get("href", "")).strip()
                if self._looks_like_image_url(href):
                    raw_urls.append(href)
                    continue

            chosen = ""
            for attr in ("data-original", "data-src", "data-lazy-src", "data-echo"):
                value = str(img.get(attr, "")).strip()
                if value:
                    chosen = value
                    break

            if not chosen:
                srcset = str(img.get("srcset", "")).strip()
                if srcset:
                    candidates = [item.strip().split()[0] for item in srcset.split(",") if item.strip()]
                    if candidates:
                        chosen = candidates[-1]

            if not chosen:
                chosen = str(img.get("src", "")).strip()

            if chosen:
                raw_urls.append(chosen)

        if scope:
            for anchor in scope.select("a[href]"):
                href = str(anchor.get("href", "")).strip()
                if self._looks_like_image_url(href):
                    raw_urls.append(href)

        result: list[str] = []
        seen: set[str] = set()
        for raw in raw_urls:
            if not raw or raw.startswith(("data:", "javascript:", "#")):
                continue
            full = urljoin(page_url, raw)
            lower = full.lower()
            if any(token in lower for token in ("loading", "spinner", "blank.gif", "no_image", "no-image")):
                continue
            if full not in seen:
                seen.add(full)
                result.append(full)

        return result

    @staticmethod
    def _looks_like_image_url(url: str) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        path = parsed.path.lower()
        return bool(
            re.search(r"\.(?:jpe?g|png|gif|webp|bmp|avif)$", path)
            or parsed.hostname in {"img2.kidsvillage.co.kr", "img.kidsvillage.co.kr"}
        )

    @staticmethod
    def _friendly_network_error(exc: Exception) -> str:
        text = str(exc)
        lower = text.lower()
        if any(token in lower for token in ("nameresolutionerror", "getaddrinfo failed", "failed to resolve")):
            return f"DNS 조회 실패: {text}"
        if "certificate_verify_failed" in lower or "sslcertverificationerror" in lower:
            return f"SSL 인증서 확인 실패: {text}"
        return text

    @staticmethod
    def _extract_product_id(url: str) -> str:
        from src.models import CsvRow
        return CsvRow(url=url).product_id
