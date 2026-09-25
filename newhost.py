# -*- coding: utf-8 -*-
import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
from dotenv import load_dotenv  # New import for .env

# --- Load environment variables ---
load_dotenv()  # Load .env file

# --- Flask Keep Alive ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Digital World HOSTING BOT"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")
# --- End Flask Keep Alive ---

# --- Configuration FROM .env FILE ---
TOKEN = os.getenv('TOKEN', ''8878404837:AAHlL2QNSxr1HUGl3wlrD3vNi6e1DychDmw)
OWNER_ID = int(os.getenv('OWNER_ID', 7201893742 ))
ADMIN_ID = int(os.getenv('ADMIN_ID', 7201893742 ))
YOUR_USERNAME = os.getenv('YOUR_USERNAME', '@M_JITENDRA')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', 'https://t.me/J7xOFFICIAL')

# Limits from .env or defaults
FREE_USER_LIMIT = int(os.getenv('FREE_USER_LIMIT', 1))
SUBSCRIBED_USER_LIMIT = int(os.getenv('SUBSCRIBED_USER_LIMIT', 3))
ADMIN_LIMIT = int(os.getenv('ADMIN_LIMIT', 20))
OWNER_LIMIT = float('inf')

# Folder setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

# Create necessary directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
banned_users = set()
user_limits = {}  # Custom limits per user
bot_locked = False

# --- Manual Modules Installation System ---
pending_modules = {}  # {user_id: {module_name: package_name}}
manual_install_requests = {}  # {admin_id: {user_id: {module_name: package_name}}}

# --- Mandatory Channels/Groups ---
mandatory_channels = {}  # {channel_id: {'username': 'channel_username', 'name': 'Channel Name'}}

# Store pending ZIP files for approval
pending_zip_files = {}  # {user_id: {file_name: file_content}}

# --- Security Settings ---
SECURITY_CONFIG = {
    'blocked_modules': ['os.system', 'os', 'zipfile', 'subprocess.Popen', 'subprocess', 'eval', 'exec','compile', '__import__'],
    'max_file_size': 20 * 1024 * 1024,  # 20MB
    'max_script_runtime': 3600,  # 1 hour
    'allowed_extensions': ['.py', '.js'],
    'blocked_imports': ['shutil.rmtree', 'subprocess','os.remove', 'os.unlink']
}

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Command Button Layouts ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📞 Contact Owner"],
    ["📦 Manual Install", "🆘 Help"]
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Running All Code"],
    ["👑 Admin Panel", "📞 Contact Owner"],
    ["📢 Channel Add", "🛠️ Manual Install"],
    ["👥 User Management", "⚙️ Settings"]
]

