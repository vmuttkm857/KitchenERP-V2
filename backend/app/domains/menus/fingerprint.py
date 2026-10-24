"""Content versions for menu editing; no stored revision or schema change needed."""

import hashlib
import json
from datetime import date, datetime
from uuid import UUID


def _json_value(value):
    if isinstance(value, (date, datetime, UUID)):
        return str(value)
    raise TypeError(f"Unsupported menu fingerprint value: {type(value).__name__}")


def _hash(value):
    encoded = json.dumps(value, default=_json_value, ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _context(aggregate):
    return {key: aggregate["menu"][key] for key in ("id", "start_date", "end_date", "is_active")}


def editor_fingerprint(aggregate):
    return _hash({"version": "menu-editor-v1", "menu": _context(aggregate),
                  "meals": [{key: getattr(meal, key) for key in
                             ("id", "name", "sort_order", "is_active")} for meal in aggregate["meal_types"]],
                  "columns": [{key: getattr(column, key) for key in
                               ("id", "menu_meal_type_id", "name", "sort_order")}
                              for column in aggregate["meal_type_columns"]],
                  "slots": aggregate["slots"]})


def slot_fingerprint(aggregate, menu_date, meal_type_id):
    meal = next(meal for meal in aggregate["meal_types"] if meal.id == meal_type_id)
    slot = next((slot for slot in aggregate["slots"]
                 if slot["menu_date"] == menu_date and slot["menu_meal_type_id"] == meal_type_id), None)
    return _hash({"version": "menu-slot-v1", "menu": _context(aggregate),
                  "date": menu_date, "meal": {key: getattr(meal, key) for key in
                  ("id", "name", "sort_order", "is_active")},
                  "columns": [{key: getattr(column, key) for key in ("id", "name", "sort_order")}
                              for column in aggregate["meal_type_columns"]
                              if column.menu_meal_type_id == meal_type_id], "slot": slot})
