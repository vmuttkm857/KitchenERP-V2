class EmptyExportError(Exception):
    pass


class ExportNotFoundError(Exception):
    pass


class SupplierWeeklyExportError(Exception):
    def __init__(self, code: str, **details):
        super().__init__(code)
        self.code = code
        self.details = details