# --- Database Setup ---
def init_db():
    """Initialize the database with required tables"""
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY, join_date TEXT, last_seen TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY, reason TEXT, banned_by INTEGER, ban_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_limits
                     (user_id INTEGER PRIMARY KEY, file_limit INTEGER, set_by INTEGER, set_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS mandatory_channels
                     (channel_id TEXT PRIMARY KEY, 
                      channel_username TEXT,
                      channel_name TEXT,
                      added_by INTEGER,
                      added_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS install_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      module_name TEXT,
                      package_name TEXT,
                      status TEXT,
                      log TEXT,
                      install_date TEXT)''')
        
        c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)', 
                  (OWNER_ID, OWNER_ID, datetime.now().isoformat()))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)', 
                      (ADMIN_ID, OWNER_ID, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    """Load data from database into memory"""
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        # Load subscriptions
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"⚠️ Invalid expiry date format for user {user_id}: {expiry}. Skipping.")

        # Load user files
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))

        # Load active users
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())

        # Load admins
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        # Load banned users
        c.execute('SELECT user_id FROM banned_users')
        banned_users.update(user_id for (user_id,) in c.fetchall())

        # Load user limits
        c.execute('SELECT user_id, file_limit FROM user_limits')
        for user_id, file_limit in c.fetchall():
            user_limits[user_id] = file_limit

        # Load mandatory channels
        c.execute('SELECT channel_id, channel_username, channel_name FROM mandatory_channels')
        for channel_id, channel_username, channel_name in c.fetchall():
            mandatory_channels[channel_id] = {
                'username': channel_username,
                'name': channel_name
            }

        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_subscriptions)} subscriptions, {len(admin_ids)} admins, {len(banned_users)} banned users, {len(user_limits)} custom limits, {len(mandatory_channels)} mandatory channels.")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

# Initialize DB and Load Data at startup
init_db()
load_data()

# --- Security Functions ---
def check_code_security(file_path, file_type):
    """Check code for dangerous commands (lightweight version)"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Comprehensive dangerous patterns with regex
        dangerous_patterns = [
    # ======================
    # SYSTEM / OS COMMANDS
    # ======================
    r'\bos\b',
    r'\bos\.system\b',
    r'\bos\.(remove|unlink|walk|listdir|scandir|stat|popen|fork|exec|kill|spawn)\b',
    r'\bshutdown\b',
    r'\breboot\b',
    r'rm\s+-rf',
    r'format\s+c:',
    r'dd\s+if=',
    r'\bmkfs\b',
    r'\bfdisk\b',
    r'chmod\s+777',
    r'chmod\s+\+x',
    r'\bsys\.exit\b',
    r'\bsys\.argv\b',

    # ======================
    # BASIC SHELL COMMANDS
    # ======================
    r'\bls\b',
    r'\bcd\b',
    r'\bvps\b',
    r'\bkill\b',
    r'\bkillall\b',
    r'\bpkill\b',
    r'\bkill\s+-\d+',
    r'\bhalt\b',
    r'\bpoweroff\b',
    r'\binit\s+0',
    r'\binit\s+6',
    r'\btelinit\s+0',
    r'\btelinit\s+6',
    r'\bmv\b.*/dev/null',
    r'\bcat\s+>/dev/null',
    r'>\s*/dev/null',
    r'2>\s*&1',
    r'\b&\s*$',
    r'\bnohup\b',
    r'\bdisown\b',

    # ======================
    # FILE DELETION/DESTRUCTION
    # ======================
    r'rm\s+-rf\s+/',
    r'rm\s+-rf\s+~',
    r'rm\s+-rf\s+\.',
    r'rm\s+-rf\s+\*',
    r'rm\s+-rf\s+.*',
    r'\bdd\s+if=/dev/zero',
    r'\bdd\s+of=/dev/sda',
    r'\bmv\s+/dev/null',
    r'>\s+\.bash_history',
    r'>\s+\.zsh_history',
    r'echo\s+""\s+>',
    r'truncate\s+-s\s+0',
    r':>\s*',

    # ======================
    # REGULAR EXPRESSIONS (re) - Yeh add kiya
    # ======================
    r'\bre\b',
    r'\bre\.(compile|search|match|findall|finditer|sub|split|escape|fullmatch)\b',
    r'\bimport\s+re\b',
    r'\bfrom\s+re\s+import\b',
    r'\bregex\b',
    r'\bpattern\s*=\s*re\.compile',
    r're\.(I|IGNORECASE|M|MULTILINE|S|DOTALL|U|UNICODE|X|VERBOSE)',
    r'\.*\{.*,\}',
    r'\^.*\$',
    r'\[.*\]',
    r'\(.*\)',
    r'\?.*',
    r'\*.*',
    r'\+.*',

    # ======================
    # IMAGE/FILE MANIPULATION - Yeh add kiya
    # ======================
    r'image\.jpeg',
    r'image\.jpg',
    r'image\.png',
    r'image\.gif',
    r'image\.bmp',
    r'\.jpeg\b',
    r'\.jpg\b',
    r'\.png\b',
    r'\.gif\b',
    r'\.bmp\b',
    r'\.ico\b',
    r'\.svg\b',
    r'\.webp\b',
    r'\.tiff\b',
    r'\.tif\b',
    r'\.pdf\b',
    r'\.docx\b',
    r'\.doc\b',
    r'\.xlsx\b',
    r'\.xls\b',
    r'\.pptx\b',
    r'\.ppt\b',
    r'\.zip\b',
    r'\.tar\b',
    r'\.gz\b',
    r'\.7z\b',
    r'\.rar\b',
    r'\bPIL\b',
    r'\bImage\b',
    r'\bImage\.(open|save|new|fromarray|frombytes)\b',
    r'\bcv2\b',
    r'\bopencv\b',
    r'\bskimage\b',
    r'\bscikit-image\b',
    r'\bmatplotlib\.image\b',
    r'\bimread\b',
    r'\bimwrite\b',
    r'\bimshow\b',
    r'\bimsave\b',

    # ======================
    # CTYPES / DLL LOADING
    # ======================
    r'\bctypes\b',
    r'\bctypes\.(CDLL|WinDLL|PyDLL|cdll|windll|oledll|py_object|Structure|Union)\b',
    r'\bCDLL\b',
    r'\bWinDLL\b',
    r'\blibc\b',
    r'\bFILE_p\b',
    r'\blibc\.(system|exec|fork|kill|popen)\b',
    r'\bmemset\b',
    r'\bmemcpy\b',
    r'\bmprotect\b',
    r'\bmmap\b',
    r'\bVirtualAlloc\b',
    r'\bCreateProcess\b',
    r'\bLoadLibrary\b',
    r'\bGetProcAddress\b',

    # ======================
    # EXEC / SUBPROCESS
    # ======================
    r'\bsubprocess\b',
    r'\bsubprocess\.(Popen|call|run|check_output|getoutput|getstatusoutput)\b',
    r'\beval\b',
    r'\bexec\b',
    r'\bcompile\b',
    r'\b__import__\b',

    # ======================
    # FILE SYSTEM / DATA READ
    # ======================
    r'\bopen\s*\(',
    r'\bread\s*\(',
    r'\bpathlib\b',
    r'\bglob\b',
    r'\bshutil\b',
    r'\bshutil\.(rmtree|copytree|move|disk_usage)\b',
    r'\bzipfile\b',
    r'\btempfile\b',
    r'\bcPickle\b',
    r'\bshelve\b',
    r'\bsqlite3\b',
    r'\bpandas\.(read_csv|read_excel|read_json)\b',

    # ======================
    # ENV / SECRETS
    # ======================
    r'\bos\.environ\b',
    r'\bdotenv\b',
    r'\bload_dotenv\b',
    r'\bprintenv\b',
    r'\benv\b',
    r'\bgetpass\b',
    r'\bkeyring\b',
    r'\bconfigparser\b',
    r'\byaml\b',
    r'\bjson\.load\b',

    # ======================
    # NETWORK / DATA EXFIL
    # ======================
    r'\bsocket\b',
    r'\bsocket\.(socket|create_connection|gethostname|gethostbyname)\b',
    r'\brequests\b',
    r'\brequests\.(get|post|put|delete|head|request)\b',
    r'\burllib\b',
    r'\burllib2\b',
    r'\burllib3\b',
    r'\bhttp\.client\b',
    r'\bwebsocket\b',
    r'\basyncio\.open_connection\b',
    r'\bwget\b',
    r'\bcurl\b',
    r'\bdownload\b',
    r'\bftplib\b',
    r'\bsmtplib\b',
    r'\bpoplib\b',
    r'\bimaplib\b',
    r'\btelnetlib\b',

    # ======================
    # SSH / REMOTE ACCESS
    # ======================
    r'\bparamiko\b',
    r'\bscp\b',
    r'\bssh\b',
    r'\bsshlib\b',
    r'\bpexpect\b',
    r'\bfabric\b',

    # ======================
    # SYSTEM INFO LEAK
    # ======================
    r'\bpsutil\b',
    r'\bplatform\b',
    r'\bplatform\.(node|processor|machine|architecture|system|version)\b',
    r'\bcmdline\b',
    r'\bpid\b',
    r'/proc/',
    r'\bmem\b',
    r'\bcpu\b',
    r'\bhostname\b',
    r'\buname\b',
    r'\bwhoami\b',

    # ======================
    # PYTHON INTERNAL ABUSE
    # ======================
    r'\bglobals\b',
    r'\blocals\b',
    r'\bvars\b',
    r'\binspect\b',
    r'\bmarshal\b',
    r'\bpickle\b',
    r'\bimportlib\b',
    r'\b__builtins__\b',
    r'\b__import__\b',
    r'\b__loader__\b',
    r'\b__file__\b',
    r'\b__package__\b',
    r'\b__spec__\b',
    r'\b__code__\b',
    r'\b__dict__\b',
    r'\bgetattr\b',
    r'\bsetattr\b',
    r'\bdelattr\b',
    r'\bhasattr\b',
    r'\bcallable\b',

    # ======================
    # TELEGRAM / BOT CONTROL
    # ======================
    r'\btelebot\b',
    r'\btelebot\.types\b',
    r'\baiogram\b',
    r'\bpyrogram\b',
    r'\btelegram\.ext\b',
    r'\btelegram\.bot\b',

    # ======================
    # LINUX / SHELL / BACKDOOR
    # ======================
    r'/bin/sh',
    r'/bin/bash',
    r'/bin/zsh',
    r'/bin/dash',
    r'nc\s+-e',
    r'netcat',
    r'\bbase64\b',
    r'\becho\b.*\|',
    r'\bawk\b',
    r'\bsed\b',
    r'\bfind\b',
    r'\bxargs\b',
    r'\bcrontab\b',
    r'\bservice\b',
    r'\bsystemctl\b',
    r'\btop\b',
    r'\bps\b',
    r'\bhtop\b',
    r'\bifconfig\b',
    r'\bip\s+a',
    r'\bss\b',
    r'\blsof\b',
    r'\bnetstat\b',

    # ======================
    # SSH KEYS / USER DATA
    # ======================
    r'/etc/passwd',
    r'/etc/shadow',
    r'/etc/hosts',
    r'/etc/resolv.conf',
    r'\.ssh/',
    r'id_rsa',
    r'id_dsa',
    r'authorized_keys',
    r'known_hosts',
    r'\.bashrc',
    r'\.bash_profile',
    r'\.zshrc',
    r'\.profile',

    # ======================
    # DATABASE ACCESS
    # ======================
    r'\bsqlite3\b',
    r'\bmysql\b',
    r'\bmysql\.connector\b',
    r'\bpsycopg2\b',
    r'\bpymongo\b',
    r'\bredis\b',

    # ======================
    # CRYPTO / ENCRYPTION
    # ======================
    r'\bcrypt\b',
    r'\bhashlib\b',
    r'\bhmac\b',
    r'\bssl\b',
    r'\btls\b',
    r'\bCrypto\b',
    r'\bcryptography\b',

    # ======================
    # PROCESS CONTROL
    # ======================
    r'\bsignal\b',
    r'\bmultiprocessing\b',
    r'\bthreading\b',
    r'\bdaemon\b',
    r'\batexit\b',
    r'\bexit\b',
    r'\bquit\b',

    # ======================
    # GUI / SCREEN CAPTURE
    # ======================
    r'\bpyautogui\b',
    r'\bselenium\b',
    r'\bpyscreenshot\b',
    r'\bImageGrab\b',

    # ======================
    # KEYLOGGING / INPUT
    # ======================
    r'\bpynput\b',
    r'\bkeyboard\b',
    r'\bmouse\b',
    r'\bgetch\b',

    # ======================
    # MISC DANGEROUS
    # ======================
    r'\.name\b',
    r'\.__name__\b',
    r'\.__class__\b',
    r'\.__bases__\b',
    r'\.__subclasses__\b',
    r'\.__mro__\b',
    r'\.__dictitems__\b',
    r'\.__reduce__\b',
    r'\.__reduce_ex__\b',
    r'\.__getstate__\b',
    r'\.__setstate__\b',

    # ======================
    # WINDOWS SPECIFIC
    # ======================
    r'\bwin32api\b',
    r'\bwin32com\b',
    r'\bwin32con\b',
    r'\bwin32event\b',
    r'\bwin32file\b',
    r'\bwin32process\b',
    r'\bwin32security\b',
    r'\bwmi\b',
    r'\bregedit\b',
    r'\bregistry\b',
    r'\bGetAsyncKeyState\b',
    r'\bSetWindowsHookEx\b',
    r'\btaskkill\b',
    r'\btasklist\b',
    r'\bschtasks\b',

    # ======================
    # ANTI-DEBUG / ANTI-VM
    # ======================
    r'\bptrace\b',
    r'\bdebugger\b',
    r'\bisatty\b',
    r'\bwindbg\b',
    r'\bollydbg\b',

    # ======================
    # MEMORY MANIPULATION
    # ======================
    r'\bmmap\b',
    r'\bmprotect\b',
    r'\bbrk\b',
    r'\bsbrk\b',
    r'\bmalloc\b',
    r'\bfree\b',
    r'\brealloc\b',
    r'\bVirtualAlloc\b',
    r'\bVirtualProtect\b',
    r'\bVirtualFree\b',
    r'\bHeapAlloc\b',
    r'\bHeapFree\b',

    # ======================
    # CODE INJECTION
    # ======================
    r'\binject\b',
    r'\bpayload\b',
    r'\bshellcode\b',
    r'\bmetasploit\b',
    r'\bbackdoor\b',
    r'\brootkit\b',
    r'\btrojan\b',
    r'\bmalware\b',
    r'\bexploit\b',
    r'\bvirus\b',
    r'\bworm\b',

    # ======================
    # NETWORK SCANNING
    # ======================
    r'\bnmap\b',
    r'\bnping\b',
    r'\bscapy\b',
    r'\barp\b',
    r'\bping\b',
    r'\btraceroute\b',
    r'\broute\b',
    r'\bifconfig\b',
    r'\bipconfig\b',
    r'\bnetstat\b',
    r'\bss\b',

    # ======================
    # PRIVILEGE ESCALATION
    # ======================
    r'\bsudo\b',
    r'\bsu\b',
    r'\brunas\b',
    r'\bprivilege\b',
    r'\bescalation\b',
    r'\buac\b',
    r'\bbypassuac\b',

    # ======================
    # PERSISTENCE
    # ======================
    r'\bregistry\b',
    r'\bstartup\b',
    r'\bautostart\b',
    r'\bscheduled\s*task\b',
    r'\bcron\b',
    r'\bat\b',
    r'\binit\.d\b',
    r'\bsystemd\b',
    r'\blaunchd\b',
    r'\bplist\b',

    # ======================
    # MORE DESTRUCTIVE COMMANDS
    # ======================
    r'\bmv\s+.*\s+/dev/null',
    r'\b>+\s*.*\.log',
    r'\btar\s+.*--exclude',
    r'\bfuser\b',
    r'\bstrace\b',
    r'\bltrace\b',
    r'\bgdb\b',
    r'\bobjdump\b',
    r'\bstrings\b',
    r'\bhexdump\b',
    r'\bxxd\b',
    r'\bod\b',
    r'\bsize\b',
    r'\bnm\b',
    r'\breadelf\b',
    r'\bldd\b',
    r'\bfile\b',
    r'\bwhich\b',
    r'\bwhereis\b',
    r'\blocate\b',
    r'\bupdatedb\b',
    r'\bmake\b',
    r'\bgcc\b',
    r'\bg\+\+\b',
    r'\bclang\b',
    r'\bclang\+\+\b',
    r'\bpython\d*\s+-c',
    r'\bperl\s+-e',
    r'\bruby\s+-e',
    r'\bphp\s+-r',
    r'\blua\s+-e',
    r'\bnode\s+-e',
    r'\bwget\s+.*\|\s*sh',
    r'\bcurl\s+.*\|\s*sh',
    r'\bwget\s+.*\|\s*bash',
    r'\bcurl\s+.*\|\s*bash',
    r'\bchattr\s+\+i',
    r'\bchattr\s+-i',
    r'\bsetfacl\b',
    r'\bgetfacl\b',
    r'\bchown\s+.*:.*',
    r'\bchgrp\b',
    r'\busermod\b',
    r'\bgroupmod\b',
    r'\badduser\b',
    r'\baddgroup\b',
    r'\bdeluser\b',
    r'\bdelgroup\b',
    r'\bpasswd\b',
    r'\bvisudo\b',
    r'\bed\b',
    r'\bex\b',
    r'\bvi\b',
    r'\bvim\b',
    r'\bnano\b',
    r'\be
