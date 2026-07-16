import unittest

from services.url_whitelist import FETCH_URL_WHITELIST, is_internal_ip, validate_fetch_url


class UrlWhitelistStructureTests(unittest.TestCase):
    def test_whitelist_is_immutable_dict_of_lists(self):
        self.assertIsInstance(FETCH_URL_WHITELIST, dict)
        for category, patterns in FETCH_URL_WHITELIST.items():
            self.assertIsInstance(category, str)
            self.assertIsInstance(patterns, (list, tuple))
            for pattern in patterns:
                self.assertIsInstance(pattern, str)

    def test_whitelist_has_expected_categories(self):
        expected = {
            "academic_publishers",
            "government",
            "organizations",
            "news",
            "encyclopedia",
            "code_repos",
        }
        self.assertEqual(set(FETCH_URL_WHITELIST), expected)


class IsInternalIpTests(unittest.TestCase):
    def test_private_ipv4_ranges(self):
        self.assertTrue(is_internal_ip("10.0.0.1"))
        self.assertTrue(is_internal_ip("10.255.255.255"))
        self.assertTrue(is_internal_ip("172.16.0.1"))
        self.assertTrue(is_internal_ip("172.31.255.255"))
        self.assertTrue(is_internal_ip("192.168.0.1"))
        self.assertTrue(is_internal_ip("192.168.255.255"))

    def test_loopback(self):
        self.assertTrue(is_internal_ip("127.0.0.1"))
        self.assertTrue(is_internal_ip("127.255.255.255"))
        self.assertTrue(is_internal_ip("::1"))

    def test_link_local(self):
        self.assertTrue(is_internal_ip("169.254.0.1"))
        self.assertTrue(is_internal_ip("169.254.255.255"))
        self.assertTrue(is_internal_ip("fe80::1"))

    def test_multicast_and_reserved(self):
        self.assertTrue(is_internal_ip("224.0.0.1"))
        self.assertTrue(is_internal_ip("239.255.255.255"))
        self.assertTrue(is_internal_ip("240.0.0.1"))

    def test_ipv6_private_ranges(self):
        self.assertTrue(is_internal_ip("fc00::1"))
        self.assertTrue(is_internal_ip("fdff::1"))
        self.assertTrue(is_internal_ip("fe80::1"))

    def test_public_ips_are_not_internal(self):
        self.assertFalse(is_internal_ip("8.8.8.8"))
        self.assertFalse(is_internal_ip("1.1.1.1"))
        self.assertFalse(is_internal_ip("93.184.216.34"))
        self.assertFalse(is_internal_ip("2001:4860:4860::8888"))

    def test_invalid_ip_returns_false(self):
        self.assertFalse(is_internal_ip("not-an-ip"))
        self.assertFalse(is_internal_ip(""))
        self.assertFalse(is_internal_ip("256.256.256.256"))


class ValidateFetchUrlTests(unittest.TestCase):
    # ── positive cases ─────────────────────────────────────────

    def test_allows_whitelisted_academic_publisher(self):
        result = validate_fetch_url("https://www.nature.com/articles/s41586-021-03819-2")
        self.assertEqual(result, "www.nature.com")

    def test_allows_whitelisted_gov_domain(self):
        result = validate_fetch_url("https://www.nih.gov/health-information")
        self.assertEqual(result, "www.nih.gov")

    def test_allows_whitelisted_nsf_gov(self):
        result = validate_fetch_url("https://www.nsf.gov/awardsearch/")
        self.assertEqual(result, "www.nsf.gov")

    def test_allows_whitelisted_wikipedia(self):
        result = validate_fetch_url("https://en.wikipedia.org/wiki/Machine_learning")
        self.assertEqual(result, "en.wikipedia.org")

    def test_allows_whitelisted_github(self):
        result = validate_fetch_url("https://github.com/torvalds/linux")
        self.assertEqual(result, "github.com")

    def test_allows_whitelisted_arxiv(self):
        result = validate_fetch_url("https://arxiv.org/abs/1706.03762")
        self.assertEqual(result, "arxiv.org")

    def test_allows_whitelisted_semanticscholar(self):
        result = validate_fetch_url("https://www.semanticscholar.org/paper/abc123")
        self.assertEqual(result, "www.semanticscholar.org")

    def test_allows_whitelisted_bbc_news(self):
        result = validate_fetch_url("https://www.bbc.com/news/science-environment")
        self.assertEqual(result, "www.bbc.com")

    def test_allows_whitelisted_ieee(self):
        result = validate_fetch_url("https://ieeexplore.ieee.org/document/12345")
        self.assertEqual(result, "ieeexplore.ieee.org")

    def test_allows_whitelisted_wildcard_subdomain(self):
        # *.gov covers any .gov domain
        result = validate_fetch_url("https://science.nasa.gov/astrophysics")
        self.assertEqual(result, "science.nasa.gov")

    # ── negative: protocol ─────────────────────────────────────

    def test_rejects_http(self):
        with self.assertRaises(ValueError) as ctx:
            validate_fetch_url("http://www.nature.com/article")
        self.assertIn("HTTPS", str(ctx.exception))

    def test_rejects_ftp(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("ftp://files.example.com/data")

    def test_rejects_file_protocol(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("file:///etc/passwd")

    # ── negative: host ─────────────────────────────────────────

    def test_rejects_non_whitelisted_domain(self):
        with self.assertRaises(ValueError) as ctx:
            validate_fetch_url("https://evil.com/malware")
        self.assertIn("not in", str(ctx.exception).lower())

    def test_rejects_ip_address(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("https://8.8.8.8/page")

    def test_rejects_ipv6_address(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("https://[::1]/page")

    def test_rejects_localhost(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("https://localhost/admin")

    def test_rejects_loopback_ip(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("https://127.0.0.1/secret")

    def test_rejects_private_ip_10(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("https://10.0.0.1/internal")

    def test_rejects_private_ip_172(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("https://172.16.0.1/admin")

    def test_rejects_private_ip_192(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("https://192.168.1.1/router")

    # ── negative: credentials ──────────────────────────────────

    def test_rejects_url_with_credentials(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("https://user:password@nature.com/article")

    # ── negative: invalid input ────────────────────────────────

    def test_rejects_empty_string(self):
        with self.assertRaises(ValueError):
            validate_fetch_url("")

    def test_rejects_none(self):
        with self.assertRaises(ValueError):
            validate_fetch_url(None)

    def test_rejects_non_string(self):
        with self.assertRaises(ValueError):
            validate_fetch_url(12345)

    # ── sanitization ───────────────────────────────────────────

    def test_error_messages_never_contain_sensitive_url(self):
        test_urls = [
            "https://evil.com/malware",
            "https://192.168.1.1/router",
            "https://user:pass@nature.com/page",
            "http://www.nature.com/article",
        ]
        for url in test_urls:
            with self.subTest(url=url):
                try:
                    validate_fetch_url(url)
                except ValueError as exc:
                    msg = str(exc)
                    # Never leak the full URL in error messages
                    self.assertNotIn("evil.com", msg)
                    self.assertNotIn("192.168", msg)
                    self.assertNotIn("user:pass", msg)
                    self.assertNotIn("nature.com", msg)


if __name__ == "__main__":
    unittest.main()
