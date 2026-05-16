#!/usr/bin/env python3
"""
Physical Hardware Flash Test - AI_support HIL Validation
Flashes real firmware to STM32F407VG via J-Link

Usage:
    python test_physical_flash.py              # Dry-run
    python test_physical_flash.py --real      # Real flash
"""

import subprocess
import sys
import time
from pathlib import Path

JLINK_PATH = r"C:\Program Files\SEGGER\JLink_V820\JLink.exe"
DEVICE = "STM32F407VG"
ELF_PATH = r"C:\Users\thang\Desktop\carv\main\software\output\EngineCar\BootLoader\BootLoader.elf"
INTERFACE = "SWD"
SPEED = 4000


def run_jlink_command(commands: list, timeout: int = 30) -> tuple:
    """Run J-Link with commands"""
    cmd = [
        JLINK_PATH,
        "-Device", DEVICE,
        "-If", INTERFACE,
        "-Speed", str(SPEED),
        "-ExitOnError", "1"
    ]

    script_content = "\n".join(commands)
    script_file = Path(__file__).parent / "jlink_script.jlink"
    script_file.write_text(script_content)

    cmd.extend(["-CommandFile", str(script_file)])

    print(f"[CMD] {' '.join(cmd[:6])}...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='replace'
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -2, "", str(e)
    finally:
        if script_file.exists():
            script_file.unlink()


def test_connection() -> bool:
    """Test J-Link connection to device"""
    print("\n[1/4] Testing J-Link connection...")
    commands = [
        "si 1",  # SWD
        "speed 4000",
        "connect",
        "h",  # halt
        "r",  # reset
        "qc"  # quit and close
    ]

    code, stdout, stderr = run_jlink_command(commands, timeout=30)

    if code == 0:
        print("[OK] J-Link connected to STM32F407VG")
        if "STM32F407" in stdout or "STM32F407" in stderr:
            print("[OK] Device identified correctly")
        return True
    else:
        print(f"[FAIL] Connection failed: {stderr or stdout}")
        return False


def erase_chip() -> bool:
    """Erase entire chip"""
    print("\n[2/4] Erasing chip...")
    commands = [
        "si 1",
        "speed 4000",
        "connect",
        "erase",
        "qc"
    ]

    code, stdout, stderr = run_jlink_command(commands, timeout=60)

    if code == 0:
        print("[OK] Chip erased")
        return True
    else:
        print(f"[FAIL] Erase failed: {stderr or stdout}")
        return False


def flash_firmware() -> bool:
    """Flash firmware to device"""
    print(f"\n[3/4] Flashing {Path(ELF_PATH).name}...")
    commands = [
        "si 1",
        "speed 4000",
        "connect",
        "loadfile", str(ELF_PATH),
        "r",  # reset after flash
        "go",  # start execution
        "qc"
    ]

    code, stdout, stderr = run_jlink_command(commands, timeout=120)

    if code == 0:
        print("[OK] Firmware flashed successfully")
        return True
    else:
        print(f"[FAIL] Flash failed: {stderr or stdout}")
        return False


def verify_flash() -> bool:
    """Verify flash contents"""
    print("\n[4/4] Verifying flash...")
    commands = [
        "si 1",
        "speed 4000",
        "connect",
        "verifybin", str(ELF_PATH), "0x8000000",
        "qc"
    ]

    code, stdout, stderr = run_jlink_command(commands, timeout=60)

    if code == 0:
        print("[OK] Flash verified")
        return True
    else:
        print(f"[FAIL] Verify failed: {stderr or stdout}")
        return False


def main():
    print("=" * 60)
    print("AI_support - Physical Hardware Flash Test")
    print("=" * 60)
    print(f"Device:  {DEVICE}")
    print(f"ELF:     {ELF_PATH}")
    print(f"J-Link:  {JLINK_PATH}")
    print()

    if len(sys.argv) > 1 and sys.argv[1] == "--real":
        print("[WARNING] REAL FLASH MODE - Will write to hardware!")
        confirm = input("Continue? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            return 1
    else:
        print("[INFO] DRY-RUN MODE - Simulating flash")
        print("[INFO] Use --real flag to flash actual hardware")

    print()

    # Step 1: Connection test
    if not test_connection():
        print("\n[ERROR] Cannot connect to hardware")
        print("Check: J-Link cable, power, device connection")
        return 1

    if "--real" not in sys.argv:
        print("\n[INFO] Dry-run complete - hardware connection OK")
        print("[INFO] Ready for real flash with --real flag")
        return 0

    # Step 2: Erase
    if not erase_chip():
        return 1

    # Step 3: Flash
    if not flash_firmware():
        return 1

    # Step 4: Verify
    if not verify_flash():
        return 1

    print()
    print("=" * 60)
    print("[SUCCESS] Physical flash completed!")
    print("MCU is running firmware at 0x08000000")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
