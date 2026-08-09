"""DETAILER_PLAN domain model and business-invariant validation (Tier 2).

Pure domain logic: no ComfyUI, Ollama, filesystem, or ``jsonschema`` imports.
JSON shape validation (Tier 1) is performed separately in the infrastructure
layer against the JSON Schema file; this module enforces the business
invariants that a JSON Schema cannot express (Requirement 5).
"""

from __future__ import annotations

from dataclasses import dataclass

from prompt_detailer_router.domain.scopes import SUPPORTED_SCOPES

SCHEMA_VERSION: int = 1

_SUPPORTED_SCOPE_SET = frozenset(SUPPORTED_SCOPES)


@dataclass(frozen=True, slots=True)
class DetailerTask:
    """A single detailer task within a plan (immutable)."""

    task_id: str
    subject_id: str
    scope: str
    extracted_features: tuple[str, ...]
    prompt_core: str
    prompt_final: str
    order: int
    enabled: bool
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        # Coerce sequence fields to tuples so a list passed to the public
        # constructor cannot be mutated after construction (true immutability).
        object.__setattr__(self, "extracted_features", tuple(self.extracted_features))
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True, slots=True)
class DetailerPlan:
    """A versioned plan of detailer tasks for the requested scopes (immutable)."""

    schema_version: int
    requested_scopes: tuple[str, ...]
    tasks: tuple[DetailerTask, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_scopes", tuple(self.requested_scopes))
        object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True, slots=True)
class PlanValidationIssue:
    """A single business-invariant violation found in a plan."""

    code: str
    message: str
    task_id: str | None = None


def make_task_id(subject_id: str, scope: str) -> str:
    """Compose the initial-spec task id: ``subject_id + "." + scope``."""

    return f"{subject_id}.{scope}"


def validate_plan(plan: DetailerPlan) -> tuple[PlanValidationIssue, ...]:
    """Return business-invariant violations for ``plan`` (empty tuple if valid).

    Enforces the plan contract (Requirements 3, 4, 5) independently of the JSON
    Schema, so a plan constructed in memory is validated to the same rules as one
    decoded from JSON:
    - ``requested_scopes`` are supported lowercase scopes with no duplicates
      (4.4);
    - ``task_id`` equals ``subject_id + "." + scope`` (3.1) and is unique (3.4);
    - the ``(subject_id, scope)`` pair is unique within the plan (3.3);
    - every ``task.scope`` is in ``requested_scopes`` (5.1, 5.2);
    - an ``enabled`` task must have a non-empty ``prompt_final`` (5.4), while a
      disabled task may leave it empty (5.5);
    - every requested scope has at least one ``enabled`` task (5.3).
    """

    issues: list[PlanValidationIssue] = []
    requested = set(plan.requested_scopes)

    # requested_scopes must be normalized: supported, lowercase, no duplicates (4.4).
    seen_requested: set[str] = set()
    for scope in plan.requested_scopes:
        if scope not in _SUPPORTED_SCOPE_SET:
            issues.append(
                PlanValidationIssue(
                    code="unsupported_requested_scope",
                    message=(
                        f"requested_scopes contains unsupported or non-normalized "
                        f"scope '{scope}'."
                    ),
                    task_id=None,
                )
            )
        if scope in seen_requested:
            issues.append(
                PlanValidationIssue(
                    code="duplicate_requested_scope",
                    message=f"requested_scopes contains duplicate scope '{scope}'.",
                    task_id=None,
                )
            )
        seen_requested.add(scope)

    seen_ids: set[str] = set()
    seen_subject_scope: set[tuple[str, str]] = set()
    for task in plan.tasks:
        if task.task_id in seen_ids:
            issues.append(
                PlanValidationIssue(
                    code="duplicate_task_id",
                    message=f"Duplicate task_id '{task.task_id}' in plan.",
                    task_id=task.task_id,
                )
            )
        seen_ids.add(task.task_id)

        expected_task_id = make_task_id(task.subject_id, task.scope)
        if task.task_id != expected_task_id:
            issues.append(
                PlanValidationIssue(
                    code="malformed_task_id",
                    message=(
                        f"task_id '{task.task_id}' must equal subject_id + '.' + "
                        f"scope ('{expected_task_id}')."
                    ),
                    task_id=task.task_id,
                )
            )

        subject_scope = (task.subject_id, task.scope)
        if subject_scope in seen_subject_scope:
            issues.append(
                PlanValidationIssue(
                    code="duplicate_subject_scope",
                    message=(
                        f"Duplicate (subject_id, scope) pair "
                        f"('{task.subject_id}', '{task.scope}') in plan."
                    ),
                    task_id=task.task_id,
                )
            )
        seen_subject_scope.add(subject_scope)

        if task.scope not in requested:
            issues.append(
                PlanValidationIssue(
                    code="scope_not_requested",
                    message=(
                        f"Task '{task.task_id}' has scope '{task.scope}' which is "
                        "not in requested_scopes."
                    ),
                    task_id=task.task_id,
                )
            )

        if task.enabled and not task.prompt_final.strip():
            issues.append(
                PlanValidationIssue(
                    code="empty_prompt_final",
                    message=(
                        f"Enabled task '{task.task_id}' has an empty prompt_final."
                    ),
                    task_id=task.task_id,
                )
            )

    enabled_scopes = {task.scope for task in plan.tasks if task.enabled}
    for scope in plan.requested_scopes:
        if scope not in enabled_scopes:
            issues.append(
                PlanValidationIssue(
                    code="missing_enabled_task",
                    message=(
                        f"Requested scope '{scope}' has no enabled task."
                    ),
                    task_id=None,
                )
            )

    return tuple(issues)
