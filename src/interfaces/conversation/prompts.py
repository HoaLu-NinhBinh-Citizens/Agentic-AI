"""Prompt templates for conversational UX.

This module contains prompt templates used by the conversational
fix engine for tradeoff analysis, risk explanation, and fix suggestions.
"""

TRADEOFF_PROMPT = """
You are analyzing a code fix recommendation for an AI code review system.

**Issue:**
{message}

**File:** {file_path}:{line}

**Explanation:**
{explanation}

**Available Options:**
{options}

Analyze the tradeoffs between options:
1. Complexity of the change
2. Risk of breaking existing functionality
3. Maintainability impact
4. Performance implications
5. Testing requirements

Provide a concise comparison that helps developers make informed decisions.
Format your response as:
TRADEFF_COMPARISON: <your analysis>
RECOMMENDED: <option index or "skip">
REASONING: <brief reasoning>
"""

RISK_PROMPT = """
Explain the risk of applying this fix:

**Before:**
```python
{old_code}
```

**After:**
```python
{new_code}
```

**Context:** {explanation}

**File:** {file_path}:{line}
**Rule:** {rule_id}

Consider:
- What could break?
- What testing is recommended?
- How reversible is this change?
- Are there any side effects?
- Impact on related code?

Format your response as:
RISK_LEVEL: <low/medium/high/critical>
RISK_FACTORS: <list of risk factors>
TESTING: <recommended testing>
REVERSIBILITY: <how easy to undo>
"""

FIX_INTRO_PROMPT = """
You are presenting a code fix to a developer in a conversational interface.

**Issue Details:**
- Rule: {rule_id}
- Severity: {severity}
- File: {file_path}:{line}
- Message: {message}

**Current Code:**
```python
{old_code}
```

**Explanation:**
{explanation}

**Root Cause:**
{root_cause}

Generate a concise, developer-friendly introduction that:
1. Explains what the issue is
2. Shows why it's a problem
3. Suggests available fix options
4. Indicates the risk level

Keep it under 200 words. Use technical but accessible language.
"""

EXPLAIN_TRADEOFF_PROMPT = """
Compare the following fix options for a code issue:

**Issue:** {message}
**File:** {file_path}:{line}

**Option 0 - {option_0_label}:**
```python
{option_0_code}
```
{explanation_0}

**Option 1 - {option_1_label}:**
```python
{option_1_code}
```
{explanation_1}

**Option 2 - {option_2_label}:**
```python
{option_2_code}
```
{explanation_2}

Compare these options considering:
- Implementation complexity
- Performance impact
- Maintainability
- Safety/reliability
- Backward compatibility

Provide a clear comparison with a recommendation.
"""

AUTO_APPLY_PROMPT = """
Based on the following findings, determine which fixes should be auto-applied:

**Findings:**
{findings}

**Auto-apply Criteria:**
- Low risk (LOW or MEDIUM risk level)
- High confidence (>= 80%)
- Non-breaking changes
- Standard best practices

**Do NOT auto-apply:**
- HIGH or CRITICAL risk fixes
- Breaking changes
- Performance-critical code paths
- Security-sensitive areas

Format your response as a JSON list of finding indices to auto-apply:
{{"auto_apply": [0, 2, 5], "reasoning": "..."}}
"""

UNDO_PROMPT = """
To undo the fix applied at {file_path}:{line}, the original code was:

```python
{original_code}
```

Provide the exact code that should replace the current (fixed) code to restore it:
```python
{current_code}
```

Ensure the undo operation is safe and reversible.
"""

SESSION_SUMMARY_PROMPT = """
Summarize the following code review session:

**Total Issues Found:** {total}
**Applied Fixes:** {applied}
**Skipped:** {skipped}
**Critical Issues:** {critical}

**Applied Fixes:**
{applied_list}

**Skipped Fixes:**
{skipped_list}

**Next Steps:**
{next_steps}

Generate a concise summary for the developer including:
1. Overall impact of the fixes
2. Any remaining concerns
3. Recommended follow-up actions
"""

HELP_CONTEXTUAL_PROMPT = """
The user is asking for help with a specific code fix context:

**Current Finding:**
- Rule: {rule_id}
- Message: {message}
- Severity: {severity}
- File: {file_path}:{line}

**User Question:** {question}

Provide a helpful, context-specific response that addresses their question
about this particular code issue and its fix.
"""
