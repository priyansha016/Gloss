import asyncio
import types

import pytest
from fastapi import HTTPException

from app.services import ratelimit


class FakeRequest:
    def __init__(self, headers: dict | None = None, host: str = "1.2.3.4"):
        self.headers = headers or {}
        self.client = types.SimpleNamespace(host=host)


class FakeRedis:
    """Minimal in-memory stand-in for the fixed-window counter."""

    def __init__(self):
        self.store: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, ttl: int) -> bool:
        return True

    async def ttl(self, key: str) -> int:
        return 3600


class TestClientIp:
    def test_prefers_cf_connecting_ip(self):
        req = FakeRequest({"cf-connecting-ip": "9.9.9.9", "x-forwarded-for": "8.8.8.8"})
        assert ratelimit._client_ip(req) == "9.9.9.9"

    def test_falls_back_to_first_forwarded_hop(self):
        req = FakeRequest({"x-forwarded-for": "8.8.8.8, 10.0.0.1"})
        assert ratelimit._client_ip(req) == "8.8.8.8"

    def test_falls_back_to_socket_peer(self):
        assert ratelimit._client_ip(FakeRequest(host="7.7.7.7")) == "7.7.7.7"


class TestEnforce:
    def test_allows_under_limit_then_blocks_over(self, monkeypatch):
        fake = FakeRedis()
        monkeypatch.setattr(ratelimit, "get_redis", lambda: fake)
        req = FakeRequest(host="5.5.5.5")

        # limit=3: first three pass, fourth is rejected with 429 + Retry-After.
        for _ in range(3):
            asyncio.run(ratelimit.enforce(req, "submit", 3, 3600))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ratelimit.enforce(req, "submit", 3, 3600))
        assert exc.value.status_code == 429
        assert "Retry-After" in exc.value.headers

    def test_separate_ips_have_separate_budgets(self, monkeypatch):
        fake = FakeRedis()
        monkeypatch.setattr(ratelimit, "get_redis", lambda: fake)
        a, b = FakeRequest(host="1.1.1.1"), FakeRequest(host="2.2.2.2")
        asyncio.run(ratelimit.enforce(a, "submit", 1, 3600))
        # b still has its own budget — must not raise.
        asyncio.run(ratelimit.enforce(b, "submit", 1, 3600))

    def test_fail_open_when_redis_unavailable(self, monkeypatch):
        monkeypatch.setattr(ratelimit, "get_redis", lambda: None)
        # No redis → never blocks, regardless of how many calls.
        for _ in range(10):
            asyncio.run(ratelimit.enforce(FakeRequest(), "submit", 1, 3600))

    def test_disabled_flag_skips_enforcement(self, monkeypatch):
        settings = ratelimit.get_settings()
        monkeypatch.setattr(settings, "rate_limit_enabled", False)
        # Even with a redis that would block, disabled = pass-through.
        monkeypatch.setattr(ratelimit, "get_redis", lambda: FakeRedis())
        for _ in range(5):
            asyncio.run(ratelimit.enforce(FakeRequest(), "submit", 1, 3600))
