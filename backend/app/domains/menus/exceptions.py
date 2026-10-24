class MenuError(Exception): pass
class MenuNotFoundError(MenuError): pass
class InvalidMenuCategoryError(MenuError): pass
class InvalidMenuDateRangeError(MenuError): pass
class MenuInUseError(MenuError): pass
class MealTypeNotFoundError(MenuError): pass
class MealTypeNameExistsError(MenuError): pass
class MealTypeInUseError(MenuError): pass
class MealTypeColumnNotFoundError(MenuError): pass
class MealTypeColumnNameExistsError(MenuError): pass
class InvalidMenuStructureError(MenuError): pass
class DuplicateMenuDishError(MenuError): pass
class InvalidMenuCopyError(MenuError): pass


class MenuVersionConflictError(MenuError):
    def __init__(self, code="MENU_VERSION_CONFLICT", current_fingerprint=None):
        self.code = code
        self.current_fingerprint = current_fingerprint


class MenuAdjustmentContextError(MenuError):
    def __init__(self, code, status_code=409):
        self.code = code
        self.status_code = status_code
