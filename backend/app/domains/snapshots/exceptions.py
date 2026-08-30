class SnapshotNotFoundError(Exception): pass
class DuplicateSnapshotError(Exception):
    def __init__(self,snapshot_id=None): self.snapshot_id=snapshot_id
class InvalidAdjustedQuantityError(Exception): pass
class EmptySnapshotError(Exception): pass
class SnapshotLockedError(Exception): pass
class InvalidPurchaseUnitError(Exception): pass
class SnapshotInUseError(Exception): pass
class InvalidSnapshotDateRangeError(Exception): pass
