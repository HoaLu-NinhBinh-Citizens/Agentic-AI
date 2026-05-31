"""Extended ML rules (ML016-ML025) for advanced ML bug detection.

This module provides additional ML-specific rules for:
- Gradient checkpointing
- Learning rate scaling
- LR warmup
- Model EMA
- Mixed precision
- Gradient accumulation
- DataLoader optimization
- Validation during training
- Early stopping
- Inference mode

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

# =============================================================================
# EXTENDED RULE DEFINITIONS
# =============================================================================


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
    message: str = ""  # Human-readable message


ML_EXTENDED_RULES: dict[str, MLExtendedRule] = {
    "ML016": MLExtendedRule(
        rule_id="ML016",
        name="Gradient Checkpointing Missing for Large Models",
        severity="MEDIUM",
        patterns=[
            r"model\s*=\s*.*[Ll]arge.*\n(?!.*gradient_checkpointing)",
            r"n_params\s*>\s*1e8(?!.*checkpoint)",
            r"BertLarge|TransformerLarge|LLaMA.*-large",
        ],
        fix_template="""# Enable gradient checkpointing for memory efficiency
from torch.utils.checkpoint import checkpoint_sequential

model.train()
# For transformers:
model.gradient_checkpointing_enable()
# Or for custom models:
model.forward = checkpoint_sequential(model.layers, 2)
# Or explicitly:
outputs = checkpoint(model, inputs)""",
        explanation="Large models (>100M params) should use gradient checkpointing to reduce memory usage by ~50%.",
        confidence=0.82,
    ),
    
    "ML017": MLExtendedRule(
        rule_id="ML017",
        name="Learning Rate Not Scaled with Batch Size",
        severity="HIGH",
        patterns=[
            r"batch[_\s]?size\s*[=>]\s*(\d+)(?!.*lr.*scale)",
            r"lr\s*=\s*[\d.e-]+\s*(?!.*linear.*scaling)",
            r"batch_size\s*=\s*512|lr\s*=\s*0\.001",
        ],
        fix_template="""# Linear scaling rule: lr ∝ batch_size
# When batch_size 256 → lr 0.1, then:
# batch_size 512 → lr 0.2
# batch_size 1024 → lr 0.4

BASE_BATCH_SIZE = 256
BASE_LR = 0.1
current_batch_size = 512  # Your batch size

lr = BASE_LR * (current_batch_size / BASE_BATCH_SIZE)
optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)""",
        explanation="When increasing batch size, scale learning rate proportionally (linear scaling rule) to maintain training dynamics.",
        confidence=0.88,
    ),
    
    "ML018": MLExtendedRule(
        rule_id="ML018",
        name="No Learning Rate Warmup",
        severity="HIGH",
        patterns=[
            r"optimizer\s*=.*(?!.*warmup)",
            r"for epoch in range\(\d+\):(?!.*warmup)",
            r"AdamW|Adam.*lr=(?!.*warmup)",
        ],
        fix_template="""# Learning rate warmup for stable training
from torch.optim.lr_scheduler import LinearLR, SequentialLR, CosineAnnealingLR

warmup_epochs = 5
total_epochs = 100

warmup_scheduler = LinearLR(
    optimizer,
    start_factor=0.1,
    end_factor=1.0,
    total_iters=warmup_epochs
)

main_scheduler = CosineAnnealingLR(
    optimizer,
    T_max=total_epochs - warmup_epochs
)

scheduler = SequentialLR(
    optimizer,
    schedulers=[warmup_scheduler, main_scheduler],
    milestones=[warmup_epochs]
)

# In training loop:
for epoch in range(total_epochs):
    train()
    scheduler.step()""",
        explanation="Learning rate warmup prevents early training instability, especially important for large models.",
        confidence=0.90,
    ),
    
    "ML019": MLExtendedRule(
        rule_id="ML019",
        name="Model EMA Not Used",
        severity="MEDIUM",
        patterns=[
            r"for epoch in range\(\d+\):(?!.*ema)",
            r"train.*eval(?!.*ema|.*moving.*average)",
            r"model\.train\(\)(?!.*ema)",
        ],
        fix_template="""# Exponential Moving Average for better generalization
