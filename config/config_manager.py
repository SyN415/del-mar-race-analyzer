import json
import os
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv
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

    def _load_environment_config(self) -> Dict[str, Any]:
        return {
            'api': {
                'equibase_key': os.getenv('EQUIBASE_API_KEY'),
                'drf_key': os.getenv('DRF_API_KEY'),
            },
            'openrouter_api_key': os.getenv('OPENROUTER_API_KEY'),
            'database': {
                'host': os.getenv('DB_HOST') or 'localhost',
                'port': int(os.getenv('DB_PORT', 5432)),
                'database': os.getenv('DB_NAME') or 'delmar_races',
                'username': os.getenv('DB_USER') or 'delmar_user',
                'password': os.getenv('DB_PASSWORD'),
            },
            'scraping': {
                'browser_timeout': int(os.getenv('BROWSER_TIMEOUT', 30)),
            },
            'environment': os.getenv('APP_ENV', 'development'),
            'debug': os.getenv('DEBUG', '0') in ('1', 'true', 'True'),
        }

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

