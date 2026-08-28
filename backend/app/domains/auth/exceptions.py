class AuthenticationError(Exception):
    pass


class InvalidCredentialsError(AuthenticationError):
    pass


class InvalidAccessTokenError(AuthenticationError):
    pass


class InvalidRefreshTokenError(AuthenticationError):
    pass
