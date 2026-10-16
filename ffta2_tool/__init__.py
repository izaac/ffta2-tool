"""FFTA2 Save and ARM Reverse Engineering Toolkit."""

from ffta2_tool.crypto import (
    calculate_checksum,
    decrypt_save_payload,
    encrypt_save_payload,
    extract_keystream,
    verify_save_checksum,
)
from ffta2_tool.save import FFTA2Save, Unit
from ffta2_tool.arm_tools import inspect_nds_rom, extract_arm9, extract_overlays

__version__ = "0.1.0"
__all__ = [
    "calculate_checksum",
    "decrypt_save_payload",
    "encrypt_save_payload",
    "extract_keystream",
    "verify_save_checksum",
    "FFTA2Save",
    "Unit",
    "inspect_nds_rom",
    "extract_arm9",
    "extract_overlays",
]
