import os
import sys
import types
import unittest
from unittest.mock import patch


if "pydantic" not in sys.modules:
    pydantic = types.ModuleType("pydantic")

    class _FieldDefault:
        def __init__(self, default=None, default_factory=None):
            self.default = default
            self.default_factory = default_factory

    def Field(default=None, default_factory=None):
        return _FieldDefault(default=default, default_factory=default_factory)

    class BaseModel:
        pass

    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    sys.modules["pydantic"] = pydantic

from config.config_manager import ConfigManager


class ConfigManagerEnvTests(unittest.TestCase):
    def test_load_environment_config_reads_delmar_ai_and_auth_settings(self):
        manager = ConfigManager()

        with patch.dict(
            os.environ,
            {
                "DELMAR_AI_DEFAULT_MODEL": "openai/gpt-5.4",
                "DELMAR_AI_AVAILABLE_MODELS": "google/gemini-3.1-flash-lite-preview, openai/gpt-5.4",
                "DELMAR_ADMIN_PASSWORD": "secret-password",
                "DELMAR_AUTH_SECRET": "secret-signing-key",
            },
            clear=True,
        ):
            env_config = manager._load_environment_config()

        self.assertEqual(env_config["ai"]["default_model"], "openai/gpt-5.4")
        self.assertEqual(
            env_config["ai"]["available_models"],
            ["google/gemini-3.1-flash-lite-preview", "openai/gpt-5.4"],
        )
        self.assertEqual(env_config["web"]["admin_password"], "secret-password")
        self.assertEqual(env_config["web"]["auth_secret"], "secret-signing-key")

    def test_load_environment_config_accepts_json_model_list(self):
        manager = ConfigManager()

        with patch.dict(
            os.environ,
            {
                "DELMAR_AI_AVAILABLE_MODELS": '["x-ai/grok-4.20-beta", "openai/gpt-5.4"]',
            },
            clear=True,
        ):
            env_config = manager._load_environment_config()

        self.assertEqual(
            env_config["ai"]["available_models"],
            ["x-ai/grok-4.20-beta", "openai/gpt-5.4"],
        )


if __name__ == "__main__":
    unittest.main()