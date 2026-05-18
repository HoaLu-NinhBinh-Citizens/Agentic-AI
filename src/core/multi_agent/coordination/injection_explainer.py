"""
Prompt Injection Explainer.

Provides explanation for prompt injection detection.
Returns detection type, score, and matched patterns.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class InjectionExplanation:
    """Explanation of injection detection."""
    detected: bool
    explanation: Dict[str, Any]
    confidence: float
    matched_patterns: List[str]
    detection_type: str  # "regex", "ml", "heuristic"


class InjectionExplainer:
    """
    Prompt injection detection with explainability.
    
    Features:
    - Regex-based detection
    - ML-based detection (simulated)
    - Heuristic detection
    - Detailed explanations
    
    Detection Types:
    - regex: Pattern-based detection
    - ml: ML model detection (simulated)
    - heuristic: Rule-based detection
    """
    
    # Common injection patterns
    INJECTION_PATTERNS = [
        # Direct instruction override
        r"ignore\s+(previous|all|prior)",
        r"(disregard|dismiss|forget)\s+(previous|all|prior)",
        r"(forget|ignore|disregard)\s+instructions",
        r"(you\s+are\s+now|act\s+as|pretend\s+you\s+are)",
        
        # Role manipulation
        r"(system|admin|developer)\s*:",
        r"(developer|admin|system)\s*mode",
        r"(jailbreak|bypass)",
        
        # Prompt extraction
        r"(reveal|show|tell)\s+(me\s+)?your\s+(system\s+)?prompt",
        r"(what|show).*(instructions?|rules?|guidelines?)",
        
        # Command injection
        r"(sudo|exec|eval|executes?)\s*\(",
        r"```system",
        r"<system>",
        
        # Leaky delimiters
        r"\[INST\].*\[/INST\]",
        r"{{User}}|{{System}}",
        r"<\|user\|>|<\|system\|>",
        
        # Encoding tricks
        r"(base64|utf-?8|hex)\s*:\s*[A-Za-z0-9+/=]",
        r"\\u[0-9a-f]{4}",
        
        # Social engineering
        r"(urgent|immediately|emergency).*(ignore|bypass)",
        r"(as\s+a\s+(security|developer|admin))",
    ]
    
    # High-risk patterns (more severe)
    HIGH_RISK_PATTERNS = [
        r"(sudo|exec|eval)\s*\(",
        r"jailbreak",
        r"(system|admin)\s*:\s*{",
        r"(reveal|show)\s+(me\s+)?your\s+system\s+prompt",
    ]
    
    def __init__(
        self,
        enable_regex: bool = True,
        enable_ml: bool = True,
        enable_heuristic: bool = True,
        confidence_threshold: float = 0.7,
    ):
        self.enable_regex = enable_regex
        self.enable_ml = enable_ml
        self.enable_heuristic = enable_heuristic
        self.confidence_threshold = confidence_threshold
        
        # Compile patterns
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS
        ]
        self._compiled_high_risk = [
            re.compile(p, re.IGNORECASE) for p in self.HIGH_RISK_PATTERNS
        ]
        
        # Detection history
        self._detection_history: List[InjectionExplanation] = []
    
    async def detect_with_explanation(
        self,
        prompt: str,
    ) -> InjectionExplanation:
        """
        Detect injection with detailed explanation.
        
        Returns:
        - detected: bool
        - explanation: dict with type, pattern, score
        - confidence: float 0-1
        - matched_patterns: list of matched patterns
        - detection_type: "regex", "ml", or "heuristic"
        """
        matched_patterns: List[str] = []
        detection_type = "none"
        confidence = 0.0
        explanations: List[str] = []
        
        # Regex detection
        if self.enable_regex:
            regex_results = self._detect_regex(prompt)
            if regex_results["detected"]:
                matched_patterns.extend(regex_results["matched"])
                confidence = max(confidence, regex_results["confidence"])
                detection_type = "regex"
                explanations.append(f"Matched {len(regex_results['matched'])} regex patterns")
        
        # ML detection (simulated)
        if self.enable_ml:
            ml_results = await self._detect_ml(prompt)
            if ml_results["detected"]:
                confidence = max(confidence, ml_results["confidence"])
                detection_type = "ml"
                explanations.append(f"ML model score: {ml_results['score']:.2f}")
        
        # Heuristic detection
        if self.enable_heuristic:
            heuristic_results = self._detect_heuristic(prompt)
            if heuristic_results["detected"]:
                confidence = max(confidence, heuristic_results["confidence"])
                detection_type = "heuristic"
                explanations.append(f"Heuristic: {heuristic_results['reason']}")
        
        # Determine final result
        detected = confidence >= self.confidence_threshold
        
        explanation = {
            "type": detection_type,
            "confidence": confidence,
            "matched_patterns": matched_patterns,
            "explanations": explanations,
            "prompt_length": len(prompt),
            "risk_level": self._get_risk_level(matched_patterns),
        }
        
        result = InjectionExplanation(
            detected=detected,
            explanation=explanation,
            confidence=confidence,
            matched_patterns=matched_patterns,
            detection_type=detection_type if detected else "none",
        )
        
        self._detection_history.append(result)
        return result
    
    def _detect_regex(self, prompt: str) -> Dict[str, Any]:
        """Regex-based detection."""
        matched = []
        
        # Check high-risk patterns first
        for i, pattern in enumerate(self._compiled_high_risk):
            if pattern.search(prompt):
                matched.append(f"HIGH_RISK_{i}:{self.HIGH_RISK_PATTERNS[i]}")
        
        # Check all patterns
        for i, pattern in enumerate(self._compiled_patterns):
            if pattern.search(prompt):
                pattern_name = self.INJECTION_PATTERNS[i]
                if pattern_name not in matched:
                    matched.append(f"PATTERN_{i}:{pattern_name}")
        
        confidence = 0.0
        if matched:
            high_risk_count = sum(1 for m in matched if "HIGH_RISK" in m)
            if high_risk_count > 0:
                confidence = 0.95
            elif len(matched) >= 2:
                confidence = 0.85
            else:
                confidence = 0.75
        
        return {
            "detected": len(matched) > 0,
            "matched": matched,
            "confidence": confidence,
        }
    
    async def _detect_ml(self, prompt: str) -> Dict[str, Any]:
        """
        ML-based detection (simulated).
        
        In production, this would call an ML model.
        """
        # Simulate ML detection
        score = 0.0
        
        # Heuristics to simulate ML behavior
        # Length-based
        if len(prompt) > 500:
            score += 0.1
        
        # Contains encoded content
        if any(pattern in prompt.lower() for pattern in ["base64", "utf-8", "hex"]):
            score += 0.3
        
        # Multiple newlines with instructions
        if prompt.count("\n\n") > 2:
            score += 0.15
        
        # Contains brackets that might be delimiters
        if "[" in prompt and "]" in prompt:
            if "{[" in prompt or "[INST]" in prompt.upper():
                score += 0.25
        
        # Suspicious repetition
        words = prompt.lower().split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.5:
                score += 0.2
        
        return {
            "detected": score >= 0.5,
            "score": min(score, 1.0),
            "confidence": min(score, 1.0),
        }
    
    def _detect_heuristic(self, prompt: str) -> Dict[str, Any]:
        """Heuristic-based detection."""
        reasons = []
        risk_score = 0.0
        
        # Check for instruction override phrases
        override_phrases = [
            "ignore previous",
            "disregard all",
            "forget prior",
            "ignore instructions",
        ]
        for phrase in override_phrases:
            if phrase in prompt.lower():
                reasons.append(f"override_phrase: {phrase}")
                risk_score = max(risk_score, 0.9)
        
        # Check for role confusion
        role_phrases = [
            "you are now",
            "act as",
            "pretend you are",
            "system role",
        ]
        for phrase in role_phrases:
            if phrase in prompt.lower():
                reasons.append(f"role_manipulation: {phrase}")
                risk_score = max(risk_score, 0.7)
        
        # Check for encoding attempts
        encoding_indicators = ["\\u", "0x", "base64:", "utf-8:"]
        for indicator in encoding_indicators:
            if indicator in prompt.lower():
                reasons.append(f"encoding_attempt: {indicator}")
                risk_score = max(risk_score, 0.8)
        
        # Check for unusual delimiters
        unusual_delimiters = ["[INST]", "[/INST]", "{{", "}}", "<|", "|>"]
        for delim in unusual_delimiters:
            if delim in prompt:
                reasons.append(f"unusual_delimiter: {delim}")
                risk_score = max(risk_score, 0.6)
        
        return {
            "detected": len(reasons) > 0,
            "confidence": risk_score,
            "reason": "; ".join(reasons) if reasons else "none",
        }
    
    def _get_risk_level(self, matched_patterns: List[str]) -> str:
        """Determine overall risk level."""
        high_risk = sum(1 for p in matched_patterns if "HIGH_RISK" in p)
        
        if high_risk >= 2:
            return "CRITICAL"
        elif high_risk >= 1:
            return "HIGH"
        elif len(matched_patterns) >= 3:
            return "MEDIUM"
        elif len(matched_patterns) >= 1:
            return "LOW"
        return "NONE"
    
    def get_detection_stats(self) -> Dict[str, Any]:
        """Get detection statistics."""
        if not self._detection_history:
            return {
                "total_checked": 0,
                "total_detected": 0,
                "detection_rate": 0.0,
            }
        
        total = len(self._detection_history)
        detected = sum(1 for r in self._detection_history if r.detected)
        
        by_type: Dict[str, int] = {}
        for result in self._detection_history:
            if result.detected:
                by_type[result.detection_type] = by_type.get(result.detection_type, 0) + 1
        
        return {
            "total_checked": total,
            "total_detected": detected,
            "detection_rate": detected / total if total > 0 else 0.0,
            "detections_by_type": by_type,
            "average_confidence": sum(r.confidence for r in self._detection_history) / total,
        }
