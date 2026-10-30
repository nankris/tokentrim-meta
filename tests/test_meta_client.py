import os
import unittest
from unittest import mock

from tokentrim.clients.meta import MetaModelClient, api_model_id

REAL_SHAPE = {"choices": [{"finish_reason": "stop", "message": {"content": "ok", "role": "assistant"}}],
              "model": "muse-spark-1.3-contributor",
              "usage": {"completion_tokens": 154, "prompt_tokens": 13, "total_tokens": 167,
                        "completion_tokens_details": {"reasoning_tokens": 144},
                        "prompt_tokens_details": {"cached_tokens": 0}}}


class MetaClientTests(unittest.TestCase):
    def test_parse_real_response_shape(self):
        r = MetaModelClient.parse(REAL_SHAPE)
        self.assertEqual((r.text, r.usage.input, r.usage.cached_input, r.usage.output), ("ok", 13, 0, 154))
        shape = dict(REAL_SHAPE, usage={"prompt_tokens": 6164, "completion_tokens": 71,
                                        "prompt_tokens_details": {"cached_tokens": 5745}})
        self.assertEqual(MetaModelClient.parse(shape).usage.cached_input, 5745)

    def test_missing_usage_details_and_empty_content(self):
        r = MetaModelClient.parse({"choices": [{"finish_reason": "length", "message": {"content": None}}],
                                   "usage": {"prompt_tokens": 5, "completion_tokens": 400}})
        self.assertEqual((r.text, r.usage.cached_input), ("", 0))

    def test_env_key_and_no_leak(self):
        with mock.patch.dict(os.environ, {"META_API_KEY": "", "MODEL_API_KEY": ""}, clear=False):
            with self.assertRaises(ValueError):
                MetaModelClient()
        with mock.patch.dict(os.environ, {"META_API_KEY": "", "MODEL_API_KEY": "dummy-test-value"}, clear=False):
            client = MetaModelClient()
            self.assertEqual(client.base_url, "https://api.meta.ai/v1")
            self.assertNotIn("dummy-test-value", repr(client))
        with mock.patch.dict(os.environ, {"META_API_KEY": "x", "META_API_BASE_URL": "http://insecure"}):
            with self.assertRaises(ValueError):
                MetaModelClient()

    def test_model_id_mapping(self):
        self.assertEqual(api_model_id("meta/muse-spark-1.3-contributor"), "muse-spark-1.3-contributor")
        self.assertEqual(api_model_id("muse-spark-1.3"), "muse-spark-1.3")


if __name__ == "__main__":
    unittest.main()
