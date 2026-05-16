"""SVDParser - parses CMSIS SVD files to register schema."""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional


class SVDParser:
    """
    Parse CMSIS SVD (System View Description) XML files.

    SVD files are the standard ARM/CMSIS format for describing
    peripheral register maps. This parser extracts:
    - Peripheral names and base addresses
    - Register names, offsets, access types, and descriptions
    - Bitfield names, offsets, widths, and enumerated values

    STM32 SVD files are available from:
    - ARM CMSIS Pack ( Keil::STM32F4xx_DFP )
    - https://developer.arm.com/tools-and-software/embedded/cmsis/cmsis-pack-descriptor
    """

    def parse(self, svd_path: str) -> Dict:
        """
        Parse an SVD file and return a register schema dict.

        Args:
            svd_path: Path to the .svd file

        Returns:
            Schema dict compatible with RegisterSchemaDB
        """
        path = Path(svd_path)
        if not path.exists():
            return {}

        try:
            tree = ET.parse(str(path))
            root = tree.getroot()
        except ET.ParseError:
            return {}

        schema = {
            "schema_version": "1.0",
            "chip": self._get_chip_name(root),
            "entries": [],
        }

        device = root.find("device")
        if device is None:
            return schema

        peripherals = device.find("peripherals")
        if peripherals is None:
            return schema

        for peri_elem in peripherals.findall("peripheral"):
            entry = self._parse_peripheral(peri_elem)
            if entry:
                schema["entries"].append(entry)

        return schema

    def _get_chip_name(self, root) -> str:
        device = root.find("device")
        if device is not None:
            name = device.get("name", "")
            if name:
                return name
            vendor = device.get("vendor", "")
            series = device.get("series", "")
            if vendor or series:
                return f"{vendor} {series}".strip()
        return "Unknown"

    def _parse_peripheral(self, peri_elem) -> Optional[Dict]:
        name = peri_elem.get("name", "")
        if not name:
            return None

        base_addr = peri_elem.get("baseAddress", "0")
        try:
            base_addr_int = int(base_addr, 0)
        except ValueError:
            base_addr_int = 0

        description_elem = peri_elem.find("description")
        description = description_elem.text.strip() if description_elem is not None and description_elem.text else name

        registers = []
        register_cluster = peri_elem.find("registers")
        if register_cluster is not None:
            for reg_elem in register_cluster.findall("register"):
                reg = self._parse_register(reg_elem)
                if reg:
                    registers.append(reg)
            for cluster_elem in register_cluster.findall("cluster"):
                for reg_elem in cluster_elem.findall("register"):
                    reg = self._parse_register(reg_elem)
                    if reg:
                        registers.append(reg)

        return {
            "peripheral": name,
            "base_address": f"0x{base_addr_int:08X}",
            "description": description,
            "registers": registers,
        }

    def _parse_register(self, reg_elem) -> Optional[Dict]:
        name = reg_elem.get("name", "")
        if not name:
            return None

        dim_elem = reg_elem.find("dim")
        dim = int(dim_elem.text) if dim_elem is not None and dim_elem.text else 1

        access_elem = reg_elem.find("access")
        access = access_elem.text if access_elem is not None and access_elem.text else "RW"

        desc_elem = reg_elem.find("description")
        description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else name

        address_offset_elem = reg_elem.find("addressOffset")
        offset = 0
        if address_offset_elem is not None and address_offset_elem.text:
            try:
                offset = int(address_offset_elem.text, 0)
            except ValueError:
                offset = 0

        reset_value_elem = reg_elem.find("resetValue")
        reset_value = None
        if reset_value_elem is not None and reset_value_elem.text:
            try:
                reset_value = int(reset_value_elem.text, 0)
            except ValueError:
                reset_value = None

        fields = []
        fields_elem = reg_elem.find("fields")
        if fields_elem is not None:
            for field_elem in fields_elem.findall("field"):
                field = self._parse_field(field_elem)
                if field:
                    fields.append(field)

        return {
            "register": name,
            "offset": offset,
            "access": access,
            "description": description,
            "bitfields": fields,
            "reset_value": reset_value,
        }

    def _parse_field(self, field_elem) -> Optional[Dict]:
        name = field_elem.get("name", "")
        if not name:
            return None

        bit_offset_elem = field_elem.find("bitOffset")
        bit_width_elem = field_elem.find("bitWidth")

        offset = 0
        width = 1
        if bit_offset_elem is not None and bit_offset_elem.text:
            try:
                offset = int(bit_offset_elem.text, 0)
            except ValueError:
                offset = 0
        if bit_width_elem is not None and bit_width_elem.text:
            try:
                width = int(bit_width_elem.text, 0)
            except ValueError:
                width = 1

        access_elem = field_elem.find("access")
        access = access_elem.text if access_elem is not None and access_elem.text else "RW"

        desc_elem = field_elem.find("description")
        description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else name

        values = {}
        enumerated_values_elem = field_elem.find("enumeratedValues")
        if enumerated_values_elem is not None:
            for enum_val in enumerated_values_elem.findall("enumeratedValue"):
                v_name = enum_val.get("name", "")
                v_value = enum_val.get("value", "")
                if v_name and v_value:
                    try:
                        values[v_name] = int(v_value, 0)
                    except ValueError:
                        values[v_name] = v_value

        return {
            "name": name,
            "offset": offset,
            "width": width,
            "access": access,
            "description": description,
            "values": values,
        }
