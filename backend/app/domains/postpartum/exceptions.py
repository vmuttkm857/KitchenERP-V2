class PostpartumError(Exception): pass
class PostpartumCaseNotFoundError(PostpartumError): pass
class PostpartumPauseNotFoundError(PostpartumError): pass
class InvalidPostpartumDataError(PostpartumError): pass
