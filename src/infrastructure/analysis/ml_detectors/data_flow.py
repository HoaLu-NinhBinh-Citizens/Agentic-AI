"""Data flow analysis for ML pattern detection.

Provides analysis of variable assignments and usage to track
how data moves through ML pipelines, enabling accurate
device placement and data leakage detection.

Key capabilities:
- Track variable assignments across scopes
- Find all usages of a variable
- Check device consistency for model/data pairs
- Detect suspicious data flow patterns
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import tree_sitter
import tree_sitter_languages


@dataclass
class Assignment:
    """Represents a variable assignment."""
    line: int
    assigned_value: str
    context: str  # The surrounding code context
    scope: str  # function name or "global"


@dataclass
class Usage:
    """Represents a variable usage."""
    line: int
    usage_type: str  # "read", "write", "call", "attribute"
    context: str


@dataclass
class DeviceInfo:
    """Represents device placement information."""
    variable: str
    line: int
    device: str  # "cuda", "cpu", variable name, etc.
    method: str  # ".to()", ".cuda()", ".cpu()"


@dataclass
class DataFlowResult:
    """Result of data flow analysis."""
    assignments: list[Assignment] = field(default_factory=list)
    usages: list[Usage] = field(default_factory=list)
    device_info: list[DeviceInfo] = field(default_factory=list)
    scope_chain: list[str] = field(default_factory=list)


class DataFlowAnalyzer:
    """Analyze data flow patterns in ML code.

    Tracks how variables are assigned, used, and moved between
    devices to enable accurate ML pattern detection.
    """

    def __init__(self) -> None:
        self._parser: Optional[Any] = None

    def _get_parser(self, language: str = "python") -> Any:
        """Get tree-sitter parser lazily."""
        if self._parser is None:
            try:
                self._parser = tree_sitter_languages.get_parser(language)
            except ImportError:
                return None
        return self._parser

    def track_variable(
        self,
        content: str,
        variable_name: str,
        language: str = "python",
    ) -> DataFlowResult:
        """Track all assignments and usages of a variable.

        Args:
            content: Source code content
            variable_name: Name of variable to track
            language: Programming language (default: python)

        Returns:
            DataFlowResult with all assignments, usages, and device info
        """
        result = DataFlowResult()

        parser = self._get_parser(language)
        if parser is None:
            return self._track_variable_regex(content, variable_name)

        try:
            source_bytes = content.encode("utf-8")
            tree = parser.parse(source_bytes)
            root = tree.root_node

            # Track current scope
            self._current_scope = "global"
            self._scope_chain = []

            # Walk the tree
            self._track_node(root, variable_name, result, content)

        except Exception:
            return self._track_variable_regex(content, variable_name)

        return result

    def _track_node(
        self,
        node: Any,
        var_name: str,
        result: DataFlowResult,
        content: str,
    ) -> None:
        """Recursively track variable in AST nodes."""
        # Handle scope changes
        if node.type in ("function_definition", "async_function_definition"):
            self._enter_scope(self._get_function_name(node))
            self._track_assignment(node, var_name, result, content)
            for child in node.children:
                self._track_node(child, var_name, result, content)
            self._exit_scope()
            return

        if node.type in ("class_definition",):
            self._enter_scope(self._get_class_name(node))
            for child in node.children:
                self._track_node(child, var_name, result, content)
            self._exit_scope()
            return

        # Track assignments
        if node.type == "assignment":
            self._track_assignment(node, var_name, result, content)
        elif node.type == "expression_statement":
            self._track_augmented_assignment(node, var_name, result, content)

        # Track usages
        if node.type == "identifier":
            if node.text.decode("utf-8") == var_name:
                parent = node.parent
                if parent:
                    self._track_identifier_usage(node, parent, var_name, result, content)

        # Recurse into children
        for child in node.children:
            self._track_node(child, var_name, result, content)

    def _track_assignment(
        self,
        node: Any,
        var_name: str,
        result: DataFlowResult,
        content: str,
    ) -> None:
        """Track an assignment statement."""
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")

        if left is None or right is None:
            return

        # Check for simple identifier assignment
        if left.type == "identifier":
            name = left.text.decode("utf-8")
            if name == var_name:
                line_no = node.start_point[0] + 1
                value = right.text.decode("utf-8")
                context = self._get_line_context(content, line_no)

                assignment = Assignment(
                    line=line_no,
                    assigned_value=value,
                    context=context,
                    scope=self._current_scope,
                )
                result.assignments.append(assignment)

                # Check for device assignment
                self._check_device_assignment(right, var_name, line_no, result, content)

        # Check for tuple unpacking: a, b = ...
        elif left.type == "tuple":
            for child in left.children:
                if child.type == "identifier":
                    name = child.text.decode("utf-8")
                    if name == var_name:
                        line_no = node.start_point[0] + 1
                        context = self._get_line_context(content, line_no)
                        assignment = Assignment(
                            line=line_no,
                            assigned_value=right.text.decode("utf-8"),
                            context=context,
                            scope=self._current_scope,
                        )
                        result.assignments.append(assignment)

    def _track_augmented_assignment(
        self,
        node: Any,
        var_name: str,
        result: DataFlowResult,
        content: str,
    ) -> None:
        """Track augmented assignments like +=, -=, etc."""
        if node.type == "expression_statement":
            child = node.children[0] if node.children else None
            if child and child.type in ("augmented_assignment",):
                left = child.child_by_field_name("left")
                if left and left.type == "identifier":
                    name = left.text.decode("utf-8")
                    if name == var_name:
                        line_no = child.start_point[0] + 1
                        context = self._get_line_context(content, line_no)
                        assignment = Assignment(
                            line=line_no,
                            assigned_value=child.text.decode("utf-8"),
                            context=context,
                            scope=self._current_scope,
                        )
                        result.assignments.append(assignment)

    def _track_identifier_usage(
        self,
        node: Any,
        parent: Any,
        var_name: str,
        result: DataFlowResult,
        content: str,
    ) -> None:
        """Track how a variable is used."""
        line_no = node.start_point[0] + 1

        # Determine usage type
        usage_type = "read"
        if parent.type in ("assignment", "annotated_assignment"):
            left = parent.child_by_field_name("left")
            if left:
                for child in left.children:
                    if child.type == "identifier" and child.text.decode("utf-8") == var_name:
                        usage_type = "write"
                        break

        elif parent.type == "attribute":
            usage_type = "attribute"
        elif parent.type == "call":
            usage_type = "call"

        usage = Usage(
            line=line_no,
            usage_type=usage_type,
            context=self._get_line_context(content, line_no),
        )
        result.usages.append(usage)

    def _check_device_assignment(
        self,
        node: Any,
        var_name: str,
        line_no: int,
        result: DataFlowResult,
        content: str,
    ) -> None:
        """Check if assignment involves device placement."""
        node_text = node.text.decode("utf-8")

        # Pattern: var = something.to(device)
        if ".to(" in node_text:
            device_match = re.search(r"\.to\s*\(\s*([^)]+)\s*\)", node_text)
            if device_match:
                device_info = DeviceInfo(
                    variable=var_name,
                    line=line_no,
                    device=device_match.group(1),
                    method=".to()",
                )
                result.device_info.append(device_info)

        # Pattern: var = something.cuda()
        elif ".cuda()" in node_text:
            device_info = DeviceInfo(
                variable=var_name,
                line=line_no,
                device="cuda",
                method=".cuda()",
            )
            result.device_info.append(device_info)

        # Pattern: var = something.cpu()
        elif ".cpu()" in node_text:
            device_info = DeviceInfo(
                variable=var_name,
                line=line_no,
                device="cpu",
                method=".cpu()",
            )
            result.device_info.append(device_info)

    def check_device_consistency(
        self,
        content: str,
        model_var: str,
        data_var: str,
        language: str = "python",
    ) -> list[dict[str, Any]]:
        """Check if model and data are on the same device.

        Analyzes the data flow of both variables to determine
        their device placements and detect mismatches.

        Args:
            content: Source code content
            model_var: Name of model variable
            data_var: Name of data variable
            language: Programming language

        Returns:
            List of findings for device mismatches
        """
        findings = []

        model_flow = self.track_variable(content, model_var, language)
        data_flow = self.track_variable(content, data_var, language)

        model_devices = self._extract_device_args(model_flow)
        data_devices = self._extract_device_args(data_flow)

        # Check for mismatches
        if model_devices and data_devices:
            # Get the device used closest to model usage
            model_device = self._get_primary_device(model_devices)
            data_device = self._get_primary_device(data_devices)

            if model_device and data_device and model_device != data_device:
                # Find the relevant lines
                model_line = model_devices[0].line if model_devices else 0
                data_line = data_devices[0].line if data_devices else 0

                findings.append({
                    "rule_id": "ML003",
                    "severity": "HIGH",
                    "line": max(model_line, data_line),
                    "message": (
                        f"Device mismatch detected: {model_var} uses {model_device}, "
                        f"{data_var} uses {data_device}"
                    ),
                    "confidence": 0.90,
                    "old_code": f"{model_var}.to({model_device})\n{data_var}.to({data_device})",
                    "new_code": f"{data_var} = {data_var}.to({model_var}.device)",
                    "explanation": (
                        "Model and data tensors must be on the same device. "
                        "Use model.device or torch.device to ensure consistency."
                    ),
                    "model_device": model_device,
                    "data_device": data_device,
                    "model_line": model_line,
                    "data_line": data_line,
                })

        return findings

    def _extract_device_args(
        self,
        flow: DataFlowResult,
    ) -> list[DeviceInfo]:
        """Extract device arguments from data flow result."""
        return flow.device_info

    def _get_primary_device(self, devices: list[DeviceInfo]) -> Optional[str]:
        """Get the primary device used for a variable."""
        if not devices:
            return None
        # Return the last device assignment (most recent)
        return devices[-1].device

    def find_data_leakage_patterns(
        self,
        content: str,
        language: str = "python",
    ) -> list[dict[str, Any]]:
        """Find potential data leakage patterns in ML pipelines.

        Detects:
        - Scaler fit before train_test_split
        - Encoder fit on full dataset
        - Preprocessing before split
        """
        findings = []
        lines = content.split("\n")

        # Scaler/encoder class patterns
        scaler_classes = "|".join([
            "StandardScaler", "MinMaxScaler", "RobustScaler", "MaxAbsScaler",
            "LabelEncoder", "OneHotEncoder", "OrdinalEncoder",
        ])

        # Step 1: Find scaler variable assignments
        scaler_assign_pattern = re.compile(
            rf"(\w+)\s*=\s*({scaler_classes})\s*\("
        )
        scaler_vars: dict[str, int] = {}  # var_name -> line

        for i, line in enumerate(lines, 1):
            match = scaler_assign_pattern.search(line)
            if match:
                scaler_vars[match.group(1)] = i

        # Step 2: Find .fit() calls on these variables
        fit_pattern = re.compile(r"\.fit\s*\(")
        scaler_fits: dict[int, str] = {}  # line -> var_name

        for i, line in enumerate(lines, 1):
            if fit_pattern.search(line):
                # Check if this line references any scaler variable
                for var_name in scaler_vars:
                    if var_name in line:
                        scaler_fits[i] = var_name
                        break

        # Step 3: Find train_test_split
        split_pattern = re.compile(r"train_test_split\s*\(")
        split_lines: list[int] = []

        for i, line in enumerate(lines, 1):
            if split_pattern.search(line):
                split_lines.append(i)

        if not split_lines:
            return findings

        first_split = min(split_lines)

        # Step 4: Check if any scaler fit is before split
        for fit_line, var_name in scaler_fits.items():
            if fit_line < first_split:
                findings.append({
                    "rule_id": "ML001",
                    "severity": "CRITICAL",
                    "line": fit_line,
                    "message": f"Potential data leakage: {var_name}.fit() before train_test_split",
                    "confidence": 0.88,
                    "old_code": lines[fit_line - 1].strip(),
                    "new_code": f"{var_name}.fit_transform(X_train)  # Fit only on training data",
                    "explanation": (
                        "Fitting on all data before splitting leaks test statistics "
                        "into training. Always fit on training data only."
                    ),
                })

        return findings

    def _enter_scope(self, scope_name: str) -> None:
        """Enter a new scope (function/class)."""
        self._scope_chain.append(scope_name)
        self._current_scope = ".".join(self._scope_chain)

    def _exit_scope(self) -> None:
        """Exit the current scope."""
        if self._scope_chain:
            self._scope_chain.pop()
        self._current_scope = ".".join(self._scope_chain) if self._scope_chain else "global"

    def _get_function_name(self, node: Any) -> str:
        """Get function name from node."""
        name = node.child_by_field_name("name")
        if name:
            return name.text.decode("utf-8")
        return "anonymous"

    def _get_class_name(self, node: Any) -> str:
        """Get class name from node."""
        name = node.child_by_field_name("name")
        if name:
            return name.text.decode("utf-8")
        return "AnonymousClass"

    def _get_line_context(
        self,
        content: str,
        line_no: int,
        context_lines: int = 1,
    ) -> str:
        """Get surrounding context for a line."""
        lines = content.split("\n")
        start = max(0, line_no - 1 - context_lines)
        end = min(len(lines), line_no + context_lines)
        return "\n".join(lines[start:end])

    def _track_variable_regex(
        self,
        content: str,
        variable_name: str,
    ) -> DataFlowResult:
        """Regex-based fallback for tracking variables."""
        result = DataFlowResult()
        lines = content.split("\n")

        # Pattern for assignments
        assign_pattern = re.compile(
            rf"^{variable_name}\s*=\s*(.+)$"
        )

        # Pattern for usages
        usage_pattern = re.compile(
            rf"\b{variable_name}\b"
        )

        for i, line in enumerate(lines, 1):
            # Check assignment
            match = assign_pattern.match(line.strip())
            if match:
                assignment = Assignment(
                    line=i,
                    assigned_value=match.group(1),
                    context=line.strip(),
                    scope="global",
                )
                result.assignments.append(assignment)

                # Check for device methods
                if ".to(" in line:
                    dev_match = re.search(r"\.to\s*\(\s*([^)]+)\s*\)", line)
                    if dev_match:
                        result.device_info.append(DeviceInfo(
                            variable=variable_name,
                            line=i,
                            device=dev_match.group(1),
                            method=".to()",
                        ))
                elif ".cuda()" in line:
                    result.device_info.append(DeviceInfo(
                        variable=variable_name,
                        line=i,
                        device="cuda",
                        method=".cuda()",
                    ))

            # Check usage
            for match in usage_pattern.finditer(line):
                # Skip if this is an assignment (already handled)
                if match.start() == 0 and "=" in line[:match.end() + 1]:
                    continue
                usage = Usage(
                    line=i,
                    usage_type="read",
                    context=line.strip(),
                )
                result.usages.append(usage)

        return result
