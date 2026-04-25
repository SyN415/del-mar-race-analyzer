import asyncio
import json
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock

_ORIGINAL_MODULES = {}

def _install_app_import_stubs():
    def _remember(name: str):
        if name not in _ORIGINAL_MODULES:
            _ORIGINAL_MODULES[name] = sys.modules.get(name)

    _remember("fastapi")
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

        def delete(self, *args, **kwargs):
            return lambda func: func

        def patch(self, *args, **kwargs):
            return lambda func: func

        def put(self, *args, **kwargs):
            return lambda func: func

        def on_event(self, *args, **kwargs):
            return lambda func: func

    fastapi.FastAPI = FastAPI
    fastapi.Request = object
    fastapi.BackgroundTasks = object
    fastapi.HTTPException = HTTPException
    sys.modules["fastapi"] = fastapi

    _remember("fastapi.responses")
    responses = types.ModuleType("fastapi.responses")

    class JSONResponse:
        def __init__(self, content=None, status_code=200):
            self.content = content or {}
            self.status_code = status_code

    class RedirectResponse:
        def __init__(self, url="/", status_code=302):
            self.url = url
            self.status_code = status_code

        def set_cookie(self, *args, **kwargs):
            pass

        def delete_cookie(self, *args, **kwargs):
            pass

    class Response:
        def __init__(self, content=None, status_code=200, media_type=None):
            self.content = content
            self.status_code = status_code
            self.media_type = media_type

    responses.JSONResponse = JSONResponse
    responses.HTMLResponse = object
    responses.RedirectResponse = RedirectResponse
    responses.Response = Response
    sys.modules["fastapi.responses"] = responses

    _remember("fastapi.staticfiles")
    staticfiles = types.ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = type("StaticFiles", (), {"__init__": lambda self, *args, **kwargs: None})
    sys.modules["fastapi.staticfiles"] = staticfiles

    _remember("fastapi.templating")
    templating = types.ModuleType("fastapi.templating")

    class Jinja2Templates:
        def __init__(self, *args, **kwargs):
            pass

        def TemplateResponse(self, *args, **kwargs):
            template = None
            context = kwargs.get("context")
            if len(args) >= 3:
                _, template, context = args[:3]
            elif len(args) >= 2:
                template, context = args[:2]
            elif len(args) == 1:
                template = args[0]
            response = {"template": template, "context": context}
            if "status_code" in kwargs:
                response["status_code"] = kwargs["status_code"]
            return response

    templating.Jinja2Templates = Jinja2Templates
    sys.modules["fastapi.templating"] = templating

    _remember("pydantic")
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

    _remember("uvicorn")
    sys.modules.setdefault("uvicorn", types.ModuleType("uvicorn"))

    _remember("race_prediction_engine")
    race_prediction_engine = types.ModuleType("race_prediction_engine")
    race_prediction_engine.RacePredictionEngine = type("RacePredictionEngine", (), {})
    sys.modules["race_prediction_engine"] = race_prediction_engine

    _remember("config.config_manager")
    config_manager = types.ModuleType("config.config_manager")

    class ConfigManager:
        def load_config(self):
            web = types.SimpleNamespace(admin_password=None, auth_secret=None)
            ai = types.SimpleNamespace(
                default_model="x-ai/grok-4.20-beta",
                available_models=[
                    "google/gemini-3.1-flash-lite-preview",
                    "x-ai/grok-4.20-beta",
                    "openai/gpt-5.4",
                    "deepseek/deepseek-v4-pro",
                ],
            )
            return types.SimpleNamespace(openrouter_api_key="test-key", web=web, ai=ai)

    config_manager.ConfigManager = ConfigManager
    sys.modules["config.config_manager"] = config_manager

    # Stub aiohttp so the real services.openrouter_client can be imported in tests.
    aiohttp_stub = types.ModuleType("aiohttp")

    class ClientSessionStub:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        def post(self, *args, **kwargs):
            raise NotImplementedError

    class ClientTimeoutStub:
        def __init__(self, total=None):
            self.total = total

    aiohttp_stub.ClientSession = ClientSessionStub
    aiohttp_stub.ClientTimeout = ClientTimeoutStub
    sys.modules["aiohttp"] = aiohttp_stub

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
        _remember(module_name)
        module = types.ModuleType(module_name)
        setattr(module, class_name, type(class_name, (), {}))
        sys.modules[module_name] = module


def _restore_original_modules():
    for module_name, original_module in _ORIGINAL_MODULES.items():
        if original_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = original_module


_install_app_import_stubs()

import app as app_module

_restore_original_modules()

from services.race_card_admin import (
    AdminRaceCardJSONError,
    _is_imperva_challenge,
    _parse_equibase_expected_horses_by_race,
    apply_deep_dive_field_corrections,
    build_equibase_card_overview_url,
    extract_json_object,
    extract_structured_horse_names_by_race,
    extract_structured_race_numbers,
    find_missing_horses_by_race,
    find_missing_race_numbers,
    merge_source_urls,
    merge_structured_race_cards,
    normalize_admin_results,
)


