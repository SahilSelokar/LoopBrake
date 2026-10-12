# Specification Quality Checklist: Ask Before Stopping (Claude Code)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-12
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Hook event names and JSON fields stay out of the requirements. FRs say "Claude Code's own approval
  prompt"; the mechanism is named only under Assumptions, as a dependency to confirm.
- Three behaviours are undocumented by Claude Code and are listed under Assumptions for research, not
  as clarifications. Each has a safe default:
  - permission prompts turned off: treat as "can't ask" and stop;
  - Claude after a refusal: later calls are refused too (FR-006);
  - deciding before a batched call: one question per ask point (FR-008).
- A constitution amendment is a dependency before the plan's Constitution Check. It covers Principle I's
  wording, the Claude Code "stop" format, and the success labels.
