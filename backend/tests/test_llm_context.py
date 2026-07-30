import asyncio

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import deps
from app.config import Settings
from app.services import llm
from app.services.llm_context import (
    PROVIDER_PRESETS,
    LlmCreds,
    build_creds,
    get_llm_creds,
    llm_available,
    set_llm_creds,
)


@pytest.fixture(autouse=True)
def clear_creds():
    set_llm_creds(None)
    yield
    set_llm_creds(None)


def settings_stub(**overrides) -> Settings:
    base = {
        "openai_api_key": "",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-4o-mini",
        "require_user_key": False,
    }
    return Settings(**{**base, **overrides})


class TestBuildCreds:
    def test_no_key_is_none(self):
        assert build_creds("", provider="groq") is None
        assert build_creds(None, provider="groq") is None
        assert build_creds("   ", provider="groq") is None

    def test_provider_preset_fills_url_and_model(self):
        creds = build_creds("sk-test", provider="groq")
        assert creds is not None
        assert creds.api_key == "sk-test"
        assert "groq.com" in creds.base_url
        assert creds.model

    def test_explicit_values_override_preset(self):
        creds = build_creds(
            "sk-test", provider="groq", base_url="https://x.dev/v1", model="my-model"
        )
        assert creds == LlmCreds("sk-test", "https://x.dev/v1", "my-model")

    def test_unknown_provider_without_overrides_is_none(self):
        assert build_creds("sk-test", provider="whoknows") is None

    def test_unknown_provider_with_overrides_works(self):
        creds = build_creds("sk-test", base_url="https://x.dev/v1", model="my-model")
        assert creds is not None
        assert creds.model == "my-model"


class TestSerialization:
    def test_round_trip(self):
        creds = LlmCreds("sk-test", "https://x.dev/v1", "m")
        assert LlmCreds.from_dict(creds.as_dict()) == creds

    def test_from_dict_rejects_partial_payloads(self):
        assert LlmCreds.from_dict(None) is None
        assert LlmCreds.from_dict({}) is None
        assert LlmCreds.from_dict({"api_key": "sk", "base_url": "", "model": "m"}) is None


class TestLlmAvailable:
    def test_false_when_nothing_configured(self, monkeypatch):
        monkeypatch.setattr("app.services.llm_context.get_settings", settings_stub)
        assert llm_available() is False

    def test_true_with_user_creds_only(self, monkeypatch):
        monkeypatch.setattr("app.services.llm_context.get_settings", settings_stub)
        set_llm_creds(LlmCreds("sk-test", "https://x.dev/v1", "m"))
        assert llm_available() is True

    def test_true_with_server_key_only(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.llm_context.get_settings",
            lambda: settings_stub(openai_api_key="server-key"),
        )
        assert llm_available() is True


class TestClientSelection:
    def test_user_creds_win_over_server_config(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.llm.get_settings",
            lambda: settings_stub(openai_api_key="server-key"),
        )
        set_llm_creds(LlmCreds("user-key", "https://user.dev/v1", "user-model"))
        client = llm.get_llm_client()
        assert client.api_key == "user-key"
        assert str(client.base_url).startswith("https://user.dev/v1")
        assert llm.active_model() == "user-model"

    def test_falls_back_to_server_config_without_creds(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.llm.get_settings",
            lambda: settings_stub(openai_api_key="server-key"),
        )
        client = llm.get_llm_client()
        assert client.api_key == "server-key"
        assert llm.active_model() == "gpt-4o-mini"

    def test_no_provider_failover_on_a_user_key(self, monkeypatch):
        """The fallback provider is the server's account — never spend it for BYOK."""
        monkeypatch.setattr(
            "app.services.llm.get_settings",
            lambda: settings_stub(
                fallback_openai_api_key="server-fallback",
                fallback_openai_base_url="https://fb.dev/v1",
                fallback_openai_model="fb-model",
            ),
        )
        assert llm.get_fallback_client() is not None
        set_llm_creds(LlmCreds("user-key", "https://user.dev/v1", "user-model"))
        assert llm.get_fallback_client() is None


class TestRequestDependency:
    """The dependency must be visible to the handler AND to tasks it spawns.

    Exercised through a real app rather than by calling the dependency directly:
    contextvar visibility depends on FastAPI awaiting async dependencies in the
    handler's own task, which is the assumption the whole design rests on.
    """

    @staticmethod
    def _app():
        app = FastAPI()

        @app.get("/probe", dependencies=[Depends(deps.llm_creds)])
        async def probe():
            async def in_child_task():
                creds = get_llm_creds()
                return creds.model if creds else None

            direct = get_llm_creds()
            (from_child,) = await asyncio.gather(in_child_task())
            return {
                "key": direct.api_key if direct else None,
                "base_url": direct.base_url if direct else None,
                "child_model": from_child,
            }

        return app

    def test_headers_reach_the_handler_and_child_tasks(self):
        client = TestClient(self._app())
        body = client.get(
            "/probe", headers={"X-LLM-Key": "sk-test", "X-LLM-Provider": "gemini"}
        ).json()
        assert body["key"] == "sk-test"
        assert "googleapis" in body["base_url"]
        # Parallel pipeline stages (verifier repairs, visuals) must inherit the key.
        assert body["child_model"] == PROVIDER_PRESETS["gemini"]["model"]

    def test_missing_headers_leave_the_context_empty(self):
        body = TestClient(self._app()).get("/probe").json()
        assert body["key"] is None

    def test_one_requests_key_does_not_leak_into_the_next(self):
        client = TestClient(self._app())
        assert client.get("/probe", headers={"X-LLM-Key": "sk-a", "X-LLM-Provider": "groq"}).json()["key"] == "sk-a"
        assert client.get("/probe").json()["key"] is None

    def test_require_raises_428_when_byok_enforced(self, monkeypatch):
        monkeypatch.setattr(
            "app.api.deps.get_settings",
            lambda: settings_stub(openai_api_key="server-key", require_user_key=True),
        )
        with pytest.raises(HTTPException) as exc:
            deps.require_llm_creds()
        assert exc.value.status_code == 428
        assert exc.value.detail == "user_key_required"

    def test_require_passes_with_a_user_key(self, monkeypatch):
        monkeypatch.setattr(
            "app.api.deps.get_settings",
            lambda: settings_stub(require_user_key=True),
        )
        set_llm_creds(LlmCreds("sk-test", "https://x.dev/v1", "m"))
        deps.require_llm_creds()

    def test_require_raises_503_when_server_has_no_key(self, monkeypatch):
        monkeypatch.setattr("app.api.deps.get_settings", settings_stub)
        with pytest.raises(HTTPException) as exc:
            deps.require_llm_creds()
        assert exc.value.status_code == 503

    def test_require_passes_on_server_key_when_byok_is_off(self, monkeypatch):
        monkeypatch.setattr(
            "app.api.deps.get_settings",
            lambda: settings_stub(openai_api_key="server-key"),
        )
        deps.require_llm_creds()
