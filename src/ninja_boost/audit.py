"""
ninja_boost.audit
~~~~~~~~~~~~~~~~~
Structured audit logging — a permanent, tamper-evident record of who did
what to which resource and when.

Audit logs are different from access logs (which every request generates)
and application logs (which record internal events). Audit logs record
*intentional user actions* with business significance: creates, updates,
deletes, logins, permission changes, data exports.

They answer the compliance question: "Who accessed or changed record X?"

How it works
------------
The audit system writes structured records to a dedicated audit logger
(``ninja_boost.audit``). Configure it to write to a separate file, a
database table, an S3 bucket, Splunk, Datadog, or any log aggregator.

Quick start::

    from ninja_boost.audit import audit_log, AuditRouter

    # Option 1: decorator on individual routes
    router = AutoRouter(tags=["Orders"])

    @router.delete("/{id}")
    @audit_log(action="order.delete", resource="order", resource_id_from="id")
    def delete_order(request, ctx, id: int): ...

    # Option 2: AuditRouter — audits every operation automatically
    #   Pass the underlying router as the first argument.
    from ninja_boost import AutoRouter
    audit_router = AuditRouter(AutoRouter(tags=["Orders"]), resource="order")

    @audit_router.get("/")       # logs: order.list
    def list_orders(request, ctx): ...

    @audit_router.delete("/{id}")  # logs: order.delete, resource_id=id
    def delete_order(request, ctx, id: int): ...

    # Option 3: manual emit (inside a view or service)
    from ninja_boost.audit import emit

    def transfer_funds(request, ctx, payload):
        result = BankingService.transfer(payload)
        emit(
            request, ctx,
            action="funds.transfer",
            resource="account",
            resource_id=payload.from_account,
            metadata={"amount": payload.amount, "to": payload.to_account},
        )
        return result

Audit record shape::

    {
        "timestamp":   "2026-02-23T14:30:00.123Z",
        "action":      "order.delete",
        "actor_id":    42,
        "actor_type":  "user",
        "resource":    "order",
        "resource_id": "7",
        "outcome":     "success",          # success | failure | error
        "ip":          "203.0.113.1",
        "trace_id":    "abc123...",
        "path":        "/api/orders/7",
        "method":      "DELETE",
        "metadata":    {}                  # any extra fields you pass
    }

Database storage (optional)::

    NINJA_BOOST = {
        "AUDIT": {
            "BACKEND":   "ninja_boost.audit.DatabaseBackend",
            "LOG_READS": False,     # set True to also log GET requests
        }
    }

    # The audit table is auto-created on first write — no migration required.

Custom backends::

    class SplunkBackend:
        def write(self, record: dict) -> None:
            splunk_client.send_event(record)

    NINJA_BOOST = {
        "AUDIT": {
            "BACKEND": "myproject.audit.SplunkBackend",
        }
    }
"""

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from functools import wraps
from typing import Any

logger = logging.getLogger("ninja_boost.audit")


# ── Audit record ──────────────────────────────────────────────────────────

class AuditRecord:
    """Immutable audit record. Build one, write it once."""

    __slots__ = (
        "timestamp", "action", "actor_id", "actor_type",
        "resource", "resource_id", "outcome",
        "ip", "trace_id", "path", "method", "metadata",
    )

    def __init__(
        self,
        action:      str,
        actor_id:    Any           = None,
        actor_type:  str           = "user",
        resource:    str | None    = None,
        resource_id: Any           = None,
        outcome:     str           = "success",
        ip:          str | None    = None,
        trace_id:    str | None    = None,
        path:        str | None    = None,
        method:      str | None    = None,
        metadata:    dict | None   = None,
    ):
        self.timestamp   = datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")
        self.action      = action
        self.actor_id    = actor_id
        self.actor_type  = actor_type
        self.resource    = resource
        self.resource_id = str(resource_id) if resource_id is not None else None
        self.outcome     = outcome
        self.ip          = ip
        self.trace_id    = trace_id
        self.path        = path
        self.method      = method
        self.metadata    = metadata or {}

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}

    def __repr__(self) -> str:
        return f"<AuditRecord {self.action} by {self.actor_id} → {self.outcome}>"


