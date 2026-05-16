"""RMParser - extracts peripheral/register/bitfield definitions from Reference Manual PDFs."""

import re
from pathlib import Path
from typing import Dict, List, Optional


class RMParser:
    """
    Parse STM32 Reference Manual PDFs to extract register definitions.

    Supports extraction of:
    - Peripheral names and base addresses
    - Register names, offsets, and access types
    - Bitfield names, offsets, widths, and descriptions
    - Known enumerated values for bitfields

    Uses structured text patterns to identify register descriptions
    in the PDF text content. Designed to be used after PDF
    text extraction (e.g., via OCR or PDF library).

    NOTE: This parses pre-extracted text. Use SchemaExtractor
    to first convert a PDF to text, then feed that text here.
    """

    def __init__(self):
        self._schema: Dict = {
            "schema_version": "1.0",
            "chip": "",
            "entries": [],
        }
        self._current_peripheral: Optional[Dict] = None
        self._current_register: Optional[Dict] = None

    def parse(self, pdf_path: str) -> Dict:
        """
        Parse a Reference Manual PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Schema dict with peripheral/register/bitfield definitions
        """
        from src.domains.hardware_engine.parser.extractor import SchemaExtractor

        extractor = SchemaExtractor()
        text = extractor.extract(pdf_path)

        if not text:
            return self._schema

        return self.parse_text(text, chip=self._infer_chip(pdf_path))

    def parse_text(self, text: str, chip: str = "") -> Dict:
        """
        Parse pre-extracted text from a Reference Manual.

        Args:
            text: Extracted text content
            chip: Chip name (e.g., "STM32F407")

        Returns:
            Schema dict
        """
        self._schema = {
            "schema_version": "1.0",
            "chip": chip,
            "entries": [],
        }

        lines = text.split("\n")
        for line in lines:
            self._process_line(line.strip())

        self._flush_peripheral()
        return self._schema

    def _infer_chip(self, pdf_path: str) -> str:
        """Infer chip name from file path."""
        name = Path(pdf_path).stem.upper()
        if "F407" in name:
            return "STM32F407"
        if "F103" in name:
            return "STM32F103"
        if "F4" in name:
            return "STM32F4"
        if "F0" in name:
            return "STM32F0"
        return name

    def _process_line(self, line: str):
        """Process a single line of text."""
        # Skip empty lines
        if not line:
            return

        # Detect peripheral header (e.g., "37 USART")
        peripheral_match = re.match(
            r"^(\d+)\s+([A-Z][A-Z0-9_]+)\s*(?:peripheral)?",
            line,
        )
        if peripheral_match and len(line) < 60:
            self._flush_peripheral()
            base_addr = peripheral_match.group(1)
            peri_name = peripheral_match.group(2)
            self._current_peripheral = {
                "peripheral": peri_name,
                "base_address": f"0x{base_addr}000",
                "description": "",
                "registers": [],
            }
            return

        # Detect register line (e.g., "Status register (USART_SR)")
        # or "USART_CR1    0x00   RW   Control register 1"
        register_match = re.match(
            r"^([A-Z_][A-Z0-9_]+)\s+(?:0x)?([0-9A-Fa-f]+)\s+([A-Z]{2})\s+(.+)",
            line,
        )
        if register_match:
            self._flush_register()
            name = register_match.group(1)
            offset = int(register_match.group(2), 16)
            access = register_match.group(3)
            description = register_match.group(4).strip()
            self._current_register = {
                "register": name,
                "offset": offset,
                "access": access,
                "description": description,
                "bitfields": [],
            }
            if self._current_peripheral:
                self._current_peripheral["registers"].append(self._current_register)
            return

        # Detect bitfield (e.g., "Bit 0: PE - Parity error")
        bitfield_match = re.match(
            r"^(?:Bit\s+)?(\d+)(?::(\d+))?\s*:\s*([A-Z_][A-Z0-9_]+)\s*[-=]\s*(.+)",
            line,
        )
        if bitfield_match:
            start_bit = int(bitfield_match.group(1))
            end_bit = int(bitfield_match.group(2)) if bitfield_match.group(2) else start_bit
            bf_name = bitfield_match.group(3)
            bf_desc = bitfield_match.group(4).strip()
            width = end_bit - start_bit + 1

            if self._current_register is not None:
                self._current_register["bitfields"].append({
                    "name": bf_name,
                    "offset": start_bit,
                    "width": width,
                    "description": bf_desc,
                    "values": self._extract_values(bf_desc),
                })
            return

        # Detect bitfield value (e.g., "0: 1 = reset")
        value_match = re.match(
            r"^\s*(\d+)\s*[:=]\s*(.+)",
            line,
        )
        if value_match and self._current_register:
            bit_val = int(value_match.group(1))
            val_desc = value_match.group(2).strip()
            if self._current_register["bitfields"]:
                last_bf = self._current_register["bitfields"][-1]
                if "values" not in last_bf:
                    last_bf["values"] = {}
                last_bf["values"][str(bit_val)] = val_desc

    def _extract_values(self, description: str) -> Dict[str, int]:
        """Extract enumerated values from a bitfield description."""
        values = {}
        # Pattern: "Mode: 0 = reset, 1 = set"
        mode_match = re.findall(r"(\d+)\s*=\s*([\w\s]+?)(?:,|$)", description)
        for val, desc in mode_match:
            values[desc.strip()] = int(val)
        return values

    def _flush_register(self):
        """Flush pending register to peripheral."""
        if self._current_register and self._current_peripheral:
            pass

    def _flush_peripheral(self):
        """Flush pending peripheral to schema."""
        if self._current_peripheral and self._current_peripheral.get("registers"):
            self._schema["entries"].append(self._current_peripheral)
        self._current_peripheral = None
        self._current_register = None

    def get_schema(self) -> Dict:
        """Get the parsed schema."""
        return self._schema

    def to_json(self, path: str):
        """Write schema to JSON file."""
        import json
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._schema, f, indent=2, ensure_ascii=False)