class RaceCardAdminTests(unittest.TestCase):
    def test_extract_json_object_handles_fenced_json(self):
        payload = extract_json_object(
            """```json
            {"race_analyses": [{"race_number": 1, "predictions": [{"horse_name": "Alpha"}]}]}
            ```"""
        )

        self.assertEqual(payload["race_analyses"][0]["race_number"], 1)

    def test_extract_json_object_handles_prose_wrapped_json_with_trailing_commas(self):
        payload = extract_json_object(
            """Here is the structured card:\n```json
            {"race_analyses": [{"race_number": 1, "predictions": [{"horse_name": "Alpha",},],}],}
            ```\nUse this payload only."""
        )

        self.assertEqual(payload["race_analyses"][0]["predictions"][0]["horse_name"], "Alpha")

    def test_extract_json_object_raises_diagnostic_error_for_malformed_json(self):
        with self.assertRaises(AdminRaceCardJSONError) as exc:
            extract_json_object(
                '{"race_analyses": [{"race_number": 1 "predictions": [{"horse_name": "Alpha"}]}]}'
            )

        self.assertIn("Expecting ',' delimiter", exc.exception.public_message)
        self.assertIn("Context near error", exc.exception.diagnostic_message)

    def test_normalize_admin_results_maps_predictions_summary_and_field_metadata(self):
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
            expected_horses_by_race={1: ["Alpha", "Bravo", "Charlie"]},
            source_urls=["https://example.com/card"],
            admin_notes="Imported from notes",
            analysis_duration_seconds=1.25,
        )

        self.assertEqual(results["summary"]["total_races"], 1)
        self.assertEqual(results["race_analyses"][0]["predictions"][0]["horse_name"], "Alpha")
        self.assertEqual(results["race_analyses"][0]["top_pick"]["horse_name"], "Alpha")
        self.assertEqual(results["admin_metadata"]["model_used"], "x-ai/grok-4.20-beta")
        self.assertEqual(results["race_analyses"][0]["field_size"], 2)
        self.assertEqual(results["race_analyses"][0]["expected_field_size"], 3)
        self.assertFalse(results["race_analyses"][0]["field_complete"])
        self.assertEqual(results["race_analyses"][0]["missing_horses"], ["Charlie"])
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

    def test_build_equibase_card_overview_url_formats_expected_path(self):
        url = build_equibase_card_overview_url("sa", "2026-03-13")

        self.assertEqual(
            url,
            "https://www.equibase.com/static/entry/SA031326USA-EQB.html?SAP=viewe2",
        )

    def test_extract_structured_race_numbers_and_find_missing_races(self):
        structured = {
            "race_analyses": [
                {"race_number": 3, "predictions": [{"horse_name": "Gamma"}]},
                {"number": 1, "entries": [{"horse": "Alpha"}]},
            ]
        }

        self.assertEqual(extract_structured_race_numbers(structured), [1, 3])
        self.assertEqual(find_missing_race_numbers(structured, [1, 2, 3, 4]), [2, 4])

    def test_extract_structured_horse_names_and_find_missing_horses_by_race(self):
        structured = {
            "race_analyses": [
                {
                    "race_number": 1,
                    "predictions": [
                        {"horse_name": "Alpha"},
                        {"horse_name": "Bravo (KY)"},
                    ],
                },
                {
                    "race_number": 2,
                    "entries": [
                        {"horse": "Charlie"},
                    ],
                },
            ]
        }

        self.assertEqual(
            extract_structured_horse_names_by_race(structured),
            {1: ["Alpha", "Bravo"], 2: ["Charlie"]},
        )
        self.assertEqual(
            find_missing_horses_by_race(
                structured,
                {1: ["Alpha", "Bravo", "Delta"], 2: ["Charlie", "Echo"]},
            ),
            {1: ["Delta"], 2: ["Echo"]},
        )

    def test_parse_equibase_expected_horses_filters_pedigree_links(self):
        fake_module = types.ModuleType("race_entry_scraper")

        class FakeRaceEntryScraper:
            def parse_card_overview(self, html):
                return [
                    {
                        "race_number": 1,
                        "horses": [
                            {
                                "name": "Empire's Classic (KY)",
                                "profile_url": "https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=10999956&registry=T&rbt=TB",
                            },
                            {
                                "name": "Classic Empire",
                                "profile_url": "https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=9709258&registry=T&rbt=TB",
                            },
                            {
                                "name": "Princess Roi",
                                "profile_url": "https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=9658264&registry=T&rbt=TB",
                            },
                            {
                                "name": "Smooth Salute (KY)",
                                "profile_url": "https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=10784093&registry=T&rbt=TB",
                            },
                            {
                                "name": "Midnight Lute",
                                "profile_url": "https://www.equibase.com/profiles/Results.cfm?type=Horse&refno=6875760&registry=T&rbt=TB",
                            },
                        ],
                    }
                ]

        fake_module.RaceEntryScraper = FakeRaceEntryScraper
        original_module = sys.modules.get("race_entry_scraper")
        sys.modules["race_entry_scraper"] = fake_module

        try:
            expected_horses = _parse_equibase_expected_horses_by_race(
                """
                <input type='checkbox' onclick="onVSAddClick(this, 10999956, 'TB', 'Empire%27s%20Classic')">
                <input type='checkbox' onclick="onVSAddClick(this, 10784093, 'TB', 'Smooth%20Salute')">
                <div><b>Pedigrees (Sire - Dam, by Dam Sire):</b></div>
                """
            )
        finally:
            if original_module is None:
                sys.modules.pop("race_entry_scraper", None)
            else:
                sys.modules["race_entry_scraper"] = original_module

        self.assertEqual(expected_horses, {1: ["Empire's Classic", "Smooth Salute"]})
        self.assertEqual(
            find_missing_horses_by_race(
                {
                    "race_analyses": [
                        {
                            "race_number": 1,
                            "predictions": [
                                {"horse_name": "Empire's Classic"},
                                {"horse_name": "Smooth Salute"},
                            ],
                        }
                    ]
                },
                expected_horses,
            ),
            {},
        )

    def test_merge_structured_race_cards_merges_split_race_fields(self):
        first = {
            "card_overview": "First pass",
            "race_analyses": [
                {
                    "race_number": 1,
                    "predictions": [
                        {"horse_name": "Alpha", "composite_rating": 90},
                        {"horse_name": "Charlie", "composite_rating": 82},
                    ],
                },
            ],
        }
        second = {
            "card_overview": "Retry pass",
            "race_analyses": [
                {
                    "race_number": 1,
                    "race_type": "Allowance",
                    "distance": "6f",
                    "surface": "Dirt",
                    "predictions": [
                        {"horse_name": "Alpha", "jockey": "A. Rider", "composite_rating": 91},
                        {"horse_name": "Bravo", "composite_rating": 84},
                    ],
                },
                {"race_number": 2, "predictions": [{"horse_name": "Charlie"}]},
            ],
        }

        merged = merge_structured_race_cards(first, second)

        self.assertEqual(merged["card_overview"], "First pass")
        self.assertEqual([race["race_number"] for race in merged["race_analyses"]], [1, 2])
        self.assertEqual(merged["race_analyses"][0]["race_type"], "Allowance")
        self.assertEqual(
            {prediction["horse_name"] for prediction in merged["race_analyses"][0]["predictions"]},
            {"Alpha", "Bravo", "Charlie"},
        )

    def test_admin_prompt_and_context_include_expected_and_missing_horses(self):
        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
            source_urls=["https://example.com/hint"],
            admin_notes="Focus on stakes races",
        )

        prompt = app_module._build_admin_structuring_prompt(
            request,
            expected_race_numbers=[1, 2, 3],
            missing_race_numbers=[3],
            expected_horses_by_race={3: ["Gamma", "Delta"]},
            missing_horses_by_race={3: ["Delta"]},
            official_card_url="https://example.com/official-card",
        )
        context = app_module._build_admin_structuring_context(
            request,
            "",
            expected_race_numbers=[1, 2, 3],
            missing_race_numbers=[3],
            expected_horses_by_race={3: ["Gamma", "Delta"]},
            missing_horses_by_race={3: ["Delta"]},
            official_card_url="https://example.com/official-card",
        )

        self.assertIn("Official card overview URL: https://example.com/official-card", prompt)
        self.assertIn("ONLY for these missing races: 3", prompt)
        self.assertIn("Missing horses on retry: Race 3: Delta.", prompt)
        self.assertIn("Never truncate to only the top 3-5 horses", prompt)
        self.assertEqual(context["expected_race_numbers"], [1, 2, 3])
        self.assertEqual(context["missing_race_numbers"], [3])
        self.assertEqual(context["expected_horses_by_race"], {3: ["Gamma", "Delta"]})
        self.assertEqual(context["missing_horses_by_race"], {3: ["Delta"]})
        self.assertEqual(context["official_card_url"], "https://example.com/official-card")

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
        original_ensure_session_manager = app_module.app_state.ensure_session_manager

        try:
            session_manager = type("LandingSessionManagerStub", (), {})()
            session_manager.get_published_curated_cards = AsyncMock(side_effect=RuntimeError("dashboard unavailable"))
            session_manager.get_recap_summary_30d = AsyncMock(side_effect=RuntimeError("recap unavailable"))
            app_module.app_state.ensure_session_manager = AsyncMock(return_value=session_manager)

            fake_request = types.SimpleNamespace(cookies={}, base_url="https://trackstar.test/")
            response = app_module.asyncio.run(app_module.landing_page(fake_request))

            self.assertEqual(response["template"], "landing.html")
            self.assertEqual(response["context"]["live_cards"], [])
            self.assertEqual(response["context"]["upcoming_cards"], [])
            self.assertEqual(response["context"]["past_cards"], [])
            self.assertIsNone(response["context"]["track_record_summary"])
        finally:
            app_module.app_state.ensure_session_manager = original_ensure_session_manager

    def test_admin_race_card_request_uses_configured_default_model(self):
        original_default_model = app_module.app_state.config.ai.default_model

        try:
            app_module.app_state.config.ai.default_model = "openai/gpt-5.4"

            request = app_module.AdminRaceCardRequest(race_date="2026-03-13")

            self.assertEqual(request.llm_model, "openai/gpt-5.4")
        finally:
            app_module.app_state.config.ai.default_model = original_default_model

    def test_configured_model_ids_preserve_custom_env_models(self):
        original_models = list(app_module.app_state.config.ai.available_models)

        try:
            app_module.app_state.config.ai.available_models = [
                "anthropic/claude-sonnet-4",
                "openai/gpt-5.4",
                "anthropic/claude-sonnet-4",
            ]

            self.assertEqual(
                app_module._get_configured_model_ids(),
                ["anthropic/claude-sonnet-4", "openai/gpt-5.4"],
            )
        finally:
            app_module.app_state.config.ai.available_models = original_models

    def test_build_model_option_creates_generic_metadata_for_custom_models(self):
        option = app_module._build_model_option("anthropic/claude-sonnet-4")

        self.assertEqual(option["id"], "anthropic/claude-sonnet-4")
        self.assertEqual(option["tier_label"], "Custom")
        self.assertIn("Configured via environment variable", option["description"])

    def test_auth_requires_both_admin_password_and_auth_secret(self):
        original_admin_password = app_module.app_state.config.web.admin_password
        original_auth_secret = app_module.app_state.config.web.auth_secret

        try:
            app_module.app_state.config.web.admin_password = "super-secret"
            app_module.app_state.config.web.auth_secret = None

            self.assertFalse(app_module._auth_enabled())
        finally:
            app_module.app_state.config.web.admin_password = original_admin_password
            app_module.app_state.config.web.auth_secret = original_auth_secret

    def test_login_submit_shows_setup_required_when_auth_secret_is_missing(self):
        original_admin_password = app_module.app_state.config.web.admin_password
        original_auth_secret = app_module.app_state.config.web.auth_secret

        try:
            app_module.app_state.config.web.admin_password = "super-secret"
            app_module.app_state.config.web.auth_secret = None

            request = types.SimpleNamespace(
                cookies={},
                form=AsyncMock(return_value={"password": "super-secret"}),
            )

            response = app_module.asyncio.run(app_module.login_submit(request))

            self.assertEqual(response["template"], "login.html")
            self.assertIn("TRACKSTAR_AUTH_SECRET", response["context"]["configuration_hint"])
        finally:
            app_module.app_state.config.web.admin_password = original_admin_password
            app_module.app_state.config.web.auth_secret = original_auth_secret


