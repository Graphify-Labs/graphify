import unittest
from graphify.security import escape_graphml_text


class TestExportEscaping(unittest.TestCase):
    def test_escape_graphml_text_special_chars(self):
        self.assertEqual(escape_graphml_text("<a> & <b>"), "&lt;a&gt; &amp; &lt;b&gt;")
        self.assertEqual(escape_graphml_text('quote "test"'), "quote &quot;test&quot;")
        self.assertEqual(escape_graphml_text(None), "")

    def test_escape_graphml_text_control_chars(self):
        self.assertEqual(escape_graphml_text("hello\x00world\x1f!"), "helloworld!")


if __name__ == '__main__':
    unittest.main()
