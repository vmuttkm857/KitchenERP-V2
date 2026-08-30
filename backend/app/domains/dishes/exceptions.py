class DishError(Exception):
    pass


class DishNotFoundError(DishError):
    pass


class DishIdentityExistsError(DishError):
    pass


class DishCodeExistsError(DishIdentityExistsError):
    pass


class DishNameExistsError(DishIdentityExistsError):
    pass


class InvalidDishCategoryError(DishError):
    pass


class DishInUseError(DishError):
    pass
