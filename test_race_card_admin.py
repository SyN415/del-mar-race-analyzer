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
                ],
            )
            return types.SimpleNamespace(openrouter_api_key="test-key", web=web, ai=ai)

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
    _poll_until_challenge_clears,
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
        self.original_fetch_equibase_all_data = app_module.fetch_equibase_all_data
        self.original_fetch_expected_horses_by_race = app_module.fetch_equibase_expected_horses_by_race
        self.original_fetch_expected_race_numbers = app_module.fetch_equibase_expected_race_numbers
        self.original_fetch_equibase_all_data_async = app_module.fetch_equibase_all_data_async
        self.original_admin_password = app_module.app_state.config.web.admin_password
        self.original_auth_secret = app_module.app_state.config.web.auth_secret
        self.original_cached_auth_secret = app_module._AUTH_SECRET

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
        app_module.app_state.config.web.admin_password = "super-secret"
        app_module.app_state.config.web.auth_secret = "signing-secret"
        app_module._AUTH_SECRET = None
        self.admin_request = types.SimpleNamespace(
            cookies={app_module.AUTH_COOKIE_NAME: app_module._sign_value("admin")}
        )
        app_module.fetch_equibase_all_data = lambda track_id, race_date, country="USA": (
            app_module.fetch_equibase_expected_horses_by_race(track_id, race_date, country=country),
            {},
        )
        app_module.fetch_equibase_expected_horses_by_race = lambda *args, **kwargs: {}
        app_module.fetch_equibase_expected_race_numbers = lambda *args, **kwargs: []

        # Default Equibase fetch stub: returns non-empty entry_details so the
        # production guardrail (which refuses to publish an ungrounded card in
        # web_search mode) does not fire.  Individual tests that exercise the
        # guardrail should override this stub.
        async def _default_equibase_all_data_async(*args, **kwargs):
            entry_details = {
                1: [
                    {
                        "name": "Alpha",
                        "post_position": 1,
                        "program_number": 1,
                        "jockey": "A. Rider",
                        "trainer": "T. One",
                        "morning_line": "5/2",
                        "scratched": False,
                    }
                ]
            }
            return {}, entry_details

        app_module.fetch_equibase_all_data_async = _default_equibase_all_data_async

    def tearDown(self):
        app_module.app_state.session_manager = self.original_session_manager
        app_module.app_state.openrouter_client = self.original_openrouter_client
        app_module.fetch_equibase_all_data = self.original_fetch_equibase_all_data
        app_module.app_state.config.web.admin_password = self.original_admin_password
        app_module.app_state.config.web.auth_secret = self.original_auth_secret
        app_module._AUTH_SECRET = self.original_cached_auth_secret
        app_module.fetch_equibase_expected_horses_by_race = self.original_fetch_expected_horses_by_race
        app_module.fetch_equibase_expected_race_numbers = self.original_fetch_expected_race_numbers
        app_module.fetch_equibase_all_data_async = self.original_fetch_equibase_all_data_async

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

    def test_create_admin_race_card_retries_missing_races_and_saves_merged_card(self):
        app_module.fetch_equibase_expected_race_numbers = lambda *args, **kwargs: [1, 2]
        self.openrouter_client.call_model = AsyncMock(side_effect=[
            {
                "content": '{"race_analyses":[{"race_number":1,"predictions":[{"horse_name":"Alpha","jockey":"A. Rider","trainer":"T. One","composite_rating":90}]}]}',
                "annotations": [{"type": "url_citation", "url": "https://example.com/initial"}],
            },
            {
                "content": '{"race_analyses":[{"race_number":2,"predictions":[{"horse_name":"Bravo","jockey":"B. Rider","trainer":"T. Two","composite_rating":88}]}]}',
                "annotations": [{"type": "url_citation", "url": "https://example.com/retry"}],
            },
        ])

        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
        )

        response = app_module.asyncio.run(app_module.create_admin_race_card(request, self.admin_request))
        saved_results = self.session_manager.save_session_results.await_args.args[1]
        first_call_kwargs = self.openrouter_client.call_model.await_args_list[0].kwargs
        second_call_kwargs = self.openrouter_client.call_model.await_args_list[1].kwargs

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.openrouter_client.call_model.await_count, 2)
        self.assertEqual([race["race_number"] for race in saved_results["race_analyses"]], [1, 2])
        self.assertEqual(
            saved_results["source_urls"],
            [
                build_equibase_card_overview_url("SA", "2026-03-13"),
                "https://example.com/initial",
                "https://example.com/retry",
            ],
        )
        self.assertEqual(first_call_kwargs["max_tokens"], app_module.ADMIN_WEB_SEARCH_INITIAL_MAX_TOKENS)
        self.assertEqual(second_call_kwargs["max_tokens"], app_module.ADMIN_WEB_SEARCH_RETRY_MAX_TOKENS)
        self.assertIn("exactly these races: 1, 2", first_call_kwargs["prompt"])
        self.assertIn("ONLY for these missing races: 2", second_call_kwargs["prompt"])
        self.assertEqual(second_call_kwargs["context"]["missing_race_numbers"], [2])
        self.assertTrue(any(args.args[3] == "admin_retry_incomplete_card" for args in self.session_manager.update_session_status.await_args_list))

    def test_create_admin_race_card_retries_missing_horses_and_saves_merged_field(self):
        app_module.fetch_equibase_expected_race_numbers = lambda *args, **kwargs: [1]
        app_module.fetch_equibase_expected_horses_by_race = lambda *args, **kwargs: {
            1: ["Alpha", "Bravo", "Charlie"]
        }
        self.openrouter_client.call_model = AsyncMock(side_effect=[
            {
                "content": '{"race_analyses":[{"race_number":1,"predictions":[{"horse_name":"Alpha","jockey":"A. Rider","trainer":"T. One","composite_rating":90}]}]}',
                "annotations": [{"type": "url_citation", "url": "https://example.com/initial"}],
            },
            {
                "content": '{"race_analyses":[{"race_number":1,"predictions":[{"horse_name":"Bravo","jockey":"B. Rider","trainer":"T. Two","composite_rating":84},{"horse_name":"Charlie","jockey":"C. Rider","trainer":"T. Three","composite_rating":82}]}]}',
                "annotations": [{"type": "url_citation", "url": "https://example.com/retry"}],
            },
        ])

        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
        )

        response = app_module.asyncio.run(app_module.create_admin_race_card(request, self.admin_request))
        saved_results = self.session_manager.save_session_results.await_args.args[1]
        second_call_kwargs = self.openrouter_client.call_model.await_args_list[1].kwargs

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.openrouter_client.call_model.await_count, 2)
        self.assertEqual(
            {prediction["horse_name"] for prediction in saved_results["race_analyses"][0]["predictions"]},
            {"Alpha", "Bravo", "Charlie"},
        )
        self.assertTrue(saved_results["race_analyses"][0]["field_complete"])
        self.assertEqual(second_call_kwargs["max_tokens"], app_module.ADMIN_WEB_SEARCH_RETRY_MAX_TOKENS)
        self.assertEqual(second_call_kwargs["context"]["missing_horses_by_race"], {1: ["Bravo", "Charlie"]})
        self.assertIn("Missing horses on retry: Race 1: Bravo, Charlie.", second_call_kwargs["prompt"])

    def test_create_admin_race_card_accepts_partial_card_after_retry(self):
        app_module.fetch_equibase_expected_race_numbers = lambda *args, **kwargs: [1, 2, 3]
        self.openrouter_client.call_model = AsyncMock(side_effect=[
            {
                "content": '{"race_analyses":[{"race_number":1,"predictions":[{"horse_name":"Alpha","jockey":"A. Rider","trainer":"T. One","composite_rating":90}]}]}',
                "annotations": [],
            },
            {
                "content": '{"race_analyses":[{"race_number":2,"predictions":[{"horse_name":"Bravo","jockey":"B. Rider","trainer":"T. Two","composite_rating":88}]}]}',
                "annotations": [],
            },
        ])

        request = app_module.AdminRaceCardRequest(
            race_date="2026-03-13",
            track_id="SA",
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
        )

        # Partial cards are now accepted with a warning instead of raising HTTPException
        result = app_module.asyncio.run(app_module.create_admin_race_card(request, self.admin_request))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.openrouter_client.call_model.await_count, 2)
        self.session_manager.save_session_results.assert_awaited_once()

    def test_create_admin_race_card_accepts_partial_field_after_retry(self):
        app_module.fetch_equibase_expected_race_numbers = lambda *args, **kwargs: [1]
        app_module.fetch_equibase_expected_horses_by_race = lambda *args, **kwargs: {
            1: ["Alpha", "Bravo"]
        }
        self.openrouter_client.call_model = AsyncMock(side_effect=[
            {
                "content": '{"race_analyses":[{"race_number":1,"predictions":[{"horse_name":"Alpha","jockey":"A. Rider","trainer":"T. One","composite_rating":90}]}]}',
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
            llm_model="x-ai/grok-4.20-beta",
            source_mode="web_search",
        )

        # Partial fields are now accepted with a warning instead of raising HTTPException
        result = app_module.asyncio.run(app_module.create_admin_race_card(request, self.admin_request))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.openrouter_client.call_model.await_count, 2)
        self.session_manager.save_session_results.assert_awaited_once()

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

    def test_create_admin_race_card_proceeds_when_equibase_entry_details_unavailable(self):
        # Override the default stub so entry_details is empty — simulates the
        # urllib+Playwright double failure (e.g. Imperva WAF block on Render's
        # datacenter IPs).  The endpoint must no longer 503 in this state; it
        # must degrade to ungrounded web_search and publish whatever the LLM
        # returns (flagging grounded=False in the session metadata).
        async def _no_equibase_data(*args, **kwargs):
            return {}, {}

        app_module.fetch_equibase_all_data_async = _no_equibase_data

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
        # The LLM must have been dispatched despite the missing Equibase data.
        self.openrouter_client.call_model.assert_awaited()
        self.session_manager.save_session_results.assert_awaited()
        # No equibase_unavailable failure status should have been emitted.
        self.assertFalse(any(
            args.args[3] == "equibase_unavailable"
            for args in self.session_manager.update_session_status.await_args_list
        ))
        # The prompt must have contained the ungrounded multi-source guidance
        # so the LLM knows to cross-reference alternative sources.
        call_kwargs = self.openrouter_client.call_model.await_args.kwargs
        prompt = call_kwargs["prompt"]
        self.assertIn("horseracingnation.com", prompt)
        self.assertIn("Cross-reference at least TWO", prompt)

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


class ImpervaChallengePollingTests(unittest.TestCase):
    """Unit tests for the Imperva challenge polling loop."""

    _CHALLENGE_HTML = (
        "<!DOCTYPE html><html><head>"
        "<noscript><title>Pardon Our Interruption</title></noscript>"
        "<script>window.reeseSkipExpirationCheck = true;</script>"
        "</head></html>"
    )
    _REAL_HTML = "<html><body>" + ("<p>horse entry " + "x" * 80 + "</p>") * 40 + "</body></html>"

    def _run(self, coro):
        return app_module.asyncio.run(coro)

    def test_returns_first_non_challenge_html(self):
        htmls = [self._CHALLENGE_HTML, self._CHALLENGE_HTML, self._REAL_HTML]
        sleeps = []
        nudges = []

        async def fetch_html():
            return htmls.pop(0)

        async def nudge(attempt):
            nudges.append(attempt)

        async def fake_sleep(ms):
            sleeps.append(ms)

        result = self._run(_poll_until_challenge_clears(
            fetch_html=fetch_html,
            nudge=nudge,
            max_attempts=5,
            interval_ms=2000,
            sleep=fake_sleep,
        ))

        self.assertFalse(_is_imperva_challenge(result))
        self.assertIn("horse entry", result)
        # Two challenges seen → nudge called twice, sleep called twice.
        self.assertEqual(nudges, [1, 2])
        self.assertEqual(sleeps, [2000, 2000])

    def test_returns_last_html_when_attempts_exhausted(self):
        call_count = {"n": 0}
        sleeps = []

        async def fetch_html():
            call_count["n"] += 1
            return self._CHALLENGE_HTML

        async def fake_sleep(ms):
            sleeps.append(ms)

        result = self._run(_poll_until_challenge_clears(
            fetch_html=fetch_html,
            nudge=None,
            max_attempts=3,
            interval_ms=500,
            sleep=fake_sleep,
        ))

        self.assertTrue(_is_imperva_challenge(result))
        self.assertEqual(call_count["n"], 3)
        # Sleeps only happen between attempts, so one fewer than max_attempts.
        self.assertEqual(sleeps, [500, 500])

    def test_nudge_exception_does_not_abort_polling(self):
        htmls = [self._CHALLENGE_HTML, self._REAL_HTML]

        async def fetch_html():
            return htmls.pop(0)

        async def failing_nudge(attempt):
            raise RuntimeError("boom")

        async def fake_sleep(ms):
            pass

        result = self._run(_poll_until_challenge_clears(
            fetch_html=fetch_html,
            nudge=failing_nudge,
            max_attempts=5,
            interval_ms=1,
            sleep=fake_sleep,
        ))

        self.assertFalse(_is_imperva_challenge(result))

    def test_succeeds_on_first_attempt_without_sleeping(self):
        sleeps = []

        async def fetch_html():
            return self._REAL_HTML

        async def fake_sleep(ms):
            sleeps.append(ms)

        result = self._run(_poll_until_challenge_clears(
            fetch_html=fetch_html,
            nudge=None,
            max_attempts=10,
            interval_ms=2000,
            sleep=fake_sleep,
        ))

        self.assertFalse(_is_imperva_challenge(result))
        self.assertEqual(sleeps, [])


if __name__ == "__main__":
    unittest.main()