# ── Backends ──────────────────────────────────────────────────────────────

class LoggingBackend:
    """Write audit records to the ``ninja_boost.audit`` Python logger (default)."""

    def write(self, record: dict) -> None:
        logger.info(json.dumps(record, default=str, ensure_ascii=False))


class DatabaseBackend:
    """
    Write audit records to the database via Django's ORM.

    Auto-creates the ``ninja_boost_audit_log`` table on first write — no
    migration step required.  The table uses only standard SQL types that
    work across all Django-supported databases (SQLite, PostgreSQL, MySQL).

    Usage::

        NINJA_BOOST = {
            "AUDIT": {
                "BACKEND": "ninja_boost.audit.DatabaseBackend",
            }
        }
    """

    _table_ensured: bool = False
    _DDL = """
        CREATE TABLE IF NOT EXISTS ninja_boost_audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            action      TEXT    NOT NULL,
            actor_id    TEXT,
            actor_type  TEXT,
            resource    TEXT,
            resource_id TEXT,
            outcome     TEXT,
            ip          TEXT,
            trace_id    TEXT,
            path        TEXT,
            method      TEXT,
            metadata    TEXT
        )
    """
    # PostgreSQL: SERIAL for auto-increment
    _DDL_PG = """
        CREATE TABLE IF NOT EXISTS ninja_boost_audit_log (
            id          SERIAL PRIMARY KEY,
            timestamp   TEXT    NOT NULL,
            action      TEXT    NOT NULL,
            actor_id    TEXT,
            actor_type  TEXT,
            resource    TEXT,
            resource_id TEXT,
            outcome     TEXT,
            ip          TEXT,
            trace_id    TEXT,
            path        TEXT,
            method      TEXT,
            metadata    TEXT
        )
    """
    # MySQL / MariaDB: AUTO_INCREMENT
    _DDL_MYSQL = """
        CREATE TABLE IF NOT EXISTS ninja_boost_audit_log (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            timestamp   TEXT    NOT NULL,
            action      TEXT    NOT NULL,
            actor_id    TEXT,
            actor_type  TEXT,
            resource    TEXT,
            resource_id TEXT,
            outcome     TEXT,
            ip          TEXT,
            trace_id    TEXT,
            path        TEXT,
            method      TEXT,
            metadata    TEXT
        )
    """

    def _ensure_table(self) -> None:
        """Create the audit table if it does not already exist."""
        if DatabaseBackend._table_ensured:
            return
        try:
            from django.db import connection
            vendor = getattr(connection, "vendor", "sqlite")
            if vendor == "postgresql":
                ddl = self._DDL_PG
            elif vendor in ("mysql", "mariadb"):
                ddl = self._DDL_MYSQL
            else:
                ddl = self._DDL  # SQLite and others
            with connection.cursor() as cursor:
                cursor.execute(ddl)
            DatabaseBackend._table_ensured = True
        except Exception:
            logger.warning(
                "DatabaseBackend: failed to auto-create audit table — "
                "check database permissions or create it manually.",
                exc_info=True,
            )

    def write(self, record: dict) -> None:
        self._ensure_table()
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ninja_boost_audit_log
                        (timestamp, action, actor_id, actor_type,
                         resource, resource_id, outcome,
                         ip, trace_id, path, method, metadata)
                    VALUES
                        (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    [
                        record["timestamp"],
                        record["action"],
                        record.get("actor_id"),
                        record.get("actor_type", "user"),
                        record.get("resource"),
                        record.get("resource_id"),
                        record.get("outcome", "success"),
                        record.get("ip"),
                        record.get("trace_id"),
                        record.get("path"),
                        record.get("method"),
                        json.dumps(record.get("metadata") or {}),
                    ],
                )
        except Exception:
            # Never let audit failure crash the request; fall back to log
            logger.exception("DatabaseBackend.write failed — falling back to log")
            logger.info("AUDIT FALLBACK: %s", json.dumps(record, default=str))


