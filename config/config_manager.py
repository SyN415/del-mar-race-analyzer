import json
import os
from pathlib import Path
from typing import Any, Dict

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

from .config_schema import ApplicationConfig

class ConfigManager:
    """Manages application configuration from files and environment"""

    def __init__(self, config_dir: Path | str = "config"):
        self._config: ApplicationConfig | None = None
        self._config_path = Path(config_dir)

    def load_config(self) -> ApplicationConfig:
        load_dotenv()
        base = self._load_base_config()
        env = self._load_environment_config()
        merged = self._merge_configs(base, env)
        self._config = ApplicationConfig(**merged)
        return self._config

    def _load_base_config(self) -> Dict[str, Any]:
        files = [
            self._config_path / "config.json",
            self._config_path / "config.development.json",
            self._config_path / "config.production.json",
        ]
        base: Dict[str, Any] = {}
        for f in files:
            if f.exists():
                with open(f, 'r') as fh:
                    try:
                        base.update(json.load(fh))
                    except Exception:
                        # ignore malformed optional files
                        pass
        return base

    def _get_first_env_value(self, *names: str) -> str | None:
        for name in names:
            value = os.getenv(name)
            if value not in (None, ""):
                return value
        return None

    def _parse_env_list(self, *names: str) -> list[str] | None:
        raw_value = self._get_first_env_value(*names)
        if raw_value is None:
            return None

        value = raw_value.strip()
        if not value:
            return []

        if value.startswith("["):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]

        return [item.strip() for item in value.split(",") if item.strip()]

    def _load_environment_config(self) -> Dict[str, Any]:
        env_config = {
            'api': {
                'equibase_key': os.getenv('EQUIBASE_API_KEY'),
                'drf_key': os.getenv('DRF_API_KEY'),
            },
            'database': {
                'host': os.getenv('DB_HOST') or 'localhost',
                'port': int(os.getenv('DB_PORT', 5432)),
                'database': os.getenv('DB_NAME') or 'delmar_races',
                'username': os.getenv('DB_USER') or 'delmar_user',
                'password': os.getenv('DB_PASSWORD'),
                'supabase_url': os.getenv('SUPABASE_URL'),
                'supabase_rest_url': os.getenv('SUPABASE_REST_URL'),
                'supabase_service_role_key': os.getenv('SUPABASE_SERVICE_ROLE_KEY'),
                'supabase_schema': os.getenv('SUPABASE_SCHEMA', 'public'),
                'supabase_request_timeout_seconds': int(os.getenv('SUPABASE_REQUEST_TIMEOUT_SECONDS', 30)),
            },
            'scraping': {
                'browser_timeout': int(os.getenv('BROWSER_TIMEOUT', 30)),
            },
            'environment': os.getenv('APP_ENV', 'development'),
            'debug': os.getenv('DEBUG', '0') in ('1', 'true', 'True'),
        }

        openrouter_api_key = self._get_first_env_value('DELMAR_OPENROUTER_API_KEY', 'OPENROUTER_API_KEY')
        if openrouter_api_key:
            env_config['openrouter_api_key'] = openrouter_api_key

        web_config: Dict[str, Any] = {}
        admin_password = self._get_first_env_value('DELMAR_ADMIN_PASSWORD')
        auth_secret = self._get_first_env_value('DELMAR_AUTH_SECRET')
        if admin_password is not None:
            web_config['admin_password'] = admin_password
        if auth_secret is not None:
            web_config['auth_secret'] = auth_secret
        if web_config:
            env_config['web'] = web_config

        ai_config: Dict[str, Any] = {}
        default_model = self._get_first_env_value('DELMAR_AI_DEFAULT_MODEL')
        available_models = self._parse_env_list('DELMAR_AI_AVAILABLE_MODELS')
        if default_model:
            ai_config['default_model'] = default_model.strip()
        if available_models is not None:
            ai_config['available_models'] = available_models
        if ai_config:
            env_config['ai'] = ai_config

        return env_config

    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        result = base.copy()
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(result.get(k), dict):
                result[k] = self._merge_configs(result[k], v)
            else:
                result[k] = v
        return result

    @property
    def config(self) -> ApplicationConfig:
        if self._config is None:
            return self.load_config()
        return self._config

