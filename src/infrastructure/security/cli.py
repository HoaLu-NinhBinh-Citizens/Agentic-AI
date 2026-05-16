"""
Security Validation CLI

CLI tool for running security validation on firmware code.

Usage:
    python -m src.infrastructure.security.cli scan --file firmware.c
    python -m src.infrastructure.security.cli scan --code "strcpy(buf, input)"
    python -m src.infrastructure.security.cli check --action flash_erase
"""

import argparse
import sys
from typing import Optional

from src.infrastructure.security.validator import (
    SecurityValidator,
    SecurityLevel,
    ActionCategory,
)


def scan_code(code: str, verbose: bool = False) -> int:
    """Scan code for security issues."""
    validator = SecurityValidator()
    result = validator.validate_firmware_patch(code)

    print("\n" + "=" * 60)
    print("SECURITY VALIDATION RESULTS")
    print("=" * 60)

    level_icon = {
        SecurityLevel.SAFE: "[OK]",
        SecurityLevel.CAUTION: "[WARN]",
        SecurityLevel.DANGEROUS: "[DANGER]",
        SecurityLevel.BLOCKED: "[BLOCKED]",
    }

    print(f"\nStatus: {level_icon.get(result.level, '?')} {result.level.value.upper()}")
    print(f"Allowed: {'Yes' if result.allowed else 'No'}")

    if result.reason:
        print(f"Reason: {result.reason}")

    if result.findings:
        print(f"\nFindings ({len(result.findings)}):")

        # Group by severity
        errors = [f for f in result.findings if f.severity == "error"]
        warnings = [f for f in result.findings if f.severity == "warning"]

        if errors:
            print(f"\n  Errors ({len(errors)}):")
            for f in errors[:10]:
                print(f"    [!] [{f.rule_id}] {f.message}")
                if verbose and f.cwe_id:
                    print(f"       CWE: {f.cwe_id}")
                if verbose and f.remediation:
                    print(f"       Fix: {f.remediation}")

        if warnings:
            print(f"\n  Warnings ({len(warnings)}):")
            for f in warnings[:10]:
                print(f"    [-] [{f.rule_id}] {f.message}")

        if len(result.findings) > 20:
            print(f"\n  ... and {len(result.findings) - 20} more findings")

    print("\n" + "=" * 60)

    return 0 if result.allowed else 1


def scan_file(filepath: str, verbose: bool = False) -> int:
    """Scan a file for security issues."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            code = f.read()
        print(f"Scanning: {filepath}")
        return scan_code(code, verbose)
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        return 1
    except Exception as e:
        print(f"Error reading file: {e}")
        return 1


def check_action(action: str, verbose: bool = False) -> int:
    """Check if an action is permitted."""
    try:
        action_enum = ActionCategory(action)
    except ValueError:
        print(f"Error: Unknown action '{action}'")
        print(f"Available actions: {[a.value for a in ActionCategory]}")
        return 1

    validator = SecurityValidator()
    permitted = validator.check_permission(action_enum)

    print("\n" + "=" * 60)
    print("ACTION PERMISSION CHECK")
    print("=" * 60)
    print(f"\nAction: {action_enum.value}")
    print(f"Permitted: {'[YES]' if permitted else '[NO]'}")

    if not permitted:
        print("\nNote: This action requires explicit confirmation before execution")

    print("\n" + "=" * 60)

    return 0 if permitted else 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AI_SUPPORT Security Validation CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan code for security issues")
    scan_parser.add_argument("--code", help="Code to scan")
    scan_parser.add_argument("--file", help="File to scan")
    scan_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # Check command
    check_parser = subparsers.add_parser("check", help="Check action permission")
    check_parser.add_argument("--action", required=True, help="Action category to check")
    check_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # List command
    list_parser = subparsers.add_parser("list", help="List available security checks")
    list_parser.add_argument("--category", choices=["vulnerabilities", "actions", "all"],
                           default="all", help="Category to list")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "scan":
            if args.code:
                return scan_code(args.code, args.verbose)
            elif args.file:
                return scan_file(args.file, args.verbose)
            else:
                print("Error: Either --code or --file is required")
                return 1

        elif args.command == "check":
            return check_action(args.action, args.verbose)

        elif args.command == "list":
            from src.infrastructure.security.validator import DANGEROUS_PATTERNS, DANGEROUS_ACTIONS

            if args.category in ("vulnerabilities", "all"):
                print("\nVulnerability Checks:")
                print("-" * 40)
                for rule_id, data in DANGEROUS_PATTERNS.items():
                    cwe = data.get("cwe", "N/A")
                    print(f"  {rule_id}: {data['message']} (CWE-{cwe})")

            if args.category in ("actions", "all"):
                print("\nDangerous Action Checks:")
                print("-" * 40)
                for action_id, data in DANGEROUS_ACTIONS.items():
                    requires_confirm = data.get("requires_confirmation", False)
                    confirm_str = " [REQUIRES CONFIRM]" if requires_confirm else ""
                    print(f"  {action_id}: {data['message']}{confirm_str}")

            return 0

    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
