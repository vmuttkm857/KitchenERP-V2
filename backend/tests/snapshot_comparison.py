"""Assertions for unchanged snapshot API content, independent of DB Decimal scale."""

from decimal import Decimal, InvalidOperation


HEADER_DECIMAL_FIELDS = frozenset({"known_estimated_cost", "total_estimated_cost"})
ITEM_DECIMAL_FIELDS = frozenset({
    "requirement_quantity", "suggested_purchase_quantity", "adjusted_quantity",
    "package_size_snapshot", "minimum_order_quantity_snapshot", "unit_price_snapshot",
    "estimated_cost_snapshot", "adjusted_estimated_cost",
})


def assert_snapshot_unchanged(actual, expected):
    """Compare every key/item; only typed snapshot Decimal paths ignore scale.

    source_summary and other JSON metadata intentionally remain byte-for-byte
    string comparisons, including any numeric-looking identifiers or quantities.
    """
    def compare(left, right, path):
        decimal_field = (
            len(path) == 1 and path[0] in HEADER_DECIMAL_FIELDS
            or len(path) == 3 and path[0] == "items" and isinstance(path[1], int)
            and path[2] in ITEM_DECIMAL_FIELDS
        )
        if decimal_field:
            if left is None or right is None:
                assert left is right, f"Nullable Decimal changed at {path}"
                return
            assert type(left) is str and type(right) is str, f"Decimal wire type changed at {path}"
            try:
                a, b = Decimal(left), Decimal(right)
            except InvalidOperation:
                raise AssertionError(f"Invalid Decimal at {path}") from None
            assert a.is_finite() and b.is_finite() and a == b, f"Decimal value changed at {path}"
            return
        assert type(left) is type(right), f"JSON type changed at {path}"
        if isinstance(left, dict):
            assert left.keys() == right.keys(), f"Snapshot keys changed at {path}"
            for key in left:
                compare(left[key], right[key], (*path, key))
        elif isinstance(left, list):
            assert len(left) == len(right), f"Snapshot list length changed at {path}"
            for index, (a, b) in enumerate(zip(left, right)):
                compare(a, b, (*path, index))
        else:
            assert left == right, f"Snapshot value changed at {path}"

    compare(actual, expected, ())
