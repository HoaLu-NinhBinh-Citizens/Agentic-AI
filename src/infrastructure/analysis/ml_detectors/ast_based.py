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

# Common ML hyperparameter names to flag when hardcoded
ML_HYPERPARAM_NAMES = frozenset({
    "batch_size", "lr", "learning_rate", "epochs", "n_estimators",
    "hidden_dim", "hidden_size", "embed_dim", "num_layers", "num_heads",
    "dropout", "weight_decay", "momentum", "beta_1", "beta_2",
    "gamma", "reg_alpha", "reg_lambda", "min_child_weight",
    "max_depth", "min_samples_split", "min_samples_leaf",
    "num_leaves", "feature_fraction", "bagging_fraction",
    "threshold", "temperature", "top_k", "beam_size",
})

# Common hardcoded path patterns
HARDCODE_PATH_PATTERNS = frozenset({
    "data_dir", "model_path", "save_path", "checkpoint_path",
    "log_dir", "output_dir", "cache_dir", "train_path", "val_path",
    "test_path", "data_path",
})

# Literal value patterns that indicate hardcoding
MAGIC_NUMBER_PATTERNS = {
    "hidden_dim": [64, 128, 256, 512],
    "batch_size": [8, 16, 32, 64, 128],
    "epochs": [10, 20, 50, 100],
    "lr": [0.001, 0.0001, 1e-4, 1e-3],
    "dropout": [0.1, 0.2, 0.3, 0.5],
}

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

    def detect_ml006_hardcoded_config(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect hardcoded ML hyperparameters and paths using AST analysis.

        AST-based approach:
        1. Find assignment nodes with common ML config names
        2. Check if value is a literal (not from config/env/argparse)
        3. Flag: batch_size, lr, learning_rate, epochs, hidden_dim, etc.
        4. Also flag: path="/data/...", data_dir="...", model_path="..."

        Distinguishes OK cases:
        - batch_size = args.batch_size (OK - from argparse)
        - lr = config.get("learning_rate") (OK - from config)
        - batch_size = 32 (HARDCODE - flagged)
        """
        findings = []

        if language != "python":
            return self._detect_ml006_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            source_bytes = content.encode("utf-8")
            tree = parser.parse(source_bytes)
            root = tree.root_node

            # Find all assignments
            assignments = self._find_ml_config_assignments(root)

            for var_name, value_node, line_no in assignments:
                if self._is_hardcoded_value(value_node, content):
                    # Get the actual value for the finding
                    old_code = self._get_code_snippet(content, line_no)
                    new_code = self._generate_config_fix(var_name, value_node)

                    findings.append({
                        "rule_id": "ML006",
                        "severity": "MEDIUM",
                        "line": line_no,
                        "message": f"Hardcoded ML config: {var_name} = {self._get_node_text(value_node)}",
                        "confidence": 0.82,
                        "old_code": old_code,
                        "new_code": new_code,
                        "explanation": (
                            f"'{var_name}' is hardcoded instead of being loaded from "
                            "config, environment variables, or command-line arguments. "
                            "This makes the code less flexible and harder to reproduce."
                        ),
                        "detection_method": "ast",
                    })

        except ImportError:
            return self._detect_ml006_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML006", error=str(e))
            return self._detect_ml006_regex_fallback(content)

        return findings

    def _find_ml_config_assignments(
        self,
        root: Any,
    ) -> list[tuple[str, Any, int]]:
        """Find assignments to ML config variables.

        Returns:
            List of (variable_name, value_node, line_number) tuples.
        """
        assignments = []

        def traverse(node: Any) -> None:
            # Handle regular assignment: var = value
            if node.type == "assignment":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left and right and left.type == "identifier":
                    var_name = left.text.decode("utf-8")
                    if self._is_ml_config_name(var_name):
                        line_no = node.start_point[0] + 1
                        assignments.append((var_name, right, line_no))

            # Handle annotated assignment: var: Type = value
            elif node.type == "annotated_assignment":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left and right and left.type == "identifier":
                    var_name = left.text.decode("utf-8")
                    if self._is_ml_config_name(var_name):
                        line_no = node.start_point[0] + 1
                        assignments.append((var_name, right, line_no))

            # Handle for loop target: for var in ...
            elif node.type == "for_statement":
                target = node.child_by_field_name("target")
                if target and target.type == "identifier":
                    var_name = target.text.decode("utf-8")
                    if self._is_ml_config_name(var_name):
                        line_no = node.start_point[0] + 1
                        # Get the iterable as the "value"
                        iterable = node.child_by_field_name("iterator")
                        if iterable:
                            assignments.append((var_name, iterable, line_no))

            for child in node.children:
                traverse(child)

        traverse(root)
        return assignments

    def _is_ml_config_name(self, name: str) -> bool:
        """Check if a variable name is a known ML config parameter."""
        # Check exact match
        if name in ML_HYPERPARAM_NAMES:
            return True
        # Check common suffixes/prefixes
        name_lower = name.lower()
        for pattern in ML_HYPERPARAM_NAMES:
            if pattern in name_lower or name_lower in pattern:
                return True
        # Check path patterns
        for path_pattern in HARDCODE_PATH_PATTERNS:
            if path_pattern in name_lower:
                return True
        return False

    def _is_hardcoded_value(self, value_node: Any, content: str) -> bool:
        """Check if a value is hardcoded (literal) vs external (config/args/env).

        Returns True if the value is a literal that should be externalized.
        Returns False if the value comes from config, args, env, or function calls.
        """
        # String literal - check for hardcoded paths
        if value_node.type == "string":
            value_text = self._get_node_text(value_node)
            # Flag paths that look like ML/model paths
            if "/" in value_text or "\\" in value_text:
                # Expanded patterns for model/checkpoint/output paths
                path_indicators = [
                    "/data/", "/model", "/checkpoint", "/output",
                    "c:", ".pt", ".pth", ".ckpt",
                ]
                # Check for trailing slash paths like "checkpoints/", "models/"
                trailing_slash_patterns = [
                    "checkpoints/", "models/", "outputs/", "data/",
                ]
                value_lower = value_text.lower().strip("'\"").strip("\"'")
                if any(p in value_lower for p in path_indicators):
                    return True
                # Also detect trailing slash directory paths
                if any(value_lower.startswith(p) for p in trailing_slash_patterns):
                    return True
            return False

        # Number literal - likely hardcoded hyperparam
        if value_node.type in ("integer", "float"):
            return True

        # Boolean literal
        if value_node.type in ("true", "false", "none"):
            return False

        # List literal - check if contains hardcoded values
        if value_node.type == "list":
            return self._list_has_hardcoded_values(value_node)

        # Dictionary literal - check values
        if value_node.type == "dictionary":
            return self._dict_has_hardcoded_values(value_node)

        # Call expression - likely from config/argparse (OK)
        if value_node.type == "call":
            return False

        # Attribute access - likely from config/namespace (OK)
        if value_node.type == "attribute":
            return False

        # Subscript - likely from config dict (OK)
        if value_node.type == "subscript":
            return False

        # Identifier - variable reference (might be OK or hardcoded)
        if value_node.type == "identifier":
            return False  # Assume OK unless we can trace it

        # Binary operation - likely expression (OK)
        if value_node.type == "binary_operator":
            return False

        return False

    def _list_has_hardcoded_values(self, node: Any) -> bool:
        """Check if a list literal contains hardcoded values."""
        for child in node.children:
            if child.type in ("integer", "float", "string"):
                return True
            if child.type == "list":
                if self._list_has_hardcoded_values(child):
                    return True
        return False

    def _dict_has_hardcoded_values(self, node: Any) -> bool:
        """Check if a dict literal contains hardcoded values."""
        for child in node.children:
            if child.type == "pair":
                value = child.child_by_field_name("value")
                if value and self._is_hardcoded_value(value, ""):
                    return True
        return False

    def _generate_config_fix(self, var_name: str, value_node: Any) -> str:
        """Generate suggested config-based fix for a hardcoded value."""
        value_text = self._get_node_text(value_node)

        if any(p in var_name.lower() for p in ["path", "dir"]):
            return (
                f"{var_name} = os.getenv('{var_name.upper()}', "
                f"'./default_{var_name}')"
            )

        if var_name.lower() in ["lr", "learning_rate"]:
            return (
                f"{var_name} = config.get('learning_rate', "
                f"{value_text})  # or: args.{var_name}"
            )

        if var_name.lower() == "batch_size":
            return (
                f"{var_name} = args.batch_size if args.batch_size else "
                f"{value_text}  # or: config['batch_size']"
            )

        if var_name.lower() == "epochs":
            return (
                f"{var_name} = args.epochs if args.epochs else "
                f"{value_text}  # or: config['epochs']"
            )

        return (
            f"{var_name} = config.get('{var_name}', "
            f"{value_text})  # or: args.{var_name}"
        )

    def _detect_ml006_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML006 hardcoded config detection."""
        findings = []

        # Patterns for hardcoded hyperparameters
        patterns = [
            # batch_size = 32 (not from config/args)
            (r"batch_size\s*=\s*(\d+)", "batch_size"),
            # lr = 0.001 or learning_rate = 0.001
            (r"(?:lr|learning_rate)\s*=\s*(0\.\d+)", "learning_rate"),
            # epochs = 100
            (r"epochs?\s*=\s*(\d+)", "epochs"),
            # hidden_dim = 256
            (r"hidden_dim(?:sion)?\s*=\s*(\d+)", "hidden_dim"),
            # dropout = 0.5
            (r"dropout\s*=\s*(0?\.\d+)", "dropout"),
            # path strings - expanded patterns
            (r"(?:data_path|model_path|train_path|val_path|checkpoint_path|save_path|output_dir|log_dir)\s*=\s*['\"]([^'\"]+)['\"]", "path"),
            # model file extensions
            (r"model_path\s*=\s*['\"]([^'\"]+\.(?:pt|pth|ckpt|pt'|pth'|ckpt'))", "model_path"),
        ]

        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            # Skip if line references config, args, or env
            if any(x in line for x in ["config.get", "args.", "argparse", "os.getenv", "env["]):
                continue

            for pattern, param_name in patterns:
                import re
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    value = match.group(1) if match.groups() else ""
                    findings.append({
                        "rule_id": "ML006",
                        "severity": "MEDIUM",
                        "line": i,
                        "message": f"Hardcoded ML config: {param_name} = {value}",
                        "confidence": 0.72,
                        "old_code": line.strip(),
                        "new_code": self._generate_config_fix(param_name, None),
                        "explanation": (
                            f"'{param_name}' should be loaded from config, "
                            "args, or environment variables."
                        ),
                        "detection_method": "regex_fallback",
                    })
                    break  # One finding per line

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

    def detect_ml007_gradient_accumulation(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect gradient accumulation errors.

        Detects when optimizer.step() is called every iteration instead of
        at accumulation_steps intervals, breaking gradient accumulation.
        """
        findings = []

        if language != "python":
            return self._detect_ml007_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            # Find training loops with optimizer.step()
            training_loops = self._find_training_loops_with_optimizer(root)

            for loop_node, line_no in training_loops:
                # Check if there's gradient accumulation logic
                has_accumulation = self._has_gradient_accumulation_logic(loop_node)
                has_step = self._loop_has_optimizer_step(loop_node)

                # If step is called but no accumulation tracking, flag it
                if has_step and not has_accumulation:
                    findings.append({
                        "rule_id": "ML007",
                        "severity": "HIGH",
                        "line": line_no,
                        "message": "optimizer.step() called in loop without gradient accumulation tracking",
                        "confidence": 0.82,
                        "old_code": self._get_code_snippet(content, line_no, lines=10),
                        "new_code": (
                            "if (step + 1) % accumulation_steps == 0:\n"
                            "    optimizer.step()\n"
                            "    optimizer.zero_grad()"
                        ),
                        "explanation": (
                            "Gradient accumulation requires calling optimizer.step() "
                            "only every accumulation_steps iterations, not every iteration. "
                            "This breaks the intended gradient accumulation behavior."
                        ),
                        "detection_method": "ast",
                    })

        except ImportError:
            return self._detect_ml007_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML007", error=str(e))
            return self._detect_ml007_regex_fallback(content)

        return findings

    def detect_ml008_wrong_optimizer(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect wrong optimizer usage patterns.

        Detects AdamW vs SGD specificity issues like weight_decay
        not working correctly with Adam optimizer.
        """
        findings = []

        if language != "python":
            return self._detect_ml008_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            # Find optimizer instantiations
            optimizers = self._find_optimizer_usages(root)

            for opt_node, opt_type, line_no in optimizers:
                if opt_type == "Adam":
                    # Check for weight_decay with Adam (should use AdamW instead)
                    if self._has_weight_decay_param(opt_node):
                        findings.append({
                            "rule_id": "ML008",
                            "severity": "MEDIUM",
                            "line": line_no,
                            "message": f"weight_decay parameter with {opt_type} optimizer",
                            "confidence": 0.78,
                            "old_code": self._get_code_snippet(content, line_no),
                            "new_code": "torch.optim.AdamW(model.parameters(), weight_decay=0.01)",
                            "explanation": (
                                f"Adam optimizer applies weight_decay to all parameters equally, "
                                f"which is different from AdamW's decoupled weight decay. "
                                f"Consider using AdamW for proper L2 regularization."
                            ),
                            "detection_method": "ast",
                        })

        except ImportError:
            return self._detect_ml008_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML008", error=str(e))
            return self._detect_ml008_regex_fallback(content)

        return findings

    def detect_ml009_augmentation_in_eval(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect data augmentation applied during evaluation.

        Augmentation should only be applied to training data, not validation/test.
        """
        findings = []

        if language != "python":
            return self._detect_ml009_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            # Find eval/validation functions
            eval_functions = self._find_eval_functions(root)

            for func_node, func_name, line_no in eval_functions:
                # Check for augmentation calls inside eval function
                has_augmentation = self._has_augmentation_in_function(func_node)
                if has_augmentation:
                    findings.append({
                        "rule_id": "ML009",
                        "severity": "HIGH",
                        "line": line_no,
                        "message": f"Data augmentation detected in evaluation function '{func_name}'",
                        "confidence": 0.85,
                        "old_code": self._get_code_snippet(content, line_no, lines=15),
                        "new_code": (
                            "# Move augmentation to train dataloader only:\n"
                            "# train_loader = DataLoader(train_dataset, transform=train_transform)\n"
                            "# val_loader = DataLoader(val_dataset, transform=None)  # No augmentation"
                        ),
                        "explanation": (
                            "Data augmentation should only be applied to training data. "
                            "Applying augmentation during evaluation/test causes inconsistent "
                            "predictions and unreliable metrics."
                        ),
                        "detection_method": "ast",
                    })

        except ImportError:
            return self._detect_ml009_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML009", error=str(e))
            return self._detect_ml009_regex_fallback(content)

        return findings

    def detect_ml010_nan_inf(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect patterns that can cause NaN/Inf propagation.

        Detects division without checks, log of negative numbers, etc.
        """
        findings = []

        if language != "python":
            return self._detect_ml010_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            # Find division and log operations
            dangerous_ops = self._find_dangerous_numeric_ops(root)

            for op_node, op_type, line_no in dangerous_ops:
                findings.append({
                    "rule_id": "ML010",
                    "severity": "CRITICAL",
                    "line": line_no,
                    "message": f"Potential NaN/Inf source: {op_type} without safety checks",
                    "confidence": 0.80,
                    "old_code": self._get_code_snippet(content, line_no),
                    "new_code": (
                        "# Add safety checks:\n"
                        "if denominator != 0 and not torch.isnan(denominator).any():\n"
                        "    result = numerator / denominator"
                    ),
                    "explanation": (
                        f"Operation '{op_type}' can produce NaN/Inf if the divisor contains "
                        f"zeros or if the operand contains NaN values. Add explicit checks "
                        f"or use safe division functions."
                    ),
                    "detection_method": "ast",
                })

        except ImportError:
            return self._detect_ml010_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML010", error=str(e))
            return self._detect_ml010_regex_fallback(content)

        return findings

    def detect_ml011_lr_scheduler(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect learning rate scheduler errors.

        Scheduler should be stepped after optimizer update, not before.
        """
        findings = []

        if language != "python":
            return self._detect_ml011_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            # Find training loops with scheduler
            training_with_scheduler = self._find_training_with_scheduler(root)

            for loop_node, scheduler_step_pos, line_no in training_with_scheduler:
                # If scheduler is stepped before optimizer, flag it
                if scheduler_step_pos == "before_optimizer":
                    findings.append({
                        "rule_id": "ML011",
                        "severity": "HIGH",
                        "line": line_no,
                        "message": "LR scheduler stepped before optimizer.step()",
                        "confidence": 0.82,
                        "old_code": self._get_code_snippet(content, line_no, lines=15),
                        "new_code": (
                            "# Correct order:\n"
                            "loss.backward()\n"
                            "optimizer.step()\n"
                            "scheduler.step()  # Step AFTER optimizer"
                        ),
                        "explanation": (
                            "Learning rate schedulers should be stepped AFTER optimizer.step(), "
                            "not before. Stepping before causes incorrect learning rate "
                            "scheduling and suboptimal training."
                        ),
                        "detection_method": "ast",
                    })

        except ImportError:
            return self._detect_ml011_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML011", error=str(e))
            return self._detect_ml011_regex_fallback(content)

        return findings

    def detect_ml012_batchnorm_small_batch(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect batch normalization with very small batch sizes.

        BatchNorm requires sufficient batch size for stable statistics.
        """
        findings = []

        if language != "python":
            return self._detect_ml012_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            # Find batch size assignments and BatchNorm layers
            batchnorm_with_small_batch = self._find_batchnorm_small_batch_patterns(root)

            for model_node, batch_size, line_no in batchnorm_with_small_batch:
                findings.append({
                    "rule_id": "ML012",
                    "severity": "HIGH",
                    "line": line_no,
                    "message": f"BatchNorm with batch_size={batch_size} may cause unstable statistics",
                    "confidence": 0.80,
                    "old_code": self._get_code_snippet(content, line_no, lines=10),
                    "new_code": (
                        "# Consider alternatives for small batch:\n"
                        "# 1. Use SyncBatchNorm for multi-GPU\n"
                        "# 2. Use GroupNorm instead of BatchNorm\n"
                        "# 3. Increase batch size if possible"
                    ),
                    "explanation": (
                        f"BatchNorm with batch_size={batch_size} is problematic because "
                        f"BatchNorm relies on batch statistics. Very small batches lead to "
                        f"unstable running statistics and poor model performance. "
                        f"Consider using GroupNorm or SyncBatchNorm instead."
                    ),
                    "detection_method": "ast",
                })

        except ImportError:
            return self._detect_ml012_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML012", error=str(e))
            return self._detect_ml012_regex_fallback(content)

        return findings

    def detect_ml013_multi_gpu_sync(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect DistributedDataParallel sync issues.

        Model must be wrapped correctly before DDP wrapping.
        """
        findings = []

        if language != "python":
            return self._detect_ml013_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            # Find DDP wrapping patterns
            ddp_patterns = self._find_ddp_patterns(root)

            for pattern, line_no in ddp_patterns:
                findings.append({
                    "rule_id": "ML013",
                    "severity": "CRITICAL",
                    "line": line_no,
                    "message": f"DistributedDataParallel wrapping issue: {pattern}",
                    "confidence": 0.78,
                    "old_code": self._get_code_snippet(content, line_no, lines=10),
                    "new_code": (
                        "# Correct DDP wrapping:\n"
                        "model = model.cuda()\n"
                        "model = DistributedDataParallel(model)\n"
                        "# Not: model = DistributedDataParallel(model.cuda())"
                    ),
                    "explanation": (
                        f"DistributedDataParallel requires careful handling of device placement "
                        f"and state dict synchronization. Issues with '{pattern}' can cause "
                        f"incorrect gradients, parameter desync, or runtime errors."
                    ),
                    "detection_method": "ast",
                })

        except ImportError:
            return self._detect_ml013_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML013", error=str(e))
            return self._detect_ml013_regex_fallback(content)

        return findings

    def detect_ml014_mixed_precision(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect mixed precision training errors.

        Missing loss scaling, overflow detection, etc.
        """
        findings = []

        if language != "python":
            return self._detect_ml014_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            # Find AMP/autocast usage
            amp_patterns = self._find_amp_patterns(root)

            for pattern, line_no in amp_patterns:
                findings.append({
                    "rule_id": "ML014",
                    "severity": "HIGH",
                    "line": line_no,
                    "message": f"Mixed precision issue: {pattern}",
                    "confidence": 0.82,
                    "old_code": self._get_code_snippet(content, line_no, lines=10),
                    "new_code": (
                        "# Use GradScaler for loss scaling:\n"
                        "scaler = GradScaler()\n"
                        "with autocast():\n"
                        "    loss = criterion(output, target)\n"
                        "scaler.scale(loss).backward()\n"
                        "scaler.step(optimizer)\n"
                        "scaler.update()"
                    ),
                    "explanation": (
                        f"Mixed precision training requires proper loss scaling to prevent "
                        f"gradient underflow. Issue with '{pattern}' can cause training "
                        f"instability or NaN losses."
                    ),
                    "detection_method": "ast",
                })

        except ImportError:
            return self._detect_ml014_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML014", error=str(e))
            return self._detect_ml014_regex_fallback(content)

        return findings

    def detect_ml015_early_stopping(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect early stopping logic bugs.

        Wrong metric monitoring, incorrect patience reset logic.
        """
        findings = []

        if language != "python":
            return self._detect_ml015_regex_fallback(content)

        try:
            import tree_sitter
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            # Find early stopping implementations
            early_stopping_impls = self._find_early_stopping_impls(root)

            for impl_node, impl_type, line_no in early_stopping_impls:
                if impl_type == "wrong_metric":
                    findings.append({
                        "rule_id": "ML015",
                        "severity": "MEDIUM",
                        "line": line_no,
                        "message": "Early stopping monitors loss instead of validation metric",
                        "confidence": 0.80,
                        "old_code": self._get_code_snippet(content, line_no, lines=15),
                        "new_code": (
                            "# Monitor validation metric, not training loss:\n"
                            "if val_metric < best_metric:\n"
                            "    best_metric = val_metric\n"
                            "    patience_counter = 0\n"
                            "else:\n"
                            "    patience_counter += 1"
                        ),
                        "explanation": (
                            "Early stopping should monitor validation metrics, not training loss. "
                            "Training loss always decreases; validation metrics show true generalization. "
                            "Monitoring training loss leads to premature or delayed stopping."
                        ),
                        "detection_method": "ast",
                    })
                elif impl_type == "wrong_patience":
                    findings.append({
                        "rule_id": "ML015",
                        "severity": "MEDIUM",
                        "line": line_no,
                        "message": "Early stopping patience reset logic is incorrect",
                        "confidence": 0.78,
                        "old_code": self._get_code_snippet(content, line_no, lines=15),
                        "new_code": (
                            "# Correct patience reset: only when metric IMPROVES\n"
                            "if mode == 'min':\n"
                            "    if current < best:\n"
                            "        best = current\n"
                            "        patience_counter = 0\n"
                            "else:\n"
                            "    if current > best:\n"
                            "        best = current\n"
                            "        patience_counter = 0"
                        ),
                        "explanation": (
                            "Early stopping patience should only reset when the monitored metric "
                            "improves. Resetting on every iteration defeats the purpose of patience."
                        ),
                        "detection_method": "ast",
                    })

        except ImportError:
            return self._detect_ml015_regex_fallback(content)
        except Exception as e:
            logger.warning("AST analysis failed for ML015", error=str(e))
            return self._detect_ml015_regex_fallback(content)

        return findings

    # ─── Helper Methods for New Detections ────────────────────────────────────

    def _detect_ml007_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML007 gradient accumulation."""
        findings = []

        # Find optimizer.step() in training loops
        step_pattern = re.compile(
            r"optimizer\.step\(\).*?(?=\n\s*(?:optimizer\.|scheduler\.|for|if|$))",
            re.DOTALL
        )

        for match in step_pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            step_context = content[max(0, match.start()-500):match.end()+500]

            # Check for accumulation tracking
            has_accumulation = any(
                p in step_context for p in ["accumulation_steps", "%", "modulo", "if step"]
            )

            if not has_accumulation and "for" in step_context:
                findings.append({
                    "rule_id": "ML007",
                    "severity": "HIGH",
                    "line": line_no,
                    "message": "optimizer.step() called without gradient accumulation tracking",
                    "confidence": 0.70,
                    "old_code": match.group(0)[:100],
                    "new_code": "if (step + 1) % accumulation_steps == 0:\n    optimizer.step()",
                    "explanation": "Gradient accumulation requires conditional step() calls.",
                    "detection_method": "regex_fallback",
                })

        return findings

    def _detect_ml008_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML008 wrong optimizer."""
        findings = []

        # Find Adam with weight_decay
        pattern = re.compile(
            r"torch\.optim\.Adam\([^)]*weight_decay\s*=",
            re.DOTALL
        )

        for match in pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            findings.append({
                "rule_id": "ML008",
                "severity": "MEDIUM",
                "line": line_no,
                "message": "weight_decay with Adam optimizer",
                "confidence": 0.65,
                "old_code": content.split("\n")[line_no-1].strip(),
                "new_code": "torch.optim.AdamW(params, weight_decay=0.01)",
                "explanation": "Use AdamW for proper L2 regularization with decoupled weight decay.",
                "detection_method": "regex_fallback",
            })

        return findings

    def _detect_ml009_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML009 augmentation in eval."""
        findings = []

        eval_func_pattern = re.compile(
            r"def\s+(?:evaluate|eval|validate|inference)\s*\([^)]*\):.*?"
            r"(?=\n(?:def |class |\Z))",
            re.DOTALL
        )

        aug_patterns = [
            r"transforms\.", r"Random", r"augment", r"ColorJitter", r"RandomRotation",
            r"RandomHorizontalFlip", r"RandomCrop", r"Compose"
        ]

        for eval_match in eval_func_pattern.finditer(content):
            func_content = eval_match.group(0)
            line_no = content[:eval_match.start()].count("\n") + 1

            if any(re.search(p, func_content, re.IGNORECASE) for p in aug_patterns):
                findings.append({
                    "rule_id": "ML009",
                    "severity": "HIGH",
                    "line": line_no,
                    "message": "Data augmentation detected in evaluation function",
                    "confidence": 0.72,
                    "old_code": func_content[:100],
                    "new_code": "# Remove augmentation from val/test loader",
                    "explanation": "Augmentation should only be applied to training data.",
                    "detection_method": "regex_fallback",
                })

        return findings

    def _detect_ml010_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML010 NaN/Inf patterns."""
        findings = []

        # Find division operations without safety
        div_pattern = re.compile(
            r"(?<!torch\.isnan\()(?<!torch\.isfinite\()"
            r"(?<!np\.isfinite\()(?<!\.item\(\))\s*/\s*"
            r"(?![\s]*[a-zA-Z_]+\s*\))"
        )

        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if "/" in line and "def " not in line:
                # Skip if already has safety checks
                if "isnan" not in line and "isfinite" not in line and "where" not in line:
                    if "scaler" not in line.lower():  # Skip scaler divisions
                        findings.append({
                            "rule_id": "ML010",
                            "severity": "CRITICAL",
                            "line": i,
                            "message": "Division without NaN/Inf safety checks",
                            "confidence": 0.65,
                            "old_code": line.strip(),
                            "new_code": "result = torch.where(denom != 0, numerator / denom, 0)",
                            "explanation": "Add explicit checks for division by zero or NaN values.",
                            "detection_method": "regex_fallback",
                        })

        return findings[:5]  # Limit findings

    def _detect_ml011_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML011 LR scheduler."""
        findings = []

        # Find scheduler.step() before optimizer.step()
        scheduler_step = re.compile(r"scheduler\.step\(\)")
        optimizer_step = re.compile(r"optimizer\.step\(\)")

        scheduler_matches = list(scheduler_step.finditer(content))
        optimizer_matches = list(optimizer_step.finditer(content))

        for sched_match in scheduler_matches:
            sched_line = content[:sched_match.start()].count("\n") + 1

            for opt_match in optimizer_matches:
                opt_line = content[:opt_match.start()].count("\n") + 1

                # If scheduler is before optimizer in same loop
                if opt_line > sched_line:
                    findings.append({
                        "rule_id": "ML011",
                        "severity": "HIGH",
                        "line": sched_line,
                        "message": "LR scheduler.step() called before optimizer.step()",
                        "confidence": 0.70,
                        "old_code": lines[sched_line-1].strip(),
                        "new_code": "# Move scheduler.step() AFTER optimizer.step()",
                        "explanation": "Schedulers should be stepped after optimizer updates.",
                        "detection_method": "regex_fallback",
                    })
                    break

        return findings

    def _detect_ml012_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML012 batch norm small batch."""
        findings = []

        # Find batch_size = 1 patterns
        pattern = re.compile(r"batch_size\s*=\s*1\b")

        for match in pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            findings.append({
                "rule_id": "ML012",
                "severity": "HIGH",
                "line": line_no,
                "message": "batch_size=1 may cause unstable BatchNorm statistics",
                "confidence": 0.68,
                "old_code": content.split("\n")[line_no-1].strip(),
                "new_code": "# Use GroupNorm or SyncBatchNorm for small batches",
                "explanation": "BatchNorm with batch_size=1 has no batch statistics. Use GroupNorm.",
                "detection_method": "regex_fallback",
            })

        return findings

    def _detect_ml013_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML013 DDP issues."""
        findings = []

        # Find DDP wrapping patterns
        pattern = re.compile(
            r"DistributedDataParallel\s*\(\s*[^)]*\.cuda\(\)",
            re.DOTALL
        )

        for match in pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            findings.append({
                "rule_id": "ML013",
                "severity": "CRITICAL",
                "line": line_no,
                "message": "DDP wrapping model.cuda() inside constructor",
                "confidence": 0.68,
                "old_code": content.split("\n")[line_no-1].strip(),
                "new_code": "model = model.cuda()\nmodel = DDP(model)",
                "explanation": "Move device placement outside DDP constructor for proper syncing.",
                "detection_method": "regex_fallback",
            })

        return findings

    def _detect_ml014_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML014 mixed precision."""
        findings = []

        # Find autocast without GradScaler
        has_autocast = "autocast" in content
        has_scaler = "GradScaler" in content or "scaler.scale" in content

        if has_autocast and not has_scaler:
            autocast_pattern = re.compile(r"with\s+autocast\(\)")
            for match in autocast_pattern.finditer(content):
                line_no = content[:match.start()].count("\n") + 1
                findings.append({
                    "rule_id": "ML014",
                    "severity": "HIGH",
                    "line": line_no,
                    "message": "autocast used without GradScaler",
                    "confidence": 0.70,
                    "old_code": content.split("\n")[line_no-1].strip(),
                    "new_code": "scaler = GradScaler()\nscaler.scale(loss).backward()",
                    "explanation": "Use GradScaler for loss scaling to prevent gradient underflow.",
                    "detection_method": "regex_fallback",
                })

        return findings

    def _detect_ml015_regex_fallback(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for ML015 early stopping."""
        findings = []

        # Find early stopping with training loss
        early_stop_pattern = re.compile(
            r"(?:patience|early_stopping).*?"
            r"(?:if|when).*?(?:loss|metric).*?"
            r"(?:>|>=|<|<=)",
            re.IGNORECASE | re.DOTALL
        )

        for match in early_stop_pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            context = content[max(0, match.start()-200):match.end()+200]

            # Check if monitoring training loss
            if "val" not in context.lower() and "test" not in context.lower():
                if "train_loss" in context or ("loss" in context and "val" not in context):
                    findings.append({
                        "rule_id": "ML015",
                        "severity": "MEDIUM",
                        "line": line_no,
                        "message": "Early stopping monitors training loss instead of validation metric",
                        "confidence": 0.68,
                        "old_code": match.group(0)[:100],
                        "new_code": "# Monitor val_metric, not train_loss",
                        "explanation": "Use validation metrics for early stopping, not training loss.",
                        "detection_method": "regex_fallback",
                    })

        return findings

    def _find_training_loops_with_optimizer(
        self,
        root: Any,
    ) -> list[tuple[Any, int]]:
        """Find training loops containing optimizer.step()."""
        loops = []

        def traverse(node: Any) -> None:
            if node.type in ("for_statement", "while_statement"):
                body_text = self._get_node_text(node)
                if "optimizer.step()" in body_text and "for" in body_text:
                    line_no = node.start_point[0] + 1
                    loops.append((node, line_no))
            for child in node.children:
                traverse(child)

        traverse(root)
        return loops

    def _has_gradient_accumulation_logic(self, node: Any) -> bool:
        """Check if node has gradient accumulation tracking logic."""
        content = self._get_node_text(node)
        patterns = ["accumulation_steps", "%", "mod", "if step", "if (step"]
        return any(p in content for p in patterns)

    def _loop_has_optimizer_step(self, node: Any) -> bool:
        """Check if loop has optimizer.step()."""
        content = self._get_node_text(node)
        return "optimizer.step()" in content

    def _find_optimizer_usages(
        self,
        root: Any,
    ) -> list[tuple[Any, str, int]]:
        """Find optimizer instantiations."""
        optimizers = []

        def traverse(node: Any) -> None:
            if node.type == "call":
                func = node.child_by_field_name("function")
                if func:
                    func_text = self._get_node_text(func)
                    for opt_type in ["Adam", "SGD", "AdamW", "RMSprop"]:
                        if opt_type in func_text:
                            line_no = node.start_point[0] + 1
                            optimizers.append((node, opt_type, line_no))
            for child in node.children:
                traverse(child)

        traverse(root)
        return optimizers

    def _has_weight_decay_param(self, node: Any) -> bool:
        """Check if optimizer has weight_decay parameter."""
        content = self._get_node_text(node)
        return "weight_decay" in content

    def _find_eval_functions(
        self,
        root: Any,
    ) -> list[tuple[Any, str, int]]:
        """Find evaluation/validation functions."""
        funcs = []
        eval_names = {"evaluate", "eval", "validate", "inference", "test"}

        def traverse(node: Any) -> None:
            if node.type in ("function_definition", "async_function_definition"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8")
                    if name in eval_names:
                        line_no = node.start_point[0] + 1
                        funcs.append((node, name, line_no))
            for child in node.children:
                traverse(child)

        traverse(root)
        return funcs

    def _has_augmentation_in_function(self, func_node: Any) -> bool:
        """Check if function has data augmentation."""
        content = self._get_node_text(func_node)
        aug_patterns = [
            r"transforms?\.", r"Random", r"augment", r"ColorJitter",
            r"RandomRotation", r"RandomFlip", r"Compose"
        ]
        return any(re.search(p, content, re.IGNORECASE) for p in aug_patterns)

    def _find_dangerous_numeric_ops(
        self,
        root: Any,
    ) -> list[tuple[Any, str, int]]:
        """Find division and log operations that can cause NaN/Inf."""
        ops = []

        def traverse(node: Any) -> None:
            if node.type == "binary_operator":
                op = node.child_by_field_name("operator")
                if op:
                    op_text = op.text.decode("utf-8")
                    if op_text == "/":
                        line_no = node.start_point[0] + 1
                        ops.append((node, "division", line_no))
            elif node.type == "call":
                func = node.child_by_field_name("function")
                if func:
                    func_text = self._get_node_text(func)
                    if "log" in func_text.lower():
                        line_no = node.start_point[0] + 1
                        ops.append((node, "log", line_no))
            for child in node.children:
                traverse(child)

        traverse(root)
        return ops

    def _find_training_with_scheduler(
        self,
        root: Any,
    ) -> list[tuple[Any, str, int]]:
        """Find training loops with LR scheduler."""
        patterns = []

        def traverse(node: Any) -> None:
            if node.type in ("for_statement", "while_statement"):
                body = self._get_node_text(node)
                if "scheduler.step()" in body or "lr_scheduler" in body:
                    # Determine order
                    body_lines = body.split("\n")
                    scheduler_line = -1
                    optimizer_line = -1
                    for i, line in enumerate(body_lines):
                        if "scheduler.step()" in line and scheduler_line < 0:
                            scheduler_line = i
                        if "optimizer.step()" in line and optimizer_line < 0:
                            optimizer_line = i

                    if scheduler_line >= 0 and optimizer_line >= 0:
                        if scheduler_line < optimizer_line:
                            pos = "before_optimizer"
                        else:
                            pos = "after_optimizer"
                    else:
                        pos = "unknown"

                    line_no = node.start_point[0] + 1
                    patterns.append((node, pos, line_no))
            for child in node.children:
                traverse(child)

        traverse(root)
        return patterns

    def _find_batchnorm_small_batch_patterns(
        self,
        root: Any,
    ) -> list[tuple[Any, int, int]]:
        """Find BatchNorm layers with small batch sizes."""
        patterns = []

        def traverse(node: Any) -> None:
            if node.type == "call":
                func = node.child_by_field_name("function")
                if func:
                    func_text = self._get_node_text(func)
                    if "BatchNorm" in func_text:
                        # Check nearby for batch_size
                        parent_text = self._get_node_text(node.parent)
                        batch_match = re.search(r"batch_size\s*=\s*(\d+)", parent_text)
                        if batch_match:
                            batch_size = int(batch_match.group(1))
                            if batch_size <= 4:
                                line_no = node.start_point[0] + 1
                                patterns.append((node, batch_size, line_no))
            for child in node.children:
                traverse(child)

        traverse(root)
        return patterns

    def _find_ddp_patterns(
        self,
        root: Any,
    ) -> list[tuple[str, int]]:
        """Find DistributedDataParallel wrapping patterns."""
        patterns = []

        def traverse(node: Any) -> None:
            if node.type == "call":
                func = node.child_by_field_name("function")
                if func:
                    func_text = self._get_node_text(func)
                    if "DistributedDataParallel" in func_text:
                        # Check for .cuda() inside
                        args = node.child_by_field_name("arguments")
                        if args:
                            args_text = self._get_node_text(args)
                            if ".cuda()" in args_text:
                                patterns.append(("cuda_inside_ddp", node.start_point[0] + 1))
            for child in node.children:
                traverse(child)

        traverse(root)
        return patterns

    def _find_amp_patterns(
        self,
        root: Any,
    ) -> list[tuple[str, int]]:
        """Find AMP/autocast usage patterns."""
        patterns = []

        def traverse(node: Any) -> None:
            if node.type == "with":
                body = self._get_node_text(node)
                if "autocast" in body:
                    # Check if GradScaler is used
                    has_scaler = "scaler.scale" in body or "GradScaler" in body
                    if not has_scaler:
                        patterns.append(("autocast_without_scaler", node.start_point[0] + 1))
            for child in node.children:
                traverse(child)

        traverse(root)
        return patterns

    def _find_early_stopping_impls(
        self,
        root: Any,
    ) -> list[tuple[Any, str, int]]:
        """Find early stopping implementations."""
        impls = []

        def traverse(node: Any) -> None:
            if node.type in ("function_definition", "for_statement"):
                text = self._get_node_text(node)
                if "early_stop" in text.lower() or "patience" in text.lower():
                    # Determine issue type
                    if "train_loss" in text or ("loss" in text and "val" not in text):
                        impls.append((node, "wrong_metric", node.start_point[0] + 1))
                    elif re.search(r"patience\s*=\s*0(?!\d)", text):
                        impls.append((node, "wrong_patience", node.start_point[0] + 1))
            for child in node.children:
                traverse(child)

        traverse(root)
        return impls
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
