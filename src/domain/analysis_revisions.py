"""Failures of private, immutable calculation history."""


class RevisionNotFound(Exception):
    pass


class RevisionIntegrityError(Exception):
    pass
