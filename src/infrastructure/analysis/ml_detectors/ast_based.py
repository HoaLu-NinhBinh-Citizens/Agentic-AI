"""AST-based ML-specific detectors using tree-sitter queries.

Provides accurate ML bug detection by analyzing the actual AST structure
rather than relying on fragile regex patterns. Each detector understands
the semantic context of ML operations.

Key improvements over regex:
- ML001: Checks train_test_split ordering, not just .fit() presence
- ML002: Validates loss function context (multi-class vs multi-label)
- ML003: Tracks actual model/data flow for device placement
- ML004: Full function scope analysis for no_grad detection
- ML005: Detects all random seed patterns across frameworks
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer

logger = logging.getLogger(__name__)

# Confidence levels for detection methods
AST_CONFIDENCE_BOOST = 0.15
CONTEXT_CLARITY_BOOST = 0.10
MULTIPLE_INDICATOR_BOOST = 0.05

# ML scaler class patterns
SCALER_CLASSES = frozenset({
    "StandardScaler", "MinMaxScaler", "RobustScaler", "MaxAbsScaler",
    "Normalizer", "PowerTransformer", "QuantileTransformer",
})

# Encoder classes
ENCODER_CLASSES = frozenset({
    "LabelEncoder", "OneHotEncoder", "OrdinalEncoder",
    "TargetEncoder", "CategoryEncoder",
})

# Random seed patterns by framework
SEED_FUNCTIONS = {
    "torch": ["manual_seed", "cuda.manual_seed", "cuda.manual_seed_all"],
    "numpy": ["seed"],
    "python": ["seed"],
    "tensorflow": ["set_random_seed", "set_seed"],
    "random": ["seed"],
}


class MLDetectorAST:
    """ML-specific detectors using tree-sitter AST analysis.

    Uses tree-sitter queries to analyze actual code structure,
    providing much higher accuracy than regex-based detection.
    """

    def __init__(self, indexer: "SafeTreeSitterIndexer") -> None:
        self.indexer = indexer

    def detect_ml001_data_leakage(
        self,
        file_path: Path,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect data leakage: scaler.fit() before train_test_split.

        AST-based approach:
        1. Find all train_test_split calls and their line numbers
        2. Find all .fit() calls and their line numbers
        3. Check if any .fit() appears BEFORE train_test_split in same scope
        4. Validate it's actually a scaler/encoder context
        """
        findings = []

        if language != "python":
            return self._detect_ml001_regex_fallback(content, file_path)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            source_bytes = content.encode("utf-8")
            tree = parser.parse(source_bytes)
            root = tree.root_node

            # Find train_test_split calls
            split_calls = self._find_function_calls(root, "train_test_split")
            first_split_line = min((line for _, line in split_calls), default=0)

            # Find all .fit() calls
            fit_calls = self._find_attribute_calls(root, "fit")

            # Find scaler instances by variable assignment
            scaler_vars = self._find_scaler_variables(root)

            for call_node, line_no in fit_calls:
                # Check if fit() is in a scaler context
                if not self._is_scaler_fit_context(call_node, scaler_vars):
                    continue

                # Check if this fit() appears before train_test_split
                if first_split_line > 0 and line_no < first_split_line:
                    confidence = self._calculate_leakage_confidence(
                        content, line_no, first_split_line
                    )
                    findings.append({
                        "rule_id": "ML001",
                        "severity": "CRITICAL",
                        "line": line_no,
                        "message": "Potential data leakage: scaler.fit() called before train_test_split",
                        "confidence": confidence,
                        "old_code": self._get_code_snippet(content, line_no),
                        "new_code": "scaler.fit_transform(X_train)  # Fit only on training data",
                        "explanation": (
                            "Fitting the scaler on all data before splitting leaks "
                            "statistics from the test set into training. Use "
                            "fit_transform() on training data and transform() on test data."
                        ),
                        "detection_method": "ast",
                    })

        except ImportError:
            logger.debug("tree-sitter not available, using regex fallback")
            return self._detect_ml001_regex_fallback(content, file_path)
        except Exception as e:
            logger.warning("AST analysis failed, falling back to regex", error=str(e))
            return self._detect_ml001_regex_fallback(content, file_path)

        return findings

    def detect_ml002_cross_entropy(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect CrossEntropyLoss used incorrectly for multi-label scenarios.

        AST-based approach:
        1. Find CrossEntropyLoss instantiations
        2. Check if multi-label indicators are present (sigmoid, BCE patterns)
        3. Validate the classification type context
        """
        findings = []

        if language != "python":
            return self._detect_ml002_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            source_bytes = content.encode("utf-8")
            tree = parser.parse(source_bytes)
            root = tree.root_node

            # Find CrossEntropyLoss usage
            ce_loss_nodes = self._find_ce_loss_usage(root)
            # Find multi-label indicators
            multi_label_indicators = self._find_multi_label_indicators(root)

            for node, line_no in ce_loss_nodes:
                if multi_label_indicators:
                    findings.append({
                        "rule_id": "ML002",
                        "severity": "CRITICAL",
                        "line": line_no,
                        "message": "CrossEntropyLoss used with multi-label indicators",
                        "confidence": 0.92,
                        "old_code": self._get_code_snippet(content, line_no),
                        "new_code": "nn.BCEWithLogitsLoss()  # For multi-label classification",
                        "explanation": (
                            "CrossEntropyLoss is for single-label multi-class classification. "
                            "For multi-label (multiple labels per sample), use BCEWithLogitsLoss."
                        ),
                        "detection_method": "ast",
                    })

        except ImportError:
            return self._detect_ml002_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML002", error=str(e))
            return self._detect_ml002_regex_fallback(content)

        return findings

    def detect_ml003_device_mismatch(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect model.to(device) vs data.to(device) device mismatch.

        AST-based approach:
        1. Find model variable assignments
        2. Track .to(device) calls for model and data separately
        3. Compare device arguments for consistency
        """
        findings = []

        if language != "python":
            return self._detect_ml003_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            source_bytes = content.encode("utf-8")
            tree = parser.parse(source_bytes)
            root = tree.root_node

            # Find model and data .to() calls
            to_calls = self._find_to_device_calls(root)

            # Group by variable
            model_devices: dict[str, tuple[int, str]] = {}
            data_devices: dict[str, tuple[int, str]] = {}

            for var_name, line_no, device_arg in to_calls:
                if self._is_model_variable(var_name):
                    model_devices[var_name] = (line_no, device_arg)
                elif self._is_data_variable(var_name):
                    data_devices[var_name] = (line_no, device_arg)

            # Check for mismatches
            for model_var, (model_line, model_dev) in model_devices.items():
                for data_var, (data_line, data_dev) in data_devices.items():
                    if model_dev != data_dev and model_dev != "" and data_dev != "":
                        findings.append({
                            "rule_id": "ML003",
                            "severity": "HIGH",
                            "line": max(model_line, data_line),
                            "message": f"Device mismatch: {model_var} on {model_dev}, {data_var} on {data_dev}",
                            "confidence": 0.88,
                            "old_code": f"{model_var}.to({model_dev})\n{data_var}.to({data_dev})",
                            "new_code": f"{data_var} = {data_var}.to({model_var}.device)",
                            "explanation": (
                                "Model and data must be on the same device. "
                                "Use model.device to get the correct device for data."
                            ),
                            "detection_method": "ast",
                        })

        except ImportError:
            return self._detect_ml003_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML003", error=str(e))
            return self._detect_ml003_regex_fallback(content)

        return findings

    def detect_ml004_missing_no_grad(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect inference code missing torch.no_grad().

        AST-based approach:
        1. Find function definitions that look like inference (predict, evaluate, inference)
        2. Check if they contain model() calls
        3. Verify no_grad context wraps those calls
        """
        findings = []

        if language != "python":
            return self._detect_ml004_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            source_bytes = content.encode("utf-8")
            tree = parser.parse(source_bytes)
            root = tree.root_node

            # Find potential inference functions
            inference_functions = self._find_inference_functions(root)

            for func_node, func_name, line_no in inference_functions:
                # Check if function has model calls without no_grad
                has_model_call = self._function_has_model_call(func_node)
                has_no_grad = self._function_has_no_grad_context(func_node)

                if has_model_call and not has_no_grad:
                    findings.append({
                        "rule_id": "ML004",
                        "severity": "HIGH",
                        "line": line_no,
                        "message": f"Function '{func_name}' performs inference without torch.no_grad()",
                        "confidence": 0.85,
                        "old_code": self._get_code_snippet(content, line_no, lines=15),
                        "new_code": "with torch.no_grad():\n    output = model(input)",
                        "explanation": (
                            "Inference should be wrapped in torch.no_grad() to disable "
                            "gradient computation and prevent memory leaks."
                        ),
                        "detection_method": "ast",
                    })

        except ImportError:
            return self._detect_ml004_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML004", error=str(e))
            return self._detect_ml004_regex_fallback(content)

        return findings

    def detect_ml005_missing_seed(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect missing random seed for reproducibility.

        AST-based approach:
        1. Find train/fit/main functions
        2. Check for seed setting across all frameworks (torch, numpy, random)
        3. Flag if no seeds are set in training functions
        """
        findings = []

        if language != "python":
            return self._detect_ml005_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            source_bytes = content.encode("utf-8")
            tree = parser.parse(source_bytes)
            root = tree.root_node

            # Find training functions
            training_functions = self._find_training_functions(root)

            for func_node, func_name, line_no in training_functions:
                has_seed = self._function_has_seed_setting(func_node)

                if not has_seed:
                    # Check if parent scope has seed (function might use args.seed)
                    has_seed_in_parent = self._check_seed_from_args(content, line_no)

                    if not has_seed_in_parent:
                        findings.append({
                            "rule_id": "ML005",
                            "severity": "MEDIUM",
                            "line": line_no,
                            "message": f"Training function '{func_name}' missing random seed",
                            "confidence": 0.78,
                            "old_code": self._get_code_snippet(content, line_no, lines=10),
                            "new_code": (
                                "def seed_everything(seed: int = 42):\n"
                                "    random.seed(seed)\n"
                                "    np.random.seed(seed)\n"
                                "    torch.manual_seed(seed)\n"
                                "    torch.cuda.manual_seed_all(seed)"
                            ),
                            "explanation": (
                                "Set random seeds for all frameworks to ensure reproducibility. "
                                "Include torch, numpy, and python random."
                            ),
                            "detection_method": "ast",
                        })

        except ImportError:
            return self._detect_ml005_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML005", error=str(e))
            return self._detect_ml005_regex_fallback(content)

        return findings

    # ─── Helper Methods ────────────────────────────────────────────────────────

    def _find_function_calls(
        self,
        root: Any,
        func_name: str,
    ) -> list[tuple[Any, int]]:
        """Find all calls to a specific function by name."""
        calls = []
        query_text = f'(call function: (identifier) @id (#eq? @id "{func_name}"))'

        try:
            import tree_sitter
            query = tree_sitter.Query(root.tree().root_node if hasattr(root, 'tree') else root, query_text)
            # Simple node traversal as fallback
            self._traverse_for_calls(root, func_name, calls)
        except Exception:
            self._traverse_for_calls(root, func_name, calls)

        return calls

    def _traverse_for_calls(
        self,
        node: Any,
        func_name: str,
        calls: list[tuple[Any, int]],
    ) -> None:
        """Traverse AST to find function calls."""
        if node.type == "call":
            func = node.child_by_field_name("function")
            if func and func.type == "identifier":
                if func.text.decode("utf-8") == func_name:
                    line_no = node.start_point[0] + 1
                    calls.append((node, line_no))

        for child in node.children:
            self._traverse_for_calls(child, func_name, calls)

    def _find_attribute_calls(
        self,
        root: Any,
        method_name: str,
    ) -> list[tuple[Any, int]]:
        """Find all attribute.method() calls."""
        calls = []

        def traverse(node: Any) -> None:
            if node.type == "call":
                func = node.child_by_field_name("function")
                if func and func.type == "attribute":
                    attr_name = func.child_by_field_name("attribute")
                    if attr_name and attr_name.text.decode("utf-8") == method_name:
                        line_no = node.start_point[0] + 1
                        calls.append((node, line_no))
            for child in node.children:
                traverse(child)

        traverse(root)
        return calls

    def _find_scaler_variables(self, root: Any) -> set[str]:
        """Find variables assigned to scaler classes."""
        scalers = set()

        def traverse(node: Any) -> None:
            if node.type == "assignment":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left and left.type == "identifier":
                    var_name = left.text.decode("utf-8")
                    if right and right.type == "call":
                        func = right.child_by_field_name("function")
                        if func:
                            func_name = func.text.decode("utf-8").split(".")[-1]
                            if func_name in SCALER_CLASSES:
                                scalers.add(var_name)
            for child in node.children:
                traverse(child)

        traverse(root)
        return scalers

    def _is_scaler_fit_context(
        self,
        call_node: Any,
        scaler_vars: set[str],
    ) -> bool:
        """Check if the fit() call is on a scaler variable."""
        func = call_node.child_by_field_name("function")
        if func and func.type == "attribute":
            obj = func.child_by_field_name("object")
            if obj and obj.type == "identifier":
                return obj.text.decode("utf-8") in scaler_vars
        return False

    def _find_ce_loss_usage(
        self,
        root: Any,
    ) -> list[tuple[Any, int]]:
        """Find CrossEntropyLoss instantiations."""
        ce_uses = []

        def traverse(node: Any) -> None:
            if node.type == "call":
                func = node.child_by_field_name("function")
                if func:
                    func_text = func.text.decode("utf-8")
                    if "CrossEntropyLoss" in func_text:
                        line_no = node.start_point[0] + 1
                        ce_uses.append((node, line_no))
            for child in node.children:
                traverse(child)

        traverse(root)
        return ce_uses

    def _find_multi_label_indicators(self, root: Any) -> bool:
        """Check for multi-label classification patterns."""
        content_sample = self._get_node_text(root)
        patterns = [
            r"sigmoid",
            r"BCEWithLogitsLoss",
            r"BCELoss",
            r"multi.?label",
            r"binary_cross_entropy",
        ]
        return any(re.search(p, content_sample, re.IGNORECASE) for p in patterns)

    def _find_to_device_calls(
        self,
        root: Any,
    ) -> list[tuple[str, int, str]]:
        """Find all .to(device) calls with variable and device name."""
        to_calls = []

        def traverse(node: Any) -> None:
            # Handle assignments: var = ... .to(device)
            if node.type == "assignment":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left and right and left.type == "identifier":
                    var_name = left.text.decode("utf-8")
                    # Look for .to() call in the right side
                    _find_to_in_expr(right, var_name)

            # Handle variable annotations: var: Type = ... .to(device)
            elif node.type == "annotated_assignment":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left and right:
                    var_name = left.text.decode("utf-8")
                    _find_to_in_expr(right, var_name)

            for child in node.children:
                traverse(child)

        def _find_to_in_expr(node: Any, var_name: str) -> None:
            """Recursively search for .to() calls in an expression."""
            if node.type == "call":
                func = node.child_by_field_name("function")
                if func and func.type == "attribute":
                    attr = func.child_by_field_name("attribute")
                    if attr and attr.text.decode("utf-8") == "to":
                        # Get the object (what .to() is called on)
                        obj = func.child_by_field_name("object")
                        # Get device argument
                        args = node.child_by_field_name("arguments")
                        device_arg = "cuda"
                        if args:
                            device_arg = args.text.decode("utf-8")
                        line_no = node.start_point[0] + 1
                        to_calls.append((var_name, line_no, device_arg))
                        return  # Found it, no need to search deeper
            # Recurse into children
            for child in node.children:
                _find_to_in_expr(child, var_name)

        traverse(root)
        return to_calls

    def _is_model_variable(self, var_name: str) -> bool:
        """Heuristic to identify model variables."""
        model_patterns = ["model", "net", "network", "classifier", "encoder", "decoder"]
        return any(p in var_name.lower() for p in model_patterns)

    def _is_data_variable(self, var_name: str) -> bool:
        """Heuristic to identify data variables."""
        data_patterns = ["x", "y", "data", "input", "batch", "loader", "dataset"]
        return any(p in var_name.lower() for p in data_patterns)

    def _find_inference_functions(
        self,
        root: Any,
    ) -> list[tuple[Any, str, int]]:
        """Find functions that look like inference functions."""
        inference_funcs = []
        inference_names = {"predict", "evaluate", "inference", "forward", "run"}

        def traverse(node: Any) -> None:
            if node.type in ("function_definition", "async_function_definition"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8")
                    if name in inference_names or "eval" in name.lower():
                        line_no = node.start_point[0] + 1
                        inference_funcs.append((node, name, line_no))
            for child in node.children:
                traverse(child)

        traverse(root)
        return inference_funcs

    def _function_has_model_call(self, func_node: Any) -> bool:
        """Check if function contains model() calls."""
        found_model = False

        def traverse(node: Any) -> None:
            nonlocal found_model
            if found_model:
                return
            if node.type == "call":
                func = node.child_by_field_name("function")
                if func:
                    # Check if calling a variable named 'model' or something.model
                    if func.type == "identifier":
                        func_text = func.text.decode("utf-8")
                        if func_text == "model":
                            found_model = True
                            return
                    elif func.type == "attribute":
                        func_text = func.text.decode("utf-8")
                        if ".model" in func_text or func_text.endswith("model"):
                            found_model = True
                            return
            for child in node.children:
                traverse(child)

        traverse(func_node)
        return found_model

    def _function_has_no_grad_context(self, func_node: Any) -> bool:
        """Check if function has torch.no_grad() context."""
        found_no_grad = False

        def traverse(node: Any) -> None:
            nonlocal found_no_grad
            if found_no_grad:
                return
            if node.type == "with":
                body = node.child_by_field_name("body")
                if body:
                    body_text = body.text.decode("utf-8")
                    if "no_grad" in body_text or "inference_mode" in body_text:
                        found_no_grad = True
                        return
            for child in node.children:
                traverse(child)

        traverse(func_node)
        return found_no_grad

    def _find_training_functions(
        self,
        root: Any,
    ) -> list[tuple[Any, str, int]]:
        """Find training-related functions."""
        training_funcs = []
        training_names = {"train", "fit", "main", "run", "execute"}

        def traverse(node: Any) -> None:
            if node.type in ("function_definition", "async_function_definition"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8")
                    if name in training_names:
                        line_no = node.start_point[0] + 1
                        training_funcs.append((node, name, line_no))
            for child in node.children:
                traverse(child)

        traverse(root)
        return training_funcs

    def _function_has_seed_setting(self, func_node: Any) -> bool:
        """Check if function sets random seeds."""
        content = self._get_node_text(func_node)
        seed_patterns = [
            r"torch\.manual_seed",
            r"torch\.cuda\.manual_seed",
            r"np\.random\.seed",
            r"random\.seed",
            r"set_random_seed",
        ]
        return any(re.search(p, content) for p in seed_patterns)

    def _check_seed_from_args(self, content: str, line_no: int) -> bool:
        """Check if seed is passed as function argument."""
        lines = content.split("\n")
        if line_no > len(lines):
            return False

        # Look at function signature and next few lines
        context = "\n".join(lines[max(0, line_no - 1):line_no + 10])
        return "seed" in context.lower() and ("def " in context or "args" in context)

    def _calculate_leakage_confidence(
        self,
        content: str,
        fit_line: int,
        split_line: int,
    ) -> float:
        """Calculate confidence based on context clarity."""
        base_confidence = 0.85
        lines = content.split("\n")

        # Boost for clear scope (both operations in same function)
        context_range = range(max(0, fit_line - 20), min(len(lines), split_line + 20))
        context = "\n".join(lines[c] for c in context_range)

        if "def " in context:
            base_confidence += AST_CONFIDENCE_BOOST
        if any(x in context for x in ["X_train", "X_test", "y_train", "y_test"]):
            base_confidence += CONTEXT_CLARITY_BOOST

        return min(1.0, base_confidence)

    def _get_code_snippet(
        self,
        content: str,
        line_no: int,
        lines: int = 3,
    ) -> str:
        """Extract code snippet around a line number."""
        content_lines = content.split("\n")
        start = max(0, line_no - 1)
        end = min(len(content_lines), start + lines)
        return "\n".join(content_lines[start:end])

    def _get_node_text(self, node: Any) -> str:
        """Get text content of a tree-sitter node."""
        try:
            return node.text.decode("utf-8")
        except Exception:
            return ""

    # ─── Regex Fallback Methods ────────────────────────────────────────────────

    def _detect_ml001_regex_fallback(
        self,
        content: str,
        file_path: Path,
    ) -> list[dict[str, Any]]:
        """Improved regex fallback for ML001."""
        findings = []
        lines = content.split("\n")

        # Find train_test_split lines
        split_lines = []
        for i, line in enumerate(lines, 1):
            if "train_test_split" in line:
                split_lines.append(i)

        if not split_lines:
            return findings

        first_split = min(split_lines)

        # Find scaler.fit() patterns
        scaler_pattern = re.compile(
            r"(\w+)\s*=\s*(StandardScaler|MinMaxScaler|RobustScaler|"
            r"MaxAbsScaler|Normalizer).*?\.fit\s*\("
        )

        for i, line in enumerate(lines[:first_split], 1):
            match = scaler_pattern.search(line)
            if match:
                findings.append({
                    "rule_id": "ML001",
                    "severity": "CRITICAL",
                    "line": i,
                    "message": f"Potential data leakage: {match.group(1)}.fit() before train_test_split",
                    "confidence": 0.75,  # Lower than AST
                    "old_code": line.strip(),
                    "new_code": f"{match.group(1)}.fit_transform(X_train)",
                    "explanation": "Use fit_transform() on training data only.",
                    "detection_method": "regex_fallback",
                })

        return findings

    def _detect_ml002_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML002."""
        findings = []
        lines = content.split("\n")

        # Find CrossEntropyLoss followed by multi-label indicators
        for i, line in enumerate(lines, 1):
            if "CrossEntropyLoss" in line:
                # Check nearby lines for multi-label indicators
                context = "\n".join(lines[max(0, i-5):min(len(lines), i+5)])
                if any(x in context.lower() for x in ["sigmoid", "bce", "multi-label", "multi_label"]):
                    findings.append({
                        "rule_id": "ML002",
                        "severity": "CRITICAL",
                        "line": i,
                        "message": "CrossEntropyLoss with multi-label indicators",
                        "confidence": 0.70,
                        "old_code": line.strip(),
                        "new_code": "nn.BCEWithLogitsLoss()",
                        "explanation": "Use BCEWithLogitsLoss for multi-label classification.",
                        "detection_method": "regex_fallback",
                    })

        return findings

    def _detect_ml003_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML003."""
        findings = []

        # Find device mismatches in .to() calls
        to_pattern = re.compile(r"\.to\s*\(\s*(\w+)\s*\)")
        matches = list(to_pattern.finditer(content))

        for i, match in enumerate(matches):
            line_no = content[:match.start()].count("\n") + 1
            device = match.group(1)
            # Check if same line has both model and data
            line_content = content.split("\n")[line_no - 1]
            if device not in ["device", "torch.device"]:
                findings.append({
                    "rule_id": "ML003",
                    "severity": "HIGH",
                    "line": line_no,
                    "message": f"Possible device mismatch: .to({device})",
                    "confidence": 0.65,
                    "old_code": line_content.strip(),
                    "new_code": f".to(model.device)",
                    "explanation": "Use consistent device for model and data.",
                    "detection_method": "regex_fallback",
                })

        return findings[:3]  # Limit to avoid noise

    def _detect_ml004_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML004."""
        findings = []

        # Find inference-like functions without no_grad
        func_pattern = re.compile(
            r"(def\s+(?:predict|evaluate|inference|forward)\s*\([^)]*\):.*?"
            r"(?=\n(?:def |class |\Z)))",
            re.DOTALL
        )

        for match in func_pattern.finditer(content):
            func_content = match.group(0)
            line_no = content[:match.start()].count("\n") + 1

            if "no_grad" not in func_content and "inference_mode" not in func_content:
                if "model(" in func_content or ".model(" in func_content:
                    findings.append({
                        "rule_id": "ML004",
                        "severity": "HIGH",
                        "line": line_no,
                        "message": f"Function performs inference without torch.no_grad()",
                        "confidence": 0.72,
                        "old_code": func_content[:100] + "...",
                        "new_code": "with torch.no_grad():\n    output = model(input)",
                        "explanation": "Wrap inference in torch.no_grad() context.",
                        "detection_method": "regex_fallback",
                    })

        return findings

    def _detect_ml005_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML005."""
        findings = []

        # Find training functions without seed
        seed_patterns = [
            r"torch\.manual_seed",
            r"torch\.cuda\.manual_seed",
            r"np\.random\.seed",
            r"random\.seed",
        ]

        has_seed = any(re.search(p, content) for p in seed_patterns)
        if not has_seed:
            func_pattern = re.compile(
                r"(def\s+(?:train|fit|main)\s*\([^)]*\):)",
            )
            for match in func_pattern.finditer(content):
                line_no = content[:match.start()].count("\n") + 1
                findings.append({
                    "rule_id": "ML005",
                    "severity": "MEDIUM",
                    "line": line_no,
                    "message": "Training function missing random seed",
                    "confidence": 0.65,
                    "old_code": match.group(1),
                    "new_code": "def seed_everything(seed=42):\n    torch.manual_seed(seed)\n    np.random.seed(seed)",
                    "explanation": "Set random seeds for reproducibility.",
                    "detection_method": "regex_fallback",
                })

        return findings
