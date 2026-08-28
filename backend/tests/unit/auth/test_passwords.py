from app.domains.auth.passwords import hash_password, verify_password


def test_password_hash_and_verify() -> None:
    password = "correct horse battery staple"
    password_hash = hash_password(password)

    assert password not in password_hash
    assert verify_password(password, password_hash)
    assert not verify_password("wrong password", password_hash)
