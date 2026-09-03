"""Central error-code registry (ADR-034 §D3).

Single source of truth for the ~33 stable, machine-readable error codes that
travel in the ``{error: {code, message, detail}}`` envelope
(``schemas/common.py`` :class:`ErrorDetail`).

Governance (ADR-034 §3):
- **I3** — code strings are a *stable contract* (frontend i18n catalog keys,
  future third-party API). They MUST NOT be renamed; changes go through the
  additive-evolution path (ADR-011).

This module is *definition only*. Introducing it does not change any behaviour
and does not force every ``raise`` site to migrate to it immediately (that is
staged in ADR-034 phases A4/B). ``error_handlers.py`` uses these members in
place of literal strings so the handler layer references the single registry.

``ErrorCode`` subclasses ``str`` so members are drop-in compatible anywhere a
plain code string is expected (e.g. ``ErrorDetail(code=ErrorCode.NOT_FOUND)``
serialises to ``"NOT_FOUND"``).
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Stable, machine-readable error codes. String value == wire contract."""

    # --- Core envelope codes (produced by error_handlers.py) ---
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFLICT = "CONFLICT"
    VERSION_PUBLISHED = "VERSION_PUBLISHED"
    TIME_SOURCE_IMMUTABLE = "TIME_SOURCE_IMMUTABLE"
    FORBIDDEN = "FORBIDDEN"
    UNAUTHORIZED = "UNAUTHORIZED"
    NO_ACTIVE_RULE_SET = "NO_ACTIVE_RULE_SET"
    NO_DEFAULT_POLICY = "NO_DEFAULT_POLICY"
    RULE_SET_ACTIVATE_CONFLICT = "RULE_SET_ACTIVATE_CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # --- Non-family HTTP status codes (ADR-034 §A4; additive, I3) ---
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

    # --- Rule-set lifecycle / integrity codes (route + service layers) ---
    RULE_SET_INCOMPLETE = "RULE_SET_INCOMPLETE"
    RULE_SET_NOT_RETIRED = "RULE_SET_NOT_RETIRED"
    RULE_SET_RETIRED = "RULE_SET_RETIRED"
    RULE_SET_ACTIVE = "RULE_SET_ACTIVE"
    RULE_SET_IN_USE = "RULE_SET_IN_USE"
    CERTIFIED_IMMUTABLE = "CERTIFIED_IMMUTABLE"
    EN_LABEL_NOT_UNIQUE = "EN_LABEL_NOT_UNIQUE"

    # --- Synonyms / dictionary codes ---
    SYNONYM_CONFLICT = "SYNONYM_CONFLICT"
    SYNONYM_PRIORITY_COLLISION = "SYNONYM_PRIORITY_COLLISION"
    OPTION_CODE_NOT_FOUND = "OPTION_CODE_NOT_FOUND"

    # --- Level System validation codes ---
    LEVEL_POLICY_MISMATCH = "LEVEL_POLICY_MISMATCH"
    LEVEL_VALIDATION_FAILED = "LEVEL_VALIDATION_FAILED"
    LEVEL_VALIDATION_REQUIRED = "LEVEL_VALIDATION_REQUIRED"

    # --- WI context / worksheet codes ---
    WI_CONTEXT_INVALID = "WI_CONTEXT_INVALID"
    SIMO_PAIR_INVALID = "SIMO_PAIR_INVALID"

    # --- WI-set project instantiation codes (ADR-034 §A4 batch 4; service explicit, I3) ---
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    EMPTY_PROJECT = "EMPTY_PROJECT"
    MANUAL_ITEM_UNSUPPORTED = "MANUAL_ITEM_UNSUPPORTED"
    WI_TEMPLATE_NOT_FOUND = "WI_TEMPLATE_NOT_FOUND"
    INVALID_WI_TEMPLATE = "INVALID_WI_TEMPLATE"
    WI_TEMPLATE_UNPUBLISHED = "WI_TEMPLATE_UNPUBLISHED"
    WI_TEMPLATE_RETIRED = "WI_TEMPLATE_RETIRED"
    WI_TEMPLATE_VERSION_NOT_FOUND = "WI_TEMPLATE_VERSION_NOT_FOUND"
    WORKSHEET_RULE_SET_NOT_FOUND = "WORKSHEET_RULE_SET_NOT_FOUND"
    VOCAB_REF_INVALID = "VOCAB_REF_INVALID"

    # --- i18n review workflow codes ---
    I18N_UNKNOWN_SCOPE_KEY = "I18N_UNKNOWN_SCOPE_KEY"
    I18N_REVIEW_ROW_NOT_FOUND = "I18N_REVIEW_ROW_NOT_FOUND"
    I18N_REVIEW_TARGET_MISSING = "I18N_REVIEW_TARGET_MISSING"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


__all__ = ["ErrorCode"]
