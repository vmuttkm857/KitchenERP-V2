class MenuImportValidationError(Exception):
    pass


class MenuImportNotFoundError(Exception):
    pass


class MenuImportLineNotFoundError(Exception):
    pass


class MenuImportHashMismatchError(Exception):
    pass


class MenuImportFatalError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Excel 內容含有無法建立草稿的錯誤")


class MenuImportDuplicateError(Exception):
    def __init__(self, batch_id):
        self.batch_id = batch_id
        super().__init__("相同 Excel 已存在尚未完成的匯入草稿")


class MenuImportDishUnavailableError(Exception):
    pass


class MenuImportAlreadyFinalizedError(Exception):
    def __init__(self, menu_id=None):
        self.menu_id = menu_id
        super().__init__("這份匯入已建立正式菜單")


class MenuImportNotReadyError(Exception):
    def __init__(self, warnings: list[str]):
        self.warnings = warnings
        super().__init__("匯入草稿尚未符合建立正式菜單的條件")
