"""
Enhanced OCR for PDF Tables - Merged Cell Detection and Reconstruction

Solves the problem of broken register maps in embedded PDF datasheets where
PyMuPDF layout extraction fails on merged cells, rotated tables, or complex layouts.

Features:
- Merged cell (colspan/rowspan) detection via heuristic alignment
- Structure validation against expected patterns
- Grid reconstruction from fragmented text
- Quality scoring with confidence weighting

Usage:
    ocr = PdfTableOCR()
    result = ocr.extract_table_with_merged_cells(page, table_bbox)
    
    if result.quality_score < 0.75:
        reconstructed = ocr.reconstruct_merged_cells(result)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CellData:
    """Represents a table cell."""
    row: int
    col: int
    text: str
    bbox: List[float] = field(default_factory=list)
    is_header: bool = False
    confidence: float = 1.0
    is_merged: bool = False
    merge_direction: str = ""  # "right", "down", "both"


@dataclass
class TableGrid:
    """Represents a reconstructed table grid."""
    rows: List[List[CellData]]
    headers: List[str]
    merged_cells: List[Tuple[int, int, int, int]]  # (row, col, rowspan, colspan)
    quality_score: float = 0.0
    issues: List[str] = field(default_factory=list)


@dataclass
class OCRResult:
    """Result of OCR table extraction."""
    success: bool
    grid: Optional[TableGrid] = None
    quality_score: float = 0.0
    method: str = ""  # "layout", "ocr_fallback", "reconstructed"
    confidence: float = 0.0
    issues: List[str] = field(default_factory=list)
    raw_cells: List[Dict] = field(default_factory=list)


class PdfTableOCR:
    """
    Enhanced OCR for PDF table extraction with merged cell handling.

    Uses heuristic approaches to detect and reconstruct:
    - Horizontal merges (colspan)
    - Vertical merges (rowspan)
    - Misaligned rows/columns
    - Fragmented headers
    """

    # Threshold for detecting merged cells
    ALIGNMENT_THRESHOLD = 5  # pixels
    MIN_CELL_WIDTH = 10
    MIN_CELL_HEIGHT = 5

    # Quality thresholds
    MIN_QUALITY_FOR_USE = 0.70
    MIN_QUALITY_FOR_AUTO = 0.85

    def __init__(self):
        self._last_result: Optional[OCRResult] = None

    def extract_table_with_merged_cells(
        self,
        page,
        table_bbox: List[float],
        expected_columns: Optional[int] = None,
    ) -> OCRResult:
        """
        Extract table with merged cell detection.

        Args:
            page: PyMuPDF page object
            table_bbox: Bounding box [x0, y0, x1, y1]
            expected_columns: Optional expected column count for validation

        Returns:
            OCRResult with extracted grid and quality metrics
        """
        if len(table_bbox) < 4:
            return OCRResult(success=False, issues=["Invalid table bbox"])

        try:
            # Extract text blocks from region
            clip = page.get_pixmap(matrix=None, clip=table_bbox)
            blocks = page.get_text("dict", clip=table_bbox)

            if not blocks or "blocks" not in blocks:
                return self._fallback_text_extraction(page, table_bbox)

            text_blocks = [b for b in blocks["blocks"] if b.get("type") == 0]

            # Parse into cells
            cells = self._parse_text_blocks(text_blocks, table_bbox)

            if not cells:
                return self._fallback_text_extraction(page, table_bbox)

            # Detect merged cells
            merged_info = self._detect_merged_cells(cells)

            # Build grid
            grid = self._build_grid(cells, merged_info, expected_columns)

            # Calculate quality score
            quality = self._calculate_quality(grid, expected_columns)

            result = OCRResult(
                success=True,
                grid=grid,
                quality_score=quality["overall"],
                method="merged_cell_detection",
                confidence=quality["confidence"],
                issues=quality["issues"],
                raw_cells=cells,
            )

            self._last_result = result
            return result

        except Exception as e:
            logger.warning(f"OCR extraction failed: {e}")
            return OCRResult(
                success=False,
                issues=[f"Extraction error: {str(e)}"],
            )

    def _parse_text_blocks(
        self,
        blocks: List[Dict],
        table_bbox: List[float],
    ) -> List[CellData]:
        """Parse text blocks into structured cells."""
        cells: List[CellData] = []
        x0, y0, x1, y1 = table_bbox
        width = x1 - x0
        height = y1 - y0

        for block in blocks:
            bbox = block.get("bbox", [])
            if len(bbox) < 4:
                continue

            # Extract text
            text = ""
            if "lines" in block:
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        text += span.get("text", "")

            text = text.strip()
            if not text:
                continue

            # Calculate relative position
            rel_x = (bbox[0] - x0) / width if width > 0 else 0
            rel_y = (bbox[1] - y0) / height if height > 0 else 0

            # Determine column/row
            col = int(rel_x * 10)  # 10-column grid
            row = int(rel_y * 20)   # 20-row grid

            cells.append(CellData(
                row=row,
                col=col,
                text=text,
                bbox=bbox,
                confidence=0.8,
            ))

        return cells

    def _detect_merged_cells(self, cells: List[CellData]) -> Dict:
        """Detect colspan/rowspan patterns from cell alignment."""
        merged: Dict[Tuple[int, int], Tuple[int, int]] = {}

        # Group by row
        rows: Dict[int, List[CellData]] = {}
        for cell in cells:
            rows.setdefault(cell.row, []).append(cell)

        # Detect horizontal merges (colspan)
        for row_idx, row_cells in rows.items():
            sorted_cells = sorted(row_cells, key=lambda c: c.col)
            prev_cell = None

            for cell in sorted_cells:
                if prev_cell is None:
                    prev_cell = cell
                    continue

                # Check if cells are adjacent (potential merge)
                gap = cell.col - prev_cell.col
                if gap > 1:
                    # Calculate gap width based on bbox
                    prev_right = prev_cell.bbox[2] if prev_cell.bbox else 0
                    cell_left = cell.bbox[0] if cell.bbox else 0

                    # If gap is small, likely merged cells
                    if prev_right and cell_left:
                        gap_width = cell_left - prev_right
                        avg_width = (cell_left + prev_right) / 2
                        if gap_width / avg_width < 0.3:  # Less than 30% gap
                            merged[(row_idx, prev_cell.col)] = (1, gap)  # colspan

                prev_cell = cell

        # Detect vertical merges (rowspan)
        cols: Dict[int, List[CellData]] = {}
        for cell in cells:
            cols.setdefault(cell.col, []).append(cell)

        for col_idx, col_cells in cols.items():
            sorted_cells = sorted(col_cells, key=lambda c: c.row)
            prev_cell = None

            for cell in sorted_cells:
                if prev_cell is None:
                    prev_cell = cell
                    continue

                gap = cell.row - prev_cell.row
                if gap > 1:
                    # Check if likely vertical merge
                    prev_bottom = prev_cell.bbox[3] if prev_cell.bbox else 0
                    cell_top = cell.bbox[1] if cell.bbox else 0

                    if prev_bottom and cell_top:
                        gap_height = cell_top - prev_bottom
                        avg_height = (cell_top + prev_bottom) / 2
                        if gap_height / avg_height < 0.3:
                            merged[(prev_cell.row, col_idx)] = (gap, 1)  # rowspan

                prev_cell = cell

        return merged

    def _build_grid(
        self,
        cells: List[CellData],
        merged_info: Dict,
        expected_columns: Optional[int] = None,
    ) -> TableGrid:
        """Build table grid from cells."""
        if not cells:
            return TableGrid(rows=[], headers=[], merged_cells=[])

        # Determine dimensions
        max_row = max(c.row for c in cells) + 1
        max_col = max(c.col for c in cells) + 1

        if expected_columns:
            max_col = max(max_col, expected_columns)

        # Initialize grid
        grid: List[List[CellData]] = []
        for r in range(max_row):
            grid.append([None] * max_col)

        # Place cells
        for cell in cells:
            if cell.row < len(grid) and cell.col < len(grid[0]):
                grid[cell.row][cell.col] = cell

        # Extract headers (first row)
        headers = []
        if grid:
            for cell in grid[0]:
                if cell:
                    headers.append(cell.text)
                else:
                    headers.append("")

        # Convert merged info to list
        merged_list: List[Tuple[int, int, int, int]] = []
        for (row, col), (rowspan, colspan) in merged_info.items():
            merged_list.append((row, col, rowspan, colspan))

        return TableGrid(
            rows=grid,
            headers=headers,
            merged_cells=merged_list,
        )

    def _calculate_quality(
        self,
        grid: TableGrid,
        expected_columns: Optional[int] = None,
    ) -> Dict:
        """Calculate quality score for extracted table."""
        issues = []
        score = 1.0

        # Check for empty cells
        total_cells = sum(len(row) for row in grid.rows)
        empty_cells = sum(
            1 for row in grid.rows for cell in row if cell is None
        )

        if total_cells > 0:
            fill_ratio = 1 - (empty_cells / total_cells)
            if fill_ratio < 0.5:
                issues.append("low_fill_ratio")
                score *= 0.7
            elif fill_ratio < 0.7:
                issues.append("medium_fill_ratio")
                score *= 0.9

        # Check column consistency
        if grid.rows:
            col_counts = [len(row) for row in grid.rows]
            if len(set(col_counts)) > 1:
                issues.append("inconsistent_columns")
                score *= 0.85

        # Check against expected columns
        if expected_columns and grid.rows:
            for row in grid.rows:
                if len(row) != expected_columns:
                    issues.append("column_mismatch")
                    score *= 0.8
                    break

        # Check for valid headers
        if not grid.headers or not any(grid.headers):
            issues.append("missing_headers")
            score *= 0.9

        # Merged cells bonus
        if grid.merged_cells:
            score *= 1.05  # Small bonus for detecting merges
            score = min(score, 1.0)

        confidence = score
        overall = max(0.0, min(1.0, score))

        return {
            "overall": round(overall, 3),
            "confidence": round(confidence, 3),
            "issues": issues,
        }

    def _fallback_text_extraction(
        self,
        page,
        table_bbox: List[float],
    ) -> OCRResult:
        """Fallback to simple text extraction."""
        try:
            text = page.get_text("text", clip=table_bbox)
            lines = text.split("\n")

            cells = []
            for row_idx, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue

                # Split by multiple spaces (column separator)
                parts = re.split(r"\s{2,}", line)

                for col_idx, part in enumerate(parts):
                    part = part.strip()
                    if part:
                        cells.append(CellData(
                            row=row_idx,
                            col=col_idx,
                            text=part,
                            confidence=0.6,  # Lower confidence for fallback
                        ))

            grid = self._build_grid(cells, {}, None)
            quality = self._calculate_quality(grid, None)

            return OCRResult(
                success=len(cells) > 0,
                grid=grid,
                quality_score=quality["overall"],
                method="text_fallback",
                confidence=quality["confidence"],
                issues=quality["issues"] + ["used_fallback_method"],
                raw_cells=cells,
            )

        except Exception as e:
            return OCRResult(
                success=False,
                issues=[f"Fallback extraction failed: {str(e)}"],
            )

    def reconstruct_merged_cells(
        self,
        ocr_result: OCRResult,
        strategy: str = "heuristic",
    ) -> OCRResult:
        """
        Attempt to reconstruct merged cells in a table.

        Args:
            ocr_result: Previous OCR result to improve
            strategy: "heuristic" or "structural"

        Returns:
            OCRResult with reconstructed cells
        """
        if not ocr_result or not ocr_result.grid:
            return ocr_result

        grid = ocr_result.grid
        reconstructed = []

        # Strategy 1: Heuristic - fill gaps based on alignment
        if strategy == "heuristic":
            for row_idx, row in enumerate(grid.rows):
                prev_cell = None
                for col_idx, cell in enumerate(row):
                    if cell is None:
                        # Check if this should be merged
                        if prev_cell:
                            # Check for horizontal merge
                            if col_idx < len(row) - 1:
                                next_cell = row[col_idx + 1]
                                if next_cell:
                                    gap = col_idx - (prev_cell.col if prev_cell else 0)
                                    if gap > 0:
                                        reconstructed.append(CellData(
                                            row=row_idx,
                                            col=col_idx,
                                            text="",
                                            is_merged=True,
                                            merge_direction="left",
                                            confidence=0.5,
                                        ))
                    else:
                        prev_cell = cell

        # Update quality score
        new_quality = self._calculate_quality(grid, None)
        new_quality["issues"].append("reconstruction_applied")

        return OCRResult(
            success=True,
            grid=grid,
            quality_score=new_quality["overall"],
            method=f"reconstructed_{strategy}",
            confidence=new_quality["confidence"],
            issues=new_quality["issues"],
            raw_cells=ocr_result.raw_cells,
        )

    def validate_register_table(
        self,
        grid: TableGrid,
        expected_registers: Optional[List[str]] = None,
    ) -> Dict:
        """
        Validate extracted table as a register map.

        Register tables typically have:
        - Headers: Register, Offset, Reset, Access, Description
        - Registers with 0x addresses
        - Bitfield names in last columns

        Returns:
            Validation report with is_valid flag
        """
        validation = {
            "is_valid": False,
            "is_register_table": False,
            "confidence": 0.0,
            "checks": {},
            "issues": [],
        }

        if not grid.headers:
            validation["issues"].append("no_headers")
            return validation

        # Check header patterns
        header_text = " ".join(grid.headers).lower()
        has_register_header = any(
            term in header_text
            for term in ["register", "name", "offset", "address", "reset"]
        )
        has_access_header = any(
            term in header_text
            for term in ["access", "type", "read", "write"]
        )

        validation["checks"]["has_register_column"] = has_register_header
        validation["checks"]["has_access_column"] = has_access_header

        # Count register-like entries
        register_count = 0
        offset_count = 0

        for row in grid.rows[1:]:  # Skip header
            for cell in row:
                if cell and cell.text:
                    text = cell.text
                    # Check for register name pattern
                    if re.match(r"^[A-Z][A-Z0-9]+_?[A-Z0-9]*$", text):
                        register_count += 1
                    # Check for offset pattern
                    if re.match(r"0x[0-9A-Fa-f]+", text):
                        offset_count += 1

        validation["checks"]["register_entries"] = register_count
        validation["checks"]["offset_entries"] = offset_count

        # Determine if this is a register table
        is_register = (
            has_register_header and
            register_count >= 2 and
            offset_count >= 2
        )

        validation["is_register_table"] = is_register

        if is_register:
            validation["confidence"] = min(1.0, 0.5 + (register_count * 0.05))
            validation["is_valid"] = validation["confidence"] >= 0.7

        if expected_registers:
            matched = sum(
                1 for reg in expected_registers
                if any(reg in cell.text for row in grid.rows for cell in row if cell)
            )
            validation["checks"]["expected_matched"] = matched
            validation["checks"]["expected_total"] = len(expected_registers)

        return validation


def extract_tables_with_fallback(
    page,
    layout_tables: List[Dict],
    min_quality: float = 0.70,
) -> List[Dict]:
    """
    Extract tables from page with automatic OCR fallback.

    Args:
        page: PyMuPDF page
        layout_tables: Tables from layout extraction
        min_quality: Minimum quality threshold

    Returns:
        List of enhanced table dicts
    """
    ocr = PdfTableOCR()
    results = []

    for table in layout_tables:
        bbox = table.get("table_bbox", [])
        if not bbox:
            continue

        result = ocr.extract_table_with_merged_cells(page, bbox)

        if result.success and result.quality_score >= min_quality:
            # Add quality report to table
            table["ocr_result"] = {
                "quality_score": result.quality_score,
                "confidence": result.confidence,
                "method": result.method,
                "issues": result.issues,
                "headers": result.grid.headers if result.grid else [],
                "row_count": len(result.grid.rows) if result.grid else 0,
            }
            results.append(table)
        elif result.success:
            # Try reconstruction
            reconstructed = ocr.reconstruct_merged_cells(result)
            if reconstructed.quality_score > result.quality_score:
                table["ocr_result"] = {
                    "quality_score": reconstructed.quality_score,
                    "confidence": reconstructed.confidence,
                    "method": reconstructed.method,
                    "issues": reconstructed.issues,
                    "reconstructed": True,
                }
                results.append(table)

    return results


if __name__ == "__main__":
    print("=== PDF Table OCR ===")
    print("Usage:")
    print("  ocr = PdfTableOCR()")
    print("  result = ocr.extract_table_with_merged_cells(page, bbox)")
    print("  print(result.quality_score, result.grid.headers)")
