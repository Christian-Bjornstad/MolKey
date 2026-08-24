"""Package workflow states for MolKey."""

from enum import StrEnum

# Transitions defined outside the enum to avoid enum member pollution
_TRANSITIONS: dict[str, set[str]] = {
    "Draft": {"Encrypting", "Failed"},
    "Encrypting": {"Verified", "Failed"},
    "Verified": {"Finalizing", "Failed"},
    "Finalizing": {"Ready", "Failed"},
    "Ready": {"Exported"},
    "Exported": set(),
    "Failed": set(),
}


class PackageState(StrEnum):
    """Package lifecycle states with allowed transitions."""

    DRAFT = "Draft"
    ENCRYPTING = "Encrypting"
    VERIFIED = "Verified"
    FINALIZING = "Finalizing"
    READY = "Ready"
    EXPORTED = "Exported"
    FAILED = "Failed"

    def can_transition_to(self, next_state: "PackageState") -> bool:
        """Check if transition to next_state is allowed."""
        return next_state.value in _TRANSITIONS.get(self.value, set())

    def require_transition_to(self, next_state: "PackageState") -> "PackageState":
        """Transition to next_state, raising if not allowed."""
        if not self.can_transition_to(next_state):
            from molkey.domain.errors import InvalidStateTransition

            raise InvalidStateTransition(f"Cannot transition from {self.value} to {next_state.value}")
        return next_state

    @property
    def is_active(self) -> bool:
        """States where processing is ongoing."""
        return self in (self.DRAFT, self.ENCRYPTING, self.VERIFIED, self.FINALIZING)

    @property
    def is_terminal(self) -> bool:
        """States where the package workflow has completed (success or failure)."""
        return self in (self.READY, self.EXPORTED, self.FAILED)
