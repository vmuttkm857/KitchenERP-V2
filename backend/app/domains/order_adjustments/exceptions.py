class OrderingAdjustmentNotFoundError(Exception): pass
class OrderingAdjustmentStateError(Exception): pass
class OrderingAdjustmentVersionConflictError(Exception): pass
class OrderingAdjustmentStaleError(Exception):
    def __init__(self, reasons=None): self.reasons = reasons or []
class OrderingAdjustmentInvariantError(Exception): pass
class OrderingAdjustmentLineNotFoundError(Exception): pass
class OrderingAdjustmentSnapshotLockedError(Exception): pass
class OrderingAdjustmentExistingDraftError(Exception):
    def __init__(self,sheet_id):self.sheet_id=sheet_id
class OrderingAdjustmentAlreadyConfirmedError(Exception):
    def __init__(self,sheet_id):self.sheet_id=sheet_id
