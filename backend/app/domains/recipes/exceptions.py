class RecipeError(Exception):
    pass


class DuplicateRecipeIngredientError(RecipeError):
    pass


class InvalidRecipeIngredientError(RecipeError):
    pass


class RecipeDetailIdentityError(RecipeError):
    pass
