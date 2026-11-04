import unittest
from unittest.mock import MagicMock, patch

from agentforge import source_reader, source_review


class TestSourceReaderSecurity(unittest.TestCase):

    def test_explicit_allowlist_fetches_approved_host(self):
        html = (
            b"<html><head><title>Test page</title></head>"
            b"<body><article>"
            + b"This is a public research article. " * 20
            + b"</article></body></html>"
        )

        response = MagicMock()
        response.headers.get_content_type.return_value = "text/html"
        response.read.return_value = html

        with patch.object(source_reader.OPENER, "open") as opener:
            opener.return_value.__enter__.return_value = response

            page = source_reader.fetch_page(
                "https://sheet.com.vn/article",
                allowed_hosts={"sheet.com.vn"},
            )

            opener.assert_called_once()

        self.assertEqual(page["title"], "Test page")
        self.assertGreater(page["extracted_characters"], 300)

    def test_unapproved_host_never_opens_connection(self):
        with patch.object(source_reader.OPENER, "open") as opener:
            with self.assertRaises(PermissionError):
                source_reader.fetch_page(
                    "https://unapproved.example.com/article",
                    allowed_hosts={"sheet.com.vn"},
                )

            opener.assert_not_called()

    def test_default_allowlist_does_not_inherit_review_permission(self):
        with patch.object(source_reader.OPENER, "open") as opener:
            with self.assertRaises(PermissionError):
                source_reader.fetch_page(
                    "https://sheet.com.vn/article"
                )

            opener.assert_not_called()

    def test_unsafe_urls_rejected_before_network(self):
        unsafe_urls = (
            "http://sheet.com.vn/test",
            "https://127.0.0.1/private",
            "https://localhost/test",
            "https://api.internal/private",
            "https://sheet.com.vn:444/test",
            "https://user:pass@sheet.com.vn/test",
            "https://sheet.com.vn\n/test",
            "https://sheet.com.vn\\@evil.com/test",
            "https://sheet.com.vn:abc/test",
            "https://[::1]/",
        )

        with patch.object(source_reader.OPENER, "open") as opener:
            for url in unsafe_urls:
                with self.subTest(url=url):
                    with self.assertRaises(ValueError):
                        source_reader.fetch_page(
                            url,
                            allowed_hosts={
                                "sheet.com.vn",
                                "127.0.0.1",
                                "api.internal",
                            },
                        )

            opener.assert_not_called()

    def test_allowlist_must_not_be_a_string(self):
        with patch.object(source_reader.OPENER, "open") as opener:
            with self.assertRaises(ValueError):
                source_reader.fetch_page(
                    "https://sheet.com.vn/article",
                    allowed_hosts="sheet.com.vn",
                )

            opener.assert_not_called()

    def test_reviewer_uses_per_call_allowlist(self):
        original = source_reader.ALLOWED_HOSTS
        url = "https://sheet.com.vn/article"

        with patch.object(
            source_reader,
            "fetch_page",
            return_value={"title": "Test"},
        ) as mocked:
            source_review.fetch_for_one_host(
                url,
                "sheet.com.vn",
            )

        mocked.assert_called_once_with(
            url,
            allowed_hosts=frozenset({"sheet.com.vn"}),
        )

        self.assertIs(source_reader.ALLOWED_HOSTS, original)

    def test_reader_and_reviewer_share_url_validation(self):
        url = "https://sheet.com.vn/article"

        self.assertEqual(
            source_reader.validate_public_https_url(url),
            source_review.safe_host(url),
        )


if __name__ == "__main__":
    unittest.main()
