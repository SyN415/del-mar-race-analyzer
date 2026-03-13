import importlib.util
import sys
import types
import unittest
from pathlib import Path


if "aiohttp" not in sys.modules:
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.ClientSession = type("ClientSession", (), {})
    aiohttp.ClientTimeout = type("ClientTimeout", (), {"__init__": lambda self, total=None: None})
    aiohttp.ClientError = Exception
    sys.modules["aiohttp"] = aiohttp


MODULE_PATH = Path(__file__).resolve().parent / "services" / "openrouter_client.py"
MODULE_SPEC = importlib.util.spec_from_file_location("real_openrouter_client_for_test", MODULE_PATH)
openrouter_client_module = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = openrouter_client_module
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(openrouter_client_module)

OpenRouterClient = openrouter_client_module.OpenRouterClient


class OpenRouterClientTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.client = OpenRouterClient(types.SimpleNamespace(openrouter_api_key="test-key"))

    def test_calculate_timeout_expands_for_large_web_requests(self):
        timeout_seconds = self.client._calculate_timeout_seconds(
            model_config=self.client._get_model_config("x-ai/grok-4.20-beta"),
            max_tokens=3500,
            plugins=[{"id": "web"}],
            context_size_chars=6000,
        )

        self.assertGreaterEqual(timeout_seconds, 100)

    def test_calculate_timeout_stays_reasonable_for_light_requests(self):
        timeout_seconds = self.client._calculate_timeout_seconds(
            model_config=self.client._get_model_config("google/gemini-3.1-flash-lite-preview"),
            max_tokens=800,
            plugins=None,
            context_size_chars=0,
        )

        self.assertGreaterEqual(timeout_seconds, 45)
        self.assertLess(timeout_seconds, 90)

    def test_calculate_timeout_caps_large_requests(self):
        timeout_seconds = self.client._calculate_timeout_seconds(
            model_config=self.client._get_model_config("openai/gpt-5.4"),
            max_tokens=12000,
            plugins=[{"id": "web"}],
            context_size_chars=50000,
        )

        self.assertGreaterEqual(timeout_seconds, 150)
        self.assertLessEqual(timeout_seconds, 180)


if __name__ == "__main__":
    unittest.main()