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

    responses.JSONResponse = JSONResponse
    responses.HTMLResponse = object
    responses.RedirectResponse = RedirectResponse
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
            return {"template": args[0] if args else None, "context": args[1] if len(args) > 1 else kwargs}

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
    _parse_equibase_expected_horses_by_race,
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

        self.assertIn("Official card URL: https://example.com/official-card", prompt)
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
        original_loader = app_module._load_dashboard_cards

        try:
            app_module._load_dashboard_cards = AsyncMock(side_effect=RuntimeError("dashboard unavailable"))

            fake_request = types.SimpleNamespace(cookies={})
            response = app_module.asyncio.run(app_module.landing_page(fake_request))

            self.assertEqual(response["template"], "landing.html")
            self.assertEqual(response["context"]["dashboard_cards"], [])
            self.assertEqual(response["context"]["card_count"], 0)
            self.assertEqual(response["context"]["completed_count"], 0)
        finally:
            app_module._load_dashboard_cards = original_loader

    def test_admin_race_card_request_uses_configured_default_model(self):
        original_default_model = app_module.app_state.config.ai.default_model

        try:
            app_module.app_state.config.ai.default_model = "openai/gpt-5.4"

            request = app_module.AdminRaceCardRequest(race_date="2026-03-13")

            self.assertEqual(request.llm_model, "openai/gpt-5.4")
        finally:
            app_module.app_state.config.ai.default_model = original_default_model


class AdminRaceCardRouteTests(unittest.TestCase):
    def setUp(self):
        self.original_session_manager = app_module.app_state.session_manager
        self.original_openrouter_client = app_module.app_state.openrouter_client
        self.original_fetch_expected_horses_by_race = app_module.fetch_equibase_expected_horses_by_race
        self.original_fetch_expected_race_numbers = app_module.fetch_equibase_expected_race_numbers

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
        app_module.fetch_equibase_expected_horses_by_race = lambda *args, **kwargs: {}
        app_module.fetch_equibase_expected_race_numbers = lambda *args, **kwargs: []

    def tearDown(self):
        app_module.app_state.session_manager = self.original_session_manager
        app_module.app_state.openrouter_client = self.original_openrouter_client
        app_module.fetch_equibase_expected_horses_by_race = self.original_fetch_expected_horses_by_race
        app_module.fetch_equibase_expected_race_numbers = self.original_fetch_expected_race_numbers

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
        official_card_url = build_equibase_card_overview_url("SA", "2026-03-13")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.openrouter_client.call_model.await_count, 1)
        self.assertEqual(call_kwargs["plugins"], [{"id": "web"}])
        self.assertEqual(call_kwargs["max_tokens"], app_module.ADMIN_WEB_SEARCH_INITIAL_MAX_TOKENS)
        self.assertTrue(call_kwargs["return_metadata"])
        self.assertEqual(
            saved_results["source_urls"],
            ["https://example.com/hint", official_card_url, "https://example.com/search"],
        )
        self.assertEqual(saved_results["admin_metadata"]["workflow"], "admin_openrouter_web_search")

    def test_create_admin_race_card_requires_admin_auth_when_enabled(self):
        original_admin_password = app_module.app_state.config.web.admin_password

        try:
            app_module.app_state.config.web.admin_password = "super-secret"
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

    def test_create_admin_race_card_allows_signed_admin_when_auth_enabled(self):
        original_admin_password = app_module.app_state.config.web.admin_password

        try:
            app_module.app_state.config.web.admin_password = "super-secret"
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

        response = app_module.asyncio.run(app_module.create_admin_race_card(request))
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

        response = app_module.asyncio.run(app_module.create_admin_race_card(request))
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

    def test_create_admin_race_card_rejects_incomplete_card_after_retry(self):
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

        with self.assertRaises(app_module.HTTPException) as exc:
            app_module.asyncio.run(app_module.create_admin_race_card(request))

        self.assertEqual(exc.exception.status_code, 422)
        self.assertIn("Missing races: 3", exc.exception.detail)
        self.assertEqual(self.openrouter_client.call_model.await_count, 2)
        self.session_manager.save_session_results.assert_not_awaited()

    def test_create_admin_race_card_rejects_incomplete_field_after_retry(self):
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

        with self.assertRaises(app_module.HTTPException) as exc:
            app_module.asyncio.run(app_module.create_admin_race_card(request))

        self.assertEqual(exc.exception.status_code, 422)
        self.assertIn("Missing horses: Race 1: Bravo", exc.exception.detail)
        self.assertEqual(self.openrouter_client.call_model.await_count, 2)
        self.session_manager.save_session_results.assert_not_awaited()

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
            app_module.asyncio.run(app_module.create_admin_race_card(request))

        self.assertEqual(exc.exception.status_code, 503)
        self.assertIn("timed out", exc.exception.detail)
        self.assertIn("4 attempts", exc.exception.detail)
        self.session_manager.save_session_results.assert_not_awaited()
        self.assertTrue(any(
            args.args[4] == exc.exception.detail
            for args in self.session_manager.update_session_status.await_args_list
        ))

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