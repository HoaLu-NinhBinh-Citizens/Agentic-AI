"""Fix templates for ML rules with multiple options.

This module provides pre-defined fix templates for ML-specific rules,
each with multiple fix options including tradeoffs and test recommendations.

Usage:
    from src.infrastructure.analysis.ml_detectors.fix_templates import FIX_TEMPLATES
    
    if rule_id in FIX_TEMPLATES:
        options = generate_from_template(finding, rule_id)
"""

from __future__ import annotations

from typing import Any


# ─── ML Fix Templates ───────────────────────────────────────────────────────────


FIX_TEMPLATES: dict[str, dict[str, dict[str, Any]]] = {
    # ML001: Data Leakage - scaler.fit() before train_test_split
    "ML001": {
        "primary": {
            "title": "Fit scaler after train_test_split",
            "description": "Move scaler.fit() or fit_transform() to after train_test_split",
            "new_code": "X_train, X_test = train_test_split(X)\nscaler.fit_transform(X_train)\nX_test_scaled = scaler.transform(X_test)",
            "risk": "low",
            "tradeoff": "Simple fix, only affects preprocessing step",
            "test_recommendation": "Verify test accuracy is no longer inflated",
        },
        "alternative_1": {
            "title": "Use sklearn Pipeline",
            "description": "Wrap preprocessing in sklearn Pipeline to prevent leakage",
            "new_code": "from sklearn.pipeline import Pipeline\npipeline = Pipeline([('scaler', StandardScaler())])\npipeline.fit(X_train)\nX_train_scaled = pipeline.transform(X_train)",
            "risk": "medium",
            "tradeoff": "More robust, prevents leakage in cross-validation",
            "test_recommendation": "Verify Pipeline is used consistently",
        },
    },

    # ML002: Loss function mismatch - CrossEntropyLoss with multi-label
    "ML002": {
        "primary": {
            "title": "Use BCEWithLogitsLoss for multi-label",
            "description": "Replace CrossEntropyLoss with BCEWithLogitsLoss for multi-label classification",
            "new_code": "criterion = nn.BCEWithLogitsLoss()",
            "risk": "medium",
            "tradeoff": "Requires sigmoid activation on output if not already present",
            "test_recommendation": "Verify multi-label accuracy metric",
        },
        "alternative_1": {
            "title": "Use MultiLabelBinarizer preprocessing",
            "description": "Keep CrossEntropyLoss but preprocess targets with MultiLabelBinarizer",
            "new_code": "from sklearn.preprocessing import MultiLabelBinarizer\nmlb = MultiLabelBinarizer()\ny_encoded = mlb.fit_transform(y)",
            "risk": "low",
            "tradeoff": "Changes target format, may need to update evaluation code",
            "test_recommendation": "Verify label encoding matches original",
        },
    },

    # ML003: Device mismatch - model.to(device) vs data.to(device)
    "ML003": {
        "primary": {
            "title": "Move model to device before data",
            "description": "Ensure model and data are on the same device",
            "new_code": "model = model.to(device)\ndata = data.to(device)",
            "risk": "low",
            "tradeoff": "Simple fix, verify no other device mismatches exist",
            "test_recommendation": "Run with CUDA_LAUNCH_BLOCKING=1 for debugging",
        },
        "alternative_1": {
            "title": "Create unified device helper",
            "description": "Use a helper function to ensure consistent device placement",
            "new_code": "def to_device(obj, device):\n    if hasattr(obj, 'to'):\n        return obj.to(device)\n    return obj",
            "risk": "low",
            "tradeoff": "Adds utility function, reusable across codebase",
            "test_recommendation": "Test with both CPU and CUDA devices",
        },
    },

    # ML004: Missing no_grad in inference
    "ML004": {
        "primary": {
            "title": "Add torch.no_grad() context",
            "description": "Wrap inference code with torch.no_grad() to disable gradients",
            "new_code": "with torch.no_grad():\n    output = model(input)",
            "risk": "low",
            "tradeoff": "Simple fix, prevents memory accumulation in inference",
            "test_recommendation": "Verify memory usage during inference",
        },
        "alternative_1": {
            "title": "Use torch.inference_mode()",
            "description": "Use inference_mode() for better performance if PyTorch 1.9+",
            "new_code": "with torch.inference_mode():\n    output = model(input)",
            "risk": "low",
            "tradeoff": "More efficient than no_grad but requires PyTorch 1.9+",
            "test_recommendation": "Test with torch.use_deterministic_algorithms()",
        },
    },

    # ML005: Missing random seed for reproducibility
    "ML005": {
        "primary": {
            "title": "Add torch.manual_seed",
            "description": "Set torch manual seed for reproducibility",
            "new_code": "torch.manual_seed(42)\nnp.random.seed(42)\nimport random\nrandom.seed(42)",
            "risk": "low",
            "tradeoff": "Simple fix, consider making seed configurable",
            "test_recommendation": "Run training twice, verify identical results",
        },
        "alternative_1": {
            "title": "Create reproducibility helper",
            "description": "Use a helper that sets all random seeds comprehensively",
            "new_code": "def set_reproducible(seed=42):\n    import torch, numpy as np, random, os\n    os.environ['PYTHONHASHSEED'] = str(seed)\n    torch.manual_seed(seed)\n    torch.cuda.manual_seed(seed)\n    np.random.seed(seed)\n    random.seed(seed)\n    if torch.cuda.is_available():\n        torch.backends.cudnn.deterministic = True",
            "risk": "low",
            "tradeoff": "More comprehensive, handles CUDA and cudnn",
            "test_recommendation": "Verify with torch.use_deterministic_algorithms()",
        },
    },

    # ML006: Hardcoded ML config (hyperparameters, paths)
    "ML006": {
        "primary": {
            "title": "Load from config/args",
            "description": "Replace hardcoded values with config or argparse",
            "new_code": "# Replace hardcoded value with:\nbatch_size = args.batch_size if args.batch_size else 32",
            "risk": "low",
            "tradeoff": "Makes training more flexible, requires CLI/config setup",
            "test_recommendation": "Test with different batch_size values",
        },
        "alternative_1": {
            "title": "Use environment variables",
            "description": "Load from environment variables with defaults",
            "new_code": "import os\nbatch_size = int(os.getenv('BATCH_SIZE', '32'))",
            "risk": "low",
            "tradeoff": "Good for containerized training, simple to override",
            "test_recommendation": "Verify env var override works",
        },
    },

    # ML007: Gradient accumulation errors
    "ML007": {
        "primary": {
            "title": "Add gradient accumulation condition",
            "description": "Add conditional step() based on accumulation_steps",
            "new_code": "if (step + 1) % accumulation_steps == 0:\n    optimizer.step()\n    optimizer.zero_grad()",
            "risk": "medium",
            "tradeoff": "Corrects the accumulation logic",
            "test_recommendation": "Verify effective batch size equals accumulation_steps * batch_size",
        },
        "alternative_1": {
            "title": "Use accumulate_steps from Lightning",
            "description": "If using PyTorch Lightning, use built-in gradient accumulation",
            "new_code": "# In Lightning trainer:\ntrainer = Trainer(accumulate_grad_batches=accumulation_steps)",
            "risk": "low",
            "tradeoff": "Cleaner code, Lightning handles the logic",
            "test_recommendation": "Verify logging shows correct effective batch size",
        },
    },

    # ML008: Wrong optimizer (Adam with weight_decay)
    "ML008": {
        "primary": {
            "title": "Switch to AdamW optimizer",
            "description": "Use AdamW instead of Adam for proper L2 regularization",
            "new_code": "optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)",
            "risk": "medium",
            "tradeoff": "AdamW has decoupled weight decay, different behavior from Adam+weight_decay",
            "test_recommendation": "Compare training curves, may need to tune weight_decay value",
        },
        "alternative_1": {
            "title": "Adjust weight_decay with Adam",
            "description": "Keep Adam but use lower weight_decay value",
            "new_code": "optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=0.001)",
            "risk": "low",
            "tradeoff": "Quick fix, but Adam's L2 is not true weight decay",
            "test_recommendation": "Verify regularization effect is as expected",
        },
    },

    # ML009: Augmentation in eval mode
    "ML009": {
        "primary": {
            "title": "Remove augmentation from eval loader",
            "description": "Set transforms to None or identity for val/test loaders",
            "new_code": "# val_loader with no augmentation:\nval_loader = DataLoader(val_dataset, transform=None)",
            "risk": "medium",
            "tradeoff": "Simple removal, ensures consistent predictions",
            "test_recommendation": "Compare predictions with and without augmentation",
        },
        "alternative_1": {
            "title": "Create separate transforms",
            "description": "Define explicit train/val transforms",
            "new_code": "train_transform = transforms.Compose([...])\nval_transform = transforms.Compose([transforms.ToTensor()])\ntrain_dataset = Dataset(transform=train_transform)\nval_dataset = Dataset(transform=val_transform)",
            "risk": "low",
            "tradeoff": "More explicit, easier to maintain",
            "test_recommendation": "Verify val predictions are deterministic",
        },
    },

    # ML010: NaN/Inf propagation
    "ML010": {
        "primary": {
            "title": "Add safety checks for division",
            "description": "Add explicit checks for division by zero or NaN values",
            "new_code": "result = torch.where(\n    (denominator != 0) & (~torch.isnan(denominator)),\n    numerator / denominator,\n    torch.zeros_like(numerator)\n)",
            "risk": "low",
            "tradeoff": "Handles edge cases, adds small overhead",
            "test_recommendation": "Test with edge case inputs (zeros, NaN, Inf)",
        },
        "alternative_1": {
            "title": "Use safe division utility",
            "description": "Create or use a safe division function",
            "new_code": "def safe_divide(a, b, fill_value=0.0):\n    return torch.where(b != 0, a / b, fill_value)",
            "risk": "low",
            "tradeoff": "Reusable utility, consistent across codebase",
            "test_recommendation": "Add unit tests for the utility function",
        },
    },

    # ML011: LR scheduler stepped before optimizer
    "ML011": {
        "primary": {
            "title": "Move scheduler.step() after optimizer.step()",
            "description": "Correct the order of scheduler and optimizer steps",
            "new_code": "# Correct order:\nloss.backward()\noptimizer.step()\nscheduler.step()  # Step AFTER optimizer",
            "risk": "medium",
            "tradeoff": "Corrects the scheduling logic",
            "test_recommendation": "Verify LR follows expected schedule",
        },
        "alternative_1": {
            "title": "Use scheduler with optimizer reference",
            "description": "Pass optimizer to scheduler for automatic stepping",
            "new_code": "scheduler = torch.optim.lr_scheduler.OneCycleLR(\n    optimizer, max_lr=lr, total_steps=num_steps\n)\n# scheduler.step() is called automatically after optimizer.step()",
            "risk": "medium",
            "tradeoff": "OneCycleLR handles stepping automatically",
            "test_recommendation": "Verify LR schedule matches intended curve",
        },
    },

    # ML012: BatchNorm with small batch size
    "ML012": {
        "primary": {
            "title": "Switch to GroupNorm",
            "description": "Replace BatchNorm with GroupNorm for small batch sizes",
            "new_code": "# Instead of nn.BatchNorm2d(num_features)\nnn.GroupNorm(num_groups=32, num_channels=num_features)",
            "risk": "medium",
            "tradeoff": "GroupNorm is independent of batch size but may need tuning num_groups",
            "test_recommendation": "Compare validation accuracy with BatchNorm",
        },
        "alternative_1": {
            "title": "Use SyncBatchNorm for multi-GPU",
            "description": "Use SyncBatchNorm to aggregate batch statistics across GPUs",
            "new_code": "nn.SyncBatchNorm(num_features)  # Use with DistributedDataParallel",
            "risk": "medium",
            "tradeoff": "Requires multi-GPU setup, increases communication overhead",
            "test_recommendation": "Verify batch statistics are synchronized across GPUs",
        },
    },

    # ML013: DDP sync issues
    "ML013": {
        "primary": {
            "title": "Fix DDP device placement order",
            "description": "Move .cuda() outside DistributedDataParallel",
            "new_code": "model = model.cuda()\nmodel = DistributedDataParallel(model)",
            "risk": "medium",
            "tradeoff": "Ensures proper state dict synchronization",
            "test_recommendation": "Run with torchrun and verify gradients match across ranks",
        },
        "alternative_1": {
            "title": "Use device_ids for single-node DDP",
            "description": "Pass local_rank device explicitly",
            "new_code": "model = DistributedDataParallel(model, device_ids=[local_rank])",
            "risk": "low",
            "tradeoff": "Explicit device handling for single-node multi-GPU",
            "test_recommendation": "Test with different local_rank values",
        },
    },

    # ML014: Mixed precision without GradScaler
    "ML014": {
        "primary": {
            "title": "Add GradScaler for loss scaling",
            "description": "Use GradScaler to prevent gradient underflow in mixed precision",
            "new_code": "scaler = GradScaler()\nwith autocast():\n    loss = criterion(output, target)\nscaler.scale(loss).backward()\nscaler.step(optimizer)\nscaler.update()",
            "risk": "medium",
            "tradeoff": "Required for stable mixed precision training",
            "test_recommendation": "Monitor loss for underflow, adjust init_scale if needed",
        },
        "alternative_1": {
            "title": "Disable loss scaling for inference",
            "description": "Only use autocast for inference, not training",
            "new_code": "# For inference only:\nwith autocast():\n    output = model(input)\n# Loss scaling not needed for inference",
            "risk": "low",
            "tradeoff": "Simpler for inference-only use case",
            "test_recommendation": "Verify output precision is acceptable",
        },
    },

    # ML015: Early stopping logic bugs
    "ML015": {
        "primary": {
            "title": "Monitor validation metric correctly",
            "description": "Track validation metric instead of training loss",
            "new_code": "if mode == 'min':\n    if current_metric < best_metric:\n        best_metric = current_metric\n        patience_counter = 0\nelse:\n    if current_metric > best_metric:\n        best_metric = current_metric\n        patience_counter = 0",
            "risk": "low",
            "tradeoff": "Correctly monitors validation performance",
            "test_recommendation": "Verify early stopping triggers at right time",
        },
        "alternative_1": {
            "title": "Use PyTorch Lightning EarlyStopping",
            "description": "Leverage built-in early stopping callback",
            "new_code": "from pytorch_lightning import LightningModule, Trainer\nfrom pytorch_lightning.callbacks import EarlyStopping\n\ncallback = EarlyStopping(\n    monitor='val_loss',\n    mode='min',\n    patience=10\n)\ntrainer = Trainer(callbacks=[callback])",
            "risk": "low",
            "tradeoff": "Cleaner implementation, well-tested",
            "test_recommendation": "Verify callback behavior matches expectations",
        },
    },
}


def get_template(rule_id: str) -> dict[str, dict[str, Any]] | None:
    """Get fix templates for a rule ID.

    Args:
        rule_id: Rule identifier (e.g., "ML001", "ML002")

    Returns:
        Dictionary of templates or None if not found
    """
    return FIX_TEMPLATES.get(rule_id)


def get_primary_option(rule_id: str) -> dict[str, Any] | None:
    """Get the primary fix option for a rule.

    Args:
        rule_id: Rule identifier

    Returns:
        Primary fix option or None if not found
    """
    templates = get_template(rule_id)
    if templates:
        return templates.get("primary")
    return None


def get_all_options(rule_id: str) -> list[dict[str, Any]]:
    """Get all fix options for a rule.

    Args:
        rule_id: Rule identifier

    Returns:
        List of all fix options
    """
    templates = get_template(rule_id)
    if templates:
        return list(templates.values())
    return []
