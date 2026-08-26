import re
import unittest
from plantimager.commons.RPC import NoResult, url_parser


class TestRPCMisc(unittest.TestCase):
    def test_url_parser_simple(self):
        m = url_parser.match("tcp://127.0.0.1:5555")
        self.assertIsNotNone(m)
        self.assertEqual(m.groups(), ("tcp", "127.0.0.1", "5555"))

    def test_url_parser_no_port(self):
        m = url_parser.match("tcp://127.0.0.1")
        self.assertIsNotNone(m)
        self.assertEqual(m.groups()[0], "tcp")

    @unittest.expectedFailure
    def test_url_parser_hyphen(self):
        # Known bug: hyphen not in character class [a-zA-Z.0-9]
        m = url_parser.match("tcp://picamera-02:8000")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "picamera-02")

    def test_noresult_falsy(self):
        nr = NoResult("e", "tb")
        self.assertFalse(bool(nr))
        self.assertFalse(nr)
        self.assertTrue(not nr)

    def test_noresult_attrs(self):
        nr = NoResult("my error", "my traceback")
        self.assertEqual(nr.error, "my error")
        self.assertEqual(nr.traceback, "my traceback")

    def test_url_parser_regex_pattern(self):
        # ensure pattern is as documented
        self.assertIsInstance(url_parser, re.Pattern)


if __name__ == "__main__":
    unittest.main()
