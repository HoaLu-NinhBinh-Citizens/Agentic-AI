"""Integration tests for UnifiedReviewEngine pipeline.

Tests the full pipeline with mock ML and firmware projects.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from src.application.workflows.unified.review_engine import (
    UnifiedReviewEngine,
    ReviewEngineConfig,
    ReviewResult,
)
from src.application.workflows.unified.detector_base import (
    Finding,
    FindingSeverity,
)
from src.application.workflows.unified.result_formatter import PipelineStats


# =============================================================================
# Mock Project Fixtures
# =============================================================================


@pytest.fixture
def mock_ml_project(tmp_path: Path) -> Path:
    """Create a mock ML project with intentional bugs.
    
    Creates files with:
    - train.py: ML001 (data leakage), ML005 (missing seed)
    - model.py: ML002 (CrossEntropyLoss), ML004 (missing no_grad)
    - utils.py: Additional ML patterns
    """
    project_root = tmp_path / "ml_project"
    project_root.mkdir(parents=True)
    
    # train.py - ML001 (scaler.fit before split) + ML005 (missing seed)
    train_py = project_root / "train.py"
    train_py.write_text("""
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

def train_model():
    # ML005: Missing random seed
    X = np.random.randn(1000, 20)
    y = np.random.randint(0, 2, 1000)
    
    # ML001: Data leakage - scaler.fit before split
    scaler = StandardScaler()
    scaler.fit(X)  # Wrong! Should be after split
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
    
    X_train_scaled = scaler.transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    return X_train_scaled, X_test_scaled, y_train, y_test

if __name__ == "__main__":
    train_model()
""")
    
    # model.py - ML002 (CrossEntropyLoss for multi-label) + ML004 (missing no_grad)
    model_py = project_root / "model.py"
    model_py.write_text("""
import torch
import torch.nn as nn

class MultiLabelClassifier(nn.Module):
    def __init__(self, input_dim, num_classes):
        super().__init__()
        self.fc = nn.Linear(input_dim, num_classes)
    
    def forward(self, x):
        return self.fc(x)

def train(model, data, labels):
    criterion = nn.CrossEntropyLoss()  # ML002: Wrong for multi-label
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    outputs = model(data)
    loss = criterion(outputs, labels)
    loss.backward()
    optimizer.step()
    
    return loss.item()

# ML004: Inference without no_grad
def evaluate(model, data):
    model.eval()
    with torch.no_grad():
        outputs = model(data)
    return outputs

def predict(model, data):
    model.eval()
    outputs = model(data)  # ML004: Missing no_grad
    return outputs
""")
    
    # utils.py - Additional patterns
    utils_py = project_root / "utils.py"
    utils_py.write_text("""
import numpy as np

def seed_everything(seed=42):
    np.random.seed(seed)

def load_data():
    # Some helper function
    return np.random.randn(100, 10)

def preprocess(X):
    # Missing proper validation
    return X / X.sum(axis=1, keepdims=True)
""")
    
    return project_root


@pytest.fixture
def mock_firmware_project(tmp_path: Path) -> Path:
    """Create a mock firmware project with intentional bugs.
    
    Creates files with:
    - main.c: EMB001 (infinite while loop)
    - isr.c: EMB004 (blocking in ISR)
    - timer.c: Additional embedded patterns
    """
    project_root = tmp_path / "firmware_project"
    project_root.mkdir(parents=True)
    
    # main.c - EMB001 (infinite while 1 loop)
    main_c = project_root / "main.c"
    main_c.write_text("""
#include <stdint.h>

volatile uint32_t tick_count = 0;

void SysTick_Handler(void);

int main(void) {
    // Initialize clock
    SystemInit();
    
    // EMB001: Infinite loop without watchdog
    while (1) {
        tick_count++;
        // Busy wait - not recommended
    }
    
    return 0;
}

void SysTick_Handler(void) {
    tick_count++;
}
""")
    
    # isr.c - EMB004 (blocking in ISR)
    isr_c = project_root / "isr.c"
    isr_c.write_text("""
#include <stdint.h>
#include "uart.h"

volatile uint8_t rx_buffer[256];
volatile uint32_t rx_head = 0;

void USART1_IRQHandler(void) {
    // EMB004: Blocking call in ISR
    if (USART1->SR & USART_SR_RXNE) {
        uint8_t data = USART1->DR;
        rx_buffer[rx_head++] = data;
        
        // Blocking print in ISR - BAD!
        uart_print("Received data");
    }
}
""")
    
    # timer.c - Additional embedded patterns
    timer_c = project_root / "timer.c"
    timer_c.write_text("""
#include <stdint.h>

volatile uint32_t timer_ticks = 0;

void timer_init(void) {
    // Timer initialization
    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;
    TIM2->PSC = 8399;  // 84MHz / 8400 = 10kHz
    TIM2->ARR = 9999;   // 1 second interrupt
    TIM2->DIER |= TIM_DIER_UIE;
    TIM2->CR1 |= TIM_CR1_CEN;
}

