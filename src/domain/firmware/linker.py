"""Firmware domain module."""


class FirmwareLinker:
    """Firmware linker configuration."""
    
    def __init__(self):
        self.sections: dict[str, str] = {}