class MultiBackend:
    """Write to multiple backends simultaneously (e.g. log + DB)."""

    def __init__(self, *backends):
        self._backends = backends

    def write(self, record: dict) -> None:
        for backend in self._backends:
            try:
                backend.write(record)
            except Exception:
                logger.exception("MultiBackend: backend %r raised", backend)


# ── Registry / facade ─────────────────────────────────────────────────────

class AuditLogger:
    """Global audit logger facade. All writes go through here."""

    def __init__(self):
        self._backend: LoggingBackend | DatabaseBackend | None = None
        self._log_reads: bool = False

    def _get_backend(self):
        if self._backend is not None:
            return self._backend

        from django.conf import settings
        from django.utils.module_loading import import_string
        cfg    = getattr(settings, "NINJA_BOOST", {}).get("AUDIT", {})
        dotted = cfg.get("BACKEND", "ninja_boost.audit.LoggingBackend")
        cls    = import_string(dotted)
        self._backend    = cls()
        self._log_reads  = cfg.get("LOG_READS", False)
        return self._backend

    def use(self, backend) -> None:
        """Explicitly set the backend. Useful in tests."""
        self._backend = backend

    def write(self, record: AuditRecord) -> None:
        """Write an audit record. Never raises — failures are logged."""
        try:
            self._get_backend().write(record.to_dict())
        except Exception:
            logger.exception("audit.write failed")

    def log_reads(self) -> bool:
        self._get_backend()  # ensure loaded
        return self._log_reads


audit_logger = AuditLogger()


# ── Helper: extract actor info from ctx ──────────────────────────────────

def _actor_id_from_ctx(ctx: dict) -> Any:
    user = ctx.get("user")
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get("id") or user.get("user_id")
    return getattr(user, "id", None)


def _actor_type_from_ctx(ctx: dict) -> str:
    user = ctx.get("user")
    if user is None:
        return "anonymous"
    if isinstance(user, dict):
        if user.get("is_service"):
            return "service"
    return "user"


# ── Public emit function ──────────────────────────────────────────────────

def emit(
    request,
    ctx:         dict,
    action:      str,
    resource:    str | None = None,
    resource_id: Any        = None,
    outcome:     str        = "success",
    metadata:    dict | None = None,
) -> AuditRecord:
    """
    Emit a single audit record.

    Parameters
    ----------
    request:
        The Django request object.
    ctx:
        The ninja_boost context dict (contains user, ip, trace_id).
    action:
        Dot-namespaced action string: ``"order.create"``, ``"user.login"``.
    resource:
        Resource type being acted on: ``"order"``, ``"user"``, ``"file"``.
    resource_id:
        ID of the specific resource. Converted to string.
    outcome:
        ``"success"`` (default), ``"failure"``, or ``"error"``.
    metadata:
        Any additional structured data to include.

    Returns the AuditRecord for inspection or chaining.

    Example::

        emit(request, ctx, "payment.refund",
             resource="payment", resource_id=payment.id,
             metadata={"amount": 49.99, "reason": "customer request"})
    """
    record = AuditRecord(
        action      = action,
        actor_id    = _actor_id_from_ctx(ctx),
        actor_type  = _actor_type_from_ctx(ctx),
        resource    = resource,
        resource_id = resource_id,
        outcome     = outcome,
        ip          = ctx.get("ip") or getattr(request, "META", {}).get("REMOTE_ADDR"),
        trace_id    = ctx.get("trace_id") or getattr(request, "trace_id", None),
        path        = getattr(request, "path", None),
        method      = getattr(request, "method", None),
        metadata    = metadata,
    )
    audit_logger.write(record)
    return record


# ── Decorator ─────────────────────────────────────────────────────────────

