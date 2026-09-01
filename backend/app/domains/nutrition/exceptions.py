class NutritionError(Exception): pass
class NutritionFoodNotFoundError(NutritionError): pass
class NutritionImportError(NutritionError): pass
class NutritionFoodInUseError(NutritionError): pass
class InvalidNutritionSourceError(NutritionError): pass
class NutritionUnitConversionNotFoundError(NutritionError): pass
class NutritionUnitConversionExistsError(NutritionError): pass
