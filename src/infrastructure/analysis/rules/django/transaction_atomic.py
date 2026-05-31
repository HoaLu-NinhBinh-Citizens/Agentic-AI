"""Django missing transaction.atomic rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class TransactionAtomicRule:
    """Detect database operations missing @transaction.atomic decorator.

    Critical database operations should be wrapped in transactions
    to ensure data consistency.
    """

    rule_id: str = "DJANGO009"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        transaction_patterns = [
            (r'@transaction\.atomic', "transaction.atomic decorator"),
            (r'with\s+transaction\.atomic\s*\(', "transaction.atomic context manager"),
            (r'from django\.db import transaction', "Transaction import"),
        ]

        critical_operations = [
            (r'\.create\s*\(', "Model.create() operation"),
            (r'\.save\s*\(', "Model.save() operation"),
            (r'\.update\s*\(', "QuerySet.update() operation"),
            (r'\.delete\s*\(', "QuerySet.delete() operation"),
            (r'get_or_create', "get_or_create() operation"),
            (r'update_or_create', "update_or_create() operation"),
            (r'bulk_create', "bulk_create() operation"),
            (r'bulk_update', "bulk_update() operation"),
        ]

        mutation_keywords = [
            'create', 'update', 'delete', 'save', 'register',
            'purchase', 'transfer', 'payment', 'checkout', 'submit',
        ]

        is_view = any(p in file_path.lower() for p in ['view', 'views', 'service'])
        has_django = 'django' in content.lower() or 'from django' in content

        if not (is_view or has_django):
            return findings

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if re.search(r'def\s+\w+\s*\(.*request', line):
                func_name_match = re.search(r'def\s+(\w+)\s*\(', line)
                if not func_name_match:
                    continue

                func_name = func_name_match.group(1)
                next_lines = '\n'.join(lines[i:min(i+50, len(lines))])

                has_transaction = any(re.search(p, next_lines) for p in transaction_patterns)
                has_critical = any(re.search(p, next_lines) for p in critical_operations)
                is_mutation = any(kw in func_name.lower() for kw in mutation_keywords)

                if (has_critical or is_mutation) and not has_transaction:
                    if not any(re.search(r'@atomic', next_lines) for _ in [1]):
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Database operations in {func_name}() may lack transaction",
                            "explanation": "Critical database operations should be wrapped in @transaction.atomic "
                                           "to ensure data consistency.",
                            "fix": "Add @transaction.atomic decorator or use: "
                                   "with transaction.atomic(): ...",
                        })

        return findings
