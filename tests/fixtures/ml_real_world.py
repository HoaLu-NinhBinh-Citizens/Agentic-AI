"""Real-world ML code patterns for testing ML detection.

This module provides realistic ML code snippets that contain common
bugs and patterns for testing the ML detector functionality.
"""

from __future__ import annotations

# =============================================================================
# DATA LEAKAGE PATTERNS (ML001)
# =============================================================================

ML_LEAKAGE_PATTERNS: dict[str, str] = {
    "scaler_before_split": '''import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

def train():
    X, y = load_data()
    scaler = StandardScaler()
    scaler.fit(X)  # LEAKAGE: fit before split!
    X_train, X_test, y_train, y_test = train_test_split(X, y)
    return scaler
''',
    "test_set_in_training": '''
def train():
    X_train, y_train = load_train()
    X_test, y_test = load_test()
    X_combined = np.vstack([X_train, X_test])  # LEAKAGE!
    model.fit(X_combined)
''',
    "minmax_scaler_before_split": '''
from sklearn.preprocessing import MinMaxScaler

def preprocess(X, y):
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)  # LEAKAGE: fit on all data
    return train_test_split(X_scaled, y, test_size=0.2)
''',
    "encoder_before_split": '''
from sklearn.preprocessing import LabelEncoder

def encode_labels(X, y):
    encoder = LabelEncoder()
    y_encoded = encoder.fit_transform(y)  # LEAKAGE: encoder sees test labels
    return train_test_split(X, y_encoded)
''',
}


# =============================================================================
# LOSS FUNCTION PATTERNS (ML002)
# =============================================================================

LOSS_FUNCTION_PATTERNS: dict[str, str] = {
    "cross_entropy_multi_label": '''
import torch
import torch.nn as nn

def train_multi_label_model():
    model = MultiLabelClassifier()
    criterion = nn.CrossEntropyLoss()  # WRONG for multi-label!
    # multi_label_targets should use BCEWithLogitsLoss
    outputs = model(X)
    loss = criterion(outputs, multi_label_targets)
''',
    "bce_single_label": '''
import torch
import torch.nn as nn

class BinaryClassifier(nn.Module):
    def forward(self, x):
        return self.net(x)

model = BinaryClassifier()
criterion = nn.BCEWithLogitsLoss()  # Should use CrossEntropyLoss for single-label
''',
}


# =============================================================================
# DEVICE MISMATCH PATTERNS (ML003)
# =============================================================================

DEVICE_MISMATCH_PATTERNS: dict[str, str] = {
    "model_cpu_data_gpu": '''
import torch

def train():
    model = MyModel().to('cuda')
    for batch in dataloader:
        inputs = batch.to('cuda')  # OK
        outputs = model(batch)  # BUG: batch not on GPU
''',
    "data_cpu_model_gpu": '''
def evaluate(model, data):
    model = model.to('cuda')
    output = model(data)  # BUG: data on CPU, model on GPU
''',
    "partial_device_move": '''
def forward_pass(model, x, y):
    model = model.cuda()
    x = x.cuda()
    # y is forgotten - device mismatch
    output = model(x)
    loss = criterion(output, y)
''',
}


# =============================================================================
# MISSING NO_GRAD PATTERNS (ML004)
# =============================================================================

MISSING_NO_GRAD_PATTERNS: dict[str, str] = {
    "inference_no_grad": '''
def predict(model, X):
    outputs = model(X)  # Should wrap in no_grad
    return outputs
''',
    "evaluation_leak": '''
def evaluate(model, test_loader):
    total_loss = 0
    for batch in test_loader:
        outputs = model(batch)  # Memory leak - no_grad missing
        loss = criterion(outputs, batch.labels)
        total_loss += loss.item()
''',
    "predict_loop": '''
def predict_batch(model, dataloader):
    predictions = []
    for batch in dataloader:
        pred = model(batch)  # Missing no_grad
        predictions.append(pred)
    return predictions
''',
}


