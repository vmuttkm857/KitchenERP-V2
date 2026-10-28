"""Count API SELECTs, excluding only three known test-guard statements at source."""

from collections import Counter
from hashlib import sha256
import sys

from sqlalchemy.sql.elements import TextClause

from tests.database_safety import verify_connection


# Full whitespace-canonical SQL fingerprints, not table-name/prefix filters.
# Any changed/new guard SQL is counted until explicitly reviewed here.
_GUARD_SELECTS = {
    "772fb097627150c5a4e8cbddae661b415e4ebad845d4441df90ddd679e22b507": "database_identity",
    "039818f7e871cfb97cf4a44e689962c2d14870daecec1dc4da7f373f6c7d873e": "competing_sessions",
    "d18830a9891357243cfeac206253c9a204d264e36bd76f99857428f8033b9de5": "application_name",
}


def _inside_connection_guard():
    frame = sys._getframe(1)
    try:
        while frame is not None:
            if frame.f_code is verify_connection.__code__:
                return True
            frame = frame.f_back
        return False
    finally:
        del frame


class SelectQueryBudget:
    def __init__(self, maximum):
        self.maximum = maximum
        self.business_selects = 0
        self.safety_selects = Counter()

    def record(self, conn, cursor, statement, parameters, context, executemany):
        # Retain the original SELECT measurement, including authentication.
        # Never retain/log SQL parameters or business data.
        if not statement.lstrip().upper().startswith("SELECT"):
            return
        clause = getattr(getattr(context, "compiled", None), "statement", None)
        if isinstance(clause, TextClause):
            fingerprint = sha256(" ".join(clause.text.split()).encode("utf-8")).hexdigest()
            category = _GUARD_SELECTS.get(fingerprint)
            if category is not None and _inside_connection_guard():
                self.safety_selects[category] += 1
                return
        self.business_selects += 1

    def assert_within_budget(self):
        assert self.business_selects <= self.maximum, (
            f"API SELECT budget exceeded: {self.business_selects} > {self.maximum}; "
            f"known test-safety SELECTs excluded: {dict(self.safety_selects)}"
        )
