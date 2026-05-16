"""Register Schema Database - queryable register definition store."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RegisterEntry:
    peripheral: str
    register: str
    offset: int
    access: str
    description: str
    bitfields: List[Dict]
    reset_value: Optional[int] = None
    address: Optional[int] = None


class RegisterSchemaDB:
    """
    Queryable database of peripheral/register/bitfield definitions.

    Loaded from parsed RM PDFs or SVD files.
    Provides fast lookup by peripheral, register name, or address.
    """

    def __init__(self):
        self._entries: List[RegisterEntry] = []
        self._by_peripheral: Dict[str, List[RegisterEntry]] = {}
        self._by_name: Dict[str, RegisterEntry] = {}
        self._by_address: Dict[int, RegisterEntry] = {}
        self._schema_version: str = ""
        self._chip: str = ""

    def load(self, schema: dict):
        """Load schema from dict (produced by RMParser or SVDParser)."""
        self._entries.clear()
        self._by_peripheral.clear()
        self._by_name.clear()
        self._by_address.clear()

        self._schema_version = schema.get("schema_version", "")
        self._chip = schema.get("chip", "")

        for entry in schema.get("entries", []):
            peripheral = entry.get("peripheral", "")
            base_address = entry.get("base_address", 0)
            if isinstance(base_address, str):
                base_address = int(base_address, 16) if base_address.startswith("0x") else int(base_address)

            for reg_entry in entry.get("registers", []):
                reg_name = reg_entry.get("register", "")
                reg_offset = reg_entry.get("offset", 0)
                if isinstance(reg_offset, str):
                    reg_offset = int(reg_offset, 16) if reg_offset.startswith("0x") else int(reg_offset)

                absolute_address = base_address + reg_offset

                bitfields = []
                for bf in reg_entry.get("bitfields", []):
                    bitfields.append({
                        "name": bf.get("name", ""),
                        "offset": bf.get("offset"),
                        "width": bf.get("width"),
                        "access": bf.get("access", "RW"),
                        "description": bf.get("description", ""),
                        "values": bf.get("values", {}),
                    })

                register_entry = RegisterEntry(
                    peripheral=peripheral,
                    register=reg_name,
                    offset=reg_offset,
                    access=reg_entry.get("access", "RW"),
                    description=reg_entry.get("description", ""),
                    bitfields=bitfields,
                    reset_value=reg_entry.get("reset_value"),
                    address=absolute_address,
                )

                self._entries.append(register_entry)

                key = f"{peripheral}.{reg_name}"
                self._by_name[key] = register_entry
                self._by_address[absolute_address] = register_entry

                if peripheral not in self._by_peripheral:
                    self._by_peripheral[peripheral] = []
                self._by_peripheral[peripheral].append(register_entry)

    def get_peripheral_schema(self, peripheral: str) -> dict:
        """Get all registers for a peripheral."""
        entries = self._by_peripheral.get(peripheral, [])
        return {
            "peripheral": peripheral,
            "chip": self._chip,
            "registers": [
                {
                    "register": e.register,
                    "offset": f"0x{e.offset:04X}",
                    "absolute_address": f"0x{e.address:08X}" if e.address else None,
                    "access": e.access,
                    "description": e.description,
                    "bitfields": e.bitfields,
                    "reset_value": e.reset_value,
                }
                for e in entries
            ],
        }

    def get_register(self, peripheral: str, register: str) -> Optional[RegisterEntry]:
        """Get a specific register."""
        key = f"{peripheral}.{register}"
        return self._by_name.get(key)

    def get_by_address(self, address: int) -> Optional[RegisterEntry]:
        """Get register by absolute address."""
        return self._by_address.get(address)

    def find_registers(self, query: str) -> List[RegisterEntry]:
        """Find registers matching a query string."""
        query_lower = query.lower()
        results = []
        for entry in self._entries:
            haystack = f"{entry.peripheral} {entry.register} {entry.description}".lower()
            if query_lower in haystack:
                results.append(entry)
        return results

    def get_bitfield(
        self, peripheral: str, register: str, bitfield_name: str
    ) -> Optional[dict]:
        """Get a specific bitfield."""
        entry = self.get_register(peripheral, register)
        if not entry:
            return None
        for bf in entry.bitfields:
            if bf.get("name", "").lower() == bitfield_name.lower():
                return bf
        return None

    def list_peripherals(self) -> List[str]:
        """List all available peripherals."""
        return sorted(self._by_peripheral.keys())

    def list_registers(self, peripheral: str) -> List[str]:
        """List all registers for a peripheral."""
        return [e.register for e in self._by_peripheral.get(peripheral, [])]

    def search_bits(
        self, peripheral: str, register: str, bit_name: str
    ) -> List[dict]:
        """Search for bitfield patterns like 'EN', 'IE', 'IF'."""
        results = []
        entry = self.get_register(peripheral, register)
        if not entry:
            return results
        for bf in entry.bitfields:
            if bit_name.lower() in bf.get("name", "").lower():
                results.append(bf)
        return results

    def get_known_values(
        self, peripheral: str, register: str, bitfield_name: str
    ) -> Dict[str, int]:
        """Get known enumerated values for a bitfield."""
        bf = self.get_bitfield(peripheral, register, bitfield_name)
        if not bf:
            return {}
        return bf.get("values", {})

    def get_access(self, peripheral: str, register: str) -> str:
        """Get access type for a register."""
        entry = self.get_register(peripheral, register)
        return entry.access if entry else "RW"

    def validate_register_access(
        self, peripheral: str, register: str, operation: str
    ) -> bool:
        """Check if an operation (read/write) is allowed."""
        access = self.get_access(peripheral, register)
        if access == "RO":
            return operation == "read"
        if access == "WO":
            return operation == "write"
        return True

    def get_address(self, peripheral: str, register: str) -> Optional[int]:
        """Get absolute address of a register."""
        entry = self.get_register(peripheral, register)
        return entry.address if entry else None

    def to_dict(self) -> dict:
        """Export schema as dict."""
        return {
            "schema_version": self._schema_version,
            "chip": self._chip,
            "entries": [
                {
                    "peripheral": entry.peripheral,
                    "register": entry.register,
                    "offset": f"0x{entry.offset:04X}",
                    "address": f"0x{entry.address:08X}" if entry.address else None,
                    "access": entry.access,
                    "description": entry.description,
                    "bitfields": entry.bitfields,
                    "reset_value": entry.reset_value,
                }
                for entry in self._entries
            ],
        }
