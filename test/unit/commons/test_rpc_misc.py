"""Unit tests for miscellaneous RPC helpers.

These tests cover the small standalone pieces of :mod:`plantimager.commons.RPC`
that do not need a live socket: the ``url_parser`` regex used to decompose
``tcp://host:port`` URLs, and the ``NoResult`` sentinel returned when a remote
call yields no value. The design keeps these pure, dependency-free checks
separate from the socket-based protocol tests so failures isolate to the
parsing/representation logic itself.
"""

import re
import unittest
from plantimager.commons.RPC import NoResult, url_parser


class TestRPCMisc(unittest.TestCase):
    """Tests for the url_parser regex and NoResult sentinel."""

    def test_url_parser_simple(self):
        """Parse a full tcp://host:port URL into scheme, host, and port."""
        m = url_parser.match("tcp://127.0.0.1:5555")
        self.assertIsNotNone(m)
        self.assertEqual(m.groups(), ("tcp", "127.0.0.1", "5555"))

    def test_url_parser_no_port(self):
        """Parse a URL with no port, still extracting the scheme."""
        m = url_parser.match("tcp://127.0.0.1")
        self.assertIsNotNone(m)
        self.assertEqual(m.groups()[0], "tcp")

    @unittest.expectedFailure
    def test_url_parser_hyphen(self):
        """Document the known bug: hyphens are not matched in hostnames."""
        # Known bug: hyphen not in character class [a-zA-Z.0-9]
        m = url_parser.match("tcp://picamera-02:8000")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "picamera-02")

    def test_noresult_falsy(self):
        """Verify NoResult evaluates as falsy."""
        nr = NoResult("e", "tb")
        self.assertFalse(bool(nr))
        self.assertFalse(nr)
        self.assertTrue(not nr)

    def test_noresult_attrs(self):
        """Verify NoResult stores its error and traceback attributes."""
        nr = NoResult("my error", "my traceback")
        self.assertEqual(nr.error, "my error")
        self.assertEqual(nr.traceback, "my traceback")

    def test_url_parser_regex_pattern(self):
        """Verify url_parser is a compiled regular expression pattern."""
        # ensure pattern is as documented
        self.assertIsInstance(url_parser, re.Pattern)


if __name__ == "__main__":
    unittest.main()
