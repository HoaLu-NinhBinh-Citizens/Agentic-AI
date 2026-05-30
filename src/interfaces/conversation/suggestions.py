"""
Interactive suggestion handler with user confirmation flow.
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class ConfirmationState(Enum):
    AWAITING_CONFIRMATION = "awaiting"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    AUTO = "auto"


@dataclass
class FixConfirmation:
    """Pending fix confirmation."""
    finding_id: str
    file_path: str
    line: int
    old_code: str
    new_code: str
    risk: str
    state: ConfirmationState = ConfirmationState.AWAITING_CONFIRMATION
    user_response: Optional[str] = None


class SuggestionHandler:
    """
    Handles user responses to suggestions.
    Implements confirmation flow for risky fixes.
    """

    def __init__(self):
        self._pending_confirmations: dict[str, FixConfirmation] = {}

    async def suggest_fix(
        self,
        finding: dict,
        options: list[dict]
    ) -> FixConfirmation:
        """Present fix options and request confirmation if needed."""
        finding_id = finding.get("id", f"{finding.get("file_path")}:{finding.get("line")}")

        if not options:
            raise ValueError("No fix options available")

        best = max(options, key=lambda o: o.get("confidence", 0))

        risk = best.get("risk", "MEDIUM")

        if risk in ["HIGH", "CRITICAL"]:
            confirmation = FixConfirmation(
                finding_id=finding_id,
                file_path=finding.get("file_path", ""),
                line=finding.get("line", 0),
                old_code=finding.get("old_code", ""),
                new_code=best.get("new_code", ""),
                risk=risk,
                state=ConfirmationState.AWAITING_CONFIRMATION
            )
            self._pending_confirmations[finding_id] = confirmation
            return confirmation

        confirmation = FixConfirmation(
            finding_id=finding_id,
            file_path=finding.get("file_path", ""),
            line=finding.get("line", 0),
            old_code=finding.get("old_code", ""),
            new_code=best.get("new_code", ""),
            risk=risk,
            state=ConfirmationState.AUTO
        )
        return confirmation

    async def confirm(self, finding_id: str, response: str) -> bool:
        """Process user confirmation response."""
        if finding_id not in self._pending_confirmations:
            return False

        confirmation = self._pending_confirmations[finding_id]

        response_lower = response.lower()

        if response_lower in ["yes", "y", "apply", "confirm", "ok", "đồng ý", "có"]:
            confirmation.state = ConfirmationState.CONFIRMED
            return True
        elif response_lower in ["no", "n", "reject", "cancel", "không", "hủy"]:
            confirmation.state = ConfirmationState.REJECTED
            return True
        elif response_lower in ["auto", "auto-apply", "auto"]:
            confirmation.state = ConfirmationState.AUTO
            return True

        return False

    def get_pending(self) -> list[FixConfirmation]:
        """Get all pending confirmations."""
        return [
            c for c in self._pending_confirmations.values()
            if c.state == ConfirmationState.AWAITING_CONFIRMATION
        ]

    def clear_pending(self, finding_id: str):
        """Clear a pending confirmation."""
        if finding_id in self._pending_confirmations:
            del self._pending_confirmations[finding_id]
