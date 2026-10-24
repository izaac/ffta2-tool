"""FFTA2 Save and ARM Reverse Engineering Toolkit."""

from ffta2_tool.arm_tools import extract_arm9, extract_overlays, inspect_nds_rom, inspect_overlays
from ffta2_tool.crypto import (
    apply_keystream,
    calculate_checksum,
    decrypt_save_payload,
    encrypt_save_payload,
    extract_keystream,
    generate_keystream,
    verify_save_checksum,
)
from ffta2_tool.save import FFTA2Save, Unit

__version__ = "0.1.0"
__all__ = [
    "apply_keystream",
    "calculate_checksum",
    "decrypt_save_payload",
    "encrypt_save_payload",
    "extract_keystream",
    "generate_keystream",
    "verify_save_checksum",
    "FFTA2Save",
    "Unit",
    "inspect_nds_rom",
    "inspect_overlays",
    "extract_arm9",
    "extract_overlays",
]