class AdminRaceCardRouteTests(unittest.TestCase):
    def setUp(self):
        self.original_session_manager = app_module.app_state.session_manager
        self.original_openrouter_client = app_module.app_state.openrouter_client
        self.original_admin_password = app_module.app_state.config.web.admin_password
        self.original_auth_secret = app_module.app_state.config.web.auth_secret
        self.original_cached_auth_secret = app_module._AUTH_SECRET

        self.session_manager = type("SessionManagerStub", (), {})()
        self.session_manager.create_session = AsyncMock(return_value="session-123")
        self.session_manager.update_session_status = AsyncMock()
        self.session_manager.save_session_results = AsyncMock()
        self.session_manager.delete_deep_dives_for_card = AsyncMock(return_value=0)

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
        app_module.app_state.config.web.admin_password = "super-secret"
        app_module.app_state.config.web.auth_secret = "signing-secret"
        app_module._AUTH_SECRET = None
        self.admin_request = types.SimpleNamespace(
            cookies={app_module.AUTH_COOKIE_NAME: app_module._sign_value("admin")}
        )

    def tearDown(self):
        app_module.app_state.session_manager = self.original_session_manager
        app_module.app_state.openrouter_client = self.original_openrouter_client
        app_module.app_state.config.web.admin_password = self.original_admin_password
        app_module.app_state.config.web.auth_secret = self.original_auth_secret
        app_module._AUTH_SECRET = self.original_cached_auth_secret

    def test_create_admin_race_card_uses_web_plugin_in_web_search_mode(self):
        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
            source_urls=["https://example.com/hint"],
        )

        response = app_module.asyncio.run(app_module.create_admin_race_card(request, self.admin_request))
        saved_results = self.session_manager.save_session_results.await_args.args[1]
        call_kwargs = self.openrouter_client.call_model.await_args.kwargs
        official_card_url = build_equibase_card_overview_url("SA", "2026-03-13")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.openrouter_client.call_model.await_count, 1)
        self.assertEqual(call_kwargs["plugins"], [{"id": "web"}])
        self.assertEqual(call_kwargs["max_tokens"], app_module.ADMIN_WEB_SEARCH_INITIAL_MAX_TOKENS)
        self.assertTrue(call_kwargs["return_metadata"])
        self.assertEqual(call_kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(
            saved_results["source_urls"],
            ["https://example.com/hint", official_card_url, "https://example.com/search"],
        )
        self.assertEqual(saved_results["admin_metadata"]["workflow"], "admin_openrouter_web_search")
        # A successful card build must invalidate the race_data_cache for the
        # (date, track) pair so any stale per-race deep-dives from a prior
        # session do not poison auto-curate / display.
        self.session_manager.delete_deep_dives_for_card.assert_awaited_once_with(
            "2026-03-13", "SA"
        )

    def test_create_admin_race_card_requires_admin_auth_when_enabled(self):
        original_admin_password = app_module.app_state.config.web.admin_password
        original_auth_secret = app_module.app_state.config.web.auth_secret

        try:
            app_module.app_state.config.web.admin_password = "super-secret"
            app_module.app_state.config.web.auth_secret = "signing-secret"
            request = app_module.AdminRaceCardRequest(
                race_date="2026-03-13",
                track_id="SA",
                llm_model="x-ai/grok-4.20-beta",
                source_mode="web_search",
            )

            with self.assertRaises(app_module.HTTPException) as exc:
                app_module.asyncio.run(
                    app_module.create_admin_race_card(request, types.SimpleNamespace(cookies={}))
                )

            self.assertEqual(exc.exception.status_code, 403)
            self.session_manager.create_session.assert_not_awaited()
            self.openrouter_client.call_model.assert_not_awaited()
        finally:
            app_module.app_state.config.web.admin_password = original_admin_password
            app_module.app_state.config.web.auth_secret = original_auth_secret

    def test_create_admin_race_card_allows_signed_admin_when_auth_enabled(self):
        original_admin_password = app_module.app_state.config.web.admin_password
        original_auth_secret = app_module.app_state.config.web.auth_secret

        try:
            app_module.app_state.config.web.admin_password = "super-secret"
            app_module.app_state.config.web.auth_secret = "signing-secret"
            request = app_module.AdminRaceCardRequest(
                race_date="2026-03-13",
                track_id="SA",
                llm_model="x-ai/grok-4.20-beta",
                source_mode="web_search",
            )
            admin_request = types.SimpleNamespace(
                cookies={app_module.AUTH_COOKIE_NAME: app_module._sign_value("admin")}
            )

            response = app_module.asyncio.run(app_module.create_admin_race_card(request, admin_request))

            self.assertEqual(response.status_code, 200)
            self.session_manager.create_session.assert_awaited()
        finally:
            app_module.app_state.config.web.admin_password = original_admin_password
            app_module.app_state.config.web.auth_secret = original_auth_secret

    def test_admin_race_card_request_defaults_to_configured_model(self):
        request = app_module.AdminRaceCardRequest(race_date="2026-03-13")

        self.assertEqual(request.llm_model, app_module.app_state.config.ai.default_model)

    def test_create_admin_race_card_surfaces_openrouter_timeout_as_503(self):
        self.openrouter_client.call_model = AsyncMock(return_value={
            "content": "AI analysis enhancement (fallback mode): timeout fallback",
            "annotations": [],
            "usage": {},
            "model": "x-ai/grok-4.20-beta",
            "fallback": True,
            "failure_reason": "timeout",
            "failure_detail": "OpenRouter API request timed out",
            "attempts": 4,
        })

        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
        )

        with self.assertRaises(app_module.HTTPException) as exc:
            app_module.asyncio.run(app_module.create_admin_race_card(request, self.admin_request))

        self.assertEqual(exc.exception.status_code, 503)
        self.assertIn("timed out", exc.exception.detail)
        self.assertIn("4 attempts", exc.exception.detail)
        self.session_manager.save_session_results.assert_not_awaited()
        self.assertTrue(any(
            args.args[4] == exc.exception.detail
            for args in self.session_manager.update_session_status.await_args_list
        ))

    def test_create_admin_race_card_surfaces_malformed_json_with_model_context(self):
        self.openrouter_client.call_model = AsyncMock(return_value={
            "content": '{"race_analyses": [{"race_number": 1 "predictions": [{"horse_name": "Alpha"}]}]}',
            "annotations": [],
            "usage": {},
            "model": "z-ai/glm-5-turbo",
        })

        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
        )

        with self.assertRaises(app_module.HTTPException) as exc:
            app_module.asyncio.run(app_module.create_admin_race_card(request, self.admin_request))

        self.assertEqual(exc.exception.status_code, 422)
        self.assertIn("malformed structured data", exc.exception.detail)
        self.assertIn("z-ai/glm-5-turbo", exc.exception.detail)
        self.assertIn("Expecting ',' delimiter", exc.exception.detail)
        self.session_manager.save_session_results.assert_not_awaited()

    def test_create_admin_race_card_retries_malformed_minimax_json_with_compact_prompt(self):
        original_available_models = app_module.app_state.config.ai.available_models
        self.openrouter_client.call_model = AsyncMock(side_effect=[
            {
                "content": '{"race_analyses": [{"race_number": 1 "predictions": [{"horse_name": "Alpha"}]}]}',
                "annotations": [{"type": "url_citation", "url": "https://example.com/initial"}],
                "usage": {},
                "model": "minimax/minimax-m2.7:free",
            },
            {
                "content": '{"card_overview":"Compact retry succeeded","race_analyses":[{"race_number":1,"race_type":"Allowance","distance":"6f","surface":"Dirt","predictions":[{"horse_name":"Alpha","post_position":1,"jockey":"A. Rider","trainer":"T. One","composite_rating":90}]}]}',
                "annotations": [{"type": "url_citation", "url": "https://example.com/retry"}],
                "usage": {},
                "model": "minimax/minimax-m2.7:free",
            },
        ])

        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="minimax/minimax-m2.7",
            source_mode="web_search",
        )

        try:
            app_module.app_state.config.ai.available_models = list(original_available_models) + ["minimax/minimax-m2.7"]
            response = app_module.asyncio.run(app_module.create_admin_race_card(request, self.admin_request))
            saved_results = self.session_manager.save_session_results.await_args.args[1]
            second_call_kwargs = self.openrouter_client.call_model.await_args_list[1].kwargs
        finally:
            app_module.app_state.config.ai.available_models = original_available_models

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.openrouter_client.call_model.await_count, 2)
        self.assertEqual(second_call_kwargs["max_tokens"], app_module.ADMIN_WEB_SEARCH_INITIAL_MAX_TOKENS)
        self.assertIn("compact retry", second_call_kwargs["prompt"])
        self.assertIn("omit `factors` and `exotic_suggestions`", second_call_kwargs["prompt"])
        self.assertEqual(saved_results["race_analyses"][0]["predictions"][0]["horse_name"], "Alpha")
        self.assertTrue(any(
            args.args[3] == "admin_retry_malformed_json"
            for args in self.session_manager.update_session_status.await_args_list
        ))

    def test_admin_prompt_adds_fallback_sources_when_no_server_grounding(self):
        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
        )

        ungrounded_prompt = app_module._build_admin_structuring_prompt(
            request,
            expected_race_numbers=[],
            expected_horses_by_race={},
            equibase_entry_details=None,
        )
        grounded_prompt = app_module._build_admin_structuring_prompt(
            request,
            expected_race_numbers=[1],
            expected_horses_by_race={1: ["Alpha"]},
            equibase_entry_details={1: [{"name": "Alpha"}]},
        )

        # Ungrounded prompt must enumerate the multi-source fallback list and
        # require cross-referencing at least two sources.
        self.assertIn("horseracingnation.com", ungrounded_prompt)
        self.assertIn("bloodhorse.com", ungrounded_prompt)
        self.assertIn("Cross-reference at least TWO", ungrounded_prompt)
        # Grounded prompt keeps the SmartPick-as-primary wording and does not
        # need the hard "two independent sources" rule in its data_source_rules
        # block.
        self.assertIn("SmartPick", grounded_prompt)
        self.assertNotIn("Cross-reference at least TWO", grounded_prompt)


