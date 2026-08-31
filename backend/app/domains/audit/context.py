from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditRequestContext:
    request_id: str | None = None
    ip_address: str | None = None


_request_context: ContextVar[AuditRequestContext] = ContextVar(
    "audit_request_context", default=AuditRequestContext()
)


def set_audit_request_context(context: AuditRequestContext) -> Token[AuditRequestContext]:
    return _request_context.set(context)


def reset_audit_request_context(token: Token[AuditRequestContext]) -> None:
    _request_context.reset(token)


def get_audit_request_context() -> AuditRequestContext:
    return _request_context.get()
