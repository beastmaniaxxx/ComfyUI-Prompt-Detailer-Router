---
name: kiro-review
description: Review a task implementation against approved specs, task boundaries, and verification evidence. Use after an implementer finishes a task, after remediation, or before accepting a task as complete.
---

# kiro-review

<background_information>
This skill performs task-local adversarial review. It verifies that the implementation is real, complete, bounded, aligned with approved requirements and design, and supported by mechanical verification evidence.

Boundary terminology continuity:
- discovery identifies `Boundary Candidates`
- design fixes `Boundary Commitments`
- tasks constrain execution with `_Boundary:_`
- review rejects concrete `Boundary Violations`
</background_information>

<instructions>
## When to Use

- After an implementer reports `READY_FOR_REVIEW`
- After remediation for a rejected review
- Before marking a task `[x]`
- Before accepting a task into feature-level validation

Do not use this skill to invent missing requirements or silently reinterpret the spec.

## Inputs

Provide:
- Task ID and exact task text from `tasks.md`
- Relevant requirement section numbers
- Relevant design section numbers
- Spec file paths (`requirements.md`, `design.md`, optionally `tasks.md`)
- The implementer's status report
- The implementer's `## Ripple Report`, and `## Remediation Report` blocks on a re-review
- The current `REVIEW_ROUND` number for this task
- The task `_Boundary:_` scope constraints
- Validation commands discovered by the controller
- Relevant steering excerpts when applicable
- Relevant `## Implementation Notes` entries when applicable

## Outputs

Return one of:
- `APPROVED`
- `REJECTED`

Also return:
- Mechanical results
- Findings with severity
- Required remediation
- One-sentence summary

Use the language specified in `spec.json`.

## First Action

Run `git diff` to inspect the actual code changes. If the diff is large or ambiguous, read the changed files directly. Do not trust the implementer report as source of truth.

## Core Principle

Read the spec yourself. Read the diff yourself. Verify mechanically where possible. Reject on concrete failures rather than interpretive optimism.
The main review question is not just "does it work?" but "does it stay inside the approved responsibility boundary without hiding new coupling?"

## Round Discipline

A task gets at most 10 review rounds (AGENTS.md §17.1). Review is bounded, so front-load it.

- Enumerate **all** occurrences of each problem. A finding may group occurrences, but it must list every affected file and line — never a representative sample.
- Exhaust each review angle in round 1. Do not open a review angle in a later round that was available earlier.
- From round 5 onward, restrict findings to defects newly introduced by remediation and to previously reported findings that are still unfixed.
- Cite a basis for every finding: a `requirements.md` or `design.md` section number, or an AGENTS.md section number. Findings with no such basis are `Suggestion` or `FYI` at most and must not drive a `REJECTED` verdict.
- Preference-based and stylistic remarks never justify rejection.
- Apply the finding threshold in AGENTS.md §17.5: only the "指摘する" categories may be `Critical` / `Important`; everything in "指摘しない" is `Suggestion` / `FYI`, capped at 5 per round. Every finding states a concrete input, the resulting wrong output or exception, and why it is wrong — no reproduction condition, no finding.
- Check the recurring defect classes in AGENTS.md §22 against the diff before concluding: config/resource loading boundaries, string post-processing and complexity, domain invariants and round-trip symmetry, preset scope/subject bleed, externalized resources and version constants, fixture coverage and Python 3.10 compatibility.

## Mechanical Checks

Run these checks and use the result as primary signal.

### 1. Regression Safety
- Run the project's canonical test suite using the validation commands discovered by the controller.
- If tests fail, reject.

### 2. No Residual Placeholder Markers
- Check changed files for `TBD`, `TODO`, `FIXME`, `HACK`, `XXX`.
- Reject if new placeholder markers were introduced without explicit task justification.

### 3. No Hardcoded Secrets
- Check changed files for hardcoded secrets or credentials.
- Reject if concrete secret patterns are introduced.

### 4. Boundary Respect
- Compare changed files against the task `_Boundary:_` scope.
- Reject if the change spills outside the approved boundary without explicit justification.
- Reject if the implementation introduces hidden cross-boundary coordination inside what should be a local task.

### 5. RED Phase Evidence
- For behavioral tasks, verify that the implementer status report includes `RED_PHASE_OUTPUT`.
- Reject if RED evidence is missing, empty, or unrelated to the task's acceptance criteria.

