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
            "old_code": "# WRONG ORDER - Data leakage!\n# Fit scaler on ALL data before split\nscaler.fit(X)  # ← Leaks information from test set!\nX_train, X_test, y_train, y_test = train_test_split(X, y)",
            "new_code": "# CORRECT ORDER - No data leakage\nX_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)\nscaler.fit(X_train)\nX_train_scaled = scaler.fit_transform(X_train)\nX_test_scaled = scaler.transform(X_test)",
            "severity": "CRITICAL",
            "line_context": "scaler.fit() must be called AFTER train_test_split(), fitting only on training data",
            "risk": "low",
            "tradeoff": "Simple fix, only affects preprocessing step",
            "test_recommendation": "Verify test accuracy is no longer inflated",
        },
        "alternative_1": {
            "title": "Use sklearn Pipeline",
            "description": "Wrap preprocessing in sklearn Pipeline to prevent leakage",
            "old_code": "# Manual preprocessing (prone to leakage)\nscaler = StandardScaler()\nscaler.fit(X)\nX_scaled = scaler.transform(X)",
            "new_code": "from sklearn.pipeline import Pipeline\npipeline = Pipeline([\n    ('scaler', StandardScaler())\n])\npipeline.fit(X_train)\nX_train_scaled = pipeline.transform(X_train)\nX_test_scaled = pipeline.transform(X_test)",
            "severity": "HIGH",
            "line_context": "Use Pipeline to automatically prevent leakage in cross-validation",
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
            "old_code": "# WRONG - CrossEntropyLoss for multi-label\ncriterion = nn.CrossEntropyLoss()\n# Multi-label targets should be independent",
            "new_code": "# CORRECT - BCEWithLogitsLoss for multi-label\ncriterion = nn.BCEWithLogitsLoss()\n# Targets should be 0/1 independent labels",
            "severity": "HIGH",
            "line_context": "CrossEntropyLoss expects mutually exclusive classes; use BCEWithLogitsLoss for multi-label",
            "risk": "medium",
            "tradeoff": "Requires sigmoid activation on output if not already present",
            "test_recommendation": "Verify multi-label accuracy metric",
        },
        "alternative_1": {
            "title": "Use MultiLabelBinarizer preprocessing",
            "description": "Keep CrossEntropyLoss but preprocess targets with MultiLabelBinarizer",
            "old_code": "# Raw multi-label targets (wrong format for CrossEntropyLoss)\ny_multi = ['cat', 'dog', 'brown']  # Multi-label strings",
            "new_code": "from sklearn.preprocessing import MultiLabelBinarizer\nmlb = MultiLabelBinarizer()\ny_encoded = mlb.fit_transform(y_multi)\n# Now y_encoded is binary matrix for CrossEntropyLoss",
            "severity": "MEDIUM",
            "line_context": "Preprocess multi-label to one-hot encoding for CrossEntropyLoss compatibility",
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
            "old_code": "# WRONG - Device mismatch\ndata = data.to(device)  # Data on GPU\noutput = model(data)  # Model on CPU → RuntimeError",
            "new_code": "# CORRECT - Consistent device placement\nmodel = model.to(device)  # Move model first\ndata = data.to(device)  # Then move data\noutput = model(data)",
            "severity": "HIGH",
            "line_context": "model.to(device) must be called BEFORE data.to(device) or they may be on different devices",
            "risk": "low",
            "tradeoff": "Simple fix, verify no other device mismatches exist",
            "test_recommendation": "Run with CUDA_LAUNCH_BLOCKING=1 for debugging",
        },
        "alternative_1": {
            "title": "Create unified device helper",
            "description": "Use a helper function to ensure consistent device placement",
            "old_code": "# Manual device placement (error-prone)\nmodel = MyModel().cuda()\ndata = data.to('cuda:0')\noutput = model(data)",
            "new_code": "def to_device(obj, device):\n    \"\"\"Move tensor or model to device if possible.\"\"\"\n    if hasattr(obj, 'to'):\n        return obj.to(device)\n    return obj\n\nmodel = to_device(model, device)\ndata = to_device(data, device)",
            "severity": "MEDIUM",
            "line_context": "Use helper function to ensure all objects move to the same device consistently",
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
            "old_code": "# WRONG - Gradients computed during inference (wastes memory)\noutput = model(input)  # Stores computation graph",
            "new_code": "# CORRECT - No gradients during inference\nwith torch.no_grad():\n    output = model(input)\n# Memory is not retained for backprop",
            "severity": "MEDIUM",
            "line_context": "Wrap inference code with torch.no_grad() to prevent gradient computation and memory accumulation",
            "risk": "low",
            "tradeoff": "Simple fix, prevents memory accumulation in inference",
            "test_recommendation": "Verify memory usage during inference",
        },
        "alternative_1": {
            "title": "Use torch.inference_mode()",
            "description": "Use inference_mode() for better performance if PyTorch 1.9+",
            "old_code": "# Using no_grad (works but less optimized)\nwith torch.no_grad():\n    output = model(input)",
            "new_code": "# PyTorch 1.9+ - inference_mode() is faster\nwith torch.inference_mode():\n    output = model(input)\n# More efficient than no_grad, prevents grad accumulation",
            "severity": "LOW",
            "line_context": "torch.inference_mode() is more efficient than torch.no_grad() for inference (PyTorch 1.9+)",
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
            "old_code": "# WRONG - No seed set (non-deterministic)\nimport torch\nmodel = MyModel()\ntrainer.fit(model)  # Different results each run",
            "new_code": "# CORRECT - Set all random seeds\nimport torch\nimport numpy as np\nimport random\nimport os\n\ndef set_seed(seed=42):\n    os.environ['PYTHONHASHSEED'] = str(seed)\n    torch.manual_seed(seed)\n    torch.cuda.manual_seed(seed)\n    np.random.seed(seed)\n    random.seed(seed)\n    if torch.cuda.is_available():\n        torch.backends.cudnn.deterministic = True\n\nset_seed(42)",
            "severity": "MEDIUM",
            "line_context": "Set all random seeds before model initialization and data loading for reproducibility",
            "risk": "low",
            "tradeoff": "Simple fix, consider making seed configurable",
            "test_recommendation": "Run training twice, verify identical results",
        },
        "alternative_1": {
            "title": "Create reproducibility helper",
            "description": "Use a helper that sets all random seeds comprehensively",
            "old_code": "# Only setting torch seed (incomplete)\ntorch.manual_seed(42)\n# numpy, random, CUDA still non-deterministic",
            "new_code": "def set_reproducible(seed=42):\n    import torch, numpy as np, random, os\n    os.environ['PYTHONHASHSEED'] = str(seed)\n    torch.manual_seed(seed)\n    torch.cuda.manual_seed(seed)\n    np.random.seed(seed)\n    random.seed(seed)\n    if torch.cuda.is_available():\n        torch.backends.cudnn.deterministic = True\n        torch.backends.cudnn.benchmark = False",
            "severity": "MEDIUM",
            "line_context": "Comprehensive seed setting including CUDA for full reproducibility",
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
            "old_code": "# WRONG - Hardcoded hyperparameters\nBATCH_SIZE = 32\nLEARNING_RATE = 0.001\nEPOCHS = 100\nmodel.train(batch_size=32, lr=0.001)",
            "new_code": "# CORRECT - Load from args/config\nimport argparse\nparser = argparse.ArgumentParser()\nparser.add_argument('--batch_size', type=int, default=32)\nparser.add_argument('--lr', type=float, default=0.001)\nparser.add_argument('--epochs', type=int, default=100)\nargs = parser.parse_args()\n\nmodel.train(batch_size=args.batch_size, lr=args.lr)",
            "severity": "LOW",
            "line_context": "Replace hardcoded hyperparameters with command-line args or config file",
            "risk": "low",
            "tradeoff": "Makes training more flexible, requires CLI/config setup",
            "test_recommendation": "Test with different batch_size values",
        },
        "alternative_1": {
            "title": "Use environment variables",
            "description": "Load from environment variables with defaults",
            "old_code": "# Hardcoded paths/values\nDATA_PATH = '/home/user/data'\nBATCH_SIZE = 32",
            "new_code": "import os\nDATA_PATH = os.getenv('DATA_PATH', '/data')\nBATCH_SIZE = int(os.getenv('BATCH_SIZE', '32'))\nLEARNING_RATE = float(os.getenv('LR', '0.001'))",
            "severity": "LOW",
            "line_context": "Use environment variables with sensible defaults for containerized training",
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
            "old_code": "# WRONG - Optimizer steps every batch\nfor batch in dataloader:\n    loss = compute_loss(batch)\n    loss.backward()\n    optimizer.step()  # ← Wrong: steps too frequently\n    optimizer.zero_grad()",
            "new_code": "# CORRECT - Gradient accumulation\naccumulation_steps = 4\nfor step, batch in enumerate(dataloader):\n    loss = compute_loss(batch)\n    loss.backward()\n    \n    if (step + 1) % accumulation_steps == 0:\n        optimizer.step()\n        optimizer.zero_grad()",
            "severity": "HIGH",
            "line_context": "optimizer.step() should be called only every accumulation_steps batches",
            "risk": "medium",
            "tradeoff": "Corrects the accumulation logic",
            "test_recommendation": "Verify effective batch size equals accumulation_steps * batch_size",
        },
        "alternative_1": {
            "title": "Use accumulate_steps from Lightning",
            "description": "If using PyTorch Lightning, use built-in gradient accumulation",
            "old_code": "# Manual gradient accumulation (error-prone)\naccumulation_steps = 4",
            "new_code": "# In Lightning trainer:\ntrainer = Trainer(\n    accumulate_grad_batches=4,\n    ...\n)\n# Lightning handles the logic automatically",
            "severity": "MEDIUM",
            "line_context": "Use PyTorch Lightning's built-in gradient accumulation for cleaner code",
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
            "old_code": "# WRONG - Adam with weight_decay (L2, not true weight decay)\noptimizer = torch.optim.Adam(\n    model.parameters(),\n    lr=0.001,\n    weight_decay=0.01  # ← L2 regularization, affects all parameters equally\n)",
            "new_code": "# CORRECT - AdamW with decoupled weight decay\noptimizer = torch.optim.AdamW(\n    model.parameters(),\n    lr=0.001,\n    weight_decay=0.01  # ← True weight decay, better regularization\n)",
            "severity": "MEDIUM",
            "line_context": "AdamW has decoupled weight decay; prefer over Adam with weight_decay for better regularization",
            "risk": "medium",
            "tradeoff": "AdamW has decoupled weight decay, different behavior from Adam+weight_decay",
            "test_recommendation": "Compare training curves, may need to tune weight_decay value",
        },
        "alternative_1": {
            "title": "Adjust weight_decay with Adam",
            "description": "Keep Adam but use lower weight_decay value",
            "old_code": "# Standard Adam with L2\noptimizer = torch.optim.Adam(model.parameters(), weight_decay=0.1)",
            "new_code": "# Lower weight_decay for Adam\noptimizer = torch.optim.Adam(\n    model.parameters(),\n    lr=0.001,\n    weight_decay=0.001  # Lower value since Adam's L2 is stronger\n)",
            "severity": "LOW",
            "line_context": "If using Adam, reduce weight_decay value as Adam's L2 is more aggressive",
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
            "old_code": "# WRONG - Augmentation applied during evaluation\nval_loader = DataLoader(\n    val_dataset,\n    transform=train_transform  # ← Augmentation in eval!\n)",
            "new_code": "# CORRECT - No augmentation in evaluation\nval_transform = transforms.Compose([\n    transforms.ToTensor(),\n])\nval_loader = DataLoader(\n    val_dataset,\n    transform=val_transform  # No augmentation\n)",
            "severity": "MEDIUM",
            "line_context": "Set transforms to None or ToTensor-only for val/test loaders",
            "risk": "medium",
            "tradeoff": "Simple removal, ensures consistent predictions",
            "test_recommendation": "Compare predictions with and without augmentation",
        },
        "alternative_1": {
            "title": "Create separate transforms",
            "description": "Define explicit train/val transforms",
            "old_code": "# Shared transform (risky)\ntrain_transform = val_transform = some_transform",
            "new_code": "train_transform = transforms.Compose([\n    transforms.RandomHorizontalFlip(),\n    transforms.ToTensor(),\n    transforms.Normalize(mean, std),\n])\n\nval_transform = transforms.Compose([\n    transforms.ToTensor(),\n    transforms.Normalize(mean, std),\n])\n\ntrain_dataset = Dataset(transform=train_transform)\nval_dataset = Dataset(transform=val_transform)",
            "severity": "LOW",
            "line_context": "Use separate transforms for train/val to explicitly control augmentation",
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
            "old_code": "# WRONG - Division without safety checks\nresult = numerator / denominator  # ← Can be inf or NaN",
            "new_code": "# CORRECT - Safe division\nresult = torch.where(\n    (denominator != 0) & (~torch.isnan(denominator)) & (~torch.isinf(denominator)),\n    numerator / denominator,\n    torch.zeros_like(numerator)\n)",
            "severity": "HIGH",
            "line_context": "Check for zero, NaN, and Inf before division to prevent NaN/Inf propagation",
            "risk": "low",
            "tradeoff": "Handles edge cases, adds small overhead",
            "test_recommendation": "Test with edge case inputs (zeros, NaN, Inf)",
        },
        "alternative_1": {
            "title": "Use safe division utility",
            "description": "Create or use a safe division function",
            "old_code": "# Direct division (risky)\nresult = a / b",
            "new_code": "def safe_divide(a, b, fill_value=0.0, eps=1e-8):\n    \"\"\"Division with NaN/Inf protection.\"\"\"\n    b_safe = torch.where(torch.abs(b) < eps, torch.ones_like(b), b)\n    result = a / b_safe\n    return torch.where(torch.isfinite(result), result, fill_value)\n\nresult = safe_divide(numerator, denominator)",
            "severity": "MEDIUM",
            "line_context": "Use utility function for consistent NaN/Inf handling across codebase",
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
            "old_code": "# WRONG ORDER - Scheduler stepped before optimizer\nfor epoch in range(num_epochs):\n    for batch in dataloader:\n        loss = compute_loss(batch)\n        scheduler.step()  # ← WRONG: Step BEFORE optimizer\n        loss.backward()\n        optimizer.step()\n        optimizer.zero_grad()",
            "new_code": "# CORRECT ORDER - Scheduler stepped after optimizer\nfor epoch in range(num_epochs):\n    for batch in dataloader:\n        loss = compute_loss(batch)\n        loss.backward()\n        optimizer.step()\n        optimizer.zero_grad()\n        scheduler.step()  # ← CORRECT: Step AFTER optimizer",
            "severity": "HIGH",
            "line_context": "scheduler.step() must be called AFTER optimizer.step() to update LR after parameter update",
            "risk": "medium",
            "tradeoff": "Corrects the scheduling logic",
            "test_recommendation": "Verify LR follows expected schedule",
        },
        "alternative_1": {
            "title": "Use scheduler with optimizer reference",
            "description": "Pass optimizer to scheduler for automatic stepping",
            "old_code": "# Manual scheduler stepping (error-prone)\noptimizer.step()\nscheduler.step()",
            "new_code": "from torch.optim.lr_scheduler import OneCycleLR\n\nscheduler = OneCycleLR(\n    optimizer,\n    max_lr=0.01,\n    total_steps=num_steps,\n    pct_start=0.3,\n)\n# scheduler.step() is called automatically after optimizer.step()\n# when used with OneCycleLR or StepLR without explicit calls",
            "severity": "MEDIUM",
            "line_context": "Use OneCycleLR or similar schedulers that integrate with optimizer lifecycle",
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
            "old_code": "# WRONG - BatchNorm with small batch (< 16)\nmodel = nn.Sequential(\n    nn.Conv2d(3, 64, 3),\n    nn.BatchNorm2d(64),  # ← Poor statistics with small batch\n    nn.ReLU(),\n)",
            "new_code": "# CORRECT - GroupNorm (independent of batch size)\nmodel = nn.Sequential(\n    nn.Conv2d(3, 64, 3),\n    nn.GroupNorm(num_groups=8, num_channels=64),  # Better for small batches\n    nn.ReLU(),\n)",
            "severity": "MEDIUM",
            "line_context": "BatchNorm statistics are unreliable with batch size < 16; use GroupNorm instead",
            "risk": "medium",
            "tradeoff": "GroupNorm is independent of batch size but may need tuning num_groups",
            "test_recommendation": "Compare validation accuracy with BatchNorm",
        },
        "alternative_1": {
            "title": "Use SyncBatchNorm for multi-GPU",
            "description": "Use SyncBatchNorm to aggregate batch statistics across GPUs",
            "old_code": "# Single-GPU BatchNorm (small effective batch)\nmodel = nn.BatchNorm2d(num_features)",
            "new_code": "from torch.nn import SyncBatchNorm\n\n# SyncBatchNorm aggregates stats across GPUs\nmodel = nn.Sequential(\n    nn.Conv2d(3, 64, 3),\n    SyncBatchNorm(64),  # Use with DistributedDataParallel\n    nn.ReLU(),\n)",
            "severity": "MEDIUM",
            "line_context": "SyncBatchNorm aggregates batch statistics across GPUs for better normalization",
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
            "old_code": "# WRONG - Device placement inside DDP\nmodel = DistributedDataParallel(model.cuda())  # ← Wrong order",
            "new_code": "# CORRECT - Device placement before DDP wrapping\nmodel = model.cuda()  # Move to device first\nmodel = DistributedDataParallel(model)\n# DDP expects model already on device",
            "severity": "HIGH",
            "line_context": "Move .cuda() BEFORE wrapping with DistributedDataParallel for proper state dict sync",
            "risk": "medium",
            "tradeoff": "Ensures proper state dict synchronization",
            "test_recommendation": "Run with torchrun and verify gradients match across ranks",
        },
        "alternative_1": {
            "title": "Use device_ids for single-node DDP",
            "description": "Pass local_rank device explicitly",
            "old_code": "# No device_ids specified\nmodel = DistributedDataParallel(model)",
            "new_code": "import os\nlocal_rank = int(os.environ.get('LOCAL_RANK', 0))\n\nmodel = DistributedDataParallel(\n    model,\n    device_ids=[local_rank],\n    output_device=local_rank,\n)",
            "severity": "MEDIUM",
            "line_context": "Specify device_ids for single-node multi-GPU to ensure proper device placement",
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
            "old_code": "# WRONG - Mixed precision without GradScaler\nwith autocast():\n    loss = criterion(output, target)\nloss.backward()  # ← Gradient underflow risk without GradScaler\noptimizer.step()",
            "new_code": "# CORRECT - Mixed precision with GradScaler\nscaler = GradScaler()\n\nwith autocast():\n    loss = criterion(output, target)\n\nscaler.scale(loss).backward()  # Scale loss to prevent underflow\nscaler.step(optimizer)  # Unscale gradients\nscaler.update()  # Update scale factor",
            "severity": "HIGH",
            "line_context": "Use GradScaler with autocast to prevent gradient underflow in mixed precision training",
            "risk": "medium",
            "tradeoff": "Required for stable mixed precision training",
            "test_recommendation": "Monitor loss for underflow, adjust init_scale if needed",
        },
        "alternative_1": {
            "title": "Disable loss scaling for inference",
            "description": "Only use autocast for inference, not training",
            "old_code": "# Mixed precision during training (needs GradScaler)\nwith autocast():\n    loss = criterion(output, target)\nloss.backward()",
            "new_code": "# For inference only - GradScaler not needed\nwith autocast():\n    output = model(input)\n# Loss scaling not needed for inference",
            "severity": "LOW",
            "line_context": "GradScaler is only needed during training; inference can use autocast alone",
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
            "old_code": "# WRONG - Monitoring training loss\nbest_loss = float('inf')\nfor epoch in range(num_epochs):\n    train_loss = train_epoch(model)\n    if train_loss < best_loss:  # ← Wrong: monitoring train loss\n        best_loss = train_loss\n        save_model(model)",
            "new_code": "# CORRECT - Monitor validation metric\nbest_metric = float('inf') if mode == 'min' else float('-inf')\nfor epoch in range(num_epochs):\n    val_loss = validate(model)\n    \n    if mode == 'min':\n        if val_loss < best_metric:\n            best_metric = val_loss\n            patience_counter = 0\n            save_model(model)\n        else:\n            patience_counter += 1\n    else:  # mode == 'max'\n        if val_loss > best_metric:\n            best_metric = val_loss\n            patience_counter = 0\n            save_model(model)\n        else:\n            patience_counter += 1\n    \n    if patience_counter >= patience:\n        print(f\"Early stopping at epoch {epoch}\")\n        break",
            "severity": "HIGH",
            "line_context": "Monitor validation metric (not training loss) for early stopping to prevent overfitting",
            "risk": "low",
            "tradeoff": "Correctly monitors validation performance",
            "test_recommendation": "Verify early stopping triggers at right time",
        },
        "alternative_1": {
            "title": "Use PyTorch Lightning EarlyStopping",
            "description": "Leverage built-in early stopping callback",
            "old_code": "# Manual early stopping (error-prone)\nbest_loss = float('inf')\npatience_counter = 0",
            "new_code": "from pytorch_lightning import LightningModule, Trainer\nfrom pytorch_lightning.callbacks import EarlyStopping\n\ncallback = EarlyStopping(\n    monitor='val_loss',\n    mode='min',  # or 'max' for metrics like accuracy\n    patience=10,\n    verbose=True,\n)\n\ntrainer = Trainer(callbacks=[callback])",
            "severity": "LOW",
            "line_context": "Use PyTorch Lightning's EarlyStopping callback for robust, well-tested implementation",
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