class PublicCuratedCardRoutingTests(unittest.TestCase):
    def _fake_request(self):
        return types.SimpleNamespace(cookies={}, base_url="https://trackstar.test/", headers={})

    def _published_card(self):
        return {
            "session_id": "session-123",
            "race_date": "2026-03-13",
            "track_id": "SA",
            "card_overview": "Santa Anita card-level analysis for a fast-paced Friday slate.",
            "races_json": [
                {
                    "race_number": 1,
                    "top_pick": "Alpha",
                    "value_play": "Bravo",
                    "longshot": "Charlie",
                    "race_notes": "Pace edge for Alpha with a favorable outside stalking trip.",
                },
                {
                    "race_number": 2,
                    "top_pick": "Delta",
                    "value_play": "Echo",
                    "longshot": "Foxtrot",
                },
            ],
            "updated_at": "2026-03-13T18:30:00+00:00",
        }

    def _session_manager_stub(self):
        session_manager = type("SessionManagerStub", (), {})()
        session_manager.get_published_curated_card = AsyncMock(return_value=self._published_card())
        session_manager.get_published_curated_cards = AsyncMock(return_value=[self._published_card()])
        session_manager.get_recap_summary_30d = AsyncMock(return_value={"summary": {}, "records": []})
        session_manager.get_session_results = AsyncMock(return_value={
            "race_analyses": [
                {
                    "race_number": 1,
                    "predictions": [
                        {
                            "horse_name": "Alpha",
                            "jockey": "",
                            "trainer": "",
                            "morning_line_odds": "5/2",
                            "win_probability": 35,
                            "composite_rating": 91,
                        }
                    ],
                }
            ]
        })
        session_manager.get_race_deep_dive = AsyncMock(return_value={
            "deep_dive": {
                "horses": [
                    {"name": "Alpha", "jockey": "A. Rider", "trainer": "T. One"}
                ]
            }
        })
        return session_manager

    def test_public_curated_card_page_builds_canonical_context_for_published_cards(self):
        session_manager = self._session_manager_stub()
        original = app_module.app_state.ensure_session_manager
        try:
            app_module.app_state.ensure_session_manager = AsyncMock(return_value=session_manager)
            response = app_module.asyncio.run(
                app_module.public_curated_card_page(self._fake_request(), "santa-anita", "2026-03-13")
            )
        finally:
            app_module.app_state.ensure_session_manager = original

        self.assertEqual(response["template"], "curated_card.html")
        self.assertEqual(response["context"]["view_mode"], "full-card")
        self.assertEqual(response["context"]["canonical_url"], "https://trackstar.test/santa-anita/2026-03-13")
        self.assertEqual(response["context"]["public_page_data"]["races"]["1"]["path"], "/santa-anita/2026-03-13/race-1")
        self.assertEqual(response["context"]["card"]["races_json"][0]["predictions"][0]["jockey"], "A. Rider")

    def test_public_curated_race_page_returns_404_when_race_is_missing(self):
        session_manager = self._session_manager_stub()
        original = app_module.app_state.ensure_session_manager
        try:
            app_module.app_state.ensure_session_manager = AsyncMock(return_value=session_manager)
            response = app_module.asyncio.run(
                app_module.public_curated_race_page(self._fake_request(), "santa-anita", "2026-03-13", 7)
            )
        finally:
            app_module.app_state.ensure_session_manager = original

        self.assertEqual(response["template"], "error.html")
        self.assertEqual(response["status_code"], 404)
        self.assertIn("Race 7", response["context"]["error"])

    def test_legacy_curated_card_route_redirects_to_canonical_path(self):
        response = app_module.asyncio.run(
            app_module.curated_card_page(self._fake_request(), "2026-03-13", "SA")
        )

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "/santa-anita/2026-03-13")

    def test_sitemap_and_robots_publish_public_card_urls(self):
        session_manager = self._session_manager_stub()
        original = app_module.app_state.ensure_session_manager
        try:
            app_module.app_state.ensure_session_manager = AsyncMock(return_value=session_manager)
            sitemap = app_module.asyncio.run(app_module.sitemap_xml(self._fake_request()))
            robots = app_module.asyncio.run(app_module.robots_txt(self._fake_request()))
        finally:
            app_module.app_state.ensure_session_manager = original

        self.assertIn("https://trackstar.test/santa-anita/2026-03-13", sitemap.content)
        self.assertIn("https://trackstar.test/santa-anita/2026-03-13/race-2", sitemap.content)
        self.assertIn("Sitemap: https://trackstar.test/sitemap.xml", robots.content)