from torch.optim.swa_utils import AveragedModel

# Create EMA model
ema_model = AveragedModel(model)
ema_decay = 0.999

def update_ema(model, ema_model, decay):
    with torch.no_grad():
        for ema_p, model_p in zip(ema_model.parameters(), model.parameters()):
            ema_p.data.mul_(decay).add_(model_p.data, alpha=1 - decay)

# In training loop:
for batch in dataloader:
    outputs = model(inputs)
    loss = criterion(outputs, targets)
    loss.backward()
    optimizer.step()
    update_ema(model, ema_model, ema_decay)

# Use ema_model for evaluation:
ema_model.eval()
with torch.no_grad():
    outputs = ema_model(inputs)""",
        explanation="Model EMA (Exponential Moving Average) often provides 0.5-2% improvement in final model performance.",
        confidence=0.85,
    ),
    
    "ML020": MLExtendedRule(
        rule_id="ML020",
        name="Mixed Precision Not Used for Large Models",
        severity="MEDIUM",
        patterns=[
            r"model.*\n(?!.*float16|.*bfloat16|.*amp|.*autocast)",
            r"\.cuda\(\)(?!.*amp)",
            r"BertLarge|model\.parameters\(\)(?!.*precision)",
        ],
        fix_template="""# Mixed precision training for memory efficiency
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()
model = model.cuda()

for batch in dataloader:
    inputs, targets = batch.cuda()
    
    optimizer.zero_grad()
    with autocast(dtype=torch.float16):
        outputs = model(inputs)
        loss = criterion(outputs, targets)
    
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()""",
        explanation="Mixed precision (FP16/BF16) reduces memory usage by ~50% and can speed up training on modern GPUs.",
        confidence=0.88,
    ),
    
    "ML021": MLExtendedRule(
        rule_id="ML021",
        name="Gradient Accumulation Step Mismatch",
        severity="CRITICAL",
        patterns=[
            r"accumulation_steps\s*=\s*(\d+)(?!.*backward.*accumulation)",
            r"loss\.backward\(\)(?!.*accumulation)",
            r"optimizer\.step\(\)(?!.*every)",
        ],
        fix_template="""# Proper gradient accumulation
accumulation_steps = 4
optimizer.zero_grad()

for step, batch in enumerate(dataloader):
    outputs = model(batch)
    loss = criterion(outputs, batch['targets'])
    loss = loss / accumulation_steps  # Normalize loss
    loss.backward()
    
    if (step + 1) % accumulation_steps == 0:
        optimizer.step()
        optimizer.zero_grad()""",
        explanation="Gradient accumulation must normalize the loss by accumulation_steps to maintain correct gradient magnitudes.",
        confidence=0.95,
    ),
    
    "ML022": MLExtendedRule(
        rule_id="ML022",
        name="DataLoader num_workers Too Low",
        severity="LOW",
        patterns=[
            r"DataLoader.*num_workers\s*=\s*0(?!.*benchmark)",
            r"num_workers\s*=\s*0",
        ],
        fix_template="""# Optimal DataLoader settings
from torch.utils.data import DataLoader

loader = DataLoader(
    dataset,
    batch_size=batch_size,
    num_workers=4,  # CPU cores - 1, or auto-detect: max(4, os.cpu_count() - 1)
    pin_memory=True,  # Faster GPU transfer
    prefetch_factor=2,  # Prefetch batches
    persistent_workers=True,  # Keep workers alive between epochs
)
# Enable cuDNN benchmark mode:
torch.backends.cudnn.benchmark = True""",
        explanation="Low num_workers causes CPU bottleneck. Set to (CPU cores - 1) for optimal data loading performance.",
        confidence=0.80,
    ),
    
    "ML023": MLExtendedRule(
        rule_id="ML023",
        name="No Validation During Training",
        severity="HIGH",
        patterns=[
            r"for epoch in.*:\s*train(?!.*val|.*eval)",
            r"train.*\n(?!.*val_loss|.*evaluate)",
            r"optimizer\.step\(\)(?!.*val)",
        ],
        fix_template="""# Validate during training
val_frequency = 1  # Validate every N epochs
best_val_loss = float('inf')

