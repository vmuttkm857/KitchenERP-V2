class RequirementError(Exception): pass
class RequirementMenuNotFoundError(RequirementError): pass


class RequirementAdjustmentError(RequirementError):
    def __init__(self,code,*,status_code=409,**context):
        self.code=code;self.status_code=status_code;self.context=context
        super().__init__(code)
