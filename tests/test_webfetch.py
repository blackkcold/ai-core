import unittest
from aicore.errors import UnsafeURL
from aicore.webfetch import fetch_page, validated_target


def safe_resolver(*args, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


class FakeResponse:
    status = 200
    def getheader(self, key, default=""):
        return {"Content-Type": "text/html; charset=utf-8", "Content-Encoding": "identity"}.get(key, default)
    def read(self, n):
        return b"<html><head><title>Test</title><script>ignored code</script></head><body><h1>Readable</h1><p>Evidence</p></body></html>"


class FakeConnection:
    def __init__(self, host, ip, timeout):
        self.host, self.ip, self.closed = host, ip, False
    def request(self, method, path, headers):
        self.path = path
    def getresponse(self):
        return FakeResponse()
    def close(self):
        self.closed = True


class FetchTests(unittest.TestCase):
    def test_private_ip_rejected(self):
        def resolver(*args, **kwargs):
            return [(2, 1, 6, "", ("127.0.0.1", 443))]
        with self.assertRaises(UnsafeURL):
            validated_target("https://example.com/", resolver=resolver)

    def test_invalid_scheme(self):
        for url in ("http://example.com/", "file:///etc/passwd", "https://localhost/",
                    "https://user:pass@example.com/", "https://example.com:444/"):
            with self.assertRaises(UnsafeURL):
                validated_target(url, resolver=safe_resolver)

    def test_dns_pinning_and_html_strip(self):
        result = fetch_page("https://example.com/article?q=hi",
                            resolver=safe_resolver, connection_factory=FakeConnection)
        self.assertEqual(result["title"], "Test")
        self.assertIn("Evidence", result["text"])
        self.assertNotIn("ignored code", result["text"])
        self.assertTrue(result["untrusted"])

    def test_public_ip_and_path(self):
        host, ip, path = validated_target("https://example.com/article?a=b", resolver=safe_resolver)
        self.assertEqual((host, ip, path), ("example.com", "93.184.216.34", "/article?a=b"))


if __name__ == "__main__":
    unittest.main()