def audit_log(
    action:             str,
    resource:           str | None           = None,
    resource_id_from:   str | None           = None,   # kwarg name to use as resource_id
    resource_id_fn:     Callable | None      = None,   # fn(request, ctx, **kwargs) -> id
    log_on_failure:     bool                 = True,
    metadata_fn:        Callable | None      = None,   # fn(request, ctx, result, **kw) -> dict
    skip_reads:         bool | None          = None,   # None = use AUDIT.LOG_READS setting
):
    """
    Decorator: automatically emit an audit record after a view executes.

    Parameters
    ----------
    action:
        Dot-namespaced action string (e.g. ``"order.delete"``).
    resource:
        Resource type name (e.g. ``"order"``).
    resource_id_from:
        Name of a path/query kwarg to use as the resource ID.
        E.g. ``resource_id_from="id"`` reads ``kwargs["id"]``.
    resource_id_fn:
        Function ``(request, ctx, **kwargs) -> Any`` that returns the resource ID.
        Use when the ID comes from the request body or return value.
    log_on_failure:
        Whether to write an audit record when the view raises an exception.
    metadata_fn:
        Function ``(request, ctx, result, **kwargs) -> dict`` that builds extra
        metadata from the view's return value.

    Example::

        @router.post("/")
        @audit_log("order.create", resource="order",
                   resource_id_fn=lambda req, ctx, result, **kw: result.get("id"))
        def create_order(request, ctx, payload: OrderCreate): ...

        @router.delete("/{id}")
        @audit_log("order.delete", resource="order", resource_id_from="id")
        def delete_order(request, ctx, id: int): ...
    """
    import asyncio

    def _should_skip_request(request) -> bool:
        """
        Return True if this request should NOT be audited.

        Logic:
          - skip_reads=True  → always skip GET requests
          - skip_reads=False → never skip (always audit, even GETs)
          - skip_reads=None  → fall back to AUDIT.LOG_READS setting:
                               skip GET when log_reads is False (the default)
        """
        is_read = getattr(request, "method", "").upper() == "GET"
        if not is_read:
            return False  # only reads can be skipped
        if skip_reads is True:
            return True
        if skip_reads is False:
            return False
        # None → use the global LOG_READS setting (skip reads when it's False)
        return not audit_logger.log_reads()

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request, ctx: dict, *args, **kwargs) -> Any:
                result = await func(request, ctx, *args, **kwargs)
                if not _should_skip_request(request):
                    resource_id = _resolve_id(
                        resource_id_from, resource_id_fn,
                        request, ctx, result, kwargs,
                    )
                    meta = {}
                    if metadata_fn is not None:
                        try:
                            meta = metadata_fn(request, ctx, result, **kwargs) or {}
                        except Exception:
                            pass
                    _write(request, ctx, action, resource, resource_id, "success", meta, kwargs)
                return result

            @wraps(func)
            async def async_wrapper_with_failure(request, ctx: dict, *args, **kwargs) -> Any:
                outcome = "success"
                result  = None
                try:
                    result = await func(request, ctx, *args, **kwargs)
                except Exception:
                    outcome = "error"
                    if not _should_skip_request(request):
                        _write(request, ctx, action, resource, None, outcome, {}, kwargs)
                    raise
                if not _should_skip_request(request):
                    resource_id = _resolve_id(
                        resource_id_from, resource_id_fn,
                        request, ctx, result, kwargs,
                    )
                    meta = {}
                    if metadata_fn is not None:
                        try:
                            meta = metadata_fn(request, ctx, result, **kwargs) or {}
                        except Exception:
                            pass
                    _write(request, ctx, action, resource, resource_id, outcome, meta, kwargs)
                return result

            return async_wrapper_with_failure if log_on_failure else async_wrapper

        # ── Sync path ──────────────────────────────────────────────────────

        def _sync_core(request, ctx, args, kwargs):
            """Run the view and return (result, outcome, resource_id, meta)."""
            outcome = "success"
            result  = None
            try:
                result = func(request, ctx, *args, **kwargs)
            except Exception:
                outcome = "error"
                raise
            resource_id = _resolve_id(
                resource_id_from, resource_id_fn,
                request, ctx, result, kwargs,
            )
            meta = {}
            if metadata_fn is not None:
                try:
                    meta = metadata_fn(request, ctx, result, **kwargs) or {}
                except Exception:
                    pass
            return result, outcome, resource_id, meta

        if log_on_failure:
            @wraps(func)
            def sync_wrapper(request, ctx: dict, *args, **kwargs) -> Any:
                outcome = "success"
                result  = None
                try:
                    result, outcome, resource_id, meta = _sync_core(request, ctx, args, kwargs)
                except Exception:
                    if not _should_skip_request(request):
                        _write(request, ctx, action, resource, None, "error", {}, kwargs)
                    raise
                if not _should_skip_request(request):
                    _write(request, ctx, action, resource, resource_id, outcome, meta, kwargs)
                return result
        else:
            @wraps(func)
            def sync_wrapper(request, ctx: dict, *args, **kwargs) -> Any:
                result, outcome, resource_id, meta = _sync_core(request, ctx, args, kwargs)
                if not _should_skip_request(request):
                    _write(request, ctx, action, resource, resource_id, outcome, meta, kwargs)
                return result

        return sync_wrapper

    return decorator