### 6. Runtime-Sensitive Static Checks
- If the project already has lint or equivalent static analysis for the touched stack, run the relevant command for the task boundary.
- Pay attention to patterns that can survive typecheck/build yet fail at runtime: type-only imports used as values, missing namespace value imports for qualified-name access, unresolved globals, and newly introduced runtime-sensitive dependencies without matching boot/runtime handling.
- If no project lint command exists, perform a targeted diff-based spot check in the changed files for those patterns.
- Reject on concrete findings that create a realistic boot-time or module-load failure.

### 6.5 Ripple Check Evidence
- Verify a `## Ripple Report` block is present for any task with a non-empty code diff (AGENTS.md §16.4).
- Reject if the block is missing, or if `SEARCH_COMMANDS` is empty — cross-repository search must be evidenced, not asserted.
- Re-run one or two of the reported searches. Reject if they surface impacted locations inside the boundary that were neither fixed nor listed under `IMPACTED_OUT_OF_BOUNDARY`.

### 6.6 Remediation Breadth (re-reviews only)
- Verify a `## Remediation Report` block exists for each finding from the previous round (AGENTS.md §17.3).
- Reject if `SAME_KIND_SEARCH` is empty, or if only the exact location named in the finding was fixed while the same class of defect survives elsewhere inside the boundary.

## Judgment Checks

### 7. Reality Check
- Confirm the implementation is real production code, not a placeholder, stub, fake path, or deferred-work shell.

### 8. Acceptance Criteria Coverage
- Read the task description and confirm all aspects are implemented, not only the primary happy path.

### 9. Requirements Alignment
- Read the referenced sections in `requirements.md`.
- Confirm each requirement is satisfied by concrete observable behavior.
- Use original section numbers only.

### 10. Design Alignment
- Read the referenced sections in `design.md`.
- Confirm the implementation uses the prescribed structures, interfaces, and dependency direction.
- Reject silent substitutions for design-mandated choices.

### 10.5 Boundary Audit
- Compare the implementation against the design's boundary commitments and out-of-boundary statements.
- Reject if downstream-specific behavior is pushed into an upstream boundary for convenience.
- Reject if the implementation creates new hidden dependencies, shared ownership, or undeclared coupling across adjacent boundaries.
- Reject if a task that is not an explicit integration task now behaves like one.

### 11. Test Quality
- Confirm tests prove the required behavior rather than only scaffolding.
- Confirm tests would fail if the implementation were removed or broken.

### 12. Error Handling
- Confirm relevant failure paths are handled and not silently swallowed.

## Severity Model

Use:
- `Critical` for broken functionality, invalid verification, data loss, security risk, or major scope violation
- `Important` for required fixes before acceptance
- `Suggestion` for non-blocking improvements
- `FYI` for informational notes

## Stop / Escalate

Escalate instead of papering over the issue when:
- The approved spec is ambiguous in a correctness-critical way
- The design conflicts with what is technically possible
- Required evidence cannot be gathered
- The implementation only works by silently deviating from approved scope
- Boundary ownership cannot be determined cleanly from requirements, design, and task scope

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| “Tests pass, so approve” | Passing tests do not prove spec compliance or boundary respect. |
| “The extra behavior is useful” | Extra behavior outside approved scope is still drift. |
| “The implementer said RED was done” | RED must be evidenced, not asserted. |
| “This gap is small enough to let through” | Real gaps must be rejected or escalated. |
| “I will raise the rest next round” | Rounds are capped at 10; withheld findings waste them. Report everything you have now. |
| “One example is enough, they will find the others” | Partial location lists cause repeat rejections. Enumerate every occurrence. |

## Output Format

```md
## Review Verdict
- VERDICT: APPROVED | REJECTED
- TASK: <task-id>
- ROUND: <current review round number> / 10
- MECHANICAL_RESULTS:
  - Tests: PASS | FAIL (command and exit code)
  - TBD/TODO grep: CLEAN | <count> matches
  - Secrets grep: CLEAN | <count> matches
  - Static checks: PASS | FAIL | SPOT_CHECKED
  - Boundary: WITHIN | <files outside boundary>
  - Boundary audit: CLEAN | <spillover / hidden dependency findings>
  - RED phase: VERIFIED | MISSING | N/A
  - Ripple Report: VALID | MISSING | NO_SEARCH_COMMANDS | <unlisted impacts found>
  - Remediation Report: VALID | MISSING | NO_SAME_KIND_SEARCH | N/A
- FINDINGS:
  1. <specific finding with exact files/spec refs, listing ALL affected locations>
- REMEDIATION: <mandatory if REJECTED>
- SUMMARY: <one sentence>
```
</instructions>
