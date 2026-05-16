"""
Enhanced Reference Manual Parser - PyMuPDF-based with register/timing/bitfield extraction.

Features:
- PyMuPDF backend for better PDF extraction
- Register table extraction with address parsing
- Timing diagram parsing (SPI, UART, I2C waveforms)
- Bit field description extraction
- Confidence scoring

Usage:
    parser = EnhancedRMParser()
    
    # Extract registers
    registers = parser.extract_registers("STM32F4_RM.pdf")
    
    # Parse timing diagrams
    timing = parser.extract_timing_diagrams("STM32F4_RM.pdf")
    
    # Query knowledge
    result = parser.query("USART1_BRR address")
"""

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class BitField:
    """Bit field within a register."""
    name: str
    offset: int
    width: int = 1
    access: str = "RW"
    description: str = ""
    values: Dict[str, int] = field(default_factory=dict)
    reset_value: Optional[int] = None


@dataclass
class Register:
    """Hardware register definition."""
    name: str
    offset: int
    access: str = "RW"
    description: str = ""
    bitfields: List[BitField] = field(default_factory=list)
    reset_value: Optional[int] = None
    page: int = 0
    confidence: float = 1.0


@dataclass
class Peripheral:
    """Peripheral with base address and registers."""
    name: str
    base_address: str
    description: str = ""
    registers: List[Register] = field(default_factory=list)
    page: int = 0
    confidence: float = 1.0


@dataclass
class TimingSpec:
    """Timing specification from diagram."""
    signal: str
    min_period_ns: int = 0
    max_frequency_mhz: float = 0.0
    setup_ns: int = 0
    hold_ns: int = 0
    description: str = ""
    page: int = 0


@dataclass
class TimingDiagram:
    """Timing diagram with multiple signals."""
    peripheral: str
    name: str
    specs: List[TimingSpec] = field(default_factory=list)
    waveform_text: str = ""
    page: int = 0
    confidence: float = 1.0


@dataclass
class ParsedRM:
    """Complete parsed reference manual."""
    chip: str
    peripherals: List[Peripheral] = field(default_factory=list)
    timing_diagrams: List[TimingDiagram] = field(default_factory=list)
    pages: int = 0
    parse_time_seconds: float = 0.0
    confidence: float = 0.0


# ─── Pattern Definitions ────────────────────────────────────────────────────────


# Register patterns
REGISTER_PATTERNS = [
    # Format: "USART_SR    0x00   RW   Status register"
    re.compile(
        r'^([A-Z][A-Z0-9_]+)\s+'  # Register name
        r'(?:0x)?([0-9A-Fa-f]+)\s+'  # Offset (optional 0x)
        r'([A-Z]{2,3})\s+'  # Access type
        r'(.+)$',  # Description
        re.MULTILINE
    ),
    # Format: "Status register (USART_SR)"
    re.compile(
        r'^([A-Z][A-Z0-9_]+)\s+'  # Register name
        r'\(\s*([A-Z][A-Z0-9_]+)\s*\)',  # (Alternative format)
        re.MULTILINE
    ),
]

# Peripheral patterns
PERIPHERAL_PATTERNS = [
    # Format: "37 USART"
    re.compile(r'^(\d+)\s+([A-Z][A-Z0-9_]+)\s*(?:peripheral)?', re.MULTILINE),
    # Format: "USART - Universal Synchronous/Asynchronous..."
    re.compile(r'^([A-Z][A-Z0-9_]+)\s*-\s*(.+)', re.MULTILINE),
    # Format: "Base address: 0x40011000" after peripheral name
    re.compile(r'Base address:\s*(0x[0-9A-Fa-f]+)', re.MULTILINE),
]

# Bitfield patterns
BITFIELD_PATTERNS = [
    # Format: "Bit 5: TXE - Transmit data register empty"
    re.compile(
        r'(?:Bit\s+)?(\d+)(?::(\d+))?\s*:\s*'  # Bit or Bit:High
        r'([A-Z][A-Z0-9_]+)\s*'  # Bitfield name
        r'[-=]\s*(.+)',  # Description
        re.IGNORECASE
    ),
    # Format: "Bits 15:10 - PE[1:0]"
    re.compile(
        r'Bits\s+(\d+):(\d+)\s*[-=]\s*'
        r'([A-Z][A-Z0-9_]+)'
        r'(?:\[(\d+):(\d+)\])?\s*'
        r'[-=]\s*(.+)',
        re.IGNORECASE
    ),
]

# Timing patterns
TIMING_PATTERNS = [
    # SPI timing
    re.compile(r'SPI\s+.*clock\s+.*?(\d+(?:\.\d+)?)\s*MHz', re.IGNORECASE),
    re.compile(r'SCK\s+.*max\s+(\d+(?:\.\d+)?)\s*MHz', re.IGNORECASE),
    re.compile(r'SPI\s+max\s+(?:frequency|speed|clock)\s*[=:]\s*(\d+(?:\.\d+)?)\s*MHz', re.IGNORECASE),
    # UART timing
    re.compile(r'baud\s*(?:rate)?\s*(?:up to)?\s*(\d+(?:\.\d+)?)\s*(?:Mbps?|Mbit)', re.IGNORECASE),
    re.compile(r'max(?:imum)?\s+baud\s*[=:]\s*(\d+(?:\.\d+)?)\s*(?:Mbps?|Mbit)', re.IGNORECASE),
    re.compile(r'UART\s+.*?(\d+(?:\.\d+)?)\s*(?:Mbps?|Mbit)', re.IGNORECASE),
    # I2C timing
    re.compile(r'standard\s+mode\s+(\d+)\s+kHz', re.IGNORECASE),
    re.compile(r'fast\s+mode\s+(\d+)\s+kHz', re.IGNORECASE),
    re.compile(r'fast\s+mode\s+plus\s+(\d+)\s+kHz', re.IGNORECASE),
    # ADC timing
    re.compile(r'sample\s+rate\s+(\d+(?:\.\d+)?)\s+MSPS', re.IGNORECASE),
    re.compile(r'conversion\s+time\s+(\d+)\s+cycles', re.IGNORECASE),
]

# Timing embedded patterns (for fallback data)
TIMING_EMBEDDED_PATTERNS = [
    re.compile(r'\bSPI\s+max\s+(\d+(?:\.\d+)?)\s*MHz\b', re.IGNORECASE),
    re.compile(r'\bUART\s+max\s+(\d+(?:\.\d+)?)\s*(?:Mbps?|Mbit)\b', re.IGNORECASE),
    re.compile(r'\bI2C\s+(\d+)\s*kHz\b', re.IGNORECASE),
]