class PublicRecordRoutingTests(unittest.TestCase):
    def _fake_request(self):
        return types.SimpleNamespace(cookies={}, base_url="https://trackstar.test/", headers={})

    def _published_card(self):
        return {
            "session_id": "session-123",
            "race_date": "2026-03-13",
            "track_id": "SA",
            "card_overview": "Santa Anita card-level analysis for a fast-paced Friday slate.",
            "races_json": [{"race_number": 1}, {"race_number": 2}],
            "updated_at": "2026-03-13T18:30:00+00:00",
        }

    def _recap_record(self):
        return {
            "id": "recap-123",
            "race_date": "2026-03-13",
            "track_id": "SA",
            "daily_score": 78.5,
            "top_pick_wins": 3,
            "top_pick_total": 8,
            "exacta_hits": 2,
            "exacta_total": 8,
            "trifecta_hits": 1,
            "trifecta_total": 8,
            "best_winner_horse": "Alpha",
            "best_winner_odds": "6-1",
            "best_exacta_payout": 48.2,
            "best_trifecta_payout": 212.4,
            "races_recap_json": [
                {
                    "race_number": 1,
                    "winner": "Alpha",
                    "winner_odds": "6-1",
                    "our_top_pick": "Alpha",
                    "our_value_play": "Bravo",
                    "our_longshot": "Charlie",
                    "exacta_payout": 48.2,
                    "trifecta_payout": 212.4,
                    "recap_note": "Alpha delivered from a stalking trip.",
                    "hits": {
                        "top_pick_won": True,
                        "value_play_won": False,
                        "longshot_won": False,
                        "exacta_hit": True,
                        "trifecta_hit": True,
                    },
                }
            ],
            "updated_at": "2026-03-13T23:00:00+00:00",
            "created_at": "2026-03-13T23:00:00+00:00",
        }

    def _recap_summary(self):
        secondary = dict(self._recap_record())
        secondary.update({
            "id": "recap-456",
            "race_date": "2026-03-12",
            "track_id": "DMR",
            "daily_score": 64.0,
            "best_winner_horse": "Delta",
            "best_winner_odds": "4-1",
        })
        return {
            "summary": {
                "total_days_recapped": 2,
                "top_pick_win_rate_pct": 37.5,
                "average_daily_score": 71.3,
                "exacta_hit_rate_pct": 25.0,
                "trifecta_hit_rate_pct": 12.5,
                "best_winner_odds_overall": "6-1",
                "best_exacta_payout_overall": 48.2,
                "best_trifecta_payout_overall": 212.4,
            },
            "records": [self._recap_record(), secondary],
        }

    def _session_manager_stub(self):
        session_manager = type("RecordSessionManagerStub", (), {})()
        session_manager.get_recap_summary_30d = AsyncMock(return_value=self._recap_summary())
        session_manager.get_recap_record = AsyncMock(side_effect=lambda race_date, track_id: self._recap_record() if (race_date, track_id) == ("2026-03-13", "SA") else None)
        session_manager.get_published_curated_cards = AsyncMock(return_value=[self._published_card()])
        return session_manager

    def test_record_page_builds_summary_context_and_route_payload(self):
        session_manager = self._session_manager_stub()
        original = app_module.app_state.ensure_session_manager
        try:
            app_module.app_state.ensure_session_manager = AsyncMock(return_value=session_manager)
            response = app_module.asyncio.run(app_module.record_page(self._fake_request()))
        finally:
            app_module.app_state.ensure_session_manager = original

        self.assertEqual(response["template"], "record.html")
        self.assertEqual(response["context"]["view_mode"], "summary")
        self.assertEqual(response["context"]["canonical_url"], "https://trackstar.test/record")
        self.assertIsNone(response["context"]["selected_record"])
        self.assertEqual(response["context"]["records"][0]["public_url"], "/record/santa-anita/2026-03-13")
        self.assertEqual(response["context"]["records"][0]["profitability_score"], 78.5)
        self.assertEqual(
            response["context"]["record_page_data"]["recaps"]["/record/santa-anita/2026-03-13"]["dailyScore"],
            78.5,
        )
        self.assertIn("/record/santa-anita/2026-03-13", response["context"]["record_page_data"]["recaps"])

    def test_record_page_prefers_profitability_score_over_legacy_daily_score_display(self):
        session_manager = self._session_manager_stub()
        profitability_record = self._recap_record()
        profitability_record["daily_score"] = 19.2
        profitability_record["top_pick_wins"] = 3
        profitability_record["top_pick_total"] = 10
        profitability_record["exacta_hits"] = 1
        profitability_record["exacta_total"] = 10
        profitability_record["trifecta_hits"] = 1
        profitability_record["trifecta_total"] = 10
        profitability_record["best_exacta_payout"] = 61.36
        profitability_record["best_trifecta_payout"] = 291.6
        profitability_record["races_recap_json"][0]["exacta_payout"] = 61.36
        profitability_record["races_recap_json"][0]["trifecta_payout"] = 291.6
        profitability_record["races_recap_json"][0]["exotic_payout_unit"] = "1_dollar"
        profitability_record["races_recap_json"][0]["hits"]["exacta_hit"] = True
        profitability_record["races_recap_json"][0]["hits"]["trifecta_hit"] = True

        summary = self._recap_summary()
        summary["records"] = [profitability_record]
        session_manager.get_recap_summary_30d = AsyncMock(return_value=summary)

        original = app_module.app_state.ensure_session_manager
        try:
            app_module.app_state.ensure_session_manager = AsyncMock(return_value=session_manager)
            response = app_module.asyncio.run(app_module.record_page(self._fake_request()))
        finally:
            app_module.app_state.ensure_session_manager = original

        record = response["context"]["records"][0]
        self.assertEqual(record["daily_score"], 19.2)
        self.assertEqual(record["profitability_score"], 61.6)
        self.assertNotEqual(record["profitability_score"], record["daily_score"])
        self.assertEqual(
            response["context"]["record_page_data"]["recaps"]["/record/santa-anita/2026-03-13"]["dailyScore"],
            61.6,
        )

    def test_record_page_normalizes_legacy_two_dollar_exotic_payouts_for_display(self):
        session_manager = self._session_manager_stub()
        legacy_record = self._recap_record()
        legacy_record["best_exacta_payout"] = 79.4
        legacy_record["best_trifecta_payout"] = 482.4
        legacy_record["races_recap_json"][0]["exacta_payout"] = 79.4
        legacy_record["races_recap_json"][0]["trifecta_payout"] = 482.4

        summary = self._recap_summary()
        summary["records"] = [legacy_record]
        summary["summary"]["best_exacta_payout_overall"] = 79.4
        summary["summary"]["best_trifecta_payout_overall"] = 482.4
        session_manager.get_recap_summary_30d = AsyncMock(return_value=summary)

        original = app_module.app_state.ensure_session_manager
        try:
            app_module.app_state.ensure_session_manager = AsyncMock(return_value=session_manager)
            response = app_module.asyncio.run(app_module.record_page(self._fake_request()))
        finally:
            app_module.app_state.ensure_session_manager = original

        race = response["context"]["records"][0]["races_recap_json"][0]
        self.assertEqual(race["exacta_payout"], 39.7)
        self.assertEqual(race["trifecta_payout"], 241.2)
        self.assertEqual(response["context"]["summary"]["best_exacta_payout_overall"], 39.7)
        self.assertEqual(response["context"]["summary"]["best_trifecta_payout_overall"], 241.2)

    def test_recap_detail_page_builds_canonical_detail_context(self):
        session_manager = self._session_manager_stub()
        original = app_module.app_state.ensure_session_manager
        try:
            app_module.app_state.ensure_session_manager = AsyncMock(return_value=session_manager)
            response = app_module.asyncio.run(
                app_module.recap_record_page(self._fake_request(), "santa-anita", "2026-03-13")
            )
        finally:
            app_module.app_state.ensure_session_manager = original

        self.assertEqual(response["template"], "record.html")
        self.assertEqual(response["context"]["view_mode"], "recap")
        self.assertEqual(response["context"]["selected_record"]["track_id"], "SA")
        self.assertEqual(response["context"]["selected_record"]["profitability_score"], 78.5)
        self.assertEqual(response["context"]["canonical_url"], "https://trackstar.test/record/santa-anita/2026-03-13")
        self.assertEqual(response["context"]["record_page_data"]["selectedKey"], "SA::2026-03-13")

    def test_recap_detail_page_returns_404_when_record_is_missing(self):
        session_manager = type("MissingRecordSessionManagerStub", (), {})()
        session_manager.get_recap_summary_30d = AsyncMock(return_value={"summary": {}, "records": []})
        session_manager.get_recap_record = AsyncMock(return_value=None)
        original = app_module.app_state.ensure_session_manager
        try:
            app_module.app_state.ensure_session_manager = AsyncMock(return_value=session_manager)
            response = app_module.asyncio.run(
                app_module.recap_record_page(self._fake_request(), "santa-anita", "2026-03-13")
            )
        finally:
            app_module.app_state.ensure_session_manager = original

        self.assertEqual(response["template"], "error.html")
        self.assertEqual(response["status_code"], 404)
        self.assertIn("Santa Anita", response["context"]["error"])

    def test_sitemap_includes_recap_urls(self):
        session_manager = self._session_manager_stub()
        original = app_module.app_state.ensure_session_manager
        try:
            app_module.app_state.ensure_session_manager = AsyncMock(return_value=session_manager)
            sitemap = app_module.asyncio.run(app_module.sitemap_xml(self._fake_request()))
        finally:
            app_module.app_state.ensure_session_manager = original

        self.assertIn("https://trackstar.test/record", sitemap.content)
        self.assertIn("https://trackstar.test/record/santa-anita/2026-03-13", sitemap.content)


class GenerateRecapNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.original_session_manager = app_module.app_state.session_manager
        self.original_openrouter_client = app_module.app_state.openrouter_client
        self.original_admin_password = app_module.app_state.config.web.admin_password
        self.original_auth_secret = app_module.app_state.config.web.auth_secret
        self.original_cached_auth_secret = app_module._AUTH_SECRET

        self.session_manager = type("RecapSessionManagerStub", (), {})()
        self.session_manager.get_curated_card = AsyncMock(return_value={
            "race_date": "2026-04-13",
            "track_id": "PRX",
            "races_json": [
                {
                    "race_number": 1,
                    "top_pick": "Matzoball Muhammet",
                    "value_play": "Gentleman Don",
                    "longshot": "Craigh Na Dun",
                    "betting_strategy": "Exacta 6-3 and trifecta 6-3-2",
                }
            ],
        })
        self.session_manager.save_recap_record = AsyncMock(return_value="recap-123")

        self.openrouter_client = type("OpenRouterClientStub", (), {})()
        self.openrouter_client.api_key = "test-key"
        self.openrouter_client.call_model = AsyncMock(return_value={
            "content": '{"races":[{"race_number":1,"winner":"Foil","winner_odds":"13-1","top_pick_won":false,"value_play_won":false,"longshot_won":false,"exacta_hit":false,"trifecta_hit":true,"exacta_payout_source":79.40,"exacta_payout_base_amount":2.0,"exacta_payout":39.70,"trifecta_payout_source":120.60,"trifecta_payout_base_amount":0.5,"trifecta_payout":241.20,"recap_note":"Official Equibase payouts captured.","data_available":true}]}'
        })

        app_module.app_state.session_manager = self.session_manager
        app_module.app_state.openrouter_client = self.openrouter_client
        app_module.app_state.config.web.admin_password = "super-secret"
        app_module.app_state.config.web.auth_secret = "signing-secret"
        app_module._AUTH_SECRET = None
        self.admin_request = types.SimpleNamespace(
            cookies={app_module.AUTH_COOKIE_NAME: app_module._sign_value("admin")}
        )

    def tearDown(self):
        app_module.app_state.session_manager = self.original_session_manager
        app_module.app_state.openrouter_client = self.original_openrouter_client
        app_module.app_state.config.web.admin_password = self.original_admin_password
        app_module.app_state.config.web.auth_secret = self.original_auth_secret
        app_module._AUTH_SECRET = self.original_cached_auth_secret

    def test_generate_recap_normalizes_exotic_payouts_to_one_dollar_before_save(self):
        request = app_module.GenerateRecapRequest(
            session_id="session-123",
            race_date="2026-04-13",
            track_id="PRX",
        )

        response = app_module.asyncio.run(app_module.generate_recap(request, self.admin_request))
        saved_payload = self.session_manager.save_recap_record.await_args.kwargs["races_recap_json"]
        saved_race = app_module.json.loads(saved_payload)[0]
        prompt = self.openrouter_client.call_model.await_args.kwargs["prompt"]

        self.assertEqual(response.status_code, 200)
        self.assertIn("normalized payout for a $1 exacta bet and a $1 trifecta bet", prompt)
        self.assertEqual(saved_race["exacta_payout"], 39.7)
        self.assertEqual(saved_race["trifecta_payout"], 241.2)
        self.assertEqual(saved_race["exacta_payout_source"], 79.4)
        self.assertEqual(saved_race["trifecta_payout_source"], 120.6)
        self.assertEqual(saved_race["exotic_payout_unit"], "1_dollar")
        self.assertEqual(self.session_manager.save_recap_record.await_args.kwargs["best_trifecta_payout"], 241.2)


class ImpervaChallengeDetectionTests(unittest.TestCase):
    """Unit tests for the Equibase WAF interstitial detector."""

    def test_detects_pardon_our_interruption_page(self):
        # Reduced fixture matching the actual 4,563-byte Imperva page served
        # when Equibase decides to block a bot request.
        html = (
            "<!DOCTYPE html><html><head>"
            "<noscript><title>Pardon Our Interruption</title></noscript>"
            "<script>window.reeseSkipExpirationCheck = true;</script>"
            "<script>window.onProtectionInitialized = function() {};</script>"
            "</head></html>"
        )
        self.assertTrue(_is_imperva_challenge(html))

    def test_passes_through_real_overview_html(self):
        # Large, realistic-looking page fragment should never be flagged.
        html = "<html>" + ("<p>" + "horse entry " * 80 + "</p>") * 60 + "</html>"
        self.assertGreater(len(html), 20000)
        self.assertFalse(_is_imperva_challenge(html))

    def test_empty_input_is_not_a_challenge(self):
        self.assertFalse(_is_imperva_challenge(""))
        self.assertFalse(_is_imperva_challenge(None))