# =============================================================================
# MISSING SEED PATTERNS (ML005)
# =============================================================================

MISSING_SEED_PATTERNS: dict[str, str] = {
    "no_seed": '''
def train():
    for epoch in range(10):
        # No seed set!
        output = train_epoch(model, dataloader)
''',
    "partial_seed": '''
import torch
import numpy as np

def train():
    torch.manual_seed(42)  # Only torch seed
    # Missing: np.random.seed(42)
    # Missing: random.seed(42)
    # Missing: torch.cuda.manual_seed_all(42) for CUDA
''',
    "cuda_no_determinism": '''
import torch

def train():
    torch.manual_seed(42)
    np.random.seed(42)
    # Missing: torch.backends.cudnn.deterministic = True
    # Missing: torch.backends.cudnn.benchmark = False
''',
}


# =============================================================================
# HARDCODED HYPERPARAMETERS (ML006)
# =============================================================================

HARDCODED_PARAMS_PATTERNS: dict[str, str] = {
    "batch_size_hardcoded": '''
batch_size = 32  # Should come from config
lr = 0.001
epochs = 100
''',
    "multiple_hardcoded": '''
batch_size = 64
lr = 0.0001
epochs = 200
hidden_dim = 512
dropout = 0.5
''',
}


# =============================================================================
# BEST PRACTICES - CORRECT CODE
# =============================================================================

BEST_PRACTICES: dict[str, str] = {
    "correct_pipeline": '''
import torch
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

def train():
    torch.manual_seed(42)
    np.random.seed(42)

    X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=42)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = MyModel().to(device)
    model.train()

    with torch.no_grad():
        eval(model, test_loader)

    return model
''',
    "correct_multi_label": '''
import torch
import torch.nn as nn

class MultiLabelClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(100, 64),
            nn.ReLU(),
            nn.Linear(64, 10)  # 10 labels
        )

    def forward(self, x):
        return self.net(x)

model = MultiLabelClassifier()
criterion = nn.BCEWithLogitsLoss()  # CORRECT for multi-label
''',
    "correct_device_handling": '''
import torch

def train():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = MyModel().to(device)

    for batch in dataloader:
        inputs = batch.to(device)  # Both on same device
        labels = batch.labels.to(device)
        outputs = model(inputs)
        loss = criterion(outputs, labels)
''',
    "correct_inference": '''
def predict(model, X):
    model.eval()
    with torch.no_grad():
        outputs = model(X)
    return outputs
''',
    "correct_reproducibility": '''
import torch
import numpy as np
import random

def set_seed(seed=42):
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

def train():
    set_seed(42)
    # Training code here
''',
}


# =============================================================================
# COMPLEX REAL-WORLD SCENARIOS
# =============================================================================

COMPLEX_SCENARIOS: dict[str, str] = {
    "training_pipeline_with_bugs": '''
import torch
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

def training_pipeline(X, y):
    # Bug 1: Scaler leakage
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Bug 2: Missing seed
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y)

    # Bug 3: Missing no_grad
    model = SimpleModel()
    for epoch in range(100):
        outputs = model(X_train)
        loss = criterion(outputs, y_train)
        optimizer.zero_grad()
        loss.backward()

    # Bug 4: Inference without eval/no_grad
    predictions = model(X_test)
    return predictions
''',
    "correct_training_pipeline": '''
import torch
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

def training_pipeline(X, y, config):
    # CORRECT: Split first
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # CORRECT: Fit scaler on train only
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # CORRECT: Set seeds
    torch.manual_seed(42)
    np.random.seed(42)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    # CORRECT: Training with no_grad disabled only for training
    model = SimpleModel()
    model.train()
    for epoch in range(config.epochs):
        outputs = model(X_train)
        loss = criterion(outputs, y_train)
        optimizer.zero_grad()
        loss.backward()

    # CORRECT: Inference with eval and no_grad
    model.eval()
    with torch.no_grad():
        predictions = model(X_test)

    return predictions
''',
}
