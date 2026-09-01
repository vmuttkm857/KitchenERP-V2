class NutritionError(Exception): pass
class NutritionFoodNotFoundError(NutritionError): pass
class NutritionImportError(NutritionError): pass
class NutritionFoodInUseError(NutritionError): pass
class InvalidNutritionSourceError(NutritionError): pass
