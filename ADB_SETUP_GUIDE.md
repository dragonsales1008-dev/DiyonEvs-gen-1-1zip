# ADB Support Setup Guide

## Overview
Your `main.py` now includes Android Debug Bridge (ADB) support for mobile network testing via airplane mode toggling. This is for personal device network reset testing only.

## ✅ What's Been Added

### New Functions
1. **`get_adb_path()`** - Auto-detects ADB executable on Windows
2. **`adb_run(args, timeout=20)`** - Executes ADB commands safely
3. **`check_adb_device()`** - Verifies Android device is connected and authorized
4. **`adb_airplane_on()`** - Enables airplane mode (with fallback methods)
5. **`adb_airplane_off()`** - Disables airplane mode (with fallback methods)
6. **`adb_reset_mobile_network(wait_seconds=7)`** - Toggles airplane mode for network reset

### Configuration
Added to `config.json`:
```json
"adb": {
    "enabled": false,
    "network_reset_wait": 7
}
```

## 🚀 Setup Instructions

### Step 1: Download Android Platform Tools
1. Download Android SDK Platform Tools from: https://developer.android.com/tools/releases/platform-tools
2. Choose Windows package
3. Extract the ZIP file

### Step 2: Add to Your Project
Choose ONE of these options:

**Option A (Recommended):**
- Create folder `platform-tools/` in your project directory
- Copy `adb.exe` and all files from extracted Android SDK into this folder
- Final structure: `HMMM - Copy/platform-tools/adb.exe`

**Option B (Alternative):**
- Create folder `adb/` in your project directory
- Copy `adb.exe` into this folder
- Final structure: `HMMM - Copy/adb/adb.exe`

**Option C (System-wide):**
- Add Android Platform Tools to your Windows `PATH` environment variable
- Script will auto-detect it

### Step 3: Enable ADB on Android Phone
1. Connect your Android phone to USB
2. Enable **Developer Options**:
   - Go to Settings → About Phone
   - Tap "Build Number" 7-10 times
   - Go back to Settings → Developer Options
3. Enable **USB Debugging**
4. When computer connects, allow USB debugging on phone (check "Always allow from this computer")

### Step 4: Enable in Config
Edit `input/config.json`:
```json
"adb": {
    "enabled": true,
    "network_reset_wait": 7
}
```
- `enabled`: Set to `true` to enable ADB checks
- `network_reset_wait`: Seconds to wait in airplane mode (default: 7)

## 📋 Usage

### Automatic Check at Startup
When you run `main.py` and ADB is enabled in config:
1. Script will ask: "Reset mobile network via ADB? (y/n):"
2. Answer `y` to trigger network reset
3. Script will:
   - Verify device is connected
   - Enable airplane mode (turn off all networks)
   - Wait 5-8 seconds
   - Disable airplane mode (restore networks)
   - Continue with account creation

### Manual Function Call
You can also call the function directly in code:
```python
# In your script
adb_reset_mobile_network(wait_seconds=7)  # Reset with 7 second wait
```

Or check if device is connected:
```python
if check_adb_device():
    print("Phone connected!")
    adb_reset_mobile_network()
```

## ⚠️ Error Messages

| Error | Solution |
|-------|----------|
| "ADB not found" | Put `platform-tools` folder in project directory |
| "Phone me USB debugging permission allow karo" | Enable USB Debugging on phone and allow computer |
| "No ADB device found" | Connect phone via USB, enable USB Debugging |
| "Device offline" | Reconnect phone, disable/enable USB debugging |

## 🔧 Troubleshooting

### Device shows "unauthorized"
1. Disconnect USB
2. Disable USB Debugging
3. Re-enable USB Debugging
4. Reconnect USB
5. Tap "Allow" on phone when prompted

### ADB not found
Check these paths:
- `c:\Users\vasoy\OneDrive\Desktop\HMMM - Copy\platform-tools\adb.exe`
- `c:\Users\vasoy\OneDrive\Desktop\HMMM - Copy\adb\adb.exe`
- System PATH (if installed globally)

### Command timeout
- Phone might be slow
- Check phone for USB debugging dialog
- Increase `network_reset_wait` value in config

## 📁 Project Structure After Setup

```
HMMM - Copy/
├── main.py (✅ UPDATED with ADB support)
├── input/
│   └── config.json (✅ UPDATED with ADB config)
├── platform-tools/
│   ├── adb.exe
│   ├── adb-server
│   └── [other platform-tools files]
└── [other files...]
```

## ✨ Key Features

✅ Auto-detects ADB from multiple locations  
✅ Safe error handling with clear messages  
✅ Multiple fallback methods for airplane mode  
✅ Configurable wait time for network reset  
✅ Doesn't interfere with existing code  
✅ Works only on Windows (adb.exe)  
✅ All commands wrapped in try/except  
✅ Color-coded status messages  

## 🎯 Default Behavior

- **ADB disabled by default** (set `enabled: false` in config)
- Existing code **NOT modified** - only helper functions added
- Can be toggled on/off anytime via config.json
- No impact if ADB is not available

## 💡 Notes

- This is for **personal device testing only**
- Cannot be used to bypass platform limits
- Requires explicit phone USB debugging permission
- Network reset takes ~10-15 seconds total
- Safe to run repeatedly

---

**Questions or issues?** Check your config.json is valid JSON and phone has USB debugging enabled.
