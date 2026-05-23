"""Skill learning from successful patches (Phase 9.4).

Provides:
- Learning from approved patches
- Skill extraction and storage
- Skill retrieval and matching
- Outcome tracking over time
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SkillCategory(Enum):
    """Skill category classification."""
    PERIPHERAL = "peripheral"        # GPIO, Timer, PWM, etc.
    INTERRUPT = "interrupt"          # ISR, NVIC, priority
    MEMORY = "memory"                # Heap, stack, DMA
    COMMUNICATION = "communication"    # UART, I2C, SPI, CAN
    TIMING = "timing"               # Delays, timeouts, scheduling
    POWER = "power"                  # Low power, sleep modes
    SAFETY = "safety"                # Watchdog, assertions
    DEBUG = "debug"                  # Logging, tracing, breakpoints
    OPTIMIZATION = "optimization"     # Performance, size, power
    BUG_FIX = "bug_fix"             # Specific bug fixes


class SkillConfidence(Enum):
    """Skill confidence level."""
    LOW = "low"           # < 60% success rate
    MEDIUM = "medium"     # 60-80% success rate
    HIGH = "high"         # 80-95% success rate
    PROVEN = "proven"     # > 95% success rate, many uses


@dataclass
class SkillPattern:
    """Extracted pattern from a successful patch."""
    id: str
    name: str
    category: SkillCategory
    description: str
    
    # Pattern details
    before_code: str = ""      # Code before fix
    after_code: str = ""       # Code after fix
    diff_snippet: str = ""     # Relevant diff portion
    
    # Trigger conditions
    bug_types: list[str] = field(default_factory=list)
    file_patterns: list[str] = field(default_factory=list)
    error_keywords: list[str] = field(default_factory=list)
    
    # Metadata
    confidence: SkillConfidence = SkillConfidence.MEDIUM
    success_count: int = 0
    failure_count: int = 0
    last_used: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Provenance
    learned_from_patch_ids: list[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total
    
    @property
    def confidence_score(self) -> float:
        """Get numeric confidence score (0-1)."""
        rate = self.success_rate
        if rate >= 0.95:
            return 0.95 + (0.05 * min(1.0, self.success_count / 20))
        elif rate >= 0.80:
            return 0.80 + (0.15 * (rate - 0.80) / 0.15)
        elif rate >= 0.60:
            return 0.60 + (0.20 * (rate - 0.60) / 0.20)
        else:
            return max(0.1, rate)
    
    def compute_hash(self) -> str:
        """Compute hash for deduplication."""
        content = f"{self.category.value}:{self.name}:{self.diff_snippet[:100]}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def update_outcome(self, success: bool) -> None:
        """Update skill outcome tracking."""
        self.last_used = datetime.now()
        self.updated_at = datetime.now()
        
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        
        # Update confidence level
        rate = self.success_rate
        if rate >= 0.95 and self.success_count >= 5:
            self.confidence = SkillConfidence.PROVEN
        elif rate >= 0.80 and self.success_count >= 3:
            self.confidence = SkillConfidence.HIGH
        elif rate >= 0.60:
            self.confidence = SkillConfidence.MEDIUM
        else:
            self.confidence = SkillConfidence.LOW


@dataclass
class SkillMatch:
    """Result of matching a bug to skills."""
    skill: SkillPattern
    match_score: float  # 0.0 - 1.0
    match_reasons: list[str] = field(default_factory=list)
    applicability: str = ""  # How to apply this skill


@dataclass
class PatchOutcome:
    """Outcome of applying a skill/patch."""
    patch_id: str
    skill_id: str | None
    success: bool
    resolved_bug_types: list[str] = field(default_factory=list)
    notes: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class PatternExtractor:
    """Extract reusable patterns from patches."""
    
    def extract(
        self,
        patch_diff: str,
        bug_type: str,
        file_changed: str,
    ) -> list[SkillPattern]:
        """Extract skill patterns from a patch.
        
        Note: successful patch != always good pattern. Track outcome over time.
        """
        patterns = []
        
        # Extract code snippets
        lines = patch_diff.split("\n")
        additions = []
        deletions = []
        
        for line in lines:
            if line.startswith("+") and not line.startswith("+++"):
                additions.append(line[1:].strip())
            elif line.startswith("-") and not line.startswith("---"):
                deletions.append(line[1:].strip())
        
        # Create pattern from before/after
        if additions and deletions:
            pattern = SkillPattern(
                id=self._generate_id(),
                name=self._generate_name(bug_type, file_changed),
                category=self._categorize(bug_type, file_changed),
                description=f"Fix for {bug_type} in {file_changed}",
                before_code="\n".join(deletions[:10]),  # Limit size
                after_code="\n".join(additions[:10]),
                diff_snippet="\n".join(deletions[:5] + ["...", ""] + additions[:5]),
                bug_types=[bug_type],
                file_patterns=[file_changed],
                error_keywords=self._extract_keywords(additions),
                learned_from_patch_ids=[],
            )
            patterns.append(pattern)
        
        return patterns
    
    def _generate_id(self) -> str:
        """Generate unique pattern ID."""
        return f"skill_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def _generate_name(self, bug_type: str, file: str) -> str:
        """Generate descriptive pattern name."""
        file_base = file.split("/")[-1].split("\\")[-1].replace(".c", "").replace(".h", "")
        return f"{bug_type.replace('_', ' ').title()} Fix in {file_base}"
    
    def _categorize(self, bug_type: str, file: str) -> SkillCategory:
        """Categorize skill based on bug type and file."""
        bug_lower = bug_type.lower()
        file_lower = file.lower()
        
        # By bug type
        if "i2c" in bug_lower or "spi" in bug_lower or "uart" in bug_lower or "can" in bug_lower:
            return SkillCategory.COMMUNICATION
        elif "interrupt" in bug_lower or "nvic" in bug_lower or "irq" in bug_lower:
            return SkillCategory.INTERRUPT
        elif "heap" in bug_lower or "stack" in bug_lower or "memory" in bug_lower or "dma" in bug_lower:
            return SkillCategory.MEMORY
        elif "watchdog" in bug_lower:
            return SkillCategory.SAFETY
        elif "timeout" in bug_lower:
            return SkillCategory.TIMING
        elif "gpio" in bug_lower or "pin" in bug_lower:
            return SkillCategory.PERIPHERAL
        
        # By file name
        if "dma" in file_lower:
            return SkillCategory.MEMORY
        elif "interrupt" in file_lower or "nvic" in file_lower:
            return SkillCategory.INTERRUPT
        elif "i2c" in file_lower or "spi" in file_lower or "uart" in file_lower:
            return SkillCategory.COMMUNICATION
        elif "watchdog" in file_lower:
            return SkillCategory.SAFETY
        elif "power" in file_lower or "sleep" in file_lower:
            return SkillCategory.POWER
        
        return SkillCategory.BUG_FIX
    
    def _extract_keywords(self, code_lines: list[str]) -> list[str]:
        """Extract keywords from code for matching."""
        keywords = set()
        
        common_keywords = [
            "NULL", "pointer", "check", "validate", "error", "return",
            "if", "while", "for", "switch", "case", "break", "continue",
            "init", "config", "enable", "disable", "start", "stop",
            "timeout", "retry", "reset", "clear", "wait", "lock", "unlock",
        ]
        
        for line in code_lines:
            line_upper = line.upper()
            for kw in common_keywords:
                if kw.upper() in line_upper:
                    keywords.add(kw.lower())
        
        return list(keywords)[:20]  # Limit to 20 keywords


class SkillStore:
    """Storage for learned skills."""
    
    def __init__(self, storage_path: str = "data/skills.json") -> None:
        self._storage_path = storage_path
        self._skills: dict[str, SkillPattern] = {}
        self._outcomes: list[PatchOutcome] = []
    
    def add(self, skill: SkillPattern) -> bool:
        """Add a new skill or update existing."""
        skill_hash = skill.compute_hash()
        
        # Check for existing skill with same hash
        for existing_id, existing in self._skills.items():
            if existing.compute_hash() == skill_hash:
                # Merge with existing
                if skill.id not in existing.learned_from_patch_ids:
                    existing.learned_from_patch_ids.append(skill.id)
                existing.success_count += skill.success_count
                existing.failure_count += skill.failure_count
                logger.info("Merged skill", existing_id=existing_id, new_id=skill.id)
                return False
        
        self._skills[skill.id] = skill
        logger.info("Added new skill", skill_id=skill.id, name=skill.name)
        return True
    
    def get(self, skill_id: str) -> SkillPattern | None:
        """Get skill by ID."""
        return self._skills.get(skill_id)
    
    def find_similar(self, skill: SkillPattern) -> list[SkillPattern]:
        """Find similar existing skills."""
        similar = []
        target_hash = skill.compute_hash()
        
        for existing in self._skills.values():
            if existing.compute_hash() == target_hash:
                continue
            
            # Simple similarity based on category and keywords
            score = 0
            if existing.category == skill.category:
                score += 0.5
            
            common_keywords = set(existing.error_keywords) & set(skill.error_keywords)
            if common_keywords:
                score += 0.3 * (len(common_keywords) / max(1, min(len(existing.error_keywords), len(skill.error_keywords))))
            
            if score > 0.3:
                similar.append(existing)
        
        return similar
    
    def get_by_category(self, category: SkillCategory) -> list[SkillPattern]:
        """Get all skills in a category."""
        return [s for s in self._skills.values() if s.category == category]
    
    def get_high_confidence(self) -> list[SkillPattern]:
        """Get high confidence skills for quick retrieval."""
        return [
            s for s in self._skills.values()
            if s.confidence in (SkillConfidence.HIGH, SkillConfidence.PROVEN)
        ]
    
    def record_outcome(self, outcome: PatchOutcome) -> None:
        """Record patch outcome for learning."""
        self._outcomes.append(outcome)
        
        # Update skill if linked
        if outcome.skill_id and outcome.skill_id in self._skills:
            skill = self._skills[outcome.skill_id]
            skill.update_outcome(outcome.success)
    
    def get_outcomes(self, skill_id: str) -> list[PatchOutcome]:
        """Get all outcomes for a skill."""
        return [o for o in self._outcomes if o.skill_id == skill_id]
    
    def save(self) -> None:
        """Save skills to storage."""
        try:
            import os
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            
            data = {
                "skills": {
                    sid: {
                        **vars(skill),
                        "created_at": skill.created_at.isoformat(),
                        "updated_at": skill.updated_at.isoformat(),
                        "last_used": skill.last_used.isoformat() if skill.last_used else None,
                    }
                    for sid, skill in self._skills.items()
                },
                "outcomes": [
                    {**vars(o), "timestamp": o.timestamp.isoformat()}
                    for o in self._outcomes
                ],
            }
            
            with open(self._storage_path, "w") as f:
                json.dump(data, f, indent=2)
            
            logger.info("Saved skills", count=len(self._skills))
        except Exception as e:
            logger.error("Failed to save skills", error=str(e))
    
    def load(self) -> None:
        """Load skills from storage."""
        try:
            with open(self._storage_path) as f:
                data = json.load(f)
            
            for sid, skill_data in data.get("skills", {}).items():
                skill_data["created_at"] = datetime.fromisoformat(skill_data["created_at"])
                skill_data["updated_at"] = datetime.fromisoformat(skill_data["updated_at"])
                if skill_data.get("last_used"):
                    skill_data["last_used"] = datetime.fromisoformat(skill_data["last_used"])
                else:
                    skill_data["last_used"] = None
                skill_data["category"] = SkillCategory(skill_data["category"])
                skill_data["confidence"] = SkillConfidence(skill_data["confidence"])
                
                self._skills[sid] = SkillPattern(**skill_data)
            
            for outcome_data in data.get("outcomes", []):
                outcome_data["timestamp"] = datetime.fromisoformat(outcome_data["timestamp"])
                self._outcomes.append(PatchOutcome(**outcome_data))
            
            logger.info("Loaded skills", count=len(self._skills))
        except FileNotFoundError:
            logger.info("No skills file found, starting fresh")
        except Exception as e:
            logger.error("Failed to load skills", error=str(e))


class SkillLearner:
    """Main skill learning system.
    
    Phase 9.4: Skill learning - patch → skill store
    
    Note: Successful patch != always good pattern.
    Track outcome over time to validate patterns.
    """
    
    def __init__(self, store: SkillStore | None = None) -> None:
        self._store = store or SkillStore()
        self._extractor = PatternExtractor()
    
    def learn_from_patch(
        self,
        patch_id: str,
        patch_diff: str,
        bug_type: str,
        file_changed: str,
    ) -> list[SkillPattern]:
        """Learn skills from an approved/successful patch."""
        patterns = self._extractor.extract(patch_diff, bug_type, file_changed)
        
        for pattern in patterns:
            pattern.learned_from_patch_ids.append(patch_id)
            pattern.success_count = 1  # Initial success
            pattern.confidence = SkillConfidence.MEDIUM
            self._store.add(pattern)
        
        return patterns
    
    def match_bug(
        self,
        bug_type: str,
        error_keywords: list[str],
        file_path: str,
    ) -> list[SkillMatch]:
        """Match a bug to relevant skills."""
        matches: list[SkillMatch] = []
        
        # Search by bug type
        for skill in self._store._skills.values():
            score = 0.0
            reasons = []
            
            # Bug type match
            if bug_type.lower() in [bt.lower() for bt in skill.bug_types]:
                score += 0.4
                reasons.append(f"Bug type match: {bug_type}")
            
            # Keyword match
            skill_keywords = set(skill.error_keywords)
            bug_keywords = set(k.lower() for k in error_keywords)
            common = skill_keywords & bug_keywords
            if common:
                keyword_score = 0.3 * (len(common) / max(1, min(len(skill_keywords), len(bug_keywords))))
                score += keyword_score
                reasons.append(f"{len(common)} keywords match: {', '.join(list(common)[:5])}")
            
            # File pattern match
            if any(fp in file_path for fp in skill.file_patterns):
                score += 0.2
                reasons.append(f"File pattern match: {file_path}")
            
            # Confidence bonus
            score += skill.confidence_score * 0.1
            
            if score > 0.1:
                applicability = self._generate_applicability(skill, bug_type)
                matches.append(SkillMatch(
                    skill=skill,
                    match_score=min(1.0, score),
                    match_reasons=reasons,
                    applicability=applicability,
                ))
        
        # Sort by score
        matches.sort(key=lambda m: m.match_score, reverse=True)
        return matches[:10]  # Top 10 matches
    
    def _generate_applicability(self, skill: SkillPattern, bug_type: str) -> str:
        """Generate guidance on how to apply the skill."""
        lines = [
            f"To fix {bug_type}, consider this pattern:",
            "",
            "Before:",
            f"  {skill.before_code[:200]}...",
            "",
            "After:",
            f"  {skill.after_code[:200]}...",
            "",
            f"Confidence: {skill.confidence.value} ({skill.success_rate:.0%} success rate)",
        ]
        return "\n".join(lines)
    
    def record_patch_outcome(
        self,
        patch_id: str,
        skill_id: str,
        success: bool,
        notes: str = "",
    ) -> None:
        """Record outcome of applying a skill.
        
        Track outcomes over time to validate patterns.
        """
        outcome = PatchOutcome(
            patch_id=patch_id,
            skill_id=skill_id,
            success=success,
            notes=notes,
        )
        self._store.record_outcome(outcome)
        logger.info("Recorded patch outcome", patch_id=patch_id, skill_id=skill_id, success=success)
    
    def get_skill_recommendations(self, bug_type: str) -> list[SkillPattern]:
        """Get recommended skills for a bug type."""
        high_confidence = self._store.get_high_confidence()
        matching = [s for s in high_confidence if bug_type.lower() in [bt.lower() for bt in s.bug_types]]
        
        # Sort by confidence and usage
        matching.sort(key=lambda s: (s.confidence_score, s.success_count), reverse=True)
        return matching[:5]
    
    def save(self) -> None:
        """Persist learned skills."""
        self._store.save()
    
    def load(self) -> None:
        """Load persisted skills."""
        self._store.load()


# Global singleton
_learner: SkillLearner | None = None


def get_skill_learner() -> SkillLearner:
    """Get global skill learner instance."""
    global _learner
    if _learner is None:
        _learner = SkillLearner()
        _learner.load()
    return _learner


# CLI for testing
if __name__ == "__main__":
    learner = get_skill_learner()
    
    # Simulate learning from a patch
    sample_diff = """
