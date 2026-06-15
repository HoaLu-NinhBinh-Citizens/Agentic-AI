"""Extended ML rules (ML016-ML025) for advanced ML bug detection.

This module provides additional ML-specific rules for:
- ML016: Gradient checkpointing for large models
- ML017: Learning rate scaling with batch size
- ML018: Learning rate warmup
- ML019: Model EMA
- ML020: Mixed precision
- ML021: Gradient accumulation
- ML022: DataLoader optimization
- ML023: Validation during training
- ML024: Early stopping
- ML025: Inference mode (model.eval)

Usage:
    from src.infrastructure.analysis.ml_detectors.extended_rules import (
        check_extended_rules,
        ML_EXTENDED_RULES,
    )

    findings = check_extended_rules(code)
    for f in findings:
        print(f"{f['rule_id']}: {f['name']}")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MLExtendedRule:
    """Extended ML rule definition."""

    rule_id: str
    name: str
    severity: str  # CRITICAL/HIGH/MEDIUM/LOW
    patterns: list[str]
    fix_template: str
    explanation: str
    confidence: float = 0.85
    message: str = ""


ML_EXTENDED_RULES: dict[str, MLExtendedRule] = {
    "ML016": MLExtendedRule(
        rule_id="ML016",
        name="Gradient Checkpointing Missing for Large Models",
        severity="MEDIUM",
        patterns=[
            r"(?:BertLarge|TransformerLarge|LLaMA|GPT|model\s*=\s*.*[Ll]arge)",
            r"n_params\s*(?:>|=)\s*1e[89]",
            r"build_large_model",
        ],
        fix_template="""# Enable gradient_checkpointing for memory efficiency with large models
from torch.utils.checkpoint import checkpoint_sequential

# For HuggingFace transformers:
model.gradient_checkpointing_enable()

# For custom models with sequential layers:
# outputs = checkpoint_sequential(model.layers, segments=2, input=x)

# For manual checkpointing:
from torch.utils.checkpoint import checkpoint
def forward(self, x):
    x = checkpoint(self.layer1, x)
    x = checkpoint(self.layer2, x)
    return x

