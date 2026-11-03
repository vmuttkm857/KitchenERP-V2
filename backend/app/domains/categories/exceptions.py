class CategoryNotFoundError(Exception):
    pass


class CategoryNameExistsError(Exception):
    pass


class CategoryInUseError(Exception):
    pass


class InvalidCategoryColorError(Exception):
    pass