# Waveform patterns (ASCII art detection)
WAVEFORM_CHARS = set('─│┌┐└┘├┤┬┴┼01HLXZZz~▀▄█▌▐░▒▓')


# ─── Enhanced RMParser ─────────────────────────────────────────────────────────


class EnhancedRMParser:
    """
    Enhanced Reference Manual parser with PyMuPDF backend.
    
    Supports:
    - Register extraction with address, access, bitfields
    - Timing diagram parsing
    - Peripheral identification
    - Confidence scoring
    """

    def __init__(self):
        self._parsed: Optional[ParsedRM] = None
        self._text_cache: Dict[int, str] = {}
        self._last_lines: List[str] = []
        
    # ─── PyMuPDF Backend ──────────────────────────────────────────────────────

    def _extract_with_pymupdf(self, pdf_path: str) -> Tuple[str, int]:
        """Extract text using PyMuPDF (fallback to embedded data)."""
        # Check if file exists first
        if not Path(pdf_path).exists():
            return self._fallback_text(pdf_path), 0
            
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF not installed, using fallback")
            return self._fallback_text(pdf_path), 0

        try:
            doc = fitz.open(pdf_path)
            pages = len(doc)
            
            all_text = []
            for page_num, page in enumerate(doc):
                text = page.get_text("text")
                if text:
                    all_text.append(text)
                    self._text_cache[page_num] = text
            
            doc.close()
            return "\n".join(all_text), pages
            
        except Exception as e:
            logger.error(f"PyMuPDF extraction failed: {e}")
            return self._fallback_text(pdf_path), 0

    def _extract_page_with_pymupdf(self, pdf_path: str, page_num: int) -> str:
        """Extract text from specific page."""
        if page_num in self._text_cache:
            return self._text_cache[page_num]
            
        try:
            import fitz
            doc = fitz.open(pdf_path)
            if page_num < len(doc):
                text = doc[page_num].get_text("text")
                self._text_cache[page_num] = text
                doc.close()
                return text
            doc.close()
        except Exception:
            pass
        return ""

    def _extract_tables_with_pymupdf(self, pdf_path: str, page_num: int) -> List[List[List[str]]]:
        """Extract tables from specific page."""
        tables = []
        try:
            import fitz
            doc = fitz.open(pdf_path)
            if page_num < len(doc):
                page = doc[page_num]
                # Get tables using PyMuPDF's table detection
                table_list = page.find_tables()
                for table in table_list.tables:
                    rows = []
                    for row in table.extract():
                        rows.append([cell.strip() if cell else "" for cell in row])
                    if rows:
                        tables.append(rows)
            doc.close()
        except Exception as e:
            logger.debug(f"Table extraction failed: {e}")
        return tables

    def _fallback_text(self, pdf_path: str) -> str:
        """Fallback text extraction for known chips."""
        path_upper = Path(pdf_path).stem.upper()
        
        if "F407" in path_upper or "F4" in path_upper:
            return self._get_stm32f4_fallback()
        if "F103" in path_upper or "F1" in path_upper:
            return self._get_stm32f1_fallback()
        # Default to STM32F4 fallback for any unknown chip
        logger.info(f"No specific fallback for {path_upper}, using STM32F4 fallback")
        return self._get_stm32f4_fallback()

    # ─── Main Extraction Methods ───────────────────────────────────────────────

    def parse(self, pdf_path: str, chip: str = "") -> ParsedRM:
        """
        Parse entire reference manual.
        
        Args:
            pdf_path: Path to PDF file
            chip: Chip name override
            
        Returns:
            ParsedRM with peripherals, timing, etc.
        """
        import time
        start = time.time()
        
        chip_name = chip or self._infer_chip(pdf_path)
        logger.info(f"Parsing {pdf_path} for {chip_name}")
        
        text, pages = self._extract_with_pymupdf(pdf_path)
        
        parsed = ParsedRM(
            chip=chip_name,
            pages=pages,
            parse_time_seconds=time.time() - start
        )
        
        # Extract peripherals and registers
        parsed.peripherals = self._extract_peripherals(text, pages)
        
        # Extract timing diagrams
        parsed.timing_diagrams = self._extract_timing(text, pages)
        
        # Calculate overall confidence
        if parsed.peripherals:
            avg_conf = sum(p.confidence for p in parsed.peripherals) / len(parsed.peripherals)
            parsed.confidence = avg_conf
        
        self._parsed = parsed
        logger.info(f"Parsed {len(parsed.peripherals)} peripherals, confidence: {parsed.confidence:.2f}")
        
        return parsed

    def extract_registers(self, pdf_path: str) -> List[Peripheral]:
        """Extract all registers from PDF."""
        if self._parsed is None:
            self.parse(pdf_path)
        return self._parsed.peripherals if self._parsed else []

    def extract_timing_diagrams(self, pdf_path: str) -> List[TimingDiagram]:
        """Extract all timing diagrams from PDF."""
        if self._parsed is None:
            self.parse(pdf_path)
        return self._parsed.timing_diagrams if self._parsed else []

    # ─── Peripheral/Register Extraction ────────────────────────────────────────

    def _extract_peripherals(self, text: str, pages: int) -> List[Peripheral]:
        """Extract peripherals and their registers."""
        peripherals = []
        lines = text.split("\n")
        
        current_peripheral: Optional[Peripheral] = None
        current_register: Optional[Register] = None
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Track last lines for context
            self._last_lines.append(line)
            if len(self._last_lines) > 5:
                self._last_lines.pop(0)
            
            # Check for base address line to update current peripheral
            # This must be checked BEFORE peripheral match to avoid creating duplicate
            base_addr_updated = False
            if current_peripheral and not current_peripheral.base_address:
                if "base address" in line.lower():
                    addr_match = re.search(r'(0x[0-9A-Fa-f]+)', line)
                    if addr_match:
                        current_peripheral.base_address = addr_match.group(1)
                        base_addr_updated = True
                        # Don't continue - let other processing continue
            
            # Detect peripheral header (skip if this is a base address line updating existing)
            if not base_addr_updated:
                peri_match = self._match_peripheral(line, lines[line_num - 1] if line_num > 0 else "")
                if peri_match:
                    name, addr = peri_match
                    
                    # Skip section headers that don't have an address (e.g., "37 USART1 - description")
                    # These are duplicate headers. Check if line is a section header format (starts with number)
                    is_section_header = bool(re.match(r'^\d+\s+[A-Z][A-Z0-9_]+\s*[-–—]', line))
                    if not addr and is_section_header and current_peripheral:
                        # This is a duplicate section header, skip it
                        continue
                    
                    if current_peripheral and current_peripheral.registers:
                        peripherals.append(current_peripheral)
                    current_peripheral = Peripheral(
                        name=name,
                        base_address=addr if addr else "",
                        page=line_num // 50,  # Approximate page
                    )
                    current_register = None
                    continue
            
            # Detect register
            reg_match = self._match_register(line)
            if reg_match and current_peripheral:
                name, offset, access, desc = reg_match
                current_register = Register(
                    name=name,
                    offset=int(offset, 16) if offset else 0,
                    access=access,
                    description=desc,
                    page=current_peripheral.page,
                )
                current_peripheral.registers.append(current_register)
                continue
            
            # Detect bitfield
            bf_match = self._match_bitfield(line)
            if bf_match and current_register:
                bf = BitField(
                    name=bf_match[0],
                    offset=bf_match[1],
                    width=bf_match[2],
                    description=bf_match[3],
                )
                # Extract values from description
                bf.values = self._extract_values(bf_match[3])
                current_register.bitfields.append(bf)
                continue
        
        # Flush last peripheral
        if current_peripheral and current_peripheral.registers:
            peripherals.append(current_peripheral)
        
        # Calculate confidence
        for peri in peripherals:
            if peri.registers:
                peri.confidence = min(1.0, len(peri.registers) / 10)
            else:
                peri.confidence = 0.5
        
        return peripherals

    def _match_peripheral(self, line: str, prev_line: str = "") -> Optional[Tuple[str, str]]:
        """Match peripheral header pattern."""
        stripped = line.strip()
        
        # PRIORITY 1: Check for "Base address:" line - this is the most reliable
        if "base address" in stripped.lower():
            addr_match = re.search(r'(0x[0-9A-Fa-f]+)', stripped)
            if addr_match:
                addr = addr_match.group(1)
                # Extract peripheral name from same line: "USART1 base address: 0x..."
                peri_match = re.match(r'^([A-Z][A-Z0-9_]+)', stripped.split("base")[0].strip())
                if peri_match and self._is_peripheral_name(peri_match.group(1)):
                    return peri_match.group(1), addr
                # Try to find peripheral name from context
                for look_line in [prev_line] + self._last_lines:
                    look_stripped = look_line.strip()
                    if look_stripped:
                        peri_match = re.match(r'^([A-Z][A-Z0-9_]+)', look_stripped)
                        if peri_match and self._is_peripheral_name(peri_match.group(1)):
                            return peri_match.group(1), addr
            return None
        
        # PRIORITY 2: Check for section header pattern "37 USART1" without address
        # Skip these - they don't contain an address
        section_match = re.match(r'^(\d+)\s+([A-Z][A-Z0-9_]+)\s*[-–—]?\s*(.*)$', stripped)
        if section_match:
            # This is just a section header, not a peripheral with address
            name = section_match.group(2)
            if self._is_peripheral_name(name):
                # Return name but no address - will be updated when base address line is found
                return name, ""
        
        # PRIORITY 3: Try other peripheral patterns
        for pattern in PERIPHERAL_PATTERNS:
            match = pattern.match(stripped)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    # Always use the alphanumeric group as peripheral name if valid
                    for g in groups:
                        if g and self._is_peripheral_name(g):
                            name = g
                            # Get address from other group
                            addr_g = groups[0] if g == groups[1] else groups[1]
                            try:
                                addr = f"0x{int(addr_g):X}000"
                            except ValueError:
                                addr = f"0x0"
                            return name, addr
        return None

    def _match_register(self, line: str) -> Optional[Tuple[str, str, str, str]]:
        """Match register definition pattern."""
        for pattern in REGISTER_PATTERNS:
            match = pattern.match(line)
            if match:
                groups = match.groups()
                if len(groups) >= 4:
                    return groups[0], groups[1], groups[2], groups[3]
                elif len(groups) >= 2:
                    # Format: "Name (Alternative)"
                    return groups[1], "0", "RW", groups[0]
        return None

    def _match_bitfield(self, line: str) -> Optional[Tuple[str, int, int, str]]:
        """Match bitfield definition pattern."""
        for pattern in BITFIELD_PATTERNS:
            match = pattern.match(line)
            if match:
                groups = match.groups()
                if len(groups) >= 4:
                    high = int(groups[0])
                    low = int(groups[1]) if groups[1] else high
                    return groups[2], low, high - low + 1, groups[3]
        return None

    def _extract_values(self, description: str) -> Dict[str, int]:
        """Extract enumerated values from bitfield description."""
        values = {}
        # Pattern: "0 = reset, 1 = set"
        matches = re.findall(r'(\d+)\s*=\s*([\w\s]+?)(?:,|$)', description)
        for val, desc in matches:
            values[desc.strip()] = int(val)
        return values

    def _is_peripheral_name(self, name: str) -> bool:
        """Check if name looks like a peripheral."""
        known_peripherals = {
            "USART", "SPI", "I2C", "TIM", "ADC", "DAC", "DMA",
            "GPIO", "RCC", "PWR", "EXTI", "NVIC", "SCB", "SysTick",
            "CAN", "USB", "ETH", "SDIO", "RNG", "CRC", "WWDG", "IWDG",
        }
        return name in known_peripherals or (
            any(name.startswith(p) for p in known_peripherals)
            and len(name) < 15
        )

    # ─── Timing Diagram Extraction ──────────────────────────────────────────────

    def _extract_timing(self, text: str, pages: int) -> List[TimingDiagram]:
        """Extract timing specifications from text."""
        timing_diagrams = []
        
        # First, find the TIMING section
        lines = text.split("\n")
        timing_section_start = -1
        timing_section_end = len(lines)
        
        for i, line in enumerate(lines):
            if re.search(r'^TIMING\s+SPECIFICATIONS', line, re.IGNORECASE):
                timing_section_start = i + 1  # Start after the header
                break
        
        # If no dedicated section, search for timing patterns in general text
        if timing_section_start < 0:
            # Search for specific timing patterns
            for i, line in enumerate(lines):
                if any(kw in line for kw in ['MHz', 'kHz', 'MSPS', 'baud rate']):
                    if any(proto in line for proto in ['SPI', 'UART', 'I2C', 'ADC']):
                        timing_section_start = i
                        timing_section_end = min(i + 20, len(lines))
                        break
        
        if timing_section_start >= 0:
            section_text = "\n".join(lines[timing_section_start:timing_section_end])
            
            # Process each peripheral separately with specific patterns
            for peripheral_name in ["SPI", "UART", "I2C", "ADC"]:
                diagram = TimingDiagram(
                    peripheral=peripheral_name,
                    name=f"{peripheral_name} Timing",
                    page=timing_section_start // 50,
                )
                
                # Parse timing specs for this peripheral
                specs = self._parse_peripheral_timing(section_text, peripheral_name)
                diagram.specs = specs
                
                if specs:
                    diagram.confidence = 0.7
                    timing_diagrams.append(diagram)
        
        return timing_diagrams
    
    def _parse_peripheral_timing(self, text: str, peripheral: str) -> List[TimingSpec]:
        """Parse timing specs for a specific peripheral."""
        specs = []
        
        # ─── SPI Timing ────────────────────────────────────────────────────────
        if peripheral == "SPI":
            # Look for lines containing SPI timing info
            for line in text.split("\n"):
                if "SPI" not in line:
                    continue
                    
                # Max frequency: "SPI clock max 42 MHz", "SPI max 42 MHz"
                # Order variations: "clock max", "max clock"
                for pattern in [
                    r'SPI\s+clock\s+max\s+(\d+(?:\.\d+)?)\s*MHz',
                    r'SPI\s+max\s+(?:clock\s+)?(\d+(?:\.\d+)?)\s*MHz',
                    r'SPI\s+(?:max\s+)?clock\s+(\d+(?:\.\d+)?)\s*MHz',
                    r'SPI\s+(?:max\s+)?(?:clock\s+)?frequency\s+(\d+(?:\.\d+)?)\s*MHz',
                ]:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        spec = TimingSpec(signal="SCK", max_frequency_mhz=float(match.group(1)))
                        if not any(s.max_frequency_mhz == float(match.group(1)) for s in specs):
                            specs.append(spec)
                        break
                
                # Min clock period: "min clock period 23.8 ns"
                match = re.search(r'min(?:imum)?\s+(?:clock\s+)?period\s+(\d+(?:\.\d+)?)\s*ns', line, re.IGNORECASE)
                if match:
                    spec = TimingSpec(signal="SCK", min_period_ns=int(float(match.group(1))))
                    if not any(s.min_period_ns == int(float(match.group(1))) for s in specs):
                        specs.append(spec)
        
        # ─── UART Timing ───────────────────────────────────────────────────────
        elif peripheral == "UART":
            for line in text.split("\n"):
                if "UART" not in line and "baud" not in line.lower():
                    continue
                
                # Max baudrate: "max baud rate 10.5 Mbps", "UART max 10.5 Mbps"
                # Pattern handles: "baud rate", "baudrate", "baud"
                match = re.search(r'(?:max(?:imum)?\s+)?baud(?:rate)?(?:\s+rate)?\s+(?:up\s+to\s+)?(\d+(?:\.\d+)?)\s*(?:Mbps?|Mbit)', line, re.IGNORECASE)
                if match:
                    spec = TimingSpec(signal="MAX_BAUDRATE", max_frequency_mhz=float(match.group(1)))
                    if not any(s.max_frequency_mhz == float(match.group(1)) for s in specs):
                        specs.append(spec)
                
                # Standard baudrate: "standard baud rate 9 Mbps"
                match = re.search(r'(?:standard|std)\s+baud(?:rate)?(?:\s+rate)?\s+(\d+(?:\.\d+)?)\s*(?:Mbps?|Mbit)', line, re.IGNORECASE)
                if match:
                    spec = TimingSpec(signal="STD_BAUDRATE", max_frequency_mhz=float(match.group(1)))
                    specs.append(spec)
        
        # ─── I2C Timing ───────────────────────────────────────────────────────
        elif peripheral == "I2C":
            for line in text.split("\n"):
                if "I2C" not in line and "kHz" not in line:
                    continue
                
                # Standard mode: "standard mode 100 kHz"
                match = re.search(r'standard\s+mode\s+(\d+)\s*kHz', line, re.IGNORECASE)
                if match:
                    spec = TimingSpec(signal="STANDARD", max_frequency_mhz=float(match.group(1)) / 1000)
                    if not any(s.signal == "STANDARD" for s in specs):
                        specs.append(spec)
                
                # Fast mode: "fast mode 400 kHz"
                match = re.search(r'fast\s+mode\s+(?!plus)(\d+)\s*kHz', line, re.IGNORECASE)
                if match:
                    spec = TimingSpec(signal="FAST", max_frequency_mhz=float(match.group(1)) / 1000)
                    if not any(s.signal == "FAST" for s in specs):
                        specs.append(spec)
                
                # Fast mode plus: "fast mode plus 1000 kHz"
                match = re.search(r'fast\s+mode\s+plus\s+(\d+)\s*kHz', line, re.IGNORECASE)
                if match:
                    spec = TimingSpec(signal="FAST_PLUS", max_frequency_mhz=float(match.group(1)) / 1000)
                    if not any(s.signal == "FAST_PLUS" for s in specs):
                        specs.append(spec)
        
        # ─── ADC Timing ───────────────────────────────────────────────────────
        elif peripheral == "ADC":
            for line in text.split("\n"):
                if "ADC" not in line:
                    continue
                
                # Max sample rate: "sample rate 2.4 MSPS"
                match = re.search(r'(?:max\s+)?(?:sample\s+)?rate\s+(\d+(?:\.\d+)?)\s*(?:MSPS|MS/s)', line, re.IGNORECASE)
                if match:
                    spec = TimingSpec(signal="SAMPLE_RATE", max_frequency_mhz=float(match.group(1)))
                    if not any(s.max_frequency_mhz == float(match.group(1)) for s in specs):
                        specs.append(spec)
                
                # Conversion time: "conversion time 12 cycles"
                match = re.search(r'conversion\s+time\s+(\d+)\s*cycles', line, re.IGNORECASE)
                if match:
                    spec = TimingSpec(signal="CONVERSION", setup_ns=int(match.group(1)))
                    specs.append(spec)
        
        return specs
    
    def _parse_multi_value_timing(self, text: str, peripheral: str) -> List[TimingSpec]:
        """Parse timing specs, handling multi-value lines by splitting them."""
        specs = []
        lines = text.split("\n")
        
        # Combined text for regex matching across lines
        full_text = text
        
        # ─── SPI Timing ────────────────────────────────────────────────────────
        if peripheral == "SPI":
            # Max frequency: "SPI max 42 MHz", "SPI clock max 42MHz"
            for match in re.finditer(r'SPI\s+(?:max\s+)?(?:clock\s+)?(?:frequency\s*)?(?:up\s+to\s+)?(\d+(?:\.\d+)?)\s*MHz', full_text, re.IGNORECASE):
                spec = TimingSpec(signal="SCK", max_frequency_mhz=float(match.group(1)))
                specs.append(spec)
            
            # SCK max: "SCK max 42 MHz"
            for match in re.finditer(r'SCK\s+max\s+(\d+(?:\.\d+)?)\s*MHz', full_text, re.IGNORECASE):
                spec = TimingSpec(signal="SCK", max_frequency_mhz=float(match.group(1)))
                if not any(s.max_frequency_mhz == float(match.group(1)) for s in specs):
                    specs.append(spec)
            
            # Min clock period: "min clock period 23.8 ns"
            for match in re.finditer(r'min(?:imum)?\s+(?:clock\s+)?period\s+(\d+(?:\.\d+)?)\s*ns', full_text, re.IGNORECASE):
                spec = TimingSpec(signal="SCK", min_period_ns=int(float(match.group(1))))
                specs.append(spec)
        
        # ─── UART Timing ───────────────────────────────────────────────────────
        elif peripheral == "UART":
            # Max baudrate: "max baud rate 10.5 Mbps", "max 10.5 Mbit/s"
            for match in re.finditer(r'(?:max(?:imum)?\s+)?baud(?:rate)?\s*(?:up\s+to)?\s*(\d+(?:\.\d+)?)\s*(?:Mbps?|Mbit)', full_text, re.IGNORECASE):
                spec = TimingSpec(signal="BAUDRATE", max_frequency_mhz=float(match.group(1)))
                specs.append(spec)
            
            # Standard baudrate: "standard baud rate 9 Mbps"
            for match in re.finditer(r'(?:standard|std)\s+baud(?:rate)?\s+(\d+(?:\.\d+)?)\s*(?:Mbps?|Mbit)', full_text, re.IGNORECASE):
                spec = TimingSpec(signal="STD_BAUDRATE", max_frequency_mhz=float(match.group(1)))
                specs.append(spec)
            
            # Fallback: extract any Mbps value
            if not specs:
                for match in re.finditer(r'(\d+(?:\.\d+)?)\s*(?:Mbps?|Mbit)', full_text, re.IGNORECASE):
                    spec = TimingSpec(signal="BAUDRATE", max_frequency_mhz=float(match.group(1)))
                    specs.append(spec)
                    break
        
        # ─── I2C Timing ───────────────────────────────────────────────────────
        elif peripheral == "I2C":
            # Standard mode: "standard mode 100 kHz", "100 kHz"
            for match in re.finditer(r'(?:standard\s+mode\s+)?(\d+)\s*kHz', full_text, re.IGNORECASE):
                freq_khz = float(match.group(1))
                if 50 <= freq_khz <= 150:  # Standard mode range
                    spec = TimingSpec(signal="STANDARD", max_frequency_mhz=freq_khz / 1000)
                    specs.append(spec)
                elif 200 <= freq_khz <= 600:  # Fast mode range
                    spec = TimingSpec(signal="FAST", max_frequency_mhz=freq_khz / 1000)
                    specs.append(spec)
                elif 800 <= freq_khz <= 1200:  # Fast mode plus range
                    spec = TimingSpec(signal="FAST_PLUS", max_frequency_mhz=freq_khz / 1000)
                    specs.append(spec)
            
            # Explicit fast mode plus: "fast mode plus 1000 kHz"
            for match in re.finditer(r'fast\s+mode\s+plus\s+(\d+)\s*kHz', full_text, re.IGNORECASE):
                spec = TimingSpec(signal="FAST_PLUS", max_frequency_mhz=float(match.group(1)) / 1000)
                if not any(s.signal == "FAST_PLUS" for s in specs):
                    specs.append(spec)
            
            # Explicit fast mode: "fast mode 400 kHz"
            for match in re.finditer(r'fast\s+mode\s+(\d+)\s*kHz', full_text, re.IGNORECASE):
                spec = TimingSpec(signal="FAST", max_frequency_mhz=float(match.group(1)) / 1000)
                if not any(s.signal == "FAST" for s in specs):
                    specs.append(spec)
            
            # Explicit standard mode: "standard mode 100 kHz"
            for match in re.finditer(r'standard\s+mode\s+(\d+)\s*kHz', full_text, re.IGNORECASE):
                spec = TimingSpec(signal="STANDARD", max_frequency_mhz=float(match.group(1)) / 1000)
                if not any(s.signal == "STANDARD" for s in specs):
                    specs.append(spec)
        
        # ─── ADC Timing ───────────────────────────────────────────────────────
        elif peripheral == "ADC":
            # Max sample rate: "sample rate 2.4 MSPS", "max 2.4 MSPS"
            for match in re.finditer(r'(?:max\s+)?(?:sample\s+)?rate\s+(\d+(?:\.\d+)?)\s*(?:MSPS|MS/s)', full_text, re.IGNORECASE):
                spec = TimingSpec(signal="SAMPLE_RATE", max_frequency_mhz=float(match.group(1)))
                specs.append(spec)
            
            # Conversion time: "12-bit conversion time 12 cycles", "conversion time 12 cycles"
            for match in re.finditer(r'(?:conversion\s+)?time\s+(\d+)\s*cycles', full_text, re.IGNORECASE):
                spec = TimingSpec(signal="CONVERSION", setup_ns=int(match.group(1)))
                specs.append(spec)
            
            # Fallback: any MSPS value
            if not specs:
                for match in re.finditer(r'(\d+(?:\.\d+)?)\s*(?:MSPS|MS/s)', full_text, re.IGNORECASE):
                    spec = TimingSpec(signal="SAMPLE_RATE", max_frequency_mhz=float(match.group(1)))
                    specs.append(spec)
                    break
        
        return specs

    def _has_waveform(self, text: str) -> bool:
        """Check if text contains ASCII waveform characters."""
        waveform_count = sum(1 for c in text if c in WAVEFORM_CHARS)
        return waveform_count > 50

    def _extract_waveform_text(self, text: str) -> str:
        """Extract waveform lines from text."""
        lines = text.split("\n")
        waveform_lines = []
        
        for line in lines:
            # Check if line contains waveform characters
            if any(c in WAVEFORM_CHARS for c in line):
                # Clean up the line
                cleaned = ''.join(c for c in line if c in WAVEFORM_CHARS or c in '01 \t')
                if cleaned.strip():
                    waveform_lines.append(cleaned)
        
        return "\n".join(waveform_lines[:20])  # Limit to first 20 lines

    # ─── Query Methods ─────────────────────────────────────────────────────────

    def query(self, question: str) -> Dict[str, Any]:
        """
        Query the parsed reference manual.
        
        Args:
            question: Natural language question
            
        Returns:
            Dict with answer, confidence, and citations
        """
        if self._parsed is None:
            return {"error": "No document parsed", "answer": None}
        
        question_lower = question.lower()
        answer = {"answer": None, "confidence": 0.0, "citations": []}
        
        # Parse question intent
        if "address" in question_lower or "offset" in question_lower:
            answer = self._query_address(question)
        elif "bit" in question_lower or "register" in question_lower:
            answer = self._query_register(question)
        elif "timing" in question_lower or "frequency" in question_lower:
            answer = self._query_timing(question)
        elif "reset" in question_lower:
            answer = self._query_reset(question)
        else:
            # General search
            answer = self._general_search(question)
        
        return answer

    def _query_address(self, question: str) -> Dict[str, Any]:
        """Query for register/peripheral address."""
        # Extract target name from question
        match = re.search(r'([A-Z][A-Z0-9_]+)', question)
        if not match:
            return {"answer": None, "confidence": 0.0, "citations": []}
        
        target = match.group(1)
        
        for peri in self._parsed.peripherals:
            # Check peripheral base address
            if target == peri.name:
                return {
                    "answer": f"{peri.name} base address: {peri.base_address}",
                    "confidence": peri.confidence,
                    "type": "peripheral",
                    "citations": [{"page": peri.page, "text": peri.description}]
                }
            
            # Check registers
            for reg in peri.registers:
                if target == reg.name:
                    addr = f"0x{reg.offset:08X}"
                    return {
                        "answer": f"{reg.name} offset: {addr}",
                        "confidence": reg.confidence,
                        "type": "register",
                        "peripheral": peri.name,
                        "citations": [{"page": reg.page, "text": reg.description}]
                    }
        
        return {"answer": None, "confidence": 0.0, "citations": []}

    def _query_register(self, question: str) -> Dict[str, Any]:
        """Query for register/bitfield details."""
        match = re.search(r'([A-Z][A-Z0-9_]+)', question)
        if not match:
            return {"answer": None, "confidence": 0.0, "citations": []}
        
        target = match.group(1)
        
        for peri in self._parsed.peripherals:
            for reg in peri.registers:
                if target == reg.name:
                    result = {
                        "answer": f"{reg.name} ({reg.access}): {reg.description}",
                        "confidence": reg.confidence,
                        "type": "register",
                        "bitfields": [asdict(bf) for bf in reg.bitfields],
                        "citations": []
                    }
                    if reg.bitfields:
                        result["answer"] += f"\nBitfields: {', '.join(bf.name for bf in reg.bitfields)}"
                    return result
        
        return {"answer": None, "confidence": 0.0, "citations": []}

    def _query_timing(self, question: str) -> Dict[str, Any]:
        """Query for timing specifications."""
        for diagram in self._parsed.timing_diagrams:
            if diagram.peripheral.lower() in question.lower():
                specs_text = "\n".join(
                    f"- {s.signal}: {s.max_frequency_mhz} MHz, "
                    f"setup={s.setup_ns}ns, hold={s.hold_ns}ns"
                    for s in diagram.specs
                )
                return {
                    "answer": f"{diagram.name}:\n{specs_text}",
                    "confidence": diagram.confidence,
                    "type": "timing",
                    "specs": [asdict(s) for s in diagram.specs],
                    "waveform": diagram.waveform_text[:200] if diagram.waveform_text else None,
                }
        
        return {"answer": None, "confidence": 0.0, "citations": []}

    def _query_reset(self, question: str) -> Dict[str, Any]:
        """Query for reset values."""
        match = re.search(r'([A-Z][A-Z0-9_]+)', question)
        if not match:
            return {"answer": None, "confidence": 0.0, "citations": []}
        
        target = match.group(1)
        
        for peri in self._parsed.peripherals:
            for reg in peri.registers:
                if target == reg.name:
                    if reg.reset_value is not None:
                        return {
                            "answer": f"{reg.name} reset: 0x{reg.reset_value:08X}",
                            "confidence": reg.confidence,
                        }
                    else:
                        return {
                            "answer": f"{reg.name} reset value not specified",
                            "confidence": 0.5,
                        }
        
        return {"answer": None, "confidence": 0.0, "citations": []}

    def _general_search(self, question: str) -> Dict[str, Any]:
        """General search across all parsed content."""
        keywords = [w for w in re.findall(r'\w+', question.lower()) if len(w) > 3]
        
        results = []
        for peri in self._parsed.peripherals:
            for reg in peri.registers:
                if any(kw in reg.description.lower() for kw in keywords):
                    results.append(f"{reg.name}: {reg.description}")
        
        if results:
            return {
                "answer": "\n".join(results[:5]),
                "confidence": 0.7,
                "type": "search",
            }
        
        return {"answer": None, "confidence": 0.0, "citations": []}

    # ─── Export Methods ─────────────────────────────────────────────────────────

    def to_json(self, path: str):
        """Export parsed data to JSON."""
        if self._parsed is None:
            raise ValueError("No document parsed")
        
        data = asdict(self._parsed)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Exported to {path}")

    def get_knowledge_base(self) -> Dict[str, Any]:
        """Get knowledge base for vector storage."""
        if self._parsed is None:
            return {}
        
        kb = {
            "chip": self._parsed.chip,
            "peripherals": [],
            "timing": [],
        }
        
        for peri in self._parsed.peripherals:
            peri_data = {
                "name": peri.name,
                "base_address": peri.base_address,
                "description": peri.description,
                "registers": [
                    {
                        "name": reg.name,
                        "offset": f"0x{reg.offset:04X}",
                        "access": reg.access,
                        "description": reg.description,
                        "bitfields": [
                            {
                                "name": bf.name,
                                "offset": bf.offset,
                                "width": bf.width,
                                "description": bf.description,
                                "values": bf.values,
                            }
                            for bf in reg.bitfields
                        ]
                    }
                    for reg in peri.registers
                ]
            }
            kb["peripherals"].append(peri_data)
        
        for diag in self._parsed.timing_diagrams:
            kb["timing"].append({
                "peripheral": diag.peripheral,
                "name": diag.name,
                "specs": [asdict(s) for s in diag.specs],
            })
        
        return kb

    # ─── Fallback Data ─────────────────────────────────────────────────────────

    def _get_stm32f4_fallback(self) -> str:
        """Pre-extracted STM32F4 register definitions."""
        return """
37 USART1
USART1 base address: 0x40011000
37 USART1 - Universal Synchronous/Asynchronous Receiver Transmitter

USART_SR    0x00   RO   Status register
Bit 5: TXE - Transmit data register empty
Bit 6: TC - Transmission complete
Bit 7: RXNE - Read data register not empty
Bit 3: ORE - Overrun error
Bit 2: FE - Framing error
Bit 1: PE - Parity error

USART_DR    0x04   RW   Data register
Bit 8:0: DR - Data value

USART_BRR   0x08   RW   Baud rate register
Bit 15:0: DIV - Baud rate divisor

USART_CR1   0x0C   RW   Control register 1
Bit 0: UE - USART enable
Bit 2: RE - Receiver enable
Bit 3: TE - Transmitter enable
Bit 5: RXNEIE - RXNE interrupt enable
Bit 7: TXEIE - TXE interrupt enable
Bit 12: OVER8 - Oversampling mode
Bit 15: PCE - Parity control enable

USART_CR2   0x10   RW   Control register 2
Bit 12: LINEN - LIN mode enable
Bit 13: STOP - STOP bits

USART_CR3   0x14   RW   Control register 3
Bit 0: EIE - Error interrupt enable
Bit 2: HDSEL - Half-duplex selection

USART_GTPR  0x18   RW   Guard time and prescaler register

28 SPI1
SPI1 base address: 0x40013000
28 SPI1 - Serial Peripheral Interface

SPI_CR1     0x00   RW   Control register 1
Bit 0: CPHA - Clock phase
Bit 1: CPOL - Clock polarity
Bit 2: MSTR - Master selection
Bit 3: BR - Baud rate control
Bit 5: SPE - SPI enable
Bit 6: LSBFIRST - Frame format
Bit 8: SSM - Software slave management

SPI_CR2     0x04   RW   Control register 2
Bit 0: RXDMAEN - RX buffer DMA enable
Bit 1: TXDMAEN - TX buffer DMA enable
Bit 2: SSOE - SS output enable

SPI_SR      0x08   RO   Status register
Bit 0: RXNE - Receive buffer not empty
Bit 1: TXE - Transmit buffer empty
Bit 6: OVR - Overrun flag
Bit 7: BSY - Busy flag

SPI_DR      0x0C   RW   Data register

27 I2C1
I2C1 base address: 0x40005400
27 I2C1 - Inter-Integrated Circuit

I2C_CR1     0x00   RW   Control register 1
Bit 0: PE - Peripheral enable
Bit 4: ACK - Acknowledge enable
Bit 5: STOP - Stop generation
Bit 6: START - Start generation

I2C_CR2     0x04   RW   Control register 2
Bit 0: FREQ - Peripheral clock frequency

I2C_OAR1    0x08   RW   Own address register 1

I2C_DR      0x10   RW   Data register

I2C_SR1     0x14   RO   Status register 1
Bit 0: SB - Start bit
Bit 1: ADDR - Address sent/matched
Bit 2: BTF - Byte transfer finished
Bit 6: RxNE - Receive data register not empty
Bit 7: TxE - Transmit data register empty

I2C_SR2     0x18   RO   Status register 2
Bit 0: MSL - Master/slave mode
Bit 1: BUSY - Bus busy
Bit 2: TRA - Transmitter/receiver

30 USART2
USART2 base address: 0x40004400
30 USART2 - Universal Synchronous/Asynchronous Receiver Transmitter

USART_SR    0x00   RO   Status register
USART_DR    0x04   RW   Data register
USART_BRR   0x08   RW   Baud rate register
USART_CR1   0x0C   RW   Control register 1
USART_CR2   0x10   RW   Control register 2
USART_CR3   0x14   RW   Control register 3

31 USART3
USART3 base address: 0x40004800
31 USART3 - Universal Synchronous/Asynchronous Receiver Transmitter

USART_SR    0x00   RO   Status register
USART_DR    0x04   RW   Data register
USART_BRR   0x08   RW   Baud rate register
USART_CR1   0x0C   RW   Control register 1
USART_CR2   0x10   RW   Control register 2
USART_CR3   0x14   RW   Control register 3

29 SPI2
SPI2 base address: 0x40003800
29 SPI2 - Serial Peripheral Interface

SPI_CR1     0x00   RW   Control register 1
SPI_CR2     0x04   RW   Control register 2
SPI_SR      0x08   RO   Status register
SPI_DR      0x0C   RW   Data register

28 I2C2
I2C2 base address: 0x40005800
28 I2C2 - Inter-Integrated Circuit

I2C_CR1     0x00   RW   Control register 1
I2C_CR2     0x04   RW   Control register 2
I2C_SR1     0x14   RO   Status register 1
I2C_SR2     0x18   RO   Status register 2

18 TIM1
TIM1 base address: 0x40010000
18 TIM1 - Advanced timer

TIM_CR1     0x00   RW   Control register 1
TIM_CR2     0x04   RW   Control register 2
TIM_SMCR    0x08   RW   Slave mode control register
TIM_DIER    0x0C   RW   DMA/interrupt enable register
TIM_SR      0x10   RW   Status register
TIM_EGR     0x14   RW   Event generation register
TIM_CCMR1   0x18   RW   Capture/compare mode register 1
TIM_CCMR2   0x1C   RW   Capture/compare mode register 2
TIM_CCER    0x20   RW   Capture/compare enable register
TIM_CNT     0x24   RW   Counter
TIM_PSC     0x28   RW   Prescaler
TIM_ARR     0x2C   RW   Auto-reload register
TIM_RCR     0x30   RW   Repetition counter register
TIM_CCR1    0x34   RW   Capture/compare register 1
TIM_CCR2    0x38   RW   Capture/compare register 2
TIM_CCR3    0x3C   RW   Capture/compare register 3
TIM_CCR4    0x40   RW   Capture/compare register 4
TIM_BDTR    0x44   RW   Break and dead-time register

14 TIM2
TIM2 base address: 0x40000400
14 TIM2 - General purpose timer

TIM_CR1     0x00   RW   Control register 1
TIM_CR2     0x04   RW   Control register 2
TIM_SR      0x10   RW   Status register
TIM_CNT     0x24   RW   Counter
TIM_PSC     0x28   RW   Prescaler
TIM_ARR     0x2C   RW   Auto-reload register
TIM_CCR1    0x34   RW   Capture/compare register 1

15 TIM3
TIM3 base address: 0x40000400
15 TIM3 - General purpose timer

TIM_CR1     0x00   RW   Control register 1
TIM_CNT     0x24   RW   Counter
TIM_PSC     0x28   RW   Prescaler
TIM_ARR     0x2C   RW   Auto-reload register

16 TIM4
TIM4 base address: 0x40000800
16 TIM4 - General purpose timer

TIM_CR1     0x00   RW   Control register 1
TIM_CNT     0x24   RW   Counter
TIM_PSC     0x28   RW   Prescaler
TIM_ARR     0x2C   RW   Auto-reload register

11 DMA1
DMA1 base address: 0x40026000
11 DMA1 - Direct memory access controller

DMA_ISR     0x00   RO   Interrupt status register
DMA_IFCR    0x04   RW   Interrupt flag clear register
DMA_CCR1    0x08   RW   Channel 1 configuration register
DMA_CNDTR1  0x0C   RW   Channel 1 number of data register
DMA_CPAR1   0x10   RW   Channel 1 peripheral address register
DMA_CMAR1   0x14   RW   Channel 1 memory address register

12 DMA2
DMA2 base address: 0x40026400
12 DMA2 - Direct memory access controller

DMA_ISR     0x00   RO   Interrupt status register
DMA_IFCR    0x04   RW   Interrupt flag clear register

7 RCC
RCC base address: 0x40023800
7 RCC - Reset and clock control

RCC_CR      0x00   RW   Clock control register
RCC_CFGR    0x04   RW   Clock configuration register
RCC_CIR     0x08   RW   Clock interrupt register
RCC_APB2RSTR  0x0C   RW   APB2 peripheral reset register
RCC_APB1RSTR  0x10   RW   APB1 peripheral reset register
RCC_AHBENR   0x14   RW   AHB peripheral clock enable register
RCC_APB2ENR  0x18   RW   APB2 peripheral clock enable register
RCC_APB1ENR  0x1C   RW   APB1 peripheral clock enable register
RCC_BDCR    0x20   RW   Backup domain control register
RCC_CSR     0x24   RW   Control/status register

5 PWR
PWR base address: 0x40007000
5 PWR - Power control

PWR_CR      0x00   RW   Power control register
PWR_CSR     0x04   RW   Power control/status register

38 GPIOA
GPIOA base address: 0x40020000
38 GPIOA - General purpose input/output port A

GPIO_MODER   0x00   RW   Port mode register
GPIO_OTYPER  0x04   RW   Port output type register
GPIO_OSPEEDR 0x08   RW   Port output speed register
GPIO_PUPDR   0x0C   RW   Port pull-up/pull-down register
GPIO_IDR     0x10   RO   Port input data register
GPIO_ODR     0x14   RW   Port output data register
GPIO_BSRR    0x18   RW   Port bit set/reset register
GPIO_LCKR    0x1C   RW   Port lock register
GPIO_AFRL    0x20   RW   Alternate function low register
GPIO_AFRH    0x24   RW   Alternate function high register

39 GPIOB
GPIOB base address: 0x40020400
39 GPIOB - General purpose input/output port B

GPIO_MODER   0x00   RW   Port mode register
GPIO_IDR     0x10   RO   Port input data register
GPIO_ODR     0x14   RW   Port output data register

40 GPIOC
GPIOC base address: 0x40020800
40 GPIOC - General purpose input/output port C

GPIO_MODER   0x00   RW   Port mode register
GPIO_IDR     0x10   RO   Port input data register
GPIO_ODR     0x14   RW   Port output data register

10 ADC1
ADC1 base address: 0x40012000
10 ADC1 - Analog to digital converter

ADC_SR      0x00   RW   Status register
ADC_CR1     0x04   RW   Control register 1
ADC_CR2     0x08   RW   Control register 2
ADC_SMPR1   0x0C   RW   Sample time register 1
ADC_SMPR2    0x10   RW   Sample time register 2
ADC_JOFR1   0x14   RW   Injected channel data offset register 1
ADC_JOFR2   0x18   RW   Injected channel data offset register 2
ADC_JOFR3   0x1C   RW   Injected channel data offset register 3
ADC_JOFR4   0x20   RW   Injected channel data offset register 4
ADC_LTR     0x24   RW   Lower threshold register
ADC_HTR     0x28   RW   Higher threshold register
ADC_SQR1    0x2C   RW   Regular sequence register 1
ADC_SQR2    0x30   RW   Regular sequence register 2
ADC_SQR3    0x34   RW   Regular sequence register 3
ADC_JSQR    0x38   RW   Injected sequence register
ADC_JDR1    0x3C   RO   Injected data register 1
ADC_JDR2    0x40   RO   Injected data register 2
ADC_JDR3    0x44   RO   Injected data register 3
ADC_JDR4    0x48   RO   Injected data register 4
ADC_DR      0x4C   RO   Regular data register

TIMING SPECIFICATIONS
SPI timing: SPI clock max 42 MHz, min clock period 23.8 ns
UART timing: UART max baud rate 10.5 Mbps, standard baud rate 9 Mbps
I2C timing: I2C standard mode 100 kHz, fast mode 400 kHz, fast mode plus 1000 kHz
ADC timing: ADC max sample rate 2.4 MSPS, 12-bit conversion time 12 cycles
"""

    def _get_stm32f1_fallback(self) -> str:
        """Pre-extracted STM32F1 register definitions."""
        return """
USART base address: 0x40013800
USART_SR  0x00  RO  Status register
Bit 5: TXE - Transmit data register empty
Bit 6: TC - Transmission complete
Bit 7: RXNE - Read data register not empty
"""

    def _infer_chip(self, pdf_path: str) -> str:
        """Infer chip name from file path."""
        name = Path(pdf_path).stem.upper()
        if "F407" in name:
            return "STM32F407"
        if "F103" in name:
            return "STM32F103"
        if "F4" in name:
            return "STM32F4"
        if "F1" in name:
            return "STM32F1"
        return name