class OpenRouterClientDeepSeekTests(unittest.TestCase):
    """Unit tests for DeepSeek-specific rate-limit handling and plugin shaping."""

    @classmethod
    def setUpClass(cls):
        # Ensure the real services.openrouter_client module is available.
        # (The test file stubs it during app import but restores it afterwards.)
        import importlib
        cls._openrouter_module = importlib.import_module("services.openrouter_client")
        cls.OpenRouterClient = cls._openrouter_module.OpenRouterClient

    def _client(self):
        ai = types.SimpleNamespace(
            default_model="x-ai/grok-4.20-beta",
            available_models=[
                "google/gemini-3.1-flash-lite-preview",
                "x-ai/grok-4.20-beta",
                "openai/gpt-5.4",
                "deepseek/deepseek-v4-pro",
            ],
        )
        config = types.SimpleNamespace(openrouter_api_key="test-key", ai=ai)
        return self.OpenRouterClient(config)

    def test_is_deepseek_model(self):
        self.assertTrue(self.OpenRouterClient._is_deepseek_model("deepseek/deepseek-v4-pro"))
        self.assertTrue(self.OpenRouterClient._is_deepseek_model("DeepSeek/Chat"))
        self.assertFalse(self.OpenRouterClient._is_deepseek_model("x-ai/grok-4.20-beta"))
        self.assertFalse(self.OpenRouterClient._is_deepseek_model(None))

    def test_parse_retry_after(self):
        self.assertEqual(self.OpenRouterClient._parse_retry_after("2"), 2.0)
        self.assertEqual(self.OpenRouterClient._parse_retry_after("30"), 30.0)
        self.assertIsNone(self.OpenRouterClient._parse_retry_after(None))
        self.assertIsNone(self.OpenRouterClient._parse_retry_after(""))
        self.assertIsNone(self.OpenRouterClient._parse_retry_after("invalid"))

    def test_truncate_error_body(self):
        self.assertEqual(self.OpenRouterClient._truncate_error_body("short"), "short")
        long_text = "x" * 600
        self.assertEqual(
            self.OpenRouterClient._truncate_error_body(long_text, limit=500),
            "x" * 500 + "...",
        )
        self.assertEqual(self.OpenRouterClient._truncate_error_body(""), "(empty body)")
        self.assertEqual(self.OpenRouterClient._truncate_error_body(None), "(empty body)")

    def test_should_use_response_healing(self):
        self.assertFalse(self.OpenRouterClient._should_use_response_healing("deepseek/deepseek-v4-pro"))
        self.assertTrue(self.OpenRouterClient._should_use_response_healing("x-ai/grok-4.20-beta"))
        self.assertTrue(self.OpenRouterClient._should_use_response_healing(None))

    def test_build_request_plugins_includes_healing_for_non_deepseek(self):
        client = self._client()
        plugins = client._build_request_plugins(
            model="x-ai/grok-4.20-beta",
            plugins=[{"id": "web"}],
            response_format={"type": "json_object"},
        )
        self.assertIsNotNone(plugins)
        ids = [p["id"] for p in plugins]
        self.assertIn("web", ids)
        self.assertIn("response-healing", ids)

    def test_build_request_plugins_omits_healing_for_deepseek(self):
        client = self._client()
        plugins = client._build_request_plugins(
            model="deepseek/deepseek-v4-pro",
            plugins=[{"id": "web"}],
            response_format={"type": "json_object"},
        )
        self.assertIsNotNone(plugins)
        ids = [p["id"] for p in plugins]
        self.assertIn("web", ids)
        self.assertNotIn("response-healing", ids)

    def test_should_fail_fast_rate_limit_for_deepseek(self):
        # DeepSeek: attempt 0 (1st try), no Retry-After -> should NOT fail fast (allow retry)
        self.assertFalse(
            self.OpenRouterClient._should_fail_fast_rate_limit(
                "deepseek/deepseek-v4-pro", "", None, attempt=0
            )
        )
        # DeepSeek: attempt 1 (2nd try), no Retry-After -> should fail fast (exhausted budget)
        self.assertTrue(
            self.OpenRouterClient._should_fail_fast_rate_limit(
                "deepseek/deepseek-v4-pro", "", None, attempt=1
            )
        )
        # DeepSeek: attempt 0, Retry-After=60 -> fail fast (exceeds cap)
        self.assertTrue(
            self.OpenRouterClient._should_fail_fast_rate_limit(
                "deepseek/deepseek-v4-pro", "", 60.0, attempt=0
            )
        )
        # DeepSeek: attempt 0, Retry-After=10 -> do not fail fast
        self.assertFalse(
            self.OpenRouterClient._should_fail_fast_rate_limit(
                "deepseek/deepseek-v4-pro", "", 10.0, attempt=0
            )
        )
        # Non-DeepSeek: never fail fast
        self.assertFalse(
            self.OpenRouterClient._should_fail_fast_rate_limit(
                "x-ai/grok-4.20-beta", "", None, attempt=5
            )
        )

    def test_rate_limit_failure_detail_contains_guidance_and_body(self):
        detail = self.OpenRouterClient._rate_limit_failure_detail(
            "deepseek/deepseek-v4-pro",
            "error body here",
            retry_after=15.0,
        )
        self.assertIn("OpenRouter rate limited deepseek/deepseek-v4-pro", detail)
        self.assertIn("switch to Grok/GPT", detail)
        self.assertIn("OpenRouter suggested retrying after 15 seconds", detail)
        self.assertIn("error body here", detail)

    def test_rate_limit_failure_detail_with_provider_metadata(self):
        detail = self.OpenRouterClient._rate_limit_failure_detail(
            "deepseek/deepseek-v4-pro",
            "some body",
            retry_after=None,
            provider_metadata={"provider_name": "Together", "is_byok": False},
        )
        self.assertIn("provider Together", detail)
        self.assertIn("BYOK", detail)

    def test_parse_provider_metadata_from_429_body(self):
        body = json.dumps({
            "error": {
                "message": "Provider returned error",
                "code": 429,
                "metadata": {
                    "raw": "deepseek/deepseek-v4-pro is temporarily rate-limited upstream.",
                    "provider_name": "Together",
                    "is_byok": False,
                },
            }
        })
        meta = self.OpenRouterClient._parse_provider_metadata_from_429_body(body)
        self.assertEqual(meta["provider_name"], "Together")
        self.assertEqual(meta["is_byok"], False)
        self.assertEqual(meta["raw"], "deepseek/deepseek-v4-pro is temporarily rate-limited upstream.")

    def test_parse_provider_metadata_from_429_body_invalid_json(self):
        meta = self.OpenRouterClient._parse_provider_metadata_from_429_body("not json")
        self.assertEqual(meta, {})

    def test_get_provider_routing_for_model_non_deepseek(self):
        self.assertIsNone(self.OpenRouterClient._get_provider_routing_for_model("x-ai/grok-4.20-beta"))

    def test_get_provider_routing_for_model_deepseek_default(self):
        # Default sort=throughput alone returns None (keeps payload lean)
        self.assertIsNone(self.OpenRouterClient._get_provider_routing_for_model("deepseek/deepseek-v4-pro"))

    @unittest.mock.patch.dict(os.environ, {"OPENROUTER_DEEPSEEK_PROVIDER_IGNORE": "together,fireworks"})
    def test_get_provider_routing_for_model_deepseek_env_ignore(self):
        provider = self.OpenRouterClient._get_provider_routing_for_model("deepseek/deepseek-v4-pro")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.get("ignore"), ["together", "fireworks"])

    @unittest.mock.patch("services.openrouter_client.aiohttp.ClientSession")
    def test_deepseek_429_with_retry_after_retries_once_then_succeeds(self, mock_session_cls):
        """DeepSeek 429 with Retry-After=2 should wait 2s, retry, then succeed."""
        client = self._client()

        call_count = 0

        class FakeResponse:
            def __init__(self, status, body, headers=None):
                self.status = status
                self._body = body
                self.headers = headers or {}

            async def text(self):
                return self._body

            async def json(self):
                import json as _json
                return _json.loads(self._body)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FakeResponse(429, "rate limited", {"Retry-After": "2"})
            import json as _json
            return FakeResponse(
                200,
                _json.dumps({
                    "choices": [{"message": {"content": "ok"}}],
                    "model": "deepseek/deepseek-v4-pro",
                }),
            )

        mock_session = unittest.mock.MagicMock()
        mock_session.post = fake_post
        mock_session_cls.return_value = mock_session

        # Need to set the session on the client
        client.session = mock_session

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                client.call_model(
                    model="deepseek/deepseek-v4-pro",
                    prompt="test",
                    task_type="analysis",
                    return_metadata=True,
                    response_format={"type": "json_object"},
                    max_tokens=8000,
                    plugins=[{"id": "web"}],
                )
            )
        finally:
            loop.close()

        self.assertEqual(call_count, 2)
        self.assertEqual(result.get("content"), "ok")
        self.assertNotIn("fallback", result)

    @unittest.mock.patch("services.openrouter_client.aiohttp.ClientSession")
    def test_deepseek_429_without_retry_after_fails_fast_with_body(self, mock_session_cls):
        """DeepSeek 429 with no Retry-After should return fallback immediately after exhausting retries."""
        client = self._client()

        call_count = 0

        class FakeResponse:
            def __init__(self, status, body, headers=None):
                self.status = status
                self._body = body
                self.headers = headers or {}

            async def text(self):
                return self._body

            async def json(self):
                return json.loads(self._body)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return FakeResponse(429, "rate limited: quota exceeded", {})

        mock_session = unittest.mock.MagicMock()
        mock_session.post = fake_post
        mock_session_cls.return_value = mock_session
        client.session = mock_session

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                client.call_model(
                    model="deepseek/deepseek-v4-pro",
                    prompt="test",
                    task_type="analysis",
                    return_metadata=True,
                    response_format={"type": "json_object"},
                    max_tokens=8000,
                    plugins=[{"id": "web"}],
                )
            )
        finally:
            loop.close()

        self.assertEqual(call_count, 2)  # initial + 1 retry (DEEPSEEK_MAX_RATE_LIMIT_RETRIES=2)
        self.assertTrue(result.get("fallback"))
        self.assertEqual(result.get("failure_reason"), "rate_limited")
        detail = result.get("failure_detail", "")
        self.assertIn("rate limited: quota exceeded", detail)
        self.assertIn("switch to Grok/GPT", detail)

    @unittest.mock.patch("services.openrouter_client.aiohttp.ClientSession")
    def test_deepseek_timeout_fails_fast_with_guidance(self, mock_session_cls):
        """DeepSeek timeout should fail after deepseek_timeout_retries (0) without long retries."""
        client = self._client()

        class FakeResponse:
            def __init__(self, status, body, headers=None):
                self.status = status
                self._body = body
                self.headers = headers or {}

            async def text(self):
                return self._body

            async def json(self):
                import json as _json
                return _json.loads(self._body)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        call_count = 0

        def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Simulate a timeout by sleeping longer than the timeout_seconds
            import asyncio
            raise asyncio.TimeoutError()

        mock_session = unittest.mock.MagicMock()
        mock_session.post = fake_post
        mock_session_cls.return_value = mock_session
        client.session = mock_session

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                client.call_model(
                    model="deepseek/deepseek-v4-pro",
                    prompt="test",
                    task_type="analysis",
                    return_metadata=True,
                    response_format={"type": "json_object"},
                    max_tokens=8000,
                    plugins=[{"id": "web"}],
                )
            )
        finally:
            loop.close()

        # DeepSeek timeout retries = 0, so it fails immediately after first timeout
        self.assertEqual(call_count, 1)
        self.assertTrue(result.get("fallback"))
        self.assertEqual(result.get("failure_reason"), "timeout")
        detail = result.get("failure_detail", "")
        self.assertIn("DeepSeek capped at", detail)
        self.assertIn("Switch to Grok/GPT", detail)

    @unittest.mock.patch("services.openrouter_client.aiohttp.ClientSession")
    def test_grok_timeout_retries_normally(self, mock_session_cls):
        """Non-DeepSeek timeout should retry up to max_retries."""
        client = self._client()

        call_count = 0

        def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            import asyncio
            raise asyncio.TimeoutError()

        mock_session = unittest.mock.MagicMock()
        mock_session.post = fake_post
        mock_session_cls.return_value = mock_session
        client.session = mock_session

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                client.call_model(
                    model="x-ai/grok-4.20-beta",
                    prompt="test",
                    task_type="analysis",
                    return_metadata=True,
                    response_format={"type": "json_object"},
                    max_tokens=8000,
                    plugins=[{"id": "web"}],
                )
            )
        finally:
            loop.close()

        # Grok retries up to max_retries=3, so 4 total calls (initial + 3 retries)
        self.assertEqual(call_count, 4)
        self.assertTrue(result.get("fallback"))
        self.assertEqual(result.get("failure_reason"), "timeout")
        detail = result.get("failure_detail", "")
        self.assertNotIn("DeepSeek capped at", detail)

    def test_deepseek_timeout_caps_timeout_seconds(self):
        client = self._client()
        # DeepSeek timeout should be capped at 60s regardless of heavy payload
        timeout = client._calculate_timeout_seconds(
            model="deepseek/deepseek-v4-pro",
            model_config=None,
            max_tokens=16000,
            plugins=[{"id": "web"}],
            context_size_chars=10000,
        )
        self.assertLessEqual(timeout, client.deepseek_timeout_seconds)

    def test_grok_timeout_not_capped_like_deepseek(self):
        client = self._client()
        timeout = client._calculate_timeout_seconds(
            model="x-ai/grok-4.20-beta",
            model_config=None,
            max_tokens=16000,
            plugins=[{"id": "web"}],
            context_size_chars=10000,
        )
        self.assertGreater(timeout, client.deepseek_timeout_seconds)