--- a/src/drivers/uart.c
+++ b/src/drivers/uart.c
@@ -10,7 +10,12 @@
 
 int uart_send(uint8_t *data, size_t len) {
-    if (data == NULL) return -1;
+    if (data == NULL) {
+        return -1;
+    }
+    if (len == 0) {
+        return 0;
+    }
     
     for (size_t i = 0; i < len; i++) {
         HAL_UART_Transmit(&huart1, &data[i], 1, 1000);
"""
    
    patterns = learner.learn_from_patch(
        patch_id="patch_001",
        patch_diff=sample_diff,
        bug_type="uart_timeout",
        file_changed="src/drivers/uart.c",
    )
    
    print(f"Learned {len(patterns)} patterns:")
    for pattern in patterns:
        print(f"\n  [{pattern.category.value}] {pattern.name}")
        print(f"    Confidence: {pattern.confidence.value} ({pattern.success_rate:.0%})")
        print(f"    Keywords: {pattern.error_keywords[:5]}")
    
    # Test matching
    matches = learner.match_bug(
        bug_type="uart_timeout",
        error_keywords=["timeout", "uart", "null", "check"],
        file_path="src/drivers/uart.c",
    )
    
    print("\n\nSkill Matches:")
    for match in matches[:3]:
        print(f"\n  {match.skill.name}: {match.match_score:.2f}")
        print(f"    Reasons: {match.match_reasons}")
