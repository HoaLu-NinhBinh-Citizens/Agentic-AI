import json
from datetime import datetime
from pathlib import Path
from typing import Dict


class HumanReviewAudit:
    """Append-only audit log for human review overrides."""

    ALLOWED_SCOPES = {"kb", "firmware", "kicad", "cross"}
    CRITICAL_FIELDS = (
        "voltage",
        "current",
        "pinout",
        "pin_mapping",
        "pin",
        "footprint",
        "package",
        "power_supply",
        "power",
        "protocol",
        "wiring",
    )

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = Path(workspace_root).resolve()
        self.audit_path = self.workspace_root / "AI_support" / "data" / "review" / "human_overrides.jsonl"

    def record_override(self, payload: Dict) -> Dict:
        required = ("reviewer", "scope", "field_path", "reason")
        missing = [field for field in required if not str(payload.get(field, "")).strip()]
        if missing:
            return {"status": "failed", "errors": [f"missing {field}" for field in missing]}
        scope = str(payload.get("scope", "")).strip()
        if scope not in self.ALLOWED_SCOPES:
            return {
                "status": "failed",
                "errors": [f"invalid scope: {scope}; expected one of {sorted(self.ALLOWED_SCOPES)}"],
            }
        critical_field = self.is_critical_field(scope, str(payload.get("field_path", "")))
        if critical_field:
            errors = []
            if not str(payload.get("citation_or_attachment", "")).strip():
                errors.append("critical hardware override requires citation_or_attachment")
            if not bool(payload.get("human_approved", False)):
                errors.append("critical hardware override requires human_approved=true")
            if errors:
                return {"status": "failed", "errors": errors}
        record = {
            "override_id": payload.get("override_id") or f"override_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "reviewer": payload["reviewer"],
            "scope": scope,
            "field_path": payload["field_path"],
            "old_value": payload.get("old_value"),
            "new_value": payload.get("new_value"),
            "reason": payload["reason"],
            "citation_or_attachment": payload.get("citation_or_attachment", ""),
            "critical_field": critical_field,
            "human_approved": bool(payload.get("human_approved", False)),
            "expires": payload.get("expires", "never"),
        }
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"status": "recorded", "path": str(self.audit_path), "record": record}

    def list_overrides(self):
        if not self.audit_path.exists():
            return []
        return [json.loads(line) for line in self.audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def is_critical_field(self, scope: str, field_path: str) -> bool:
        lowered = f"{scope}.{field_path}".lower()
        return any(term in lowered for term in self.CRITICAL_FIELDS)
