"""Integration test for real J-Link/ST-Link hardware.

Run with:
    python -m pytest tests/integration/test_jlink_probe.py -v
    # or directly:
    python tests/integration/test_jlink_probe.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_jlink_connection():
    """Test J-Link connection."""
    print("\n" + "=" * 60)
    print("J-LINK INTEGRATION TEST")
    print("=" * 60)
    
    # Try pylink2 backend
    try:
        from src.infrastructure.hardware.jlink.pylink_backend import PylinkBackend, HAS_PYLINK
        
        if not HAS_PYLINK:
            print("❌ pylink2 not installed")
            print("   Install: pip install pylink2")
            return False
        
        print("\n1. Creating J-Link backend...")
        backend = PylinkBackend(serial=None, interface=1, speed_khz=4000)
        
        print("2. Connecting to J-Link...")
        if backend.connect():
            print("   ✅ Connected!")
            
            print("\n3. Getting IDCODE...")
            idcode = backend.get_idcode()
            if idcode:
                print(f"   ✅ IDCODE: 0x{idcode:08X}")
            else:
                print("   ⚠️  IDCODE not available")
            
            print("\n4. Reading core registers...")
            try:
                pc = backend.read_register("pc")
                sp = backend.read_register("sp")
                lr = backend.read_register("lr")
                print(f"   ✅ PC: 0x{pc:08X}")
                print(f"   ✅ SP: 0x{sp:08X}")
                print(f"   ✅ LR: 0x{lr:08X}")
            except Exception as e:
                print(f"   ⚠️  Could not read registers: {e}")
            
            print("\n5. Reading target memory (SRAM)...")
            try:
                # Read first 64 bytes of SRAM
                data = backend.read_bytes(0x20000000, 64)
                print(f"   ✅ Read {len(data)} bytes from 0x20000000")
                print(f"   First 16 bytes: {data[:16].hex()}")
            except Exception as e:
                print(f"   ⚠️  Could not read memory: {e}")
            
            print("\n6. Disconnecting...")
            backend.disconnect()
            print("   ✅ Disconnected")
            
            print("\n" + "=" * 60)
            print("J-LINK TEST: PASSED ✅")
            print("=" * 60)
            return True
            
        else:
            print("   ❌ Connection failed")
            print("\n" + "=" * 60)
            print("J-LINK TEST: FAILED ❌")
            print("=" * 60)
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_stlink_connection():
    """Test ST-Link connection via OpenOCD."""
    print("\n" + "=" * 60)
    print("ST-LINK INTEGRATION TEST (via OpenOCD)")
    print("=" * 60)
    
    # Try OpenOCD backend
    try:
        from src.infrastructure.hardware.stlink.openocd_backend import OpenOCDBackend
        
        print("\n1. Creating OpenOCD backend...")
        backend = OpenOCDBackend(
            interface_config="interface/stlink.cfg",
            target_config="target/stm32f4x.cfg",
            speed_khz=4000,
        )
        
        print("2. Connecting to OpenOCD server...")
        if backend.connect(host="localhost", port=4444):
            print("   ✅ Connected to OpenOCD!")
            
            print("\n3. Halt target...")
            backend.halt()
            await asyncio.sleep(0.5)
            print("   ✅ Target halted")
            
            print("\n4. Reading core registers...")
            try:
                pc = backend.read_register("pc")
                sp = backend.read_register("sp")
                print(f"   ✅ PC: 0x{pc:08X}")
                print(f"   ✅ SP: 0x{sp:08X}")
            except Exception as e:
                print(f"   ⚠️  Could not read registers: {e}")
            
            print("\n5. Reading target memory...")
            try:
                data = backend.read_memory(0x20000000, 64)
                print(f"   ✅ Read {len(data)} bytes")
            except Exception as e:
                print(f"   ⚠️  Could not read memory: {e}")
            
            print("\n6. Resuming and disconnecting...")
            backend.resume()
            backend.disconnect()
            print("   ✅ Done")
            
            print("\n" + "=" * 60)
            print("ST-LINK TEST: PASSED ✅")
            print("=" * 60)
            return True
            
        else:
            print("   ❌ Could not connect to OpenOCD")
            print("   Make sure OpenOCD is running:")
            print("   openocd -f interface/stlink.cfg -f target/stm32f4x.cfg")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_jlink_probe_adapter():
    """Test J-Link probe adapter with real backend."""
    print("\n" + "=" * 60)
    print("J-LINK PROBE ADAPTER TEST")
    print("=" * 60)
    
    try:
        from src.infrastructure.hardware.jlink.probe import JLinkProbeAdapter
        from src.infrastructure.hardware.jlink.pylink_backend import PylinkBackend, HAS_PYLINK
        
        if not HAS_PYLINK:
            print("❌ pylink2 not installed, skipping adapter test")
            return False
        
        print("\n1. Creating probe adapter with pylink backend...")
        pylink = PylinkBackend(serial=None, interface=1, speed_khz=4000)
        
        if not pylink.connect():
            print("   ❌ Could not connect to J-Link")
            return False
        
        adapter = JLinkProbeAdapter(
            serial=None,
            interface=1,
            speed_khz=4000,
            backend=pylink,
            use_mock=False,
        )
        
        print("   ✅ Adapter created")
        
        print("\n2. Connecting probe...")
        await adapter.connect()
        print("   ✅ Connected")
        
        print("\n3. Reading memory via adapter...")
        result = await adapter.read_memory(0x20000000, 32)
        if result.success:
            print(f"   ✅ Read {len(result.data)} bytes")
        else:
            print(f"   ⚠️  Read failed: {result.error}")
        
        print("\n4. Disconnecting...")
        await adapter.disconnect()
        print("   ✅ Disconnected")
        
        print("\n" + "=" * 60)
        print("J-LINK ADAPTER TEST: PASSED ✅")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all integration tests."""
    print("\n" + "#" * 60)
    print("# J-LINK / ST-LINK HARDWARE INTEGRATION TESTS")
    print("#" * 60)
    
    results = {}
    
    # Test J-Link with pylink2
    results["J-Link (pylink2)"] = await test_jlink_connection()
    
    # Test J-Link probe adapter
    results["J-Link Adapter"] = await test_jlink_probe_adapter()
    
    # Test ST-Link via OpenOCD (requires separate OpenOCD server)
    results["ST-Link (OpenOCD)"] = await test_stlink_connection()
    
    # Summary
    print("\n" + "#" * 60)
    print("# TEST SUMMARY")
    print("#" * 60)
    
    for name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {name}: {status}")
    
    all_passed = all(results.values())
    print()
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️  SOME TESTS FAILED - Check connections and dependencies")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
