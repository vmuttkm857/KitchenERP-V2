"""Explicitly calculate the viewed result before API-test snapshot creation."""


def save_snapshot(client, headers, criteria):
    calculation = client.post("/api/v1/requirements/calculate", headers=headers, json=criteria)
    assert calculation.status_code == 200, calculation.text
    return client.post("/api/v1/requirement-snapshots", headers=headers, json={
        "criteria": criteria,
        "expected_result_fingerprint": calculation.json()["result_fingerprint"],
    })
