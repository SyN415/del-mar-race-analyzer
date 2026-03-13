import sys
import types
import unittest
from unittest.mock import AsyncMock

def _install_app_import_stubs():
    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code: int, detail: str):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def mount(self, *args, **kwargs):
                return None

            def get(self, *args, **kwargs):
                return lambda func: func

            def post(self, *args, **kwargs):
                return lambda func: func

            def on_event(self, *args, **kwargs):
                return lambda func: func

        fastapi.FastAPI = FastAPI
        fastapi.Request = object
        fastapi.BackgroundTasks = object
        fastapi.HTTPException = HTTPException
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class JSONResponse:
            def __init__(self, content=None, status_code=200):
                self.content = content or {}
                self.status_code = status_code

        responses.JSONResponse = JSONResponse
        responses.HTMLResponse = object
        sys.modules["fastapi.responses"] = responses

        staticfiles = types.ModuleType("fastapi.staticfiles")
        staticfiles.StaticFiles = type("StaticFiles", (), {"__init__": lambda self, *args, **kwargs: None})
        sys.modules["fastapi.staticfiles"] = staticfiles

        templating = types.ModuleType("fastapi.templating")

        class Jinja2Templates:
            def __init__(self, *args, **kwargs):
                pass

            def TemplateResponse(self, *args, **kwargs):
                return {"template": args[0] if args else None, "context": args[1] if len(args) > 1 else kwargs}

        templating.Jinja2Templates = Jinja2Templates
        sys.modules["fastapi.templating"] = templating

    if "pydantic" not in sys.modules:
        pydantic = types.ModuleType("pydantic")

        class _FieldDefault:
            def __init__(self, default=None, default_factory=None):
                self.default = default
                self.default_factory = default_factory

        def Field(default=None, default_factory=None):
            return _FieldDefault(default=default, default_factory=default_factory)

        class BaseModel:
            def __init__(self, **kwargs):
                annotations = {}
                for cls in reversed(self.__class__.mro()):
                    annotations.update(getattr(cls, "__annotations__", {}))

                for name in annotations:
                    if name in kwargs:
                        value = kwargs[name]
                    elif hasattr(self.__class__, name):
                        default = getattr(self.__class__, name)
                        if isinstance(default, _FieldDefault):
                            value = default.default_factory() if default.default_factory else default.default
                        else:
                            value = default
                    else:
                        raise TypeError(f"Missing required field: {name}")
                    setattr(self, name, value)

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

    sys.modules.setdefault("uvicorn", types.ModuleType("uvicorn"))

    race_prediction_engine = types.ModuleType("race_prediction_engine")
    race_prediction_engine.RacePredictionEngine = type("RacePredictionEngine", (), {})
    sys.modules["race_prediction_engine"] = race_prediction_engine

    config_manager = types.ModuleType("config.config_manager")

    class ConfigManager:
        def load_config(self):
            return types.SimpleNamespace(openrouter_api_key="test-key")

    config_manager.ConfigManager = ConfigManager
    sys.modules["config.config_manager"] = config_manager

    for module_name, class_name in [
        ("scrapers.playwright_equibase_scraper", "PlaywrightEquibaseScraper"),
        ("scrapers.smartpick_playwright", "FixedPlaywrightSmartPickScraper"),
        ("scrapers.smartpick_scraper", "SmartPickRaceScraper"),
        ("services.session_manager", "SessionManager"),
        ("services.orchestration_service", "OrchestrationService"),
        ("services.openrouter_client", "OpenRouterClient"),
        ("services.gradient_boosting_predictor", "GradientBoostingPredictor"),
        ("services.kelly_optimizer", "KellyCriterionOptimizer"),
    ]:
        module = types.ModuleType(module_name)
        setattr(module, class_name, type(class_name, (), {}))
        sys.modules[module_name] = module


_install_app_import_stubs()

import app as app_module

from services.race_card_admin import extract_json_object, merge_source_urls, normalize_admin_results


