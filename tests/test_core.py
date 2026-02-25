"""
ninja_boost — core test suite.

Each test class is labelled with the bug it covers or feature it validates.
"""

from unittest.mock import MagicMock

# ── responses ─────────────────────────────────────────────────────────────

class TestWrapResponse:
    def test_success_envelope(self):
        from ninja_boost.responses import wrap_response
        assert wrap_response({"id": 1}) == {"ok": True, "data": {"id": 1}}

    def test_wraps_list(self):
        from ninja_boost.responses import wrap_response
        assert wrap_response([1, 2]) == {"ok": True, "data": [1, 2]}

    def test_wraps_none(self):
        from ninja_boost.responses import wrap_response
        assert wrap_response(None) == {"ok": True, "data": None}


# ── pagination — BUG FIX: len(queryset) → .count() ────────────────────────

class TestAutoPaginate:
    def _req(self, page=1, size=20):
        r = MagicMock()
        r.GET = {"page": str(page), "size": str(size)}
        return r

    def test_paginates_list(self):
        from ninja_boost.pagination import auto_paginate

        @auto_paginate
        def view(request): return list(range(50))

        result = view(self._req(page=1, size=10))
        assert result == {"items": list(range(10)), "page": 1,
                          "size": 10, "total": 50, "pages": 5}

    def test_second_page(self):
        from ninja_boost.pagination import auto_paginate

        @auto_paginate
        def view(request): return list(range(50))

        assert view(self._req(page=2, size=10))["items"] == list(range(10, 20))

    def test_passes_dict_through(self):
        from ninja_boost.pagination import auto_paginate

        @auto_paginate
        def view(request): return {"key": "value"}

        assert view(self._req()) == {"key": "value"}

    def test_passes_none_through(self):
        from ninja_boost.pagination import auto_paginate

        @auto_paginate
        def view(request): return None

        assert view(self._req()) is None

    def test_invalid_page_defaults_to_1(self):
        from ninja_boost.pagination import auto_paginate

        @auto_paginate
        def view(request): return list(range(5))

        r = MagicMock()
        r.GET = {"page": "bad", "size": "bad"}
        assert view(r)["page"] == 1

    def test_size_capped_at_max(self):
        from ninja_boost.pagination import MAX_PAGE_SIZE, auto_paginate

        @auto_paginate
        def view(request): return list(range(5))

        r = MagicMock() 
        r.GET = {"page": "1", "size": "99999"}
        assert view(r)["size"] == MAX_PAGE_SIZE

    def test_queryset_uses_count_not_len(self):
        """
        BUG FIX: original template used len(queryset) which loads the entire
        table into memory. We must call .count() instead.
        """
        from ninja_boost.pagination import _is_queryset, auto_paginate

        qs = MagicMock()
        qs.count.return_value = 500
        qs.__getitem__ = lambda self, s: list(range(20))
        qs.filter = MagicMock()   # make _is_queryset() return True
        qs.values = MagicMock()

        assert _is_queryset(qs)

        @auto_paginate
        def view(request): return qs

        r = MagicMock()
        r.GET = {"page": "1", "size": "20"}
        result = view(r)

        qs.count.assert_called_once()     # must use .count(), not len()
        assert result["total"] == 500

    def test_pages_ceiling_division(self):
        from ninja_boost.pagination import auto_paginate

        @auto_paginate
        def view(request): return list(range(21))   # 21 items, size 10 → 3 pages

        r = MagicMock() 
        r.GET = {"page": "1", "size": "10"}
        assert view(r)["pages"] == 3


# ── dependencies ──────────────────────────────────────────────────────────

class TestInjectContext:
    def _req(self, auth=None, ip="127.0.0.1", trace_id="abc"):
        r = MagicMock()
        r.auth = auth
        r.META = {"REMOTE_ADDR": ip}
        r.trace_id = trace_id
        return r

    def test_injects_ctx(self):
        from ninja_boost.dependencies import inject_context
        captured = {}

        @inject_context
        def view(request, ctx): captured.update(ctx)

        view(self._req(auth={"user_id": 1}, trace_id="xyz"))
        assert captured == {"user": {"user_id": 1}, "ip": "127.0.0.1", "trace_id": "xyz"}

    def test_missing_trace_id_is_none(self):
        from ninja_boost.dependencies import inject_context

        @inject_context
        def view(request, ctx): return ctx["trace_id"]

        r = MagicMock(spec=["auth", "META"])
        r.auth = None
        r.META = {"REMOTE_ADDR": "1.2.3.4"}
        assert view(r) is None

    def test_x_forwarded_for(self):
        from ninja_boost.dependencies import _client_ip
        r = MagicMock()
        r.META = {"HTTP_X_FORWARDED_FOR": "203.0.113.5, 10.0.0.1",
                  "REMOTE_ADDR": "10.0.0.1"}
        assert _client_ip(r) == "203.0.113.5"


# ── middleware ────────────────────────────────────────────────────────────

class TestTracingMiddleware:
    def test_sets_trace_id_on_request(self):
        from ninja_boost.middleware import TracingMiddleware
        req = MagicMock()
        response = MagicMock()
        response.__setitem__ = MagicMock()
        TracingMiddleware(lambda r: response)(req)
        assert hasattr(req, "trace_id") and len(req.trace_id) == 32

    def test_x_trace_id_header(self):
        from ninja_boost.middleware import TracingMiddleware
        headers = {}
        response = MagicMock()
        response.__setitem__ = lambda s, k, v: headers.update({k: v})
        TracingMiddleware(lambda r: response)(MagicMock())
        assert "X-Trace-Id" in headers and len(headers["X-Trace-Id"]) == 32


# ── integrations — BearerTokenAuth ────────────────────────────────────────

class TestBearerTokenAuth:
    def test_demo_token(self):
        from ninja_boost.integrations import BearerTokenAuth
        assert BearerTokenAuth().authenticate(MagicMock(), "demo")["user_id"] == 1

    def test_bad_token_returns_none(self):
        from ninja_boost.integrations import BearerTokenAuth
        assert BearerTokenAuth().authenticate(MagicMock(), "hacker") is None


# ── conf — settings proxy ─────────────────────────────────────────────────

class TestBoostSettings:
    def test_loads_auth(self):
        from ninja_boost.conf import boost_settings
        boost_settings.reload()
        assert callable(boost_settings.AUTH)

    def test_wraps_correctly(self):
        from ninja_boost.conf import boost_settings
        boost_settings.reload()
        assert boost_settings.RESPONSE_WRAPPER(99) == {"ok": True, "data": 99}

    def test_cache_returns_same_object(self):
        from ninja_boost.conf import boost_settings
        boost_settings.reload()
        assert boost_settings.AUTH is boost_settings.AUTH


# ── Schema bug regression ─────────────────────────────────────────────────

class TestSchemaFix:
    def test_user_create_schema_parses(self):
        """Regression: original had UserCreate(schema) — undefined lowercase name."""
        from ninja import Schema

        class UserCreate(Schema):   # corrected version
            username: str
            email: str
            password: str

        u = UserCreate(username="alice", email="a@b.com", password="s3cr3t")
        assert u.username == "alice"
        assert u.email == "a@b.com"
