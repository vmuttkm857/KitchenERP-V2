from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import re
import uuid
from typing import Any

from pydantic import BaseModel


_SENSITIVE_KEYS = {
    "password", "currentpassword", "newpassword", "confirmpassword", "passwordhash",
    "accesstoken", "refreshtoken", "tokenhash", "authorization", "cookie",
    "databaseurl", "jwtsecret", "secret",
}


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _is_sensitive(key: object) -> bool:
    normalized = _normalized_key(key)
    return normalized in _SENSITIVE_KEYS or "password" in normalized or normalized.endswith("token")


def sanitize_audit_data(value: Any) -> Any:
    """Return a JSON-safe recursively sanitized audit value."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return sanitize_audit_data(value.value)
    if isinstance(value, BaseModel):
        return sanitize_audit_data(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return sanitize_audit_data(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive(key) else sanitize_audit_data(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_audit_data(item) for item in value]
    return str(value)
