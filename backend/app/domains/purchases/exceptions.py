class PurchaseNotFoundError(Exception):pass
class SnapshotNotReadyError(Exception):
    def __init__(self,issues):self.issues=issues
class DuplicatePurchaseError(Exception):
    def __init__(self,purchase_id=None):self.purchase_id=purchase_id
class InvalidPurchaseStatusError(Exception):pass
