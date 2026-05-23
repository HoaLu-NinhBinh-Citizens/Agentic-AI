import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.core.config.agent_prompts import AGENT_MEMORY_FILE, AGENT_POLICY_FILE, GENERIC_QUERY_STOPWORDS
from src.core.memory.conflict_detector import ConflictDetector, ConflictCheckResult
from src.infrastructure.models import ExperienceEntry


class AgentMemory:
    """Persistent memory that stores lessons from previous runs."""

    CRITICAL_FIELDS = ("voltage", "current", "pinout", "footprint", "power", "protocol", "wiring")
    PROMOTABLE_LAYERS = {"project_kb", "pattern_kb", "failure_memory"}
    PROMPT_BLOCKLIST = re.compile(
        r"\b(ignore|disregard|system prompt|developer message|previous instructions?|"
        r"act as|you are now|copy this|paste this)\b",
        re.IGNORECASE,
    )

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.memory_path = self.project_root / AGENT_MEMORY_FILE
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        self._conflict_detector = ConflictDetector()

    def _load(self) -> Dict:
        if not self.memory_path.exists():
            return self.empty_memory()
        try:
            data = json.loads(self.memory_path.read_text(encoding="utf-8"))
            data.setdefault("experiences", [])
            data.setdefault("knowledge", [])
            data.setdefault("rules", [])
            data.setdefault("feedback", [])
            data.setdefault("policy_scores", {})
            data.setdefault("learning_proposals", [])
            data.setdefault("source_kb_refs", [])
            data.setdefault("project_kb", [])
            data.setdefault("pattern_kb", [])
            data.setdefault("failure_memory", [])
            data.setdefault("memory_approvals", [])
            data.setdefault("memory_versions", [])
            data.setdefault("memory_conflicts", [])
            data.setdefault("memory_compactions", [])
            if not data.get("learning_proposals") and not data.get("knowledge"):
                data["learning_proposals"] = [
                    self._proposal_from_record(record, source="legacy_migration")
                    for record in self._migrate_legacy_knowledge(data.get("experiences", []))
                ]
            return data
        except (OSError, json.JSONDecodeError):
            return self.empty_memory()

    def empty_memory(self) -> Dict:
        return {
            "experiences": [],
            "knowledge": [],
            "rules": [],
            "feedback": [],
            "policy_scores": {},
            "learning_proposals": [],
            "source_kb_refs": [],
            "project_kb": [],
            "pattern_kb": [],
            "failure_memory": [],
            "memory_approvals": [],
            "memory_versions": [],
            "memory_conflicts": [],
            "memory_compactions": [],
        }

    def save(self):
        """Save memory to disk atomically.
        
        FIX W-002: Uses fsync for durability before atomic rename.
        """
        payload = json.dumps(self.data, indent=2)
        tmp_path = self.memory_path.with_name(f"{self.memory_path.name}.tmp")
        
        # FIX: Write with fsync for crash safety
        with open(tmp_path, 'w', encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        
        os.replace(tmp_path, self.memory_path)
        logger.debug("memory_saved", path=str(self.memory_path))

    def get_recent_lessons(self, limit: int = 8) -> List[str]:
        lessons: List[str] = []
        for rule in self.data.get("rules", []):
            if rule not in lessons:
                lessons.append(rule)
            if len(lessons) >= limit:
                break
        return lessons

    def retrieve_relevant(self, task: str, build_error: str = "", review_feedback: str = "", limit: int = 4) -> List[Dict]:
        query_text = " ".join(part for part in [task, build_error, review_feedback] if str(part).strip())
        query_terms = self._tokenize(query_text)
        if not query_terms:
            return []

        scored: List[Tuple[float, Dict]] = []
        for item in self.approved_memory_items():
            if not isinstance(item, dict):
                continue
            if self._should_skip_memory_item(item):
                continue
            score = self._score_memory_item(item, query_terms, build_error=build_error, review_feedback=review_feedback)
            if score <= 0:
                continue
            scored.append((score, item))

        scored.sort(key=lambda entry: entry[0], reverse=True)
        results: List[Dict] = []
        for score, item in scored[:limit]:
            record = dict(item)
            record["score"] = round(score, 2)
            results.append(record)
        return results

    def format_for_prompt(self, items: List[Dict], max_chars: int = 1200) -> str:
        if not items:
            return "none"
        lines: List[str] = []
        for item in items[:4]:
            lines.append(
                "- phase={phase} outcome={outcome} error={error} cause={cause} fix={fix}".format(
                    phase=self._prompt_safe_text(item.get("phase", "unknown"), 60),
                    outcome=self._prompt_safe_text(item.get("outcome", "unknown"), 60),
                    error=self._prompt_safe_text(item.get("error_signature", "none"), 120),
                    cause=self._prompt_safe_text(item.get("root_cause", "unknown"), 160),
                    fix=self._prompt_safe_text(item.get("fix_strategy", "avoid repeating this failure"), 160),
                )
            )
            prevention_rules = item.get("prevention_rules", [])
            if isinstance(prevention_rules, list) and prevention_rules:
                safe_rules = [
                    self._prompt_safe_text(rule, 180)
                    for rule in prevention_rules[:2]
                    if self._prompt_safe_text(rule, 180)
                ]
                if safe_rules:
                    lines.append("  prevention: " + " | ".join(safe_rules))
        return self._compact_text("\n".join(lines), max_chars)

    def record(self, entry: ExperienceEntry):
        experiences = self.data.setdefault("experiences", [])
        experiences.append({
            "timestamp": entry.timestamp,
            "task": entry.task,
            "success": entry.success,
            "attempts": entry.attempts,
            "files_created": entry.files_created,
            "last_error": entry.last_error,
            "response_preview": entry.response_preview,
            "lessons": entry.lessons,
            "memory_records": entry.memory_records,
        })
        self.data["experiences"] = experiences[-50:]
        proposals = self.data.setdefault("learning_proposals", [])
        for record in entry.memory_records:
            if isinstance(record, dict):
                proposals.append(self._proposal_from_record(record, source="task_experience"))
        self.data["learning_proposals"] = proposals[-200:]
        self._refresh_rules()
        self.save()

    def _refresh_rules(self):
        self._update_policy_scores()
        rules: List[str] = []
        scored_rules = sorted(
            self.data.get("policy_scores", {}).items(),
            key=lambda item: item[1],
            reverse=True,
        )
        for rule, score in scored_rules:
            if score >= 2 and rule not in rules:
                rules.append(rule)
        for item in reversed(self.approved_pattern_items()):
            rule = str(item.get("rule") or item.get("new_value") or item.get("policy_proposal", "")).strip()
            if rule and rule not in rules:
                rules.append(rule)
        self.data["rules"] = rules[:12]

    def _update_policy_scores(self):
        scores: Dict[str, float] = {}
        for item in self.approved_pattern_items():
            if not isinstance(item, dict):
                continue
            rule = str(item.get("rule") or item.get("new_value") or item.get("policy_proposal", "")).strip()
            if rule:
                scores[rule] = scores.get(rule, 0.0) + float(item.get("priority", 1.0) or 1.0)
        self.data["policy_scores"] = {key: round(value, 2) for key, value in scores.items() if value > 0}

    def record_feedback(self, rating: str, note: str = "", task: str = ""):
        feedback = self.data.setdefault("feedback", [])
        safe_note = self._compact_text(note, 1200)
        feedback.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "rating": rating,
            "note": safe_note,
            "task": task.strip(),
        })
        self.data["feedback"] = feedback[-50:]
        if safe_note:
            proposals = self.data.setdefault("learning_proposals", [])
            proposals.append(self._proposal_from_feedback(rating, safe_note, task))
            self.data["learning_proposals"] = proposals[-200:]
        self._refresh_rules()
        self.save()

    def synthesize_policy(self, limit: int = 20) -> Dict:
        """Write a compact coding policy distilled from scored memory rules."""
        self._refresh_rules()
        scored_rules = sorted(
            self.data.get("policy_scores", {}).items(),
            key=lambda item: item[1],
            reverse=True,
        )[:limit]
        policy_path = self.project_root / AGENT_POLICY_FILE
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# AI Coding Policy",
            "",
            f"Generated: {datetime.now().isoformat(timespec='seconds')}",
            "",
            "## High-Confidence Rules",
        ]
        if not scored_rules:
            lines.append("- No high-confidence rules yet.")
        for rule, score in scored_rules:
            lines.append(f"- score={score}: {rule}")
        lines.extend([
            "",
            "## Current Learned Rules",
        ])
        for rule in self.data.get("rules", [])[:limit]:
            lines.append(f"- {rule}")
        policy_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {
            "path": str(policy_path),
            "rule_count": len(scored_rules),
            "rules": [{"rule": rule, "score": score} for rule, score in scored_rules],
        }

    def list_learning_proposals(self, status: str = "") -> List[Dict]:
        proposals = [item for item in self.data.get("learning_proposals", []) if isinstance(item, dict)]
        wanted = str(status).strip().upper()
        if wanted:
            proposals = [
                item for item in proposals
                if str(item.get("approval_status", "PENDING")).upper() == wanted
            ]
        return proposals

    def review_learning_proposals(self, status: str = "PENDING", limit: int = 20) -> Dict:
        proposals = self.list_learning_proposals(status=status)[:max(int(limit), 1)]
        rows: List[Dict] = []
        for proposal in proposals:
            rows.append({
                "proposal_id": proposal.get("proposal_id", ""),
                "status": proposal.get("approval_status", "PENDING"),
                "risk": proposal.get("risk_level", ""),
                "target_layer": proposal.get("target_layer", ""),
                "field": proposal.get("field", ""),
                "value": str(proposal.get("new_value", ""))[:180],
                "reason": str(proposal.get("reason", ""))[:180],
                "requires_human_approval": bool(proposal.get("requires_human_approval", False)),
                "evidence": proposal.get("evidence", {}),
            })
        return {
            "proposal_count": len(rows),
            "status_filter": status,
            "proposals": rows,
            "commands": {
                "approve": "python -m src.application.api.app.embedded_agent memory-approve <proposal_id> --reviewer <name> --reason <reason> --evidence <evidence>",
                "reject": "python -m src.application.api.app.embedded_agent memory-reject <proposal_id> --reviewer <name> --reason <reason>",
            },
        }

    def approve_learning_proposal(
        self,
        proposal_id: str,
        reviewer: str,
        reason: str,
        evidence: str = "",
        target_layer: str = "",
    ) -> Dict:
        proposal, index = self._find_learning_proposal(proposal_id)
        if proposal is None:
            return {"status": "failed", "errors": [f"proposal not found: {proposal_id}"]}
        errors = self._validate_learning_approval(proposal, reviewer, reason, evidence, target_layer)
        if errors:
            return {"status": "failed", "errors": errors, "proposal": proposal}

        layer = str(target_layer or proposal.get("target_layer", "")).strip()
        approved_at = datetime.now().isoformat(timespec="seconds")
        approved_proposal = dict(proposal)
        approved_proposal.update({
            "target_layer": layer,
            "validation_status": "VALIDATED",
            "approval_status": "APPROVED",
            "approved_for_policy": layer == "pattern_kb",
            "approved_by": reviewer.strip(),
            "approved_at": approved_at,
            "approval_reason": reason.strip(),
            "approval_evidence": evidence.strip(),
            "memory_version": int(proposal.get("memory_version", 1) or 1) + 1,
        })

        self.data["learning_proposals"][index] = approved_proposal
        promoted_item = self._promoted_memory_item(approved_proposal, layer)
        previous_item = self._find_promoted_item(layer, promoted_item)
        self._upsert_memory_item(layer, promoted_item)
        diff = self._memory_diff(previous_item, promoted_item)
        approval_record = self._approval_record(approved_proposal, "APPROVED", diff=diff)
        self.data.setdefault("memory_approvals", []).append(approval_record)
        self.data["memory_approvals"] = self.data["memory_approvals"][-200:]
        self.data.setdefault("memory_versions", []).append(self._version_record(approved_proposal, "APPROVED", diff))
        self.data["memory_versions"] = self.data["memory_versions"][-300:]
        self._refresh_rules()
        self.save()
        return {
            "status": "approved",
            "proposal_id": approved_proposal.get("proposal_id"),
            "target_layer": layer,
            "promoted_item": promoted_item,
            "approval": approval_record,
        }

    def reject_learning_proposal(self, proposal_id: str, reviewer: str, reason: str) -> Dict:
        proposal, index = self._find_learning_proposal(proposal_id)
        if proposal is None:
            return {"status": "failed", "errors": [f"proposal not found: {proposal_id}"]}
        missing = []
        if not str(reviewer).strip():
            missing.append("reviewer is required")
        if not str(reason).strip():
            missing.append("reason is required")
        if missing:
            return {"status": "failed", "errors": missing, "proposal": proposal}

        rejected = dict(proposal)
        rejected.update({
            "approval_status": "REJECTED",
            "rejected_by": reviewer.strip(),
            "rejected_at": datetime.now().isoformat(timespec="seconds"),
            "rejection_reason": reason.strip(),
            "approved_for_policy": False,
            "memory_version": int(proposal.get("memory_version", 1) or 1) + 1,
        })
        self.data["learning_proposals"][index] = rejected
        diff = self._memory_diff(proposal, rejected)
        approval_record = self._approval_record(rejected, "REJECTED", diff=diff)
        self.data.setdefault("memory_approvals", []).append(approval_record)
        self.data["memory_approvals"] = self.data["memory_approvals"][-200:]
        self.data.setdefault("memory_versions", []).append(self._version_record(rejected, "REJECTED", diff))
        self.data["memory_versions"] = self.data["memory_versions"][-300:]
        self._refresh_rules()
        self.save()
        return {"status": "rejected", "proposal_id": rejected.get("proposal_id"), "approval": approval_record}

    def detect_memory_conflicts(self) -> Dict:
        observations: Dict[str, List[Dict]] = {}
        for layer in ("source_kb_refs", "project_kb", "pattern_kb", "failure_memory"):
            for item in self.data.get(layer, []):
                if not isinstance(item, dict):
                    continue
                for observation in self._memory_observations(layer, item):
                    key = str(observation.get("field", "")).strip().lower()
                    value = self._normalize_memory_value(observation.get("value", ""))
                    if key and value:
                        observation["normalized_value"] = value
                        observations.setdefault(key, []).append(observation)

        conflicts: List[Dict] = []
        for field, items in observations.items():
            values = {}
            for item in items:
                values.setdefault(item["normalized_value"], []).append(item)
            if len(values) <= 1:
                continue
            conflicts.append({
                "field": field,
                "values": [
                    {
                        "value": value,
                        "sources": [
                            {
                                "layer": src.get("layer", ""),
                                "proposal_id": src.get("proposal_id", ""),
                                "source": src.get("source", ""),
                                "approved": src.get("approved", False),
                            }
                            for src in sources
                        ],
                    }
                    for value, sources in values.items()
                ],
                "blocking": any(field_part in field for field_part in self.CRITICAL_FIELDS),
            })
        report = {
            "valid": not any(item.get("blocking", False) for item in conflicts),
            "conflict_count": len(conflicts),
            "blocking_conflicts": sum(1 for item in conflicts if item.get("blocking", False)),
            "conflicts": conflicts,
        }
        self.data["memory_conflicts"] = conflicts
        self.save()
        return report

    def check_rule_conflicts(self, new_rule: str, context: Optional[Dict] = None) -> ConflictCheckResult:
        """
        Check if a new rule conflicts with existing rules before insertion.
        
        This is called BEFORE adding a new learning proposal to prevent
        the AI from learning contradictory rules.
        
        Args:
            new_rule: The rule to be checked
            context: Optional context (domain, scope, priority)
            
        Returns:
            ConflictCheckResult with detected conflicts
        """
        # Get all existing rules
        existing_rules = list(self.data.get("rules", []))
        
        # Also get rules from knowledge layers
        for layer in ["project_kb", "pattern_kb", "failure_memory"]:
            for item in self.data.get(layer, []):
                if isinstance(item, dict):
                    rule = item.get("rule") or item.get("new_value") or ""
                    if rule:
                        existing_rules.append(rule)

        return self._conflict_detector.check_conflicts(new_rule, existing_rules, context)

    def add_rule_with_conflict_check(
        self,
        new_rule: str,
        context: Optional[Dict] = None,
        force: bool = False,
    ) -> Dict:
        """
        Add a rule with automatic conflict detection.
        
        Args:
            new_rule: The rule to add
            context: Optional context dict
            force: If True, skip conflict check (use with caution)
            
        Returns:
            Dict with insertion result and any conflict info
        """
        if not force:
            result = self.check_rule_conflicts(new_rule, context)
            
            if result.has_conflicts and result.requires_human_review:
                return {
                    "inserted": False,
                    "reason": "conflict_detected",
                    "conflicts": [c.__dict__ for c in result.conflicts],
                    "severity": result.severity.value,
                    "recommendation": result.recommendation,
                    "requires_human_review": True,
                }
            
            # Log conflicts even if not blocking
            if result.has_conflicts:
                self.data.setdefault("memory_conflicts", []).append({
                    "timestamp": datetime.now().isoformat(),
                    "new_rule": new_rule,
                    "conflicts": [c.__dict__ for c in result.conflicts],
                    "resolution": "auto_inserted_with_notes",
                })

        # Proceed with insertion
        rules = self.data.setdefault("rules", [])
        if new_rule not in rules:
            rules.append(new_rule)
            self.data["rules"] = rules[:50]  # Keep last 50 rules
        self._refresh_rules()
        self.save()

        return {
            "inserted": True,
            "rule": new_rule,
            "conflicts_resolved": result.severity.value if not force else "skipped",
        }

    def auto_compact_if_needed(self) -> Dict:
        """
        Automatically compact memory when thresholds are exceeded.

        This should be called periodically (e.g., at startup or after task execution).
        Checks memory size against configurable thresholds and compacts if needed.

        Returns a report with compaction results, or empty dict if no compaction needed.
        """
        try:
            from src.core.config.config_loader import get_config
            cfg = get_config()
        except Exception:
            cfg = None

        def cfg_get(key: str, default):
            return cfg.get(key, default) if cfg else default

        threshold = cfg_get("memory.compaction.auto_compact_threshold", 250)
        keep_proposals = cfg_get("memory.compaction.keep_proposals", 100)
        keep_versions = cfg_get("memory.compaction.keep_versions", 300)

        proposal_count = len([p for p in self.data.get("learning_proposals", []) if isinstance(p, dict)])

        if proposal_count < threshold:
            return {}

        # Count pending proposals
        pending = len([
            p for p in self.data.get("learning_proposals", [])
            if isinstance(p, dict) and str(p.get("approval_status", "")).upper() == "PENDING"
        ])

        logger.info(
            "AgentMemory: Auto-compacting (proposals=%d threshold=%d pending=%d)",
            proposal_count,
            threshold,
            pending,
        )

        report = self.compact_memory(
            keep_proposals=keep_proposals,
            keep_versions=keep_versions,
        )
        report["auto_triggered"] = True
        report["proposals_before"] = proposal_count
        return report

    def compact_memory(self, keep_proposals: int = 100, keep_versions: int = 300) -> Dict:
        report = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "deduped": {},
            "trimmed": {},
        }
        for layer in ("project_kb", "pattern_kb", "failure_memory"):
            before = len(self.data.get(layer, []))
            self.data[layer] = self._dedupe_memory_records(self.data.get(layer, []))
            report["deduped"][layer] = before - len(self.data[layer])

        proposals = [item for item in self.data.get("learning_proposals", []) if isinstance(item, dict)]
        before_proposals = len(proposals)
        self.data["learning_proposals"] = proposals[-max(int(keep_proposals), 1):]
        report["trimmed"]["learning_proposals"] = before_proposals - len(self.data["learning_proposals"])

        versions = [item for item in self.data.get("memory_versions", []) if isinstance(item, dict)]
        before_versions = len(versions)
        self.data["memory_versions"] = versions[-max(int(keep_versions), 1):]
        report["trimmed"]["memory_versions"] = before_versions - len(self.data["memory_versions"])

        self.data.setdefault("memory_compactions", []).append(report)
        self.data["memory_compactions"] = self.data["memory_compactions"][-50:]
        self._refresh_rules()
        self.save()
        return report

    def _score_memory_item(self, item: Dict, query_terms: List[str], build_error: str = "", review_feedback: str = "") -> float:
        haystack_parts = [
            str(item.get("task", "")),
            str(item.get("phase", "")),
            str(item.get("error_signature", "")),
            str(item.get("root_cause", "")),
            str(item.get("fix_strategy", "")),
            " ".join(str(token) for token in item.get("context_terms", []) if str(token).strip()),
            " ".join(str(token) for token in item.get("prevention_rules", []) if str(token).strip()),
        ]
        haystack = " ".join(haystack_parts).lower()
        score = 0.0
        for term in query_terms:
            if term in haystack:
                score += 1.5
        if build_error and str(item.get("phase", "")) == "fix":
            score += 2.0
        if review_feedback and str(item.get("phase", "")) in {"generate", "review"}:
            score += 2.0
        if str(item.get("outcome", "")).lower() == "failure":
            score += 1.0
        if str(item.get("outcome", "")).lower() == "success":
            score += 0.5
        if str(item.get("phase", "")).lower() == "legacy":
            score -= 0.75
            if not str(item.get("error_signature", "")).strip():
                score -= 1.0
            if not str(item.get("root_cause", "")).strip() and not str(item.get("fix_strategy", "")).strip():
                score -= 1.5
        return score

    def approved_memory_items(self) -> List[Dict]:
        items: List[Dict] = []
        for layer in ("failure_memory", "project_kb", "pattern_kb", "knowledge"):
            for item in self.data.get(layer, []):
                if isinstance(item, dict) and self.is_approved(item):
                    items.append(item)
        return items

    def approved_pattern_items(self) -> List[Dict]:
        items = [
            item for item in self.data.get("pattern_kb", [])
            if isinstance(item, dict) and self.is_approved(item)
        ]
        return items

    def is_approved(self, item: Dict) -> bool:
        return (
            str(item.get("approval_status", "")).upper() == "APPROVED"
            and str(item.get("validation_status", "")).upper() == "VALIDATED"
        )

    def _proposal_from_record(self, record: Dict, source: str) -> Dict:
        field = str(record.get("phase", "memory_record") or "memory_record")
        new_value = "; ".join(str(rule).strip() for rule in record.get("prevention_rules", []) if str(rule).strip())
        if not new_value:
            new_value = str(record.get("fix_strategy", "")).strip()
        risk_level = self.classify_risk(" ".join([field, new_value, str(record.get("root_cause", ""))]))
        return {
            "proposal_id": f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "type": "failure_pattern",
            "target_layer": "project_kb" if self.is_project_specific(record) else "failure_memory",
            "field": field,
            "old_value": "",
            "new_value": new_value,
            "reason": str(record.get("root_cause", "") or record.get("error_signature", "") or "task experience"),
            "evidence": {
                "source": source,
                "task": str(record.get("task", "")),
                "evidence_paths": record.get("evidence_paths", []),
                "outcome": str(record.get("outcome", "")),
                "iteration": record.get("iteration", 0),
            },
            "confidence": "UNVERIFIED",
            "risk_level": risk_level,
            "requires_human_approval": risk_level in {"HIGH", "MEDIUM"},
            "validation_status": "UNVERIFIED",
            "approval_status": "PENDING",
            "memory_version": 1,
            "source_record": record,
        }

    def _proposal_from_feedback(self, rating: str, note: str, task: str = "") -> Dict:
        risk_level = self.classify_risk(note)
        return {
            "proposal_id": f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "type": "human_feedback",
            "target_layer": "project_kb" if task else "pattern_kb",
            "field": "policy_feedback",
            "old_value": "",
            "new_value": note.strip(),
            "reason": f"user feedback rating={rating}",
            "evidence": {"source": "user_feedback", "task": task.strip()},
            "confidence": "UNVERIFIED",
            "risk_level": risk_level,
            "requires_human_approval": True,
            "validation_status": "UNVERIFIED",
            "approval_status": "PENDING",
            "memory_version": 1,
        }

    def classify_risk(self, text: str) -> str:
        lowered = str(text).lower()
        if any(field in lowered for field in self.CRITICAL_FIELDS):
            return "HIGH"
        if any(token in lowered for token in ("driver", "register", "schema", "compile")):
            return "MEDIUM"
        return "LOW"

    def is_project_specific(self, record: Dict) -> bool:
        text = " ".join([
            str(record.get("task", "")),
            " ".join(str(path) for path in record.get("evidence_paths", [])),
            " ".join(str(term) for term in record.get("context_terms", [])),
        ]).lower()
        return any(token in text for token in ("stm32", "esp32", "rp2040", "nrf", "uart", "i2c", "spi", "can"))

    def _find_learning_proposal(self, proposal_id: str) -> Tuple[Dict | None, int]:
        wanted = str(proposal_id).strip()
        for index, proposal in enumerate(self.data.get("learning_proposals", [])):
            if isinstance(proposal, dict) and str(proposal.get("proposal_id", "")).strip() == wanted:
                return proposal, index
        return None, -1

    def _validate_learning_approval(self, proposal: Dict, reviewer: str, reason: str, evidence: str, target_layer: str) -> List[str]:
        errors: List[str] = []
        if str(proposal.get("approval_status", "PENDING")).upper() == "APPROVED":
            errors.append("proposal is already approved")
        if str(proposal.get("approval_status", "PENDING")).upper() == "REJECTED":
            errors.append("proposal is already rejected")
        if not str(reviewer).strip():
            errors.append("reviewer is required")
        if not str(reason).strip():
            errors.append("reason is required")
        layer = str(target_layer or proposal.get("target_layer", "")).strip()
        if layer not in self.PROMOTABLE_LAYERS:
            errors.append(f"invalid target_layer: {layer}; expected one of {sorted(self.PROMOTABLE_LAYERS)}")
        required = ("proposal_id", "type", "target_layer", "field", "new_value", "reason", "evidence", "risk_level")
        for field in required:
            if field not in proposal:
                errors.append(f"proposal missing {field}")
        risk_level = str(proposal.get("risk_level", "")).upper()
        requires_human = bool(proposal.get("requires_human_approval", False))
        if (risk_level == "HIGH" or requires_human) and not str(evidence).strip():
            errors.append("high/approval-required proposal needs approval evidence")
        return errors

    def _promoted_memory_item(self, proposal: Dict, layer: str) -> Dict:
        source_record = proposal.get("source_record") if isinstance(proposal.get("source_record"), dict) else {}
        if layer in {"project_kb", "failure_memory"} and source_record:
            item = dict(source_record)
        else:
            item = {
                "phase": str(proposal.get("field", "policy")),
                "outcome": "approved",
                "error_signature": "",
                "root_cause": str(proposal.get("reason", "")),
                "fix_strategy": str(proposal.get("new_value", "")),
                "context_terms": self._tokenize(" ".join([
                    str(proposal.get("field", "")),
                    str(proposal.get("new_value", "")),
                    str(proposal.get("reason", "")),
                ])),
                "prevention_rules": [str(proposal.get("new_value", "")).strip()] if str(proposal.get("new_value", "")).strip() else [],
                "evidence_paths": [],
            }
        item.update({
            "proposal_id": proposal.get("proposal_id"),
            "type": proposal.get("type"),
            "target_layer": layer,
            "field": proposal.get("field"),
            "rule": str(proposal.get("new_value", "")).strip(),
            "validation_status": "VALIDATED",
            "approval_status": "APPROVED",
            "approved_by": proposal.get("approved_by"),
            "approved_at": proposal.get("approved_at"),
            "approval_reason": proposal.get("approval_reason"),
            "approval_evidence": proposal.get("approval_evidence"),
            "memory_version": proposal.get("memory_version", 1),
        })
        return item

    def _upsert_memory_item(self, layer: str, item: Dict):
        records = self.data.setdefault(layer, [])
        proposal_id = str(item.get("proposal_id", "")).strip()
        rule = str(item.get("rule", "")).strip()
        for index, existing in enumerate(records):
            if not isinstance(existing, dict):
                continue
            same_proposal = proposal_id and str(existing.get("proposal_id", "")).strip() == proposal_id
            same_rule = rule and str(existing.get("rule", "")).strip() == rule
            if same_proposal or same_rule:
                records[index] = item
                return
        records.append(item)
        self.data[layer] = records[-200:]

    def _find_promoted_item(self, layer: str, item: Dict) -> Dict | None:
        proposal_id = str(item.get("proposal_id", "")).strip()
        rule = str(item.get("rule", "")).strip()
        for existing in self.data.get(layer, []):
            if not isinstance(existing, dict):
                continue
            if proposal_id and str(existing.get("proposal_id", "")).strip() == proposal_id:
                return dict(existing)
            if rule and str(existing.get("rule", "")).strip() == rule:
                return dict(existing)
        return None

    def _memory_diff(self, old: Dict | None, new: Dict) -> Dict:
        old = old or {}
        keys = sorted(set(old.keys()) | set(new.keys()))
        changes = []
        for key in keys:
            old_value = old.get(key)
            new_value = new.get(key)
            if old_value != new_value:
                changes.append({"field": key, "old": old_value, "new": new_value})
        return {"change_count": len(changes), "changes": changes[:50]}

    def _version_record(self, proposal: Dict, decision: str, diff: Dict) -> Dict:
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "proposal_id": proposal.get("proposal_id"),
            "decision": decision,
            "target_layer": proposal.get("target_layer"),
            "memory_version": proposal.get("memory_version", 1),
            "reviewer": proposal.get("approved_by") or proposal.get("rejected_by"),
            "reason": proposal.get("approval_reason") or proposal.get("rejection_reason"),
            "diff": diff,
        }

    def _approval_record(self, proposal: Dict, decision: str, diff: Dict | None = None) -> Dict:
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "proposal_id": proposal.get("proposal_id"),
            "decision": decision,
            "target_layer": proposal.get("target_layer"),
            "reviewer": proposal.get("approved_by") or proposal.get("rejected_by"),
            "reason": self._compact_text(proposal.get("approval_reason") or proposal.get("rejection_reason"), 600),
            "evidence": self._compact_text(proposal.get("approval_evidence", ""), 1200),
            "risk_level": proposal.get("risk_level"),
            "memory_version": proposal.get("memory_version", 1),
            "diff": diff or {"change_count": 0, "changes": []},
        }

    def _memory_observations(self, layer: str, item: Dict) -> List[Dict]:
        observations: List[Dict] = []
        source = str(item.get("source_file") or item.get("kb_id") or item.get("proposal_id") or item.get("field") or layer)
        base = {
            "layer": layer,
            "proposal_id": item.get("proposal_id", ""),
            "source": source,
            "approved": self.is_approved(item) or bool(item.get("approved", False)),
        }
        field = str(item.get("field", "")).strip()
        value = item.get("rule") or item.get("new_value") or item.get("value")
        if field and value not in (None, ""):
            observations.append({**base, "field": field, "value": value})

        component = item.get("component") if isinstance(item.get("component"), dict) else {}
        if component.get("part_number"):
            observations.append({**base, "field": "component.part_number", "value": component.get("part_number")})
        electrical = item.get("electrical") if isinstance(item.get("electrical"), dict) else {}
        voltage = electrical.get("operating_voltage") if isinstance(electrical.get("operating_voltage"), dict) else {}
        for key in ("min", "typ", "max"):
            if voltage.get(key) is not None:
                observations.append({**base, "field": f"electrical.operating_voltage.{key}", "value": voltage.get(key)})
        package = item.get("package") if isinstance(item.get("package"), dict) else {}
        for key in ("name", "recommended_land_pattern"):
            if package.get(key):
                observations.append({**base, "field": f"package.{key}", "value": package.get(key)})
        for pin in item.get("pinout", []) if isinstance(item.get("pinout", []), list) else []:
            if isinstance(pin, dict) and pin.get("pin_name"):
                observations.append({**base, "field": f"pinout.{pin.get('pin_name')}", "value": pin.get("pin_number") or pin.get("pin_name")})
        return observations

    def _normalize_memory_value(self, value) -> str:
        return re.sub(r"\s+", " ", str(value).strip().lower())

    def _compact_text(self, text, max_chars: int, marker: str = " ...[TRUNCATED]... ") -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(normalized) <= max_chars:
            return normalized
        if max_chars <= len(marker) + 2:
            return normalized[:max_chars].strip()
        head = max((max_chars - len(marker)) // 2, 1)
        tail = max(max_chars - len(marker) - head, 1)
        return f"{normalized[:head].rstrip()}{marker}{normalized[-tail:].lstrip()}"

    def _prompt_safe_text(self, text, max_chars: int) -> str:
        safe_lines: List[str] = []
        for line in str(text or "").splitlines():
            stripped = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", line).strip()
            if not stripped or self.PROMPT_BLOCKLIST.search(stripped):
                continue
            safe_lines.append(stripped)
        return self._compact_text(" ".join(safe_lines), max_chars)

    def _dedupe_memory_records(self, records: List[Dict]) -> List[Dict]:
        deduped: Dict[str, Dict] = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            key = self._memory_record_key(record)
            current = deduped.get(key)
            if current is None:
                deduped[key] = dict(record)
                deduped[key]["duplicate_count"] = int(record.get("duplicate_count", 1) or 1)
                continue
            existing_version = int(current.get("memory_version", 0) or 0)
            new_version = int(record.get("memory_version", 0) or 0)
            winner = dict(record if new_version >= existing_version else current)
            winner["duplicate_count"] = int(current.get("duplicate_count", 1) or 1) + int(record.get("duplicate_count", 1) or 1)
            deduped[key] = winner
        return list(deduped.values())

    def _memory_record_key(self, record: Dict) -> str:
        for field in ("proposal_id", "rule", "field"):
            value = str(record.get(field, "")).strip().lower()
            if value:
                return f"{field}:{value}"
        return self._normalize_memory_value(json.dumps(record, sort_keys=True))

    def _should_skip_memory_item(self, item: Dict) -> bool:
        phase = str(item.get("phase", "")).strip().lower()
        error_signature = str(item.get("error_signature", "")).strip()
        root_cause = str(item.get("root_cause", "")).strip()
        fix_strategy = str(item.get("fix_strategy", "")).strip()
        prevention_rules = [str(rule).strip() for rule in item.get("prevention_rules", []) if str(rule).strip()]
        evidence_paths = [str(path).strip() for path in item.get("evidence_paths", []) if str(path).strip()]
        context_terms = [str(term).strip() for term in item.get("context_terms", []) if str(term).strip()]
        if phase != "legacy":
            return False
        has_specific_content = any([error_signature, root_cause, fix_strategy, evidence_paths, context_terms])
        if has_specific_content:
            return False
        generic_prevention = all(
            rule.lower() == "on failure, preserve response preview and error summary for the next prompt."
            for rule in prevention_rules
        ) if prevention_rules else True
        return generic_prevention

    def _tokenize(self, text: str) -> List[str]:
        terms: List[str] = []
        seen = set()
        for token in re.findall(r"[a-z0-9_]+", text.lower()):
            if len(token) < 3 or token in GENERIC_QUERY_STOPWORDS or token in seen:
                continue
            seen.add(token)
            terms.append(token)
        return terms[:24]

    def _normalize_signature(self, text: str) -> str:
        tokens = self._tokenize(text)
        return " ".join(tokens[:12])

    def _migrate_legacy_knowledge(self, experiences: List[Dict]) -> List[Dict]:
        migrated: List[Dict] = []
        for item in experiences:
            if not isinstance(item, dict):
                continue
            task = str(item.get("task", "")).strip()
            last_error = str(item.get("last_error", "")).strip()
            response_preview = str(item.get("response_preview", "")).strip()
            lessons = item.get("lessons", [])
            if not isinstance(lessons, list):
                lessons = []
            legacy_focus = self._extract_legacy_failure_focus(lessons)
            normalized_error = last_error if last_error and "failed after" not in last_error.lower() else legacy_focus or response_preview
            context_terms = self._tokenize(" ".join([task, last_error, response_preview, " ".join(str(lesson) for lesson in lessons)]))
            migrated.append({
                "timestamp": str(item.get("timestamp", "")).strip(),
                "task": task,
                "iteration": int(item.get("attempts", 0) or 0),
                "phase": "legacy",
                "outcome": "success" if bool(item.get("success", False)) else "failure",
                "error_signature": self._normalize_signature(normalized_error),
                "root_cause": (legacy_focus or normalized_error)[:300],
                "fix_strategy": response_preview[:300],
                "context_terms": context_terms,
                "prevention_rules": [str(lesson).strip() for lesson in lessons if str(lesson).strip()][:4],
                "evidence_paths": [str(path).strip() for path in item.get("files_created", []) if str(path).strip()][:4],
            })
        return migrated[-200:]

    def _extract_legacy_failure_focus(self, lessons: List[str]) -> str:
        for lesson in lessons:
            text = str(lesson).strip()
            if text.startswith("Reviewer focus:"):
                return text.split(":", 1)[1].strip()
        return ""