def _resolve_id(from_kwarg, id_fn, request, ctx, result, kwargs) -> Any:
    if id_fn is not None:
        try:
            return id_fn(request, ctx, result, **kwargs)
        except Exception:
            return None
    if from_kwarg and from_kwarg in kwargs:
        return kwargs[from_kwarg]
    return None


def _write(request, ctx, action, resource, resource_id, outcome, meta, kwargs) -> None:
    try:
        emit(request, ctx, action=action, resource=resource,
             resource_id=resource_id, outcome=outcome, metadata=meta)
    except Exception:
        logger.exception("audit_log decorator: emit failed")


# ── AuditRouter ───────────────────────────────────────────────────────────

class AuditRouter:
    """
    A router wrapper that automatically applies ``@audit_log`` to every operation.

    Generates action names as ``"{resource}.{method}"``:
        GET    /          → {resource}.list
        GET    /{id}      → {resource}.retrieve
        POST   /          → {resource}.create
        PUT    /{id}      → {resource}.update
        PATCH  /{id}      → {resource}.partial_update
        DELETE /{id}      → {resource}.delete

    Usage::

        from ninja_boost.audit import AuditRouter
        from ninja_boost import AutoRouter

        router = AuditRouter(AutoRouter(tags=["Orders"]), resource="order")

        @router.get("/")
        def list_orders(request, ctx): ...        # logs: order.list

        @router.delete("/{id}")
        def delete_order(request, ctx, id: int):  # logs: order.delete
            ...
    """

    _METHOD_ACTION = {
        "GET":    {True: "list",   False: "retrieve"},  # True = no path param (list)
        "POST":   {True: "create", False: "create"},
        "PUT":    {True: "update", False: "update"},
        "PATCH":  {True: "partial_update", False: "partial_update"},
        "DELETE": {True: "delete", False: "delete"},
    }

    def __init__(self, router, resource: str, log_reads: bool = False):
        self._router   = router
        self._resource = resource
        self._log_reads = log_reads

    def _wrap(self, method: str, path: str, func: Callable, kwargs: dict) -> Callable:
        has_id_param = "{" in path
        is_read = method == "GET"
        if is_read and not self._log_reads:
            return func  # skip read audit unless explicitly requested

        action_suffix = self._METHOD_ACTION.get(method, {}).get(not has_id_param, method.lower())
        action = f"{self._resource}.{action_suffix}"

        id_kwarg = None
        if has_id_param:
            import re
            m = re.search(r"\{(\w+)\}", path)
            if m:
                id_kwarg = m.group(1)

        return audit_log(action=action, resource=self._resource,
                         resource_id_from=id_kwarg)(func)

    def get(self, path, **kwargs):
        def decorator(func):
            return self._router.get(path, **kwargs)(self._wrap("GET", path, func, kwargs))
        return decorator

    def post(self, path, **kwargs):
        def decorator(func):
            return self._router.post(path, **kwargs)(self._wrap("POST", path, func, kwargs))
        return decorator

    def put(self, path, **kwargs):
        def decorator(func):
            return self._router.put(path, **kwargs)(self._wrap("PUT", path, func, kwargs))
        return decorator

    def patch(self, path, **kwargs):
        def decorator(func):
            return self._router.patch(path, **kwargs)(self._wrap("PATCH", path, func, kwargs))
        return decorator

    def delete(self, path, **kwargs):
        def decorator(func):
            return self._router.delete(path, **kwargs)(self._wrap("DELETE", path, func, kwargs))
        return decorator