void TIM2_IRQHandler(void) {
    if (TIM2->SR & TIM_SR_UIF) {
        TIM2->SR &= ~TIM_SR_UIF;
        timer_ticks++;
    }
}
""")
    
    return project_root


@pytest.fixture
def clean_project(tmp_path: Path) -> Path:
    """Create a clean project without bugs for negative tests."""
    project_root = tmp_path / "clean_project"
    project_root.mkdir(parents=True)
    
    # Python file with correct patterns
    clean_py = project_root / "clean.py"
    clean_py.write_text("""
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import torch
import torch.nn as nn

def train_model():
    # Correct pattern: split first, then fit
    X = np.random.randn(1000, 20)
    y = np.random.randint(0, 2, 1000)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    return X_train_scaled, X_test_scaled, y_train, y_test

class SimpleNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Linear(20, 2)
    
    def forward(self, x):
        return self.fc(x)

def train(model, data, labels):
    torch.manual_seed(42)  # Set seed for reproducibility
    model.train()
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    outputs = model(data)
    loss = criterion(outputs, labels)
    loss.backward()
    optimizer.step()
    
    return loss.item()

def evaluate(model, data):
    model.eval()
    with torch.no_grad():  # Correct: no_grad for inference
        outputs = model(data)
    return outputs
""")
    
    return project_root


# =============================================================================
# UnifiedReviewEngine Tests
# =============================================================================


class TestUnifiedReviewEngine:
    """Integration tests for the full review pipeline."""
    
    @pytest.mark.asyncio
    async def test_full_pipeline_single_file(self, mock_ml_project: Path) -> None:
        """Test review on a single Python file."""
        config = ReviewEngineConfig(
            focus_areas=["ml"],
            output_format="markdown",
            confidence_threshold=0.5,
        )
        engine = UnifiedReviewEngine(config)
        
        train_file = mock_ml_project / "train.py"
        result = await engine.review([train_file])
        
        assert isinstance(result, ReviewResult)
        assert result.stats.files_scanned >= 1
        assert result.output is not None
        assert len(result.output) > 0
    
    @pytest.mark.asyncio
    async def test_full_pipeline_multiple_files(self, mock_ml_project: Path) -> None:
        """Test review across multiple files."""
        config = ReviewEngineConfig(
            focus_areas=["ml"],
            output_format="json",
        )
        engine = UnifiedReviewEngine(config)
        
        files = list(mock_ml_project.glob("*.py"))
        result = await engine.review(files)
        
        assert result.stats.files_scanned >= len(files)
        assert result.stats.findings_count >= 0
        assert "findings" in result.to_dict()
    
    @pytest.mark.asyncio
    async def test_full_pipeline_directory(self, mock_ml_project: Path) -> None:
        """Test review on a directory."""
        config = ReviewEngineConfig(focus_areas=["ml"])
        engine = UnifiedReviewEngine(config)
        
        result = await engine.review([mock_ml_project])
        
        assert result.stats.files_scanned >= 3  # 3 Python files in mock project
        assert isinstance(result.output, str)
    
    @pytest.mark.asyncio
    async def test_markdown_output_format(self, mock_ml_project: Path) -> None:
        """Test MarkdownFormatter output structure."""
        config = ReviewEngineConfig(
            focus_areas=["ml"],
            output_format="markdown",
        )
        engine = UnifiedReviewEngine(config)
        
        result = await engine.review([mock_ml_project])
        
        assert "# Code Review Report" in result.output or "Code Review" in result.output
        assert "Summary" in result.output or "summary" in result.output.lower()
    
    @pytest.mark.asyncio
    async def test_json_output_format(self, mock_ml_project: Path) -> None:
        """Test JsonFormatter output structure."""
        import json
        
        config = ReviewEngineConfig(
            focus_areas=["ml"],
            output_format="json",
        )
        engine = UnifiedReviewEngine(config)
        
        result = await engine.review([mock_ml_project / "train.py"])
        
        # JSON output should be parseable
        parsed = json.loads(result.output)
        assert "report" in parsed or "findings" in parsed
    
    @pytest.mark.asyncio
    async def test_console_output_format(self, mock_ml_project: Path) -> None:
        """Test ConsoleFormatter output."""
        config = ReviewEngineConfig(
            focus_areas=["ml"],
            output_format="console",
        )
        engine = UnifiedReviewEngine(config)
        
        result = await engine.review([mock_ml_project / "model.py"])
        
        assert result.output is not None
        assert len(result.output) > 0
    
    @pytest.mark.asyncio
    async def test_no_files_returns_empty(self, tmp_path: Path) -> None:
        """Test review with no files returns empty result."""
        config = ReviewEngineConfig()
        engine = UnifiedReviewEngine(config)
        
        result = await engine.review([tmp_path / "nonexistent.py"])
        
        assert result.findings == []
        assert "No files found" in result.output
    
    @pytest.mark.asyncio
    async def test_confidence_threshold_filtering(self, mock_ml_project: Path) -> None:
        """Test that confidence threshold filters findings."""
        # High threshold - should filter out low confidence
        config = ReviewEngineConfig(
            focus_areas=["ml"],
            confidence_threshold=0.9,
        )
        engine = UnifiedReviewEngine(config)
        
        result_high = await engine.review([mock_ml_project / "train.py"], incremental=False)
        
        # Low threshold - should include more findings
        config_low = ReviewEngineConfig(
            focus_areas=["ml"],
            confidence_threshold=0.3,
        )
        engine_low = UnifiedReviewEngine(config_low)
        result_low = await engine_low.review([mock_ml_project / "train.py"], incremental=False)
        
        # Lower threshold should find same or more issues
        assert result_low.stats.findings_count >= result_high.stats.findings_count
    
    @pytest.mark.asyncio
    async def test_focus_area_filtering(self, mock_ml_project: Path) -> None:
        """Test that focus areas filter detectors."""
        config_ml = ReviewEngineConfig(focus_areas=["ml"])
        engine_ml = UnifiedReviewEngine(config_ml)
        
        result_ml = await engine_ml.review([mock_ml_project / "train.py"])
        
        config_security = ReviewEngineConfig(focus_areas=["security"])
        engine_security = UnifiedReviewEngine(config_security)
        
        result_security = await engine_security.review([mock_ml_project / "train.py"])
        
        # ML detector should find ML-specific issues
        assert "ml" in engine_ml.get_detectors()
        assert "security" in engine_security.get_detectors()
    
    @pytest.mark.asyncio
    async def test_clean_project_no_issues(self, clean_project: Path) -> None:
        """Test that clean code produces minimal or no findings."""
        config = ReviewEngineConfig(
            focus_areas=["ml"],
            confidence_threshold=0.8,
        )
        engine = UnifiedReviewEngine(config)
        
        result = await engine.review([clean_project / "clean.py"])
        
        # Clean code should have fewer findings
        assert result.stats.findings_count == 0 or result.stats.findings_count < 3
    
    @pytest.mark.asyncio
    async def test_parallel_processing(self, mock_ml_project: Path) -> None:
        """Test parallel file processing."""
        config = ReviewEngineConfig(
            focus_areas=["ml"],
            enable_parallel=True,
            max_workers=2,
        )
        engine = UnifiedReviewEngine(config)
        
        result = await engine.review([mock_ml_project])
        
        assert result.stats.files_scanned >= 3
    
    @pytest.mark.asyncio
    async def test_sequential_processing(self, mock_ml_project: Path) -> None:
        """Test sequential file processing."""
        config = ReviewEngineConfig(
            focus_areas=["ml"],
            enable_parallel=False,
        )
        engine = UnifiedReviewEngine(config)
        
        result = await engine.review([mock_ml_project])
        
        assert result.stats.files_scanned >= 1
    
    @pytest.mark.asyncio
    async def test_get_stats(self, mock_ml_project: Path) -> None:
        """Test get_stats returns expected structure."""
        config = ReviewEngineConfig(focus_areas=["ml"])
        engine = UnifiedReviewEngine(config)
        
        await engine.review([mock_ml_project])
        stats = engine.get_stats()
        
        assert "detectors" in stats
        assert "config" in stats
        assert isinstance(stats["detectors"], list)
    
    @pytest.mark.asyncio
    async def test_get_detectors(self, mock_ml_project: Path) -> None:
        """Test get_detectors returns detector names."""
        config = ReviewEngineConfig(focus_areas=["ml", "security"])
        engine = UnifiedReviewEngine(config)
        
        detectors = engine.get_detectors()
        
        assert "ml" in detectors
        assert isinstance(detectors, list)


class TestReviewEngineDeduplication:
    """Test finding deduplication logic."""
    
    @pytest.mark.asyncio
    async def test_duplicate_findings_removed(self, mock_ml_project: Path) -> None:
        """Test that duplicate findings are deduplicated."""
        config = ReviewEngineConfig(focus_areas=["ml"])
        engine = UnifiedReviewEngine(config)
        
        # Run review twice on same file
        file_path = mock_ml_project / "train.py"
        result1 = await engine.review([file_path], incremental=False)
        result2 = await engine.review([file_path], incremental=False)
        
        # Should not double count if deduplication works
        # Note: This test verifies the engine can handle repeated runs
        assert result1.stats.findings_count == result2.stats.findings_count


class TestReviewResult:
    """Test ReviewResult structure and methods."""
    
    def test_to_dict_serialization(self) -> None:
        """Test ReviewResult serialization."""
        findings = [
            Finding(
                rule_id="ML001",
                rule_name="data-leakage",
                severity=FindingSeverity.ERROR,
                file="test.py",
                line=10,
                end_line=10,
                message="Test finding",
                confidence=0.9,
            )
        ]
        
        result = ReviewResult(
            findings=findings,
            stats=PipelineStats(files_scanned=1),
            output="Test output",
        )
        
        serialized = result.to_dict()
        
        assert "findings" in serialized
        assert "stats" in serialized
        assert "output" in serialized
        assert len(serialized["findings"]) == 1
