"""Plan validation use case.

Application layer (Requirement 5). Thin wrapper that runs the domain invariant
check and promotes any violations to a user-facing PlanValidationError. It does
not duplicate the validation logic.
"""

from __future__ import annotations

from prompt_detailer_router.domain.detailer_plan import DetailerPlan, validate_plan
from prompt_detailer_router.domain.errors import PlanValidationError


def validate_detailer_plan(plan: DetailerPlan) -> None:
    """Raise PlanValidationError if ``plan`` violates any business invariant."""

    issues = validate_plan(plan)
    if issues:
        raise PlanValidationError(
            "Plan violates invariants: "
            + "; ".join(issue.message for issue in issues)
        )
