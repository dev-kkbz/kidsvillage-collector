from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from src.config_loader import WholesaleConfig
from src.scraper import WholesaleScraper


class ScraperImageTests(unittest.TestCase):
    def test_lazy_attributes_and_deduplication(self):
        html = """
        <div id="sit_inf_explan">
          <img src="/loading.gif" data-original="//img2.kidsvillage.co.kr/a/a.jpg">
          <img data-src="https://img2.kidsvillage.co.kr/b/b.png">
          <a href="https://img2.kidsvillage.co.kr/c/c.webp"><img src="/thumb.jpg"></a>
          <img src="https://img2.kidsvillage.co.kr/b/b.png">
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        scraper = WholesaleScraper(WholesaleConfig(base_url="https://www.kidsvillage.co.kr"))
        urls = scraper._get_image_urls(
            soup,
            "#sit_inf_explan img",
            "https://www.kidsvillage.co.kr/shop/item.php?it_id=1",
        )
        self.assertIn("https://img2.kidsvillage.co.kr/a/a.jpg", urls)
        self.assertIn("https://img2.kidsvillage.co.kr/b/b.png", urls)
        self.assertIn("https://img2.kidsvillage.co.kr/c/c.webp", urls)
        self.assertNotIn("https://www.kidsvillage.co.kr/thumb.jpg", urls)
        self.assertEqual(urls.count("https://img2.kidsvillage.co.kr/b/b.png"), 1)
