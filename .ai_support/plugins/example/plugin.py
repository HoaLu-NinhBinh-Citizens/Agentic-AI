"""Example plugin for AI_SUPPORT.

This plugin demonstrates how to create custom rules and hooks.
"""

from typing import Any, Optional


def register() -> dict:
    """Plugin entry point - called when plugin is loaded.

    Returns:
        Plugin metadata dictionary
    """
    print("Example plugin loaded!")
    return {
        "name": "example-plugin",
        "version": "1.0.0",
        "description": "Example plugin for AI_SUPPORT",
    }


class ExampleRule:
    """Example custom rule implemented by plugin.

    This rule detects TODO comments without proper descriptions.
    """

    rule_id = "EXAMPLE001"
    severity = "WARNING"

    @staticmethod
    def detect(content: str, file_path: str) -> list[dict]:
        """Detect TODOs without explanations.

        Args:
            content: Source code content
            file_path: Path to the file

        Returns:
            List of finding dictionaries
        """
        findings = []

        for i, line in enumerate(content.split('\n'), 1):
            # Detect TODO without question mark (no description)
            if 'TODO' in line and '?' not in line and 'TODO:' not in line:
                findings.append({
                    'rule_id': ExampleRule.rule_id,
                    'severity': ExampleRule.severity,
                    'file': file_path,
                    'line': i,
                    'message': 'TODO without description',
                    'explanation': 'TODOs should have clear descriptions explaining what needs to be done.',
                })

        return findings


def on_finding_found(finding: Optional[dict]) -> Optional[dict]:
    """Hook called for each finding.

    This hook can modify or filter findings before they're reported.

    Args:
        finding: The finding dictionary from rule detection

    Returns:
        Modified finding, or None to skip
    """
    if finding is None:
        return None

    # Example: Add plugin source to finding
    finding['source'] = 'example-plugin'

    # Example: Upgrade severity for certain findings
    if 'TODO' in str(finding.get('message', '')):
        finding['plugin_modified'] = True

    return finding


def on_review_start(context: dict) -> dict:
    """Hook called before review starts.

    Args:
        context: Review context dictionary

    Returns:
        Modified context
    """
    print(f"Example plugin: Review starting for {context.get('workspace', 'unknown')}")
    context['example_plugin_active'] = True
    return context


def on_review_complete(results: dict) -> dict:
    """Hook called after review completes.

    Args:
        results: Review results dictionary

    Returns:
        Modified results
    """
    print(f"Example plugin: Review complete with {len(results.get('findings', []))} findings")
    results['example_plugin_processed'] = True
    return results


def get_custom_rules() -> list:
    """Get custom rules implemented by this plugin.

    Returns:
        List of rule classes
    """
    return [ExampleRule]
