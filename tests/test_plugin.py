import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from plugin import Plugin


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.plugin = Plugin()

    def test_parse_series_whitelist(self):
        self.assertEqual(
            self.plugin._parse_series_whitelist("12, 34, 12, 0056"),
            [12, 34, 56],
        )
        self.assertEqual(self.plugin._parse_series_whitelist(""), [])

    def test_parse_series_whitelist_rejects_invalid_ids(self):
        for value in ("abc", "1, -2", "1, 2.5", "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.plugin._parse_series_whitelist(value)

    def test_filename_is_portable_and_byte_bounded(self):
        self.assertEqual(self.plugin._sanitize_filename('CON'), '_CON')
        self.assertLessEqual(len(self.plugin._sanitize_filename('語' * 200).encode()), 180)


if __name__ == '__main__':
    unittest.main()