class RaceCardAdminTests(unittest.TestCase):
    def test_extract_json_object_handles_fenced_json(self):
        payload = extract_json_object(
            """```json
            {"race_analyses": [{"race_number": 1, "predictions": [{"horse_name": "Alpha"}]}]}
            ```"""
        )

        self.assertEqual(payload["race_analyses"][0]["race_number"], 1)

    def test_normalize_admin_results_maps_predictions_and_summary(self):
        structured = {
            "overview": "Del Mar Friday card",
            "races": [
                {
                    "number": 1,
                    "type": "Allowance",
                    "distance": "6f",
                    "surface": "Dirt",
                    "entries": [
                        {"horse": "Alpha", "post": 1, "jockey": "A. Rider", "trainer": "T. One", "rating": 92},
                        {"horse": "Bravo", "post": 4, "jockey": "B. Rider", "trainer": "T. Two", "rating": 84},
                    ],
                }
            ],
        }

        results = normalize_admin_results(
            structured,
            race_date="2026-03-13",
            track_id="DMR",
            llm_model="x-ai/grok-4.20-beta",
            source_urls=["https://example.com/card"],
            admin_notes="Imported from notes",
            analysis_duration_seconds=1.25,
        )

        self.assertEqual(results["summary"]["total_races"], 1)
        self.assertEqual(results["race_analyses"][0]["predictions"][0]["horse_name"], "Alpha")
        self.assertEqual(results["race_analyses"][0]["top_pick"]["horse_name"], "Alpha")
        self.assertEqual(results["admin_metadata"]["model_used"], "x-ai/grok-4.20-beta")
        self.assertAlmostEqual(
            sum(pred["win_probability"] for pred in results["race_analyses"][0]["predictions"]),
            100.0,
            places=1,
        )

    def test_merge_source_urls_adds_openrouter_citations_without_duplicates(self):
        merged = merge_source_urls(
            source_urls=["https://example.com/card", "not-a-url"],
            annotations=[
                {"type": "url_citation", "url": "https://example.com/card"},
                {"type": "url_citation", "url_citation": {"url": "https://example.com/entries"}},
            ],
        )

        self.assertEqual(merged, ["https://example.com/card", "https://example.com/entries"])

    def test_app_state_initialize_only_sets_up_lightweight_services(self):
        session_manager_called = False

        class SessionManagerShouldNotRun:
            def __init__(self, *args, **kwargs):
                nonlocal session_manager_called
                session_manager_called = True

        class OpenRouterClientStub:
            def __init__(self, config):
                self.api_key = getattr(config, "openrouter_api_key", None)

        original_session_manager = app_module.SessionManager
        original_openrouter_client = app_module.OpenRouterClient

        try:
            app_module.SessionManager = SessionManagerShouldNotRun
            app_module.OpenRouterClient = OpenRouterClientStub

            app_state = app_module.AppState()
            app_module.asyncio.run(app_state.initialize())

            self.assertFalse(session_manager_called)
            self.assertIsNone(app_state.session_manager)
            self.assertEqual(app_state.openrouter_client.api_key, "test-key")
        finally:
            app_module.SessionManager = original_session_manager
            app_module.OpenRouterClient = original_openrouter_client

    def test_landing_page_fails_open_when_dashboard_loading_errors(self):
        original_loader = app_module._load_dashboard_cards

        try:
            app_module._load_dashboard_cards = AsyncMock(side_effect=RuntimeError("dashboard unavailable"))

            response = app_module.asyncio.run(app_module.landing_page(object()))

            self.assertEqual(response["template"], "landing.html")
            self.assertEqual(response["context"]["dashboard_cards"], [])
            self.assertEqual(response["context"]["card_count"], 0)
            self.assertEqual(response["context"]["completed_count"], 0)
        finally:
            app_module._load_dashboard_cards = original_loader


class AdminRaceCardRouteTests(unittest.TestCase):
    def setUp(self):
        self.original_session_manager = app_module.app_state.session_manager
        self.original_openrouter_client = app_module.app_state.openrouter_client

        self.session_manager = type("SessionManagerStub", (), {})()
        self.session_manager.create_session = AsyncMock(return_value="session-123")
        self.session_manager.update_session_status = AsyncMock()
        self.session_manager.save_session_results = AsyncMock()

        self.openrouter_client = type("OpenRouterClientStub", (), {})()
        self.openrouter_client.api_key = "test-key"
        self.openrouter_client.call_model = AsyncMock(return_value={
            "content": '{"race_analyses":[{"race_number":1,"predictions":[{"horse_name":"Alpha","jockey":"A. Rider","trainer":"T. One","composite_rating":90}]}]}',
            "annotations": [{"type": "url_citation", "url_citation": {"url": "https://example.com/search"}}],
            "usage": {},
            "model": "x-ai/grok-4.20-beta",
        })

        app_module.app_state.session_manager = self.session_manager
        app_module.app_state.openrouter_client = self.openrouter_client

    def tearDown(self):
        app_module.app_state.session_manager = self.original_session_manager
        app_module.app_state.openrouter_client = self.original_openrouter_client

    def test_create_admin_race_card_uses_web_plugin_in_web_search_mode(self):
        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
            source_urls=["https://example.com/hint"],
        )

        response = app_module.asyncio.run(app_module.create_admin_race_card(request))
        saved_results = self.session_manager.save_session_results.await_args.args[1]
        call_kwargs = self.openrouter_client.call_model.await_args.kwargs

        self.assertEqual(response.status_code, 200)
        self.assertEqual(call_kwargs["plugins"], [{"id": "web"}])
        self.assertTrue(call_kwargs["return_metadata"])
        self.assertEqual(
            saved_results["source_urls"],
            ["https://example.com/hint", "https://example.com/search"],
        )
        self.assertEqual(saved_results["admin_metadata"]["workflow"], "admin_openrouter_web_search")

    def test_create_admin_race_card_requires_text_in_manual_mode(self):
        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="manual",
            source_text="",
        )

        with self.assertRaises(app_module.HTTPException) as exc:
            app_module.asyncio.run(app_module.create_admin_race_card(request))

        self.assertEqual(exc.exception.status_code, 400)
        self.assertIn("manual mode", exc.exception.detail)


if __name__ == "__main__":
    unittest.main()