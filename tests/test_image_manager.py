from __future__ import annotations

import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

from src.image_manager import ImageDownloadError, ImageManager

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 512 + b"\xff\xd9"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/image.jpg":
            if "kidsvillage.co.kr" not in self.headers.get("Referer", ""):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"forbidden")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(JPEG)))
            self.end_headers()
            self.wfile.write(JPEG)
            return

        if self.path == "/html.jpg":
            body = b"<html>blocked</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        return


class ImageManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_download_sends_referer_and_validates_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ImageManager(tmp, requests.Session())
            paths = manager.download_images(
                "001_test",
                [self.base + "/image.jpg"],
                referer_url="https://www.kidsvillage.co.kr/shop/item.php?it_id=1",
            )
            self.assertEqual(len(paths), 1)
            self.assertTrue(Path(paths[0]).exists())
            self.assertEqual(Path(paths[0]).suffix, ".jpg")

    def test_html_is_not_saved_as_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ImageManager(tmp, requests.Session())
            with self.assertRaises(ImageDownloadError):
                manager.download_images(
                    "001_test",
                    [self.base + "/html.jpg"],
                    referer_url="https://www.kidsvillage.co.kr/shop/item.php?it_id=1",
                )