for epoch in range(num_epochs):
    model.train()
    train_loss = 0
    for batch in train_loader:
        outputs = model(batch)
        loss = criterion(outputs, batch['targets'])
        loss.backward()
        optimizer.step()
        train_loss += loss.item()
    
    # Validate every N epochs
    if (epoch + 1) % val_frequency == 0:
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for batch in val_loader:
                outputs = model(batch)
                loss = criterion(outputs, batch['targets'])
                val_loss += loss.item()
        
        val_loss /= len(val_loader)
        print(f"Epoch {epoch}: train={train_loss/len(train_loader):.4f}, val={val_loss:.4f}")
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), 'best_model.pt')""",
        explanation="Regular validation during training is essential to detect overfitting and save the best model.",
        confidence=0.92,
    ),
    
    "ML024": MLExtendedRule(
        rule_id="ML024",
        name="Early Stopping Not Implemented",
        severity="MEDIUM",
        patterns=[
            r"for epoch in range\(\d+\):(?!.*patience|.*early.*stop)",
            r"train.*\n(?!.*patience)",
        ],
        fix_template="""# Early stopping implementation
from copy import deepcopy

patience = 10
min_delta = 0.001
best_loss = float('inf')
best_model_state = None
patience_counter = 0

for epoch in range(num_epochs):
    train_loss = train_epoch(model, train_loader)
    val_loss = validate_epoch(model, val_loader)
    
    if val_loss < best_loss - min_delta:
        best_loss = val_loss
        patience_counter = 0
        best_model_state = deepcopy(model.state_dict())
        torch.save(model.state_dict(), 'best_model.pt')
    else:
        patience_counter += 1
    
    if patience_counter >= patience:
        print(f"Early stopping at epoch {epoch}")
        break

# Restore best model
if best_model_state:
    model.load_state_dict(best_model_state)""",
        explanation="Early stopping prevents overfitting and saves training time by stopping when validation loss stops improving.",
        confidence=0.88,
    ),
    
    "ML025": MLExtendedRule(
        rule_id="ML025",
        name="Model eval() Not Called Before Inference",
        severity="HIGH",
        patterns=[
            r"(?!.*model\.eval\(\))(?:predict|inference|evaluate)\s*\(",
            r"model\(.*\)(?!.*\.eval\(\)|\.train\(\))",
            r"outputs\s*=\s*model\(.*\)(?!.*no_grad)",
        ],
        fix_template="""# Correct inference pattern
model.eval()  # Set to evaluation mode (disables dropout, fixes batch norm)

# For inference with no gradients:
with torch.no_grad():
    # Or use torch.inference_mode() for newer PyTorch:
    # with torch.inference_mode():
    outputs = model(inputs)
    
    # For probability outputs:
    probs = torch.softmax(outputs, dim=-1)
    predictions = torch.argmax(probs, dim=-1)""",
        explanation="Always call model.eval() before inference to disable dropout/batch norm updates and ensure consistent behavior.",
        confidence=0.95,
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
    
    for rule_id, rule in ML_EXTENDED_RULES.items():
        for pattern in rule.patterns:
            if re.search(pattern, code, re.MULTILINE | re.DOTALL | re.IGNORECASE):
                findings.append({
                    "rule_id": rule_id,
                    "name": rule.name,
                    "severity": rule.severity,
                    "explanation": rule.explanation,
                    "fix": rule.fix_template,
                    "confidence": rule.confidence,
                })
                break  # One finding per rule
    
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
    
    return findings


def get_rule_by_id(rule_id: str) -> Optional[MLExtendedRule]:
    """Get a rule by its ID.
    
    Args:
        rule_id: Rule ID (e.g., "ML016")
        
    Returns:
        MLExtendedRule or None if not found
    """
    return ML_EXTENDED_RULES.get(rule_id)


def get_rules_by_severity(severity: str) -> list[MLExtendedRule]:
    """Get all rules of a specific severity.
    
    Args:
        severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW)
        
    Returns:
        List of matching rules
    """
    return [
        rule for rule in ML_EXTENDED_RULES.values()
        if rule.severity == severity.upper()
    ]
