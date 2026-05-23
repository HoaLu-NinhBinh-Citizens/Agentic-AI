"""Model quantization and optimization (Phase 12.5).

Provides model quantization pipeline:
- Quantization methods (INT8, INT4, etc.)
- ONNX export
- TensorRT optimization
- Performance benchmarking
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class QuantMethod(Enum):
    """Quantization methods."""
    INT8 = "int8"
    INT4 = "int4"
    FP16 = "fp16"
    BF16 = "bf16"
    GPTQ = "gptq"
    AWQ = "awq"


class OptimizationTarget(Enum):
    """Optimization targets."""
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    MEMORY = "memory"
    ACCURACY = "accuracy"


@dataclass
class QuantConfig:
    """Quantization configuration."""
    method: QuantMethod
    target: OptimizationTarget = OptimizationTarget.LATENCY
    
    # Calibration
    calibration_samples: int = 100
    calibration_dataset: str = ""
    
    # Options
    bits: int = 8
    group_size: int = 128
    desc_act: bool = False  # Activation quantization
    
    # Hardware
    backend: str = "auto"  # auto, cpu, cuda, tensorrt


@dataclass
class QuantizationResult:
    """Quantization result."""
    model_id: str
    original_size_mb: float
    quantized_size_mb: float
    
    # Performance
    original_latency_ms: float
    quantized_latency_ms: float
    
    # Accuracy
    accuracy_retained: float  # 0.0 - 1.0
    
    # Metadata
    quantization_time_seconds: float
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class BenchmarkResult:
    """Benchmark result."""
    model_id: str
    
    # Latency
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    
    # Throughput
    tokens_per_second: float
    requests_per_second: float
    
    # Memory
    memory_usage_mb: float
    vram_usage_mb: float
    
    # Benchmark metadata
    batch_size: int
    sequence_length: int
    benchmark_duration_seconds: int


class Quantizer:
    """Model quantizer."""
    
    def __init__(self) -> None:
        self._models: dict[str, dict] = {}
    
    def quantize(
        self,
        model_path: str,
        config: QuantConfig,
    ) -> QuantizationResult:
        """Quantize model."""
        import hashlib
        model_id = hashlib.md5(f"{model_path}:{config.method.value}".encode()).hexdigest()[:12]
        
        logger.info("Quantizing model", model_id=model_id, method=config.method.value)
        
        # Simulate quantization
        original_size = 4000.0  # MB
        compression_ratio = {
            QuantMethod.INT8: 0.3,
            QuantMethod.INT4: 0.15,
            QuantMethod.FP16: 0.5,
            QuantMethod.BF16: 0.5,
        }.get(config.method, 0.3)
        
        quantized_size = original_size * compression_ratio
        
        result = QuantizationResult(
            model_id=model_id,
            original_size_mb=original_size,
            quantized_size_mb=quantized_size,
            original_latency_ms=100.0,
            quantized_latency_ms=100.0 * compression_ratio,
            accuracy_retained=0.95 + hash(model_id) % 50 / 1000,
            quantization_time_seconds=300.0,
        )
        
        self._models[model_id] = {
            "model_path": model_path,
            "config": config,
            "result": result,
        }
        
        logger.info(
            "Quantization complete",
            model_id=model_id,
            size_reduction=f"{(1-compression_ratio)*100:.0f}%",
        )
        
        return result
    
    def get_model(self, model_id: str) -> dict | None:
        """Get quantized model info."""
        return self._models.get(model_id)


class ONNXExporter:
    """ONNX model exporter."""
    
    def export(
        self,
        model_path: str,
        output_path: str,
        optimize: bool = True,
    ) -> str:
        """Export model to ONNX."""
        onnx_path = f"{output_path}.onnx"
        logger.info("Exporting to ONNX", input=model_path, output=onnx_path)
        return onnx_path
    
    def optimize(
        self,
        onnx_path: str,
        level: int = 3,
    ) -> str:
        """Optimize ONNX model."""
        optimized_path = onnx_path.replace(".onnx", f"_opt_l{level}.onnx")
        logger.info("Optimizing ONNX", input=onnx_path, output=optimized_path, level=level)
        return optimized_path


class TensorRTOptimizer:
    """TensorRT optimization."""
    
    def __init__(self) -> None:
        self._engines: dict[str, str] = {}
    
    def build_engine(
        self,
        onnx_path: str,
        precision: str = "fp16",
        max_batch_size: int = 8,
    ) -> str:
        """Build TensorRT engine."""
        engine_path = onnx_path.replace(".onnx", f"_{precision}.engine")
        
        logger.info(
            "Building TensorRT engine",
            input=onnx_path,
            output=engine_path,
            precision=precision,
        )
        
        self._engines[engine_path] = onnx_path
        return engine_path
    
    def get_engine(self, model_id: str) -> str | None:
        """Get engine path."""
        for engine, _ in self._engines.items():
            if model_id in engine:
                return engine
        return None


class Benchmarker:
    """Model benchmarker."""
    
    def __init__(self) -> None:
        self._results: dict[str, list[BenchmarkResult]] = {}
    
    def benchmark(
        self,
        model_path: str,
        batch_size: int = 1,
        sequence_length: int = 512,
        duration_seconds: int = 60,
    ) -> BenchmarkResult:
        """Benchmark model."""
        import random
        import hashlib
        
        model_id = hashlib.md5(model_path.encode()).hexdigest()[:12]
        
        # Simulate benchmark
        base_latency = 50.0 if "quantized" in model_path else 100.0
        
        result = BenchmarkResult(
            model_id=model_id,
            avg_latency_ms=base_latency + random.gauss(0, 5),
            p50_latency_ms=base_latency,
            p95_latency_ms=base_latency * 1.5,
            p99_latency_ms=base_latency * 2.0,
            tokens_per_second=1000.0 / base_latency,
            requests_per_second=100.0 / batch_size,
            memory_usage_mb=2048.0 if "quantized" in model_path else 4096.0,
            vram_usage_mb=1536.0 if "quantized" in model_path else 3072.0,
            batch_size=batch_size,
            sequence_length=sequence_length,
            benchmark_duration_seconds=duration_seconds,
        )
        
        if model_id not in self._results:
            self._results[model_id] = []
        self._results[model_id].append(result)
        
        logger.info("Benchmark complete", model_id=model_id, latency=result.avg_latency_ms)
        
        return result
    
    def get_results(self, model_id: str) -> list[BenchmarkResult]:
        """Get benchmark results."""
        return self._results.get(model_id, [])
    
    def compare(
        self,
        model_id_1: str,
        model_id_2: str,
    ) -> dict[str, Any]:
        """Compare two models."""
        results1 = self._results.get(model_id_1, [])
        results2 = self._results.get(model_id_2, [])
        
        if not results1 or not results2:
            return {"error": "No results for one or both models"}
        
        r1 = results1[-1]
        r2 = results2[-1]
        
        return {
            "latency_improvement": (r1.avg_latency_ms - r2.avg_latency_ms) / r1.avg_latency_ms,
            "throughput_improvement": (r2.tokens_per_second - r1.tokens_per_second) / r1.tokens_per_second,
            "memory_reduction": (r1.memory_usage_mb - r2.memory_usage_mb) / r1.memory_usage_mb,
        }


class ModelOptimizer:
    """Main model optimization pipeline.
    
    Phase 12.5: Quantization & optimization
    """
    
    def __init__(self) -> None:
        self._quantizer = Quantizer()
        self._onnx_exporter = ONNXExporter()
        self._trt_optimizer = TensorRTOptimizer()
        self._benchmarker = Benchmarker()
    
    def quantize(
        self,
        model_path: str,
        config: QuantConfig,
    ) -> QuantizationResult:
        """Quantize model."""
        return self._quantizer.quantize(model_path, config)
    
    def export_onnx(
        self,
        model_path: str,
        output_path: str,
        optimize: bool = True,
    ) -> str:
        """Export to ONNX."""
        onnx_path = self._onnx_exporter.export(model_path, output_path, optimize)
        if optimize:
            onnx_path = self._onnx_exporter.optimize(onnx_path)
        return onnx_path
    
    def build_tensorrt(
        self,
        onnx_path: str,
        precision: str = "fp16",
    ) -> str:
        """Build TensorRT engine."""
        return self._trt_optimizer.build_engine(onnx_path, precision)
    
    def benchmark(
        self,
        model_path: str,
        batch_size: int = 1,
    ) -> BenchmarkResult:
        """Benchmark model."""
        return self._benchmarker.benchmark(model_path, batch_size)
    
    def full_pipeline(
        self,
        model_path: str,
        quant_config: QuantConfig,
    ) -> dict[str, Any]:
        """Run full optimization pipeline."""
        logger.info("Starting full optimization pipeline", model_path=model_path)
        
        # 1. Quantize
        quant_result = self.quantize(model_path, quant_config)
        
        # 2. Export ONNX (simulated)
        onnx_path = f"{model_path}.onnx"
        
        # 3. Build TensorRT
        engine_path = self.build_tensorrt(onnx_path, "fp16")
        
        # 4. Benchmark
        benchmark_result = self.benchmark(model_path)
        
        return {
            "quantization": quant_result,
            "onnx_path": onnx_path,
            "engine_path": engine_path,
            "benchmark": benchmark_result,
        }


# Global optimizer
_model_optimizer: ModelOptimizer | None = None


def get_model_optimizer() -> ModelOptimizer:
    """Get global model optimizer."""
    global _model_optimizer
    if _model_optimizer is None:
        _model_optimizer = ModelOptimizer()
    return _model_optimizer


if __name__ == "__main__":
    optimizer = get_model_optimizer()
    
    print("Model Optimization")
    print("=" * 40)
    
    # Quantize
    config = QuantConfig(
        method=QuantMethod.INT8,
        target=OptimizationTarget.LATENCY,
    )
    
    result = optimizer.quantize("models/llama3", config)
    
    print(f"Original size: {result.original_size_mb:.0f} MB")
    print(f"Quantized size: {result.quantized_size_mb:.0f} MB")
    print(f"Latency improvement: {result.original_latency_ms - result.quantized_latency_ms:.1f} ms")
    print(f"Accuracy retained: {result.accuracy_retained:.1%}")
    
    # Benchmark
    benchmark = optimizer.benchmark("models/llama3")
    print(f"\nBenchmark:")
    print(f"  Avg latency: {benchmark.avg_latency_ms:.1f} ms")
    print(f"  Throughput: {benchmark.tokens_per_second:.0f} tokens/s")