# This reduces memory by ~50% at the cost of ~20% slower training.""",
        explanation="Large models (>100M params) consume massive GPU memory during backpropagation. Gradient checkpointing trades compute for memory by recomputing intermediate activations instead of storing them.",
        confidence=0.82,
        message="Large model detected without gradient checkpointing",
    ),

    "ML017": MLExtendedRule(
        rule_id="ML017",
        name="Learning Rate Not Scaled with Batch Size",
        severity="HIGH",
        patterns=[
            r"batch_size\s*=\s*(?:12[89]|[2-9]\d{2}|\d{4,})\s*\n(?:.*\n)*?.*lr\s*=",
            r"batch_size\s*=\s*(?:12[89]|[2-9]\d{2}|\d{4,})(?:.*\n)*?.*(?:optimizer|Adam|SGD)",
        ],
        fix_template="""# Scale learning rate linearly with batch size
# Linear scaling rule: lr_new = lr_base * (batch_size / base_batch_size)
base_batch_size = 32
base_lr = 0.001

# Linear scaling
lr = base_lr * (batch_size / base_batch_size)

# Or use square root scaling (more conservative):
# lr = base_lr * math.sqrt(batch_size / base_batch_size)

optimizer = AdamW(model.parameters(), lr=lr)

# With warmup for large batch training:
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=int(0.1 * total_steps),
    num_training_steps=total_steps,
)""",
        explanation="When batch size increases significantly (>128), the learning rate should be scaled proportionally. Without scaling, large batches effectively reduce the learning rate, slowing convergence.",
        confidence=0.85,
        message="Large batch size without learning rate scaling detected",
    ),

    "ML018": MLExtendedRule(
        rule_id="ML018",
        name="Learning Rate Warmup Missing",
        severity="HIGH",
        patterns=[
            r"(?:Adam|AdamW|SGD)\s*\(.*lr\s*=.*\)\s*\n(?:.*\n)*?.*for\s+epoch\s+in\s+range\(\d{2,}\)",
            r"optimizer\s*=\s*(?:Adam|AdamW|SGD)\(.*\)\s*\n(?:.*\n)*?.*(?:for|while).*(?:epoch|step)",
            r"lr\s*=\s*\d+\.\d+\s*\n(?:.*\n)*?.*for\s+epoch",
        ],
        fix_template="""# Add learning rate warmup to stabilize early training
from torch.optim.lr_scheduler import LinearLR, CosineAnnealingLR, SequentialLR

optimizer = AdamW(model.parameters(), lr=0.001)

# Option 1: Linear warmup + cosine decay
warmup_epochs = 5
warmup_scheduler = LinearLR(optimizer, start_factor=0.1, total_iters=warmup_epochs)
main_scheduler = CosineAnnealingLR(optimizer, T_max=num_epochs - warmup_epochs)
scheduler = SequentialLR(optimizer, [warmup_scheduler, main_scheduler], milestones=[warmup_epochs])

# Option 2: Using transformers library
from transformers import get_linear_schedule_with_warmup
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=1000,
    num_training_steps=total_steps,
)

# In training loop:
for epoch in range(num_epochs):
    train_epoch(model)
    scheduler.step()""",
        explanation="Training without warmup can cause gradient explosion in the first few steps, especially with Adam/AdamW optimizers. Warmup gradually increases LR from a small value to target LR, stabilizing early training.",
        confidence=0.88,
        message="Training loop without learning rate warmup detected",
    ),

    "ML019": MLExtendedRule(
        rule_id="ML019",
        name="Model EMA Not Used",
        severity="MEDIUM",
        patterns=[
            r"for\s+epoch\s+in\s+range\(\d+\)\s*:(?:.*\n)*?.*(?:train|model)",
            r"model\.train\(\)(?:.*\n)*?.*(?:eval|validate)",
        ],
        fix_template="""# Exponential Moving Average (EMA) for better generalization
import torch
from torch.optim.swa_utils import AveragedModel
from copy import deepcopy

# Create EMA model
ema_model = AveragedModel(model)
ema_decay = 0.999

def update_ema(model, ema_model, decay=0.999):
    \"\"\"Update EMA weights.\"\"\"
    with torch.no_grad():
        for ema_p, model_p in zip(ema_model.parameters(), model.parameters()):
            ema_p.data.mul_(decay).add_(model_p.data, alpha=1.0 - decay)

# In training loop:
for epoch in range(num_epochs):
    model.train()
    for batch in train_loader:
        loss = criterion(model(batch), targets)
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        update_ema(model, ema_model, ema_decay)

    # Use EMA model for evaluation
    ema_model.eval()
    with torch.no_grad():
        val_metrics = evaluate(ema_model, val_loader)""",
        explanation="Model EMA maintains a moving average of model weights during training. It typically provides 0.5-2% improvement in final model performance and smoother convergence without additional training cost.",
        confidence=0.80,
        message="Training loop without model EMA detected",
    ),

    "ML020": MLExtendedRule(
        rule_id="ML020",
        name="Mixed Precision Not Used",
        severity="MEDIUM",
        patterns=[
            r"\.cuda\(\)(?:.*\n)*?.*(?:model|output|loss)",
            r"model\s*=.*\.cuda\(\)",
            r"model\(.*\.cuda\(\)\)",
        ],
        fix_template="""# Mixed precision training with torch.cuda.amp for ~2x speedup and ~50% memory reduction
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()
model = model.cuda()

for batch in dataloader:
    inputs, targets = batch[0].cuda(), batch[1].cuda()

    optimizer.zero_grad()

    # Forward pass in float16
    with autocast(dtype=torch.float16):
        outputs = model(inputs)
        loss = criterion(outputs, targets)

    # Backward pass with gradient scaling
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()

# For inference:
model.eval()
with torch.no_grad(), autocast(dtype=torch.float16):
    outputs = model(inputs)""",
        explanation="Mixed precision (FP16/BF16) reduces memory usage by ~50% and can speed up training 1.5-3x on modern GPUs (Volta+). torch.cuda.amp handles numeric stability automatically via gradient scaling.",
        confidence=0.85,
        message="GPU training without mixed precision detected",
    ),

    "ML021": MLExtendedRule(
        rule_id="ML021",
        name="Gradient Accumulation Issues",
        severity="CRITICAL",
        patterns=[
            r"loss\.backward\(\)\s*\n\s*optimizer\.step\(\)",
            r"backward\(\)(?:.*\n)*?.*optimizer\.step\(\)(?!.*accum)",
        ],
        fix_template="""# Proper gradient accumulation for effective large batch training
accumulation_steps = 4  # Effective batch = batch_size * accumulation_steps

optimizer.zero_grad()
for step, batch in enumerate(dataloader):
    inputs, targets = batch
    outputs = model(inputs)
    loss = criterion(outputs, targets)

    # CRITICAL: normalize loss by accumulation steps
    loss = loss / accumulation_steps
    loss.backward()

    if (step + 1) % accumulation_steps == 0:
        # Optional: gradient clipping before step
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        optimizer.zero_grad()

# Handle remaining gradients at end of epoch
if (step + 1) % accumulation_steps != 0:
    optimizer.step()
    optimizer.zero_grad()""",
        explanation="Gradient accumulation must normalize the loss by accumulation_steps to maintain correct gradient magnitudes. Without normalization, effective learning rate scales with accumulation steps, causing instability.",
        confidence=0.92,
        message="Gradient accumulation pattern without proper loss normalization",
    ),

    "ML022": MLExtendedRule(
        rule_id="ML022",
        name="DataLoader num_workers Too Low",
        severity="LOW",
        patterns=[
            r"DataLoader\s*\([^)]*num_workers\s*=\s*0",
            r"num_workers\s*=\s*0",
        ],
        fix_template="""# Optimize DataLoader for faster data loading
import os
from torch.utils.data import DataLoader

# Auto-detect optimal workers (CPU cores - 1, minimum 4)
num_workers = max(4, os.cpu_count() - 1) if os.cpu_count() else 4

train_loader = DataLoader(
    dataset,
    batch_size=batch_size,
    shuffle=True,
    num_workers=num_workers,
    pin_memory=True,           # Faster CPU->GPU transfer
    prefetch_factor=2,         # Prefetch N batches per worker
    persistent_workers=True,   # Keep workers alive between epochs
    drop_last=True,            # Consistent batch sizes
)

# Enable cuDNN benchmark for consistent input sizes:
torch.backends.cudnn.benchmark = True""",
        explanation="Setting num_workers=0 means data loading happens in the main process, creating a CPU bottleneck. Parallel workers (typically CPU_cores - 1) significantly speed up data loading.",
        confidence=0.80,
        message="DataLoader using num_workers=0 (single process data loading)",
    ),

    "ML023": MLExtendedRule(
        rule_id="ML023",
        name="No Validation During Training",
        severity="HIGH",
        patterns=[
            r"for\s+epoch\s+in\s+range\(\d+\)\s*:\s*\n(?:.*\n)*?.*(?:train|model\.train)(?!.*val|.*eval)",
            r"for\s+epoch.*:.*\n\s*(?:model\.)?train",
        ],
        fix_template="""# Add validation to detect overfitting during training
best_val_loss = float('inf')
val_frequency = 1  # Validate every N epochs

for epoch in range(num_epochs):
    # Training phase
    model.train()
    train_loss = 0.0
    for batch in train_loader:
        optimizer.zero_grad()
        outputs = model(batch['input'])
        loss = criterion(outputs, batch['target'])
        loss.backward()
        optimizer.step()
        train_loss += loss.item()
    train_loss /= len(train_loader)

    # Validation phase
    if (epoch + 1) % val_frequency == 0:
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for batch in val_loader:
                outputs = model(batch['input'])
                loss = criterion(outputs, batch['target'])
                val_loss += loss.item()
        val_loss /= len(val_loader)

        print(f'Epoch {epoch+1}: train_loss={train_loss:.4f}, val_loss={val_loss:.4f}')

        # Save best model
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), 'best_model.pt')""",
        explanation="Training without validation makes it impossible to detect overfitting. Regular validation allows monitoring generalization performance and saving the best model checkpoint.",
        confidence=0.90,
        message="Training loop without validation step detected",
    ),

    "ML024": MLExtendedRule(
        rule_id="ML024",
        name="Early Stopping Not Implemented",
        severity="MEDIUM",
        patterns=[
            r"for\s+epoch\s+in\s+range\(\d{2,}\)\s*:(?!.*patience|.*early.stop)",
            r"for\s+epoch\s+in\s+range\(\d+\)\s*:\s*\n(?:.*\n)*?.*(?:train|val)(?!.*patience)",
        ],
        fix_template="""# Implement early stopping to prevent overfitting and save compute
from copy import deepcopy

patience = 10           # Epochs to wait before stopping
min_delta = 0.001       # Minimum improvement to reset patience
best_val_loss = float('inf')
best_model_state = None
patience_counter = 0

for epoch in range(num_epochs):
    train_loss = train_epoch(model, train_loader, optimizer, criterion)
    val_loss = validate_epoch(model, val_loader, criterion)

    # Check for improvement
    if val_loss < best_val_loss - min_delta:
        best_val_loss = val_loss
        patience_counter = 0
        best_model_state = deepcopy(model.state_dict())
        torch.save(model.state_dict(), 'best_model.pt')
        print(f'  New best: val_loss={val_loss:.4f}')
    else:
        patience_counter += 1
        print(f'  No improvement ({patience_counter}/{patience})')

    if patience_counter >= patience:
        print(f'Early stopping at epoch {epoch+1}')
        break

# Restore best model
if best_model_state is not None:
    model.load_state_dict(best_model_state)""",
        explanation="Without early stopping, training for a fixed number of epochs risks overfitting if the model starts memorizing training data. Early stopping saves the best model and halts when validation stops improving.",
        confidence=0.88,
        message="Long training loop without early stopping mechanism",
    ),

    "ML025": MLExtendedRule(
        rule_id="ML025",
        name="Model eval() Not Called Before Inference",
        severity="HIGH",
        patterns=[
            r"outputs?\s*=\s*model\s*\([^)]+\)(?!.*\.eval\(\))",
            r"model\s*\([^)]+\)\s*\n(?!.*eval)",
            r"(?:predictions?|logits?|probs?)\s*=.*model\(",
        ],
        fix_template="""# Always call model.eval() before inference
model.eval()  # Disables dropout, fixes batch norm running stats

# Proper inference pattern:
with torch.no_grad():  # Disable gradient computation
    outputs = model(inputs)
    probabilities = torch.softmax(outputs, dim=-1)
    predictions = torch.argmax(probabilities, dim=-1)

# For PyTorch 1.9+ (faster, more restrictive):
# with torch.inference_mode():
#     outputs = model(inputs)

# IMPORTANT: Remember to set back to train mode after:
# model.train()

# Common mistake - eval mode is per-call, not global:
# WRONG:
#   model(test_input)  # Still in train mode!
# CORRECT:
#   model.eval()
#   model(test_input)  # Now in eval mode""",
        explanation="model.eval() disables dropout layers and uses running statistics for batch normalization. Without it, inference results are non-deterministic and typically worse due to active dropout and per-batch norm stats.",
        confidence=0.92,
        message="Model inference without calling model.eval() first",
    ),
}


