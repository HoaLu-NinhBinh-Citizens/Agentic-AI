"""
OCR Pipeline

Stub module for OCR processing.
"""

from typing import Any


class OCRPipeline:
    """OCR processing pipeline."""
    
    def process(self, image_path: str) -> dict:
        return {"text": "", "confidence": 0.0}


__all__ = ["OCRPipeline"]
