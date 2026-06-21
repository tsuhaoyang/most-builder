# ADR-010: Natural language → MOST sequence (backlog)

**Status:** Proposed / not implemented  
**Date:** 2026-04-19  

## Context

Users may want to type a free-text method description and obtain a suggested MiniMOST sequence (indices + GM/CM).

## Decision (for now)

Do **not** implement NL→MOST in Phase 1. Reasons:

1. **Correctness risk**: Wrong suggestions become false “standards” unless every suggestion is validated by a trained analyst and the same canonical validators used today.
2. **Ambiguity**: One sentence often maps to multiple legal sequence models; product must define disambiguation, confidence, and rejection UX.
3. **Scope**: Requires intent classification, slot filling (A/B/G/…), and tight coupling to `MOST-core-algorithm-spec.md` plus regression tests.

## Follow-up (when prioritized)

- Define an explicit **suggestion** vs **committed step** lifecycle (never auto-commit without validation).
- Store parser version and source sentence for audit.
- Evaluate small **closed vocabulary** shortcuts (e.g. map known verbs to partial presets) before full LLM parsing.
