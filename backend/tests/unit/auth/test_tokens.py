import uuid

import pytest

from app.domains.auth.exceptions import InvalidAccessTokenError
from app.domains.auth.tokens import create_access_token, decode_access_token


def test_access_token_validation() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "admin")

    assert decode_access_token(token) == user_id


def test_invalid_access_token_is_rejected() -> None:
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token("not-a-jwt")
