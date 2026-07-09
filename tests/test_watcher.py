import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.watcher import (
    _find_model_line,
    _has_cb_prefix,
    _strip_cb_prefix,
    _extract_model,
    _get_upstream_host,
)


class TestCbPrefix(unittest.TestCase):
    def test_has_prefix(self):
        self.assertTrue(_has_cb_prefix("-cb-deepseek-v4-pro"))
        self.assertTrue(_has_cb_prefix("-cb-gpt-4"))

    def test_no_prefix(self):
        self.assertFalse(_has_cb_prefix("deepseek-v4-pro"))
        self.assertFalse(_has_cb_prefix(""))
        self.assertFalse(_has_cb_prefix("cb-deepseek"))

    def test_strip_prefix(self):
        self.assertEqual(_strip_cb_prefix("-cb-deepseek-v4-pro"), "deepseek-v4-pro")
        self.assertEqual(_strip_cb_prefix("-cb-gpt-4o"), "gpt-4o")


class TestExtractModel(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(_extract_model({"model": "deepseek-v4-pro"}), "deepseek-v4-pro")

    def test_missing(self):
        self.assertEqual(_extract_model({}), "")


class TestFindModelLine(unittest.TestCase):
    def test_find(self):
        lines = [
            'model_provider = "custom"\n',
            'model = "deepseek-v4-pro"\n',
            'model_reasoning_effort = "high"\n',
        ]
        self.assertEqual(_find_model_line(lines), 1)

    def test_not_found(self):
        lines = [
            'model_provider = "custom"\n',
            'other = "value"\n',
        ]
        self.assertEqual(_find_model_line(lines), -1)


class TestGetUpstreamHost(unittest.TestCase):
    def test_simple_host(self):
        config = {
            "model_provider": "custom",
            "model_providers": {
                "custom": {"base_url": "https://api.deepseek.com"}
            },
        }
        self.assertEqual(_get_upstream_host(config), "api.deepseek.com")

    def test_host_with_path(self):
        config = {
            "model_provider": "custom",
            "model_providers": {
                "custom": {"base_url": "https://coding.dashscope.aliyuncs.com/v1"}
            },
        }
        self.assertEqual(
            _get_upstream_host(config),
            "coding.dashscope.aliyuncs.com/v1",
        )

    def test_trailing_slash_stripped(self):
        config = {
            "model_provider": "custom",
            "model_providers": {
                "custom": {"base_url": "https://api.openai.com/v1/"}
            },
        }
        self.assertEqual(_get_upstream_host(config), "api.openai.com/v1")

    def test_default_provider(self):
        config = {
            "model_providers": {
                "custom": {"base_url": "https://api.example.com"}
            },
        }
        self.assertEqual(_get_upstream_host(config), "api.example.com")


if __name__ == "__main__":
    unittest.main()
