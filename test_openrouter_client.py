import asyncio
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

if "pydantic" not in sys.modules:
    pydantic = types.ModuleType("pydantic")

    class _FieldDefault:
        def __init__(self, default=None, default_factory=None):
            self.default = default
            self.default_factory = default_factory

    def Field(default=None, default_factory=None):
        return _FieldDefault(default=default, default_factory=default_factory)

    pydantic.BaseModel = type("BaseModel", (), {})
    pydantic.Field = Field
    sys.modules["pydantic"] = pydantic


MODULE_PATH = Path(__file__).resolve().parent / "services" / "openrouter_client.py"
MODULE_SPEC = importlib.util.spec_from_file_location("real_openrouter_client_for_test", MODULE_PATH)
openrouter_client_module = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = openrouter_client_module
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(openrouter_client_module)

OpenRouterClient = openrouter_client_module.OpenRouterClient


class _FakeResponse:
    def __init__(self, status, *, json_data=None, text_data=""):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = []

    def post(self, url, *, headers=None, json=None, timeout=None):
        self.posts.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self._responses.pop(0)


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


class OpenRouterClientModelSelectionTests(unittest.TestCase):
    def test_get_optimal_model_prefers_configured_default_model(self):
        client = OpenRouterClient(
            types.SimpleNamespace(
                openrouter_api_key="test-key",
                ai=types.SimpleNamespace(
                    default_model="openai/gpt-5.4",
                    available_models=["google/gemini-3.1-flash-lite-preview", "openai/gpt-5.4"],
                ),
            )
        )

        self.assertEqual(client.get_optimal_model("analysis"), "openai/gpt-5.4")

    def test_get_available_models_respects_configured_allow_list(self):
        client = OpenRouterClient(
            types.SimpleNamespace(
                openrouter_api_key="test-key",
                ai=types.SimpleNamespace(
                    default_model="google/gemini-3.1-flash-lite-preview",
                    available_models=["google/gemini-3.1-flash-lite-preview"],
                ),
            )
        )

        available_models = asyncio.run(client.get_available_models())

        self.assertEqual([model["name"] for model in available_models], ["google/gemini-3.1-flash-lite-preview"])

    def test_get_available_models_includes_custom_configured_model_ids(self):
        client = OpenRouterClient(
            types.SimpleNamespace(
                openrouter_api_key="test-key",
                ai=types.SimpleNamespace(
                    default_model="anthropic/claude-sonnet-4",
                    available_models=["anthropic/claude-sonnet-4", "openai/gpt-5.4"],
                ),
            )
        )

        available_models = asyncio.run(client.get_available_models())

        self.assertEqual([model["name"] for model in available_models], ["anthropic/claude-sonnet-4", "openai/gpt-5.4"])
        self.assertEqual(available_models[0]["tier"], "custom")
        self.assertIsNone(available_models[0]["max_tokens"])


class OpenRouterClientStructuredOutputTests(unittest.TestCase):
    def setUp(self):
        self.client = OpenRouterClient(types.SimpleNamespace(openrouter_api_key="test-key"))

    def test_call_model_includes_response_format_in_payload(self):
        self.client.session = _FakeSession([
            _FakeResponse(
                200,
                json_data={
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                    "model": "x-ai/grok-4.20-beta",
                },
            )
        ])

        result = asyncio.run(
            self.client.call_model(
                model="x-ai/grok-4.20-beta",
                prompt="Return JSON",
                response_format={"type": "json_object"},
            )
        )

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(
            self.client.session.posts[0]["json"]["response_format"],
            {"type": "json_object"},
        )
        self.assertEqual(
            self.client.session.posts[0]["json"]["plugins"],
            [{"id": "response-healing"}],
        )

    def test_call_model_appends_response_healing_to_existing_plugins(self):
        self.client.session = _FakeSession([
            _FakeResponse(
                200,
                json_data={
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                    "model": "minimax/minimax-m2.7",
                },
            )
        ])

        result = asyncio.run(
            self.client.call_model(
                model="minimax/minimax-m2.7",
                prompt="Return JSON",
                plugins=[{"id": "web"}],
                response_format={"type": "json_object"},
            )
        )

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(
            self.client.session.posts[0]["json"]["plugins"],
            [{"id": "web"}, {"id": "response-healing"}],
        )

    def test_call_model_retries_without_response_format_when_provider_rejects_it(self):
        self.client.session = _FakeSession([
            _FakeResponse(
                400,
                text_data='{"error":{"message":"response_format json_object is not supported by this provider"}}',
            ),
            _FakeResponse(
                200,
                json_data={
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                    "model": "minimax/minimax-m2.7",
                },
            ),
        ])

        result = asyncio.run(
            self.client.call_model(
                model="minimax/minimax-m2.7",
                prompt="Return JSON",
                response_format={"type": "json_object"},
            )
        )

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(len(self.client.session.posts), 2)
        self.assertIn("response_format", self.client.session.posts[0]["json"])
        self.assertNotIn("response_format", self.client.session.posts[1]["json"])


if __name__ == "__main__":
    unittest.main()