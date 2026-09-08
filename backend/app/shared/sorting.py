from sqlalchemy import Numeric, case, cast, func


def natural_code_order(column):
    """Return deterministic PostgreSQL ordering expressions for numeric and text codes."""
    is_numeric = column.op("~")(r"^[0-9]+$")
    return (
        case((is_numeric, 0), else_=1),
        case((is_numeric, cast(column, Numeric)), else_=None),
        case((is_numeric, func.length(column)), else_=None),
        func.lower(column),
        column,
    )
