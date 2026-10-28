"""Fixed-code diagnostics for pytest connections; never format driver exceptions."""

import logging
from contextvars import ContextVar

from sqlalchemy.exc import DBAPIError, InvalidRequestError, TimeoutError

_LOG = logging.getLogger("kitchenerp.test_database_guard")
_CURRENT = ContextVar("test_connection_diagnostic", default=None)
_PHASES = frozenset({
    "connect", "identity_query", "competing_sessions_query", "identity_validation",
    "rollback", "application_name", "commit", "verified", "close",
})
_REJECTIONS = frozenset({
    "TEST_DB_ACTUAL_IDENTITY_MISMATCH", "TEST_DB_ISOLATION_NOT_VERIFIED", "TEST_DB_IN_USE",
})


class ConnectionDiagnostic:
    def __init__(self):
        self.phase = "connect"
        self.other_count = None

    def stage(self, phase):
        self.phase = phase if phase in _PHASES else "unknown"

    def failure(self, error):
        from tests.database_safety import UnsafeTestDatabase
        # Do not call str/repr(error), inspect SQL/URLs, or retain the exception.
        reason = "UNEXPECTED_ERROR"
        if isinstance(error, UnsafeTestDatabase):
            reason = error.args[0] if len(error.args) == 1 and type(error.args[0]) is str and error.args[0] in _REJECTIONS else "GUARD_REJECTED"
        elif isinstance(error, TimeoutError):
            reason = "POOL_TIMEOUT"
        elif isinstance(error, InvalidRequestError):
            reason = "TRANSACTION_STATE_ERROR"
        elif isinstance(error, DBAPIError):
            reason = "DRIVER_CONNECTION_ERROR" if self.phase == "connect" else "DRIVER_OPERATION_ERROR"
        try:
            _LOG.error("TEST_DB_DIAGNOSTIC phase=%s reason=%s", self.phase, reason)
        except Exception:
            # A broken log handler must never replace the original rejection.
            pass


def connection_stage(phase):
    diagnostic = _CURRENT.get()
    if diagnostic is not None:
        diagnostic.stage(phase)


def connection_competitors(count):
    diagnostic = _CURRENT.get()
    if diagnostic is not None:
        diagnostic.other_count = count if type(count) is int and count >= 0 else None


def open_verified_connection(connect, engine, target, application_name, *args, verify=None, **kwargs):
    from tests.database_safety import UnsafeTestDatabase, verify_connection

    verifier = verify_connection if verify is None else verify
    diagnostic = ConnectionDiagnostic()
    token = _CURRENT.set(diagnostic)
    connection = None
    from tests.session_diagnostics import active_trace
    trace = active_trace()
    try:
        if trace is not None:
            try:
                trace.instrument(engine)
            except Exception:
                pass
        connection = connect(engine, *args, **kwargs)
        verifier(connection, target, application_name)
        if trace is not None:
            trace.verified(connection)
    except Exception as error:
        diagnostic.failure(error)
        if (trace is not None and connection is not None and isinstance(error, UnsafeTestDatabase)
                and error.args == ("TEST_DB_IN_USE",)):
            try:
                trace.rejected(connection, application_name, diagnostic.other_count)
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception as close_error:
                diagnostic.stage("close")
                diagnostic.failure(close_error)
        raise UnsafeTestDatabase("TEST_DB_CONNECTION_NOT_VERIFIED") from None
    finally:
        _CURRENT.reset(token)
    return connection
