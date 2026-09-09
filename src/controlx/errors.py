"""Structured error hierarchy. Exit codes are part of the CLI contract."""

from __future__ import annotations


class ControlXError(Exception):
    """Base class for every error ControlX raises on purpose."""

    exit_code = 1

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class UserError(ControlXError):
    """The user asked for something impossible. Exit 1."""

    exit_code = 1


class NotFoundError(UserError):
    pass


class VaultError(ControlXError):
    exit_code = 1


class ProviderError(ControlXError):
    """A provider call failed. Exit 2."""

    exit_code = 2


class AuthError(ProviderError):
    exit_code = 2


class CapabilityError(ProviderError):
    """The provider cannot do what was asked (e.g. write project instructions)."""

    exit_code = 2


class ThresholdError(ControlXError):
    """Audit scored below --min-score. Exit 3."""

    exit_code = 3
