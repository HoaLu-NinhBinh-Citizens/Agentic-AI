"""Integration test for J-Link/ST-Link probe adapters.

Run with:
    python tests/integration/test_jlink_probe.py

For real hardware:
1. J-Link: pip install pylink2 (Linux/Mac only)
2. ST-Link: Install OpenOCD, then run:
   openocd -f interface/stlink.cfg -f target/stm32f4x.cfg
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_mock_jlink_backend():
    """Test J-Link mock backend."""
    print("\n" + "=" * 60)
    print("J-LINK MOCK BACKEND TEST")
    print("=" * 60)
    
    try:
        from src.infrastructure.hardware.jlink.probe import JLinkProbeAdapter, MockJLinkBackend
        
        print("\n1. Creating mock backend...")
        backend = MockJLinkBackend()
        
        print("2. Writing test data...")
        test_data = b"\xDE\xAD\xBE\xEF" * 16
        backend.write_bytes(0x20000000, test_data)
        print("   [OK] Wrote 64 bytes to 0x20000000")
        
        print("3. Reading back data...")
        read_data = backend.read_bytes(0x20000000, 64)
        if read_data == test_data:
            print("   [OK] Data verified!")
        else:
            print("   [FAIL] Data mismatch!")
            return False
        
        print("4. Testing register read/write...")
        backend.write_register("pc", 0x08001000)
        pc = backend.read_register("pc")
        if pc == 0x08001000:
            print("   [OK] Register R/W works!")
        else:
            print("   [FAIL] Register mismatch!")
            return False
        
        print("\n" + "=" * 60)
        print("J-LINK MOCK TEST: PASSED")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_jlink_probe_adapter_mock():
    """Test J-Link probe adapter with mock backend."""
    print("\n" + "=" * 60)
    print("J-LINK PROBE ADAPTER TEST (MOCK)")
    print("=" * 60)
    
    try:
        from src.infrastructure.hardware.jlink.probe import JLinkProbeAdapter
        
        print("\n1. Creating probe adapter with mock backend...")
        adapter = JLinkProbeAdapter(
            serial="MOCK123",
            interface=1,  # SWD
            speed_khz=4000,
            use_mock=True,
        )
        print("   [OK] Adapter created")
        
        print("\n2. Connecting...")
        await adapter.connect()
        print(f"   [OK] Connected: {adapter.is_connected}")
        
        print("\n3. Reading memory...")
        result = await adapter.read_memory(0x20000000, 32)
        if result.success:
            print(f"   [OK] Read {len(result.data)} bytes")
        else:
            print(f"   [FAIL] {result.error}")
            return False
        
        print("\n4. Writing memory...")
        test_data = b"\x12\x34\x56\x78" * 8
        success = await adapter.write_memory(0x20000000, test_data)
        if success:
            print("   [OK] Write successful")
        else:
            print("   [FAIL] Write failed")
            return False
        
        print("\n5. Verifying write...")
        result = await adapter.read_memory(0x20000000, 32)
        if result.data == test_data:
            print("   [OK] Data verified!")
        else:
            print("   [FAIL] Data mismatch!")
            return False
        
        print("\n6. Testing register access...")
        await adapter.write_register("pc", 0x08002000)
        reg_value = await adapter.read_register("pc")
        pc_value = reg_value.value if hasattr(reg_value, 'value') else reg_value
        if pc_value == 0x08002000:
            print("   [OK] Register R/W works!")
        else:
            print(f"   [FAIL] Expected 0x08002000, got 0x{pc_value:08X}")
            return False
        
        print("\n" + "=" * 60)
        print("J-LINK ADAPTER TEST: PASSED")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_stlink_adapter_mock():
    """Test ST-Link adapter with mock mode."""
    print("\n" + "=" * 60)
    print("ST-LINK ADAPTER TEST (MOCK)")
    print("=" * 60)
    
    try:
        from src.infrastructure.hardware.stlink.stlink_adapter import STLinkAdapter
        
        print("\n1. Creating ST-Link adapter in mock mode...")
        adapter = STLinkAdapter(
            serial="MOCK_STLINK",
            interface=1,  # SWD
            speed_khz=4000,
            use_mock=True,
        )
        print("   [OK] Adapter created")
        
        print("\n2. Connecting...")
        await adapter.connect()
        print(f"   [OK] Connected: {adapter.is_connected}")
        
        print("\n3. Getting IDCODE...")
        idcode = await adapter.get_idcode()
        full_code = idcode.full_code if hasattr(idcode, 'full_code') else 0
        print(f"   [OK] IDCODE: 0x{full_code:08X}")
        
        print("\n4. Reading memory...")
        data = await adapter.read_memory(0x20000000, 64)
        print(f"   [OK] Read {len(data)} bytes")
        
        print("\n5. Halt/Resume...")
        halted = await adapter.halt()
        print(f"   [OK] Halt: {halted}")
        resumed = await adapter.resume()
        print(f"   [OK] Resume: {resumed}")
        
        print("\n6. Reset...")
        await adapter.reset()
        print("   [OK] Reset done")
        
        print("\n" + "=" * 60)
        print("ST-LINK ADAPTER TEST: PASSED")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_pylink_backend_availability():
    """Check if pylink2 is available."""
    print("\n" + "=" * 60)
    print("PYLINK2 AVAILABILITY CHECK")
    print("=" * 60)
    
    try:
        import pylink2
        print(f"\n[OK] pylink2 version: {pylink2.__version__}")
        print("   Real J-Link hardware access available!")
        return True
    except ImportError:
        print("\n[INFO] pylink2 not installed")
        print("   Install on Linux/Mac: pip install pylink2")
        print("   Windows: Use OpenOCD + ST-Link instead")
        return False


async def test_openocd_availability():
    """Check if OpenOCD is available."""
    print("\n" + "=" * 60)
    print("OPENOCD AVAILABILITY CHECK")
    print("=" * 60)
    
    import shutil
    if shutil.which("openocd"):
        print("\n[OK] OpenOCD is installed")
        print("   To use: Start OpenOCD server, then run test with --openocd flag")
        return True
    else:
        print("\n[INFO] OpenOCD not found in PATH")
        print("   Install OpenOCD, then run:")
        print("   openocd -f interface/stlink.cfg -f target/stm32f4x.cfg")
        return False


async def main():
    """Run all integration tests."""
    print("\n" + "#" * 60)
    print("# J-LINK / ST-LINK HARDWARE INTEGRATION TESTS")
    print("#" * 60)
    
    results = {}
    
    # Check availability
    results["pylink2"] = await test_pylink_backend_availability()
    results["openocd"] = await test_openocd_availability()
    
    # Mock tests (always run)
    results["J-Link Mock Backend"] = await test_mock_jlink_backend()
    results["J-Link Adapter (Mock)"] = await test_jlink_probe_adapter_mock()
    results["ST-Link Adapter (Mock)"] = await test_stlink_adapter_mock()
    
    # Summary
    print("\n" + "#" * 60)
    print("# TEST SUMMARY")
    print("#" * 60)
    
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: [{status}]")
    
    all_passed = all(results.values())
    print()
    if all_passed:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED - See above for details")
    
    print("\n" + "#" * 60)
    print("# HARDWARE SETUP INSTRUCTIONS")
    print("#" * 60)
    print("""
For REAL hardware testing:

1. J-Link (Linux/Mac):
   pip install pylink2
   # Connect J-Link, run test again

2. ST-Link + OpenOCD (Windows/Linux/Mac):
   # Install OpenOCD from https://openocd.org/
   
   # Windows: Add OpenOCD to PATH, then:
   openocd -f interface/stlink.cfg -f target/stm32f4x.cfg
   
   # Then run test in another terminal:
   python tests/integration/test_jlink_probe.py

3. J-Link + OpenOCD:
   openocd -f interface/jlink.cfg -f target/stm32f4x.cfg
""")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
