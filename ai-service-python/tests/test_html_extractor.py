import unittest


class HtmlExtractorModuleTests(unittest.TestCase):
    def test_module_imports(self):
        from services import html_extractor
        self.assertIsNotNone(html_extractor)


class TagRemovalTests(unittest.TestCase):
    def test_strips_script_tags_and_content(self):
        from services.html_extractor import extract_html_content

        html = "<html><head><script>alert('xss')</script></head><body><p>Safe text</p></body></html>"
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]
        self.assertIn("Safe text", text)
        self.assertNotIn("alert", text)
        self.assertNotIn("xss", text)

    def test_strips_style_tags_and_content(self):
        from services.html_extractor import extract_html_content

        html = "<html><head><style>body { color: red; }</style></head><body><p>Hello</p></body></html>"
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]
        self.assertIn("Hello", text)
        self.assertNotIn("color", text)
        self.assertNotIn("red", text)

    def test_strips_iframe_object_embed(self):
        from services.html_extractor import extract_html_content

        html = '<html><body><p>Before</p><iframe src="evil"></iframe><object data="x"></object><p>After</p></body></html>'
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]
        self.assertIn("Before", text)
        self.assertIn("After", text)
        self.assertNotIn("iframe", text.lower())

    def test_strips_void_embed_tag(self):
        from services.html_extractor import extract_html_content

        html = '<html><body><p>Start</p><embed src="y"><p>End</p></body></html>'
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]
        self.assertIn("Start", text)
        self.assertIn("End", text)
        self.assertNotIn("embed", text.lower())

    def test_strips_svg_and_math_tags(self):
        from services.html_extractor import extract_html_content

        html = '<html><body><p>Text</p><svg><circle r="5"/></svg><math><mi>x</mi></math></body></html>'
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]
        self.assertIn("Text", text)
        self.assertNotIn("svg", text.lower())

    def test_strips_form_and_input_tags(self):
        from services.html_extractor import extract_html_content

        html = '<html><body><form action="/submit"><input type="text" name="user"><button>Click</button></form><p>Safe</p></body></html>'
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]
        self.assertIn("Safe", text)
        self.assertNotIn("submit", text.lower())


class TextPostProcessingTests(unittest.TestCase):
    def test_compresses_multiple_spaces(self):
        from services.html_extractor import extract_html_content

        html = "<html><body><p>Hello    World    !</p></body></html>"
        result = extract_html_content(html, url="https://example.com")
        self.assertIn("Hello World !", result["text"])

    def test_dedupes_consecutive_newlines(self):
        from services.html_extractor import extract_html_content

        html = "<html><body><p>A</p><br><br><br><br><p>B</p></body></html>"
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]
        self.assertNotIn("\n\n\n", text)
        self.assertIn("A", text)
        self.assertIn("B", text)

    def test_truncates_to_max_chars(self):
        from services.html_extractor import extract_html_content

        html = "<html><body><p>" + ("x" * 60000) + "</p></body></html>"
        result = extract_html_content(html, url="https://example.com", max_chars=50000)
        self.assertLessEqual(len(result["text"]), 50000)
        self.assertTrue(result["truncated"])

    def test_removes_non_printable_characters(self):
        from services.html_extractor import extract_html_content

        html = "<html><body><p>Hello\x00\x01\x02\x1fWorld</p></body></html>"
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]
        self.assertIn("Hello", text)
        self.assertIn("World", text)
        self.assertNotIn("\x00", text)
        self.assertNotIn("\x01", text)

    def test_handles_empty_html(self):
        from services.html_extractor import extract_html_content

        result = extract_html_content("", url="https://example.com")
        self.assertEqual(result["text"], "")
        self.assertEqual(result["char_count"], 0)

    def test_handles_none_html(self):
        from services.html_extractor import extract_html_content

        result = extract_html_content(None, url="https://example.com")
        self.assertEqual(result["text"], "")
        self.assertEqual(result["char_count"], 0)

    def test_preserves_title_metadata(self):
        from services.html_extractor import extract_html_content

        html = "<html><head><title>My Research Article</title></head><body><p>Content</p></body></html>"
        result = extract_html_content(html, url="https://www.nature.com/article")
        self.assertEqual(result["title"], "My Research Article")
        self.assertEqual(result["url"], "https://www.nature.com/article")


class ComplexHtmlTests(unittest.TestCase):
    def test_extracts_text_from_complex_page(self):
        from services.html_extractor import extract_html_content

        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Attention Is All You Need - arXiv</title>
    <script>trackPageView();</script>
    <style>.abstract { font-weight: bold; }</style>
    <!-- navigation comment -->
</head>
<body>
    <nav><a href="/">Home</a></nav>
    <article>
        <h1>Attention Is All You Need</h1>
        <p class="abstract">The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</p>
        <p>We propose a new simple network architecture, the <em>Transformer</em>, based solely on attention mechanisms.</p>
        <p>Experiments on two machine translation tasks show these models are superior in quality.</p>
    </article>
    <footer>© 2017 NeurIPS</footer>
    <script>trackExit();</script>
</body>
</html>"""
        result = extract_html_content(html, url="https://arxiv.org/abs/1706.03762")
        text = result["text"]

        self.assertEqual(result["title"], "Attention Is All You Need - arXiv")
        self.assertIn("Attention Is All You Need", text)
        self.assertIn("Transformer", text)
        self.assertIn("attention mechanisms", text)
        self.assertIn("machine translation", text)
        self.assertNotIn("trackPageView", text)
        self.assertNotIn("trackExit", text)
        self.assertNotIn("navigation comment", text)
        self.assertNotIn("font-weight", text)
        self.assertEqual(result["url"], "https://arxiv.org/abs/1706.03762")

    def test_extracts_text_with_nested_lists(self):
        from services.html_extractor import extract_html_content

        html = """<html><body>
        <h2>Methods</h2>
        <ul>
            <li>Item A: <strong>important</strong> detail</li>
            <li>Item B with <a href="/ref">reference</a></li>
            <li>Item C</li>
        </ul>
        <p>Conclusion paragraph.</p>
        </body></html>"""
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]

        self.assertIn("Methods", text)
        self.assertIn("Item A", text)
        self.assertIn("important", text)
        self.assertIn("Item B", text)
        self.assertIn("Item C", text)
        self.assertIn("Conclusion", text)

    def test_handles_unicode_and_entities(self):
        from services.html_extractor import extract_html_content

        html = '<html><body><p>Café résumé naïve &amp; co.</p><p>αβγ × ÷ ≤ ≥</p></body></html>'
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]

        self.assertIn("Café", text)
        self.assertIn("résumé", text)
        self.assertIn("&", text)
        self.assertIn("αβγ", text)

    def test_handles_malformed_html(self):
        from services.html_extractor import extract_html_content

        html = "<p>Unclosed paragraph<b>Bold<i>Bold italic</b> still italic</i><br><p>New para"
        result = extract_html_content(html, url="https://example.com")
        text = result["text"]

        self.assertIn("Unclosed paragraph", text)
        self.assertIn("Bold", text)
        self.assertIn("Bold italic", text)
        self.assertIn("New para", text)


if __name__ == "__main__":
    unittest.main()
