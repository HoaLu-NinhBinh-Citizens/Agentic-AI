# Physical Connection Checklist

## Before running flash test, verify:

### 1. J-Link Cable
- [ ] J-Link 20-pin cable connected to MCU
- [ ] Cable not loose

### 2. MCU Power
- [ ] STM32F407 powered ON (LED indicator)
- [ ] 3.3V present on MCU pins

### 3. SWD Pins Connected
```
J-Link          STM32F407
-------         ----------
VTref    -->    3.3V
GND      -->    GND
SWDIO    -->    PA13 (pin 34)
SWCLK    -->    PA14 (pin 37)
```

### 4. Check Device in J-Link Commander
Run manually:
```powershell
"C:\Program Files\SEGGER\JLink_V820\JLink.exe"
```
Then type:
```
si 1        # Select SWD
speed 4000   # Set speed
connect      # Connect to device
```

### 5. Driver Check
- [ ] J-Link driver installed in Windows Device Manager
- [ ] J-Link appears under "Universal Serial Bus devices"

---

## Quick Test Commands

```powershell
# Test J-Link without device (should show version)
"C:\Program Files\SEGGER\JLink_V820\JLink.exe" -version

# Test with device
"C:\Program Files\SEGGER\JLink_V820\JLink.exe" -Device STM32F407VG -If SWD -Speed 4000
```

## Status LED Meanings

| LED | Meaning |
|-----|---------|
| Red solid | No connection |
| Green blinking | Connected |
| Green solid | Programming |
| Orange | Error |

---

After confirming physical connection, run:
```
python hardware/test_physical_flash.py
```