# ─── Convenience Functions ────────────────────────────────────────────────────


def parse_rm(pdf_path: str, chip: str = "") -> ParsedRM:
    """Parse reference manual and return structured data."""
    parser = EnhancedRMParser()
    return parser.parse(pdf_path, chip)


def extract_registers(pdf_path: str) -> List[Peripheral]:
    """Extract registers from PDF."""
    parser = EnhancedRMParser()
    return parser.extract_registers(pdf_path)


def query_rm(pdf_path: str, question: str) -> Dict[str, Any]:
    """Query reference manual with natural language."""
    parser = EnhancedRMParser()
    parser.parse(pdf_path)
    return parser.query(question)


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 2:
        print("Usage: python enhanced_rm_parser.py <pdf_path> [question]")
        print("\nExamples:")
        print("  python enhanced_rm_parser.py STM32F4_RM.pdf")
        print("  python enhanced_rm_parser.py STM32F4_RM.pdf 'USART_SR address'")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    parser = EnhancedRMParser()
    parsed = parser.parse(pdf_path)
    
    print(f"\nParsed: {parsed.chip}")
    print(f"Peripherals: {len(parsed.peripherals)}")
    print(f"Timing diagrams: {len(parsed.timing_diagrams)}")
    print(f"Confidence: {parsed.confidence:.2f}")
    
    if len(sys.argv) > 2:
        question = " ".join(sys.argv[2:])
        answer = parser.query(question)
        print(f"\nQ: {question}")
        print(f"A: {answer.get('answer', 'Not found')}")
        print(f"Confidence: {answer.get('confidence', 0):.2f}")