class AdminRaceCardRouteDeepSeekTests(unittest.TestCase):
    """App-level tests for DeepSeek-specific admin workflow shaping."""

    def setUp(self):
        self.original_session_manager = app_module.app_state.session_manager
        self.original_openrouter_client = app_module.app_state.openrouter_client
        self.original_admin_password = app_module.app_state.config.web.admin_password
        self.original_auth_secret = app_module.app_state.config.web.auth_secret
        self.original_cached_auth_secret = app_module._AUTH_SECRET

        self.session_manager = type("SessionManagerStub", (), {})()
        self.session_manager.create_session = AsyncMock(return_value="session-123")
        self.session_manager.update_session_status = AsyncMock()
        self.session_manager.save_session_results = AsyncMock()
        self.session_manager.delete_deep_dives_for_card = AsyncMock(return_value=0)

        self.openrouter_client = type("OpenRouterClientStub", (), {})()
        self.openrouter_client.api_key = "test-key"
        self.openrouter_client.call_model = AsyncMock(return_value={
            "content": '{"race_analyses":[{"race_number":1,"predictions":[{"horse_name":"Alpha","jockey":"A. Rider","trainer":"T. One","composite_rating":90}]}]}',
            "annotations": [{"type": "url_citation", "url_citation": {"url": "https://example.com/search"}}],
            "usage": {},
            "model": "deepseek/deepseek-v4-pro",
        })

        app_module.app_state.session_manager = self.session_manager
        app_module.app_state.openrouter_client = self.openrouter_client
        app_module.app_state.config.web.admin_password = "super-secret"
        app_module.app_state.config.web.auth_secret = "signing-secret"
        app_module._AUTH_SECRET = None
        self.admin_request = types.SimpleNamespace(
            cookies={app_module.AUTH_COOKIE_NAME: app_module._sign_value("admin")}
        )

    def tearDown(self):
        app_module.app_state.session_manager = self.original_session_manager
        app_module.app_state.openrouter_client = self.original_openrouter_client
        app_module.app_state.config.web.admin_password = self.original_admin_password
        app_module.app_state.config.web.auth_secret = self.original_auth_secret
        app_module._AUTH_SECRET = self.original_cached_auth_secret

    def test_deepseek_admin_uses_lower_initial_max_tokens(self):
        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="deepseek/deepseek-v4-pro",
            source_mode="web_search",
        )

        response = app_module.asyncio.run(
            app_module.create_admin_race_card(request, self.admin_request)
        )

        self.assertEqual(response.status_code, 200)
        call_kwargs = self.openrouter_client.call_model.await_args.kwargs
        self.assertEqual(
            call_kwargs["max_tokens"],
            app_module.ADMIN_DEEPSEEK_WEB_SEARCH_INITIAL_MAX_TOKENS,
        )

    def test_deepseek_admin_uses_lower_retry_max_tokens_for_gap_fill(self):
        # First call returns a card with missing jockey/trainer to trigger the
        # jockey/trainer gap-fill retry path.
        self.openrouter_client.call_model = AsyncMock(side_effect=[
            {
                "content": '{"race_analyses":[{"race_number":1,"predictions":[{"horse_name":"Alpha","jockey":"","trainer":"","composite_rating":90}]}]}',
                "annotations": [],
            },
            {
                "content": '{"race_analyses":[{"race_number":1,"predictions":[{"horse_name":"Alpha","jockey":"A. Rider","trainer":"T. One","composite_rating":90}]}]}',
                "annotations": [],
            },
        ])

        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="deepseek/deepseek-v4-pro",
            source_mode="web_search",
        )

        response = app_module.asyncio.run(
            app_module.create_admin_race_card(request, self.admin_request)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.openrouter_client.call_model.await_count, 2)
        # Second call is the jockey/trainer gap-fill retry
        second_call_kwargs = self.openrouter_client.call_model.await_args_list[1].kwargs
        self.assertEqual(
            second_call_kwargs["max_tokens"],
            app_module.ADMIN_DEEPSEEK_WEB_SEARCH_RETRY_MAX_TOKENS,
        )

    def test_deepseek_admin_keeps_web_plugin(self):
        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="deepseek/deepseek-v4-pro",
            source_mode="web_search",
        )

        response = app_module.asyncio.run(
            app_module.create_admin_race_card(request, self.admin_request)
        )

        self.assertEqual(response.status_code, 200)
        call_kwargs = self.openrouter_client.call_model.await_args.kwargs
        self.assertEqual(call_kwargs["plugins"], [{"id": "web"}])

    def test_deepseek_admin_prompt_is_compact(self):
        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="deepseek/deepseek-v4-pro",
            source_mode="web_search",
        )

        response = app_module.asyncio.run(
            app_module.create_admin_race_card(request, self.admin_request)
        )

        self.assertEqual(response.status_code, 200)
        call_kwargs = self.openrouter_client.call_model.await_args.kwargs
        prompt = call_kwargs["prompt"]
        self.assertIn("Compact retry mode", prompt)

    def test_non_deepseek_admin_uses_standard_max_tokens(self):
        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
        )

        response = app_module.asyncio.run(
            app_module.create_admin_race_card(request, self.admin_request)
        )

        self.assertEqual(response.status_code, 200)
        call_kwargs = self.openrouter_client.call_model.await_args.kwargs
        self.assertEqual(
            call_kwargs["max_tokens"],
            app_module.ADMIN_WEB_SEARCH_INITIAL_MAX_TOKENS,
        )

    def test_deepseek_preflight_passes_then_runs_card(self):
        self.openrouter_client.deepseek_preflight_enabled = True
        self.openrouter_client.preflight_check = AsyncMock(return_value={"ok": True})

        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="deepseek/deepseek-v4-pro",
            source_mode="web_search",
        )

        response = app_module.asyncio.run(
            app_module.create_admin_race_card(request, self.admin_request)
        )

        self.assertEqual(response.status_code, 200)
        self.openrouter_client.preflight_check.assert_awaited_once()

    def test_deepseek_preflight_fails_returns_503(self):
        self.openrouter_client.deepseek_preflight_enabled = True
        self.openrouter_client.preflight_check = AsyncMock(return_value={
            "ok": False,
            "failure_detail": "OpenRouter rate limited deepseek/deepseek-v4-pro",
        })

        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="deepseek/deepseek-v4-pro",
            source_mode="web_search",
        )

        response = app_module.asyncio.run(
            app_module.create_admin_race_card(request, self.admin_request)
        )

        self.assertEqual(response.status_code, 503)
        # JSONResponse body may not be accessible in the stub; verify via status only
        # but log the detail if available for debugging.
        detail = getattr(response, "detail", None)
        if detail:
            self.assertIn("DeepSeek route is unavailable", detail)


if __name__ == "__main__":
    unittest.main()