# =============================================================================
# RULE CHECKER
# =============================================================================


def get_extended_rules() -> dict[str, MLExtendedRule]:
    """Get all extended ML rules.

    Returns:
        Dictionary of rule_id -> MLExtendedRule
    """
    return ML_EXTENDED_RULES


def _strip_comments_and_docstrings(code: str) -> str:
    """Remove triple-quoted blocks and ``#`` comments from Python source.

    Reduces false positives where extended-rule regexes would otherwise match
    commented-out or documented code. Line structure is preserved (blocks are
    blanked, not deleted) so multi-line patterns still behave predictably.
    """
    import re

    def _blank(match: "re.Match") -> str:
        # Preserve newlines so line-based patterns are not distorted.
        return re.sub(r"[^\n]", " ", match.group(0))

    # Triple-quoted strings/docstrings first.
    code = re.sub(r"\"\"\".*?\"\"\"", _blank, code, flags=re.DOTALL)
    code = re.sub(r"'''.*?'''", _blank, code, flags=re.DOTALL)
    # Then line comments (best-effort; does not parse strings containing '#').
    code = re.sub(r"#[^\n]*", "", code)
    return code


def check_extended_rules(
    code: str,
    language: str = "python",
) -> list[dict]:
    """Check code against extended ML rules.

    Args:
        code: Source code to check
        language: Programming language (default: python)

    Returns:
        List of findings with rule_id, severity, explanation, and fix
    """
    import re

    findings = []
    scan_code = _strip_comments_and_docstrings(code) if language == "python" else code

    for rule_id, rule in ML_EXTENDED_RULES.items():
        for pattern in rule.patterns:
            try:
                if re.search(pattern, scan_code, re.MULTILINE | re.DOTALL | re.IGNORECASE):
                    findings.append({
                        "rule_id": rule_id,
                        "name": rule.name,
                        "severity": rule.severity,
                        "explanation": rule.explanation,
                        "fix": rule.fix_template,
                        "confidence": rule.confidence,
                    })
                    break  # One finding per rule
            except re.error:
                # Skip invalid regex patterns
                continue

    return findings


def check_single_rule(
    code: str,
    rule_id: str,
) -> list[dict]:
    """Check code against a single extended ML rule.

    Args:
        code: Source code to check
        rule_id: Rule ID to check (e.g., "ML016")

    Returns:
        List of findings for the rule
    """
    import re

    rule = ML_EXTENDED_RULES.get(rule_id)
    if not rule:
        return []

    findings = []
    for pattern in rule.patterns:
        try:
            if re.search(pattern, code, re.MULTILINE | re.DOTALL | re.IGNORECASE):
                findings.append({
                    "rule_id": rule_id,
                    "name": rule.name,
                    "severity": rule.severity,
                    "explanation": rule.explanation,
                    "fix": rule.fix_template,
                    "confidence": rule.confidence,
                })
                break
        except re.error:
            continue

    return findings


def get_rule_by_id(rule_id: str) -> Optional[MLExtendedRule]:
    """Get a rule by its ID."""
    return ML_EXTENDED_RULES.get(rule_id)


def get_rules_by_severity(severity: str) -> list[MLExtendedRule]:
    """Get all rules of a specific severity."""
    return [
        rule for rule in ML_EXTENDED_RULES.values()
        if rule.severity == severity.upper()
    ]
