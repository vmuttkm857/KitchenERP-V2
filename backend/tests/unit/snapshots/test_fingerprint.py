import uuid
from decimal import Decimal
from app.domains.snapshots.fingerprint import snapshot_fingerprint

def test_fingerprint_is_deterministic_for_key_menu_and_date_order():
    one,two=uuid.uuid4(),uuid.uuid4()
    left={"menu_ids":[one,two],"selected_dates":["2026-09-02","2026-09-01"],"value":Decimal("1.00")}
    right={"value":Decimal("1"),"selected_dates":["2026-09-01","2026-09-02"],"menu_ids":[two,one]}
    assert snapshot_fingerprint(left)==snapshot_fingerprint(right)

def test_fingerprint_changes_with_calculation_criteria():
    menu=uuid.uuid4()
    assert snapshot_fingerprint({"menu_ids":[menu],"start_date":"2026-09-01"})!=snapshot_fingerprint({"menu_ids":[menu],"start_date":"2026-09-02"})
