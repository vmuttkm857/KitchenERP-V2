def save_editor(client, url, *, headers, json):
    """Regression fixtures use a fresh version; conflict tests send explicit versions."""
    current = client.get(url, headers=headers)
    assert current.status_code == 200, current.text
    payload = {"expected_editor_fingerprint": current.json()["editor_fingerprint"], **json}
    return client.put(url, headers=headers, json=payload)
