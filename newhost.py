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
import logging
import threading
import re
import sys
import atexit
import requests
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# FLASK KEEP ALIVE
# ============================================================
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Hosting Bot Running"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, threaded=True)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

# ============================================================
# CONFIG (Already filled)
# ============================================================
TOKEN = os.getenv('TOKEN', '8878404837:AAFvROY7Okwk7sYUiKXLI7du2nmrvl15AvU')
OWNER_ID = int(os.getenv('OWNER_ID', 7201893742))
ADMIN_ID = int(os.getenv('ADMIN_ID', 7201893742))
YOUR_USERNAME = os.getenv('YOUR_USERNAME', 'M_JITENDRA')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', 'J7xOFFICIAL')

FREE_USER_LIMIT = int(os.getenv('FREE_USER_LIMIT', 3))
SUBSCRIBED_USER_LIMIT = int(os.getenv('SUBSCRIBED_USER_LIMIT', 5))
ADMIN_LIMIT = int(os.getenv('ADMIN_LIMIT', 20))
OWNER_LIMIT = float('inf')

# ============================================================
# PATHS
# ============================================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ============================================================
# BOT
# ============================================================
bot = telebot.TeleBot(TOKEN, threaded=True)

# ============================================================
# GLOBAL STATE
# ============================================================
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
banned_users = set()
user_limits = {}
bot_locked = False
mandatory_channels = {}

# ============================================================
# SECURITY
# ============================================================
DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/', r'rm\s+-rf\s+~', r'rm\s+-rf\s+\*',
    r'\bshutdown\b', r'\breboot\b', r'\bpoweroff\b',
    r'\bmkfs\b', r'\bfdisk\b',
    r'dd\s+if=/dev/zero', r'dd\s+of=/dev/sda',
    r'/etc/passwd', r'/etc/shadow',
    r'\.ssh/id_rsa', r'authorized_keys',
    r'nc\s+-e\s+/bin/(ba)?sh',
    r'metasploit', r'meterpreter',
    r'format\s+c:',
]

def is_code_safe(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return False, "Dangerous pattern detected"
        return True, "Safe"
    except:
        return True, "Safe"

def is_zip_safe(zip_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                if info.filename.endswith(('.py', '.js', '.sh', '.txt')):
                    try:
                        with zf.open(info.filename) as f:
                            content = f.read().decode('utf-8', errors='ignore')
                        for pattern in DANGEROUS_PATTERNS:
                            if re.search(pattern, content, re.IGNORECASE):
                                return False, f"Danger in {info.filename}"
                    except:
                        continue
        return True, "Safe"
    except:
        return True, "Safe"

# ============================================================
# MODULE MAP
# ============================================================
MODULE_MAP = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'bs4': 'beautifulsoup4',
    'PIL': 'Pillow',
    'cv2': 'opencv-python',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil',
    'sklearn': 'scikit-learn',
    'Crypto': 'pycryptodome',
    'jwt': 'PyJWT',
    'psycopg2': 'psycopg2-binary',
    'tgcrypto': 'tgcrypto',
}

CORE_MODULES = set(
    "os sys re json time datetime math random logging threading subprocess "
    "zipfile tempfile shutil sqlite3 atexit signal socket ssl hashlib hmac "
    "base64 struct collections itertools functools operator copy pickle io "
    "codecs string textwrap glob pathlib argparse platform ctypes multiprocessing "
    "concurrent contextlib abc types typing enum dataclasses inspect traceback "
    "warnings weakref gc builtins __future__ calendar locale secrets uuid "
    "decimal fractions statistics ipaddress mimetypes ftplib smtplib poplib "
    "imaplib telnetlib xml html webbrowser urllib http email csv configparser "
    "netrc plistlib ast token keyword tokenize importlib pkgutil modulefinder "
    "runpy site code codeop zipimport unittest test pdb cProfile timeit trace "
    "doctest distutils venv asyncio queue binascii errno stat fcntl pwd grp "
    "crypt termios tty pty select selectors mmap array cmath unicodedata "
    "stringprep readline rlcompleter pprint reprlib numbers getopt getpass "
    "fileinput filecmp fnmatch linecache binhex quopri uu cgi cgitb wsgiref "
    "xmlrpc mailbox mailcap smtpd nntplib socketserver resource".split()
)

# ============================================================
# DATABASE
# ============================================================
DB_LOCK = threading.Lock()

def db_execute(query, params=(), fetch=False):
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=10)
        c = conn.cursor()
        c.execute(query, params)
        result = c.fetchall() if fetch else None
        conn.commit()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"DB error: {e}")
        return [] if fetch else None

def init_db():
    logger.info(f"Initializing DB: {DATABASE_PATH}")
    tables = [
        'CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER PRIMARY KEY, expiry TEXT)',
        'CREATE TABLE IF NOT EXISTS user_files (user_id INTEGER, file_name TEXT, file_type TEXT, PRIMARY KEY (user_id, file_name))',
        'CREATE TABLE IF NOT EXISTS active_users (user_id INTEGER PRIMARY KEY, join_date TEXT, last_seen TEXT)',
        'CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_date TEXT)',
        'CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY, reason TEXT, banned_by INTEGER, ban_date TEXT)',
        'CREATE TABLE IF NOT EXISTS user_limits (user_id INTEGER PRIMARY KEY, file_limit INTEGER, set_by INTEGER, set_date TEXT)',
        'CREATE TABLE IF NOT EXISTS mandatory_channels (channel_id TEXT PRIMARY KEY, channel_username TEXT, channel_name TEXT, added_by INTEGER, added_date TEXT)',
        'CREATE TABLE IF NOT EXISTS install_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, module_name TEXT, package_name TEXT, status TEXT, log TEXT, install_date TEXT)',
    ]
    for t in tables:
        db_execute(t)
    db_execute('INSERT OR IGNORE INTO admins VALUES (?, ?, ?)',
               (OWNER_ID, OWNER_ID, datetime.now().isoformat()))
    if ADMIN_ID != OWNER_ID:
        db_execute('INSERT OR IGNORE INTO admins VALUES (?, ?, ?)',
                   (ADMIN_ID, OWNER_ID, datetime.now().isoformat()))
    logger.info("DB initialized")

def load_data():
    logger.info("Loading data...")
    try:
        for uid, exp in db_execute('SELECT user_id, expiry FROM subscriptions', fetch=True) or []:
            try:
                user_subscriptions[uid] = {'expiry': datetime.fromisoformat(exp)}
            except:
                pass
        for uid, fn, ft in db_execute('SELECT user_id, file_name, file_type FROM user_files', fetch=True) or []:
            if uid not in user_files:
                user_files[uid] = []
            user_files[uid].append((fn, ft))
        for (uid,) in db_execute('SELECT user_id FROM active_users', fetch=True) or []:
            active_users.add(uid)
        for (uid,) in db_execute('SELECT user_id FROM admins', fetch=True) or []:
            admin_ids.add(uid)
        for (uid,) in db_execute('SELECT user_id FROM banned_users', fetch=True) or []:
            banned_users.add(uid)
        for uid, fl in db_execute('SELECT user_id, file_limit FROM user_limits', fetch=True) or []:
            user_limits[uid] = fl
        for cid, cu, cn in db_execute('SELECT channel_id, channel_username, channel_name FROM mandatory_channels', fetch=True) or []:
            mandatory_channels[cid] = {'username': cu, 'name': cn}
        logger.info(f"Loaded: {len(active_users)} users")
    except Exception as e:
        logger.error(f"Load error: {e}")

init_db()
load_data()

# ============================================================
# HELPERS
# ============================================================
def get_user_folder(user_id):
    folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(folder, exist_ok=True)
    return folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_limits: return user_limits[user_id]
    if user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_user_banned(user_id):
    return user_id in banned_users

def is_script_alive(script_key):
    info = bot_scripts.get(script_key)
    if not info:
        return False
    try:
        proc = info.get('process')
        if proc and proc.poll() is None:
            return True
    except:
        pass
    return False

def is_bot_running(owner_id, file_name):
    return is_script_alive(f"{owner_id}_{file_name}")

def _cleanup_dead_script(script_key):
    info = bot_scripts.pop(script_key, None)
    if info:
        try:
            if info.get('log_file') and not info['log_file'].closed:
                info['log_file'].close()
        except:
            pass

def kill_process_tree(info):
    try:
        try:
            if info.get('log_file') and not info['log_file'].closed:
                info['log_file'].close()
        except:
            pass
        process = info.get('process')
        if process and process.pid:
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except:
                        try: child.kill()
                        except: pass
                psutil.wait_procs(children, timeout=2)
                for p in children:
                    try:
                        if p.is_running(): p.kill()
                    except: pass
                try:
                    parent.terminate()
                    try:
                        parent.wait(timeout=2)
                    except psutil.TimeoutExpired:
                        parent.kill()
                except:
                    try: parent.kill()
                    except: pass
            except psutil.NoSuchProcess:
                pass
    except Exception as e:
        logger.error(f"Kill error: {e}")

# ============================================================
# DB OPS
# ============================================================
def save_user_file(user_id, file_name, file_type='py'):
    db_execute('INSERT OR REPLACE INTO user_files VALUES (?, ?, ?)', (user_id, file_name, file_type))
    if user_id not in user_files:
        user_files[user_id] = []
    user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
    user_files[user_id].append((file_name, file_type))

def remove_user_file_db(user_id, file_name):
    db_execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
    if user_id in user_files:
        user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
        if not user_files[user_id]:
            del user_files[user_id]

def add_active_user(user_id):
    active_users.add(user_id)
    now = datetime.now().isoformat()
    db_execute('INSERT OR REPLACE INTO active_users VALUES (?, ?, ?)', (user_id, now, now))

def save_subscription(user_id, expiry):
    db_execute('INSERT OR REPLACE INTO subscriptions VALUES (?, ?)', (user_id, expiry.isoformat()))
    user_subscriptions[user_id] = {'expiry': expiry}

def remove_subscription_db(user_id):
    db_execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
    user_subscriptions.pop(user_id, None)

def add_admin_db(admin_id, added_by):
    db_execute('INSERT OR IGNORE INTO admins VALUES (?, ?, ?)',
               (admin_id, added_by, datetime.now().isoformat()))
    admin_ids.add(admin_id)

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        return False
    db_execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
    admin_ids.discard(admin_id)
    return True

def ban_user_db(user_id, reason, banned_by):
    db_execute('INSERT OR REPLACE INTO banned_users VALUES (?, ?, ?, ?)',
               (user_id, reason, banned_by, datetime.now().isoformat()))
    banned_users.add(user_id)

def unban_user_db(user_id):
    db_execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
    banned_users.discard(user_id)

def set_user_limit_db(user_id, limit, set_by):
    db_execute('INSERT OR REPLACE INTO user_limits VALUES (?, ?, ?, ?)',
               (user_id, limit, set_by, datetime.now().isoformat()))
    user_limits[user_id] = limit

def remove_user_limit_db(user_id):
    db_execute('DELETE FROM user_limits WHERE user_id = ?', (user_id,))
    user_limits.pop(user_id, None)

def save_install_log(user_id, module_name, package_name, status, log):
    db_execute('INSERT INTO install_logs (user_id, module_name, package_name, status, log, install_date) VALUES (?, ?, ?, ?, ?, ?)',
               (user_id, module_name, package_name, status, log[:2000], datetime.now().isoformat()))

def save_mandatory_channel(channel_id, channel_username, channel_name, added_by):
    db_execute('INSERT OR REPLACE INTO mandatory_channels VALUES (?, ?, ?, ?, ?)',
               (channel_id, channel_username, channel_name, added_by, datetime.now().isoformat()))
    mandatory_channels[channel_id] = {'username': channel_username, 'name': channel_name}

def remove_mandatory_channel_db(channel_id):
    db_execute('DELETE FROM mandatory_channels WHERE channel_id = ?', (channel_id,))
    mandatory_channels.pop(channel_id, None)

# ============================================================
# MANDATORY CHANNELS
# ============================================================
def is_user_member(user_id, channel_id):
    try:
        member = bot.get_chat_member(channel_id, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return True

def check_mandatory_subscription(user_id):
    if not mandatory_channels:
        return True, []
    not_joined = []
    for cid, cinfo in mandatory_channels.items():
        if not is_user_member(user_id, cid):
            not_joined.append((cid, cinfo))
    return (False, not_joined) if not_joined else (True, [])

def create_mandatory_channels_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add', callback_data='add_mandatory_channel'),
        types.InlineKeyboardButton('➖ Remove', callback_data='remove_mandatory_channel')
    )
    markup.row(types.InlineKeyboardButton('📋 List', callback_data='list_mandatory_channels'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_subscription_check_message(not_joined):
    message = "📢 **Join Our Channels First:**\n\n"
    markup = types.InlineKeyboardMarkup()
    for cid, cinfo in not_joined:
        username = cinfo.get('username', '')
        name = cinfo.get('name', 'Channel')
        link = f"https://t.me/{username.replace('@', '')}" if username else f"https://t.me/c/{cid.replace('-100', '')}"
        message += f"• {name}\n"
        markup.add(types.InlineKeyboardButton(f"Join {name}", url=link))
    markup.add(types.InlineKeyboardButton("✅ Verify", callback_data='check_subscription_status'))
    return message, markup

# ============================================================
# PACKAGE INSTALL
# ============================================================
def install_python_package(module_name, message_obj=None, user_id=None):
    base = module_name.split('.')[0]
    pkg = MODULE_MAP.get(module_name.lower()) or MODULE_MAP.get(base.lower())
    if base in CORE_MODULES:
        return True, "Core"
    if pkg is None:
        pkg = base
    try:
        if message_obj:
            try:
                bot.reply_to(message_obj, f"🔄 Installing `{pkg}`...", parse_mode='Markdown')
            except:
                pass
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', pkg],
            capture_output=True, text=True, timeout=180,
            encoding='utf-8', errors='ignore'
        )
        if result.returncode == 0:
            if message_obj:
                try:
                    bot.reply_to(message_obj, f"✅ `{pkg}` installed!", parse_mode='Markdown')
                except:
                    pass
            save_install_log(user_id or 0, module_name, pkg, "success", result.stdout[:500])
            return True, "OK"
        else:
            err = (result.stderr or result.stdout or "")[:500]
            if message_obj:
                try:
                    bot.reply_to(message_obj, f"❌ Failed: `{pkg}`", parse_mode='Markdown')
                except:
                    pass
            save_install_log(user_id or 0, module_name, pkg, "failed", err)
            return False, err
    except Exception as e:
        return False, str(e)

def install_npm_package(module_name, user_folder, message_obj=None, user_id=None):
    try:
        if message_obj:
            try:
                bot.reply_to(message_obj, f"🟠 Installing npm `{module_name}`...", parse_mode='Markdown')
            except:
                pass
        result = subprocess.run(
            ['npm', 'install', module_name],
            capture_output=True, text=True, timeout=180,
            cwd=user_folder, encoding='utf-8', errors='ignore'
        )
        if result.returncode == 0:
            if message_obj:
                try:
                    bot.reply_to(message_obj, f"✅ npm `{module_name}` installed!", parse_mode='Markdown')
                except:
                    pass
            return True, "OK"
        return False, (result.stderr or "")[:500]
    except FileNotFoundError:
        return False, "npm not found"
    except Exception as e:
        return False, str(e)

# ============================================================
# MENUS
# ============================================================
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton('📢 Updates Channel',
               url=f'https://t.me/{UPDATE_CHANNEL.replace("@", "")}'))
    markup.add(
        types.InlineKeyboardButton('📤 Upload File', callback_data='upload'),
        types.InlineKeyboardButton('📂 Check Files', callback_data='check_files')
    )
    markup.add(
        types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
        types.InlineKeyboardButton('📊 Statistics', callback_data='stats')
    )
    markup.add(types.InlineKeyboardButton('📦 Manual Install', callback_data='manual_install'))
    if user_id in admin_ids:
        markup.add(
            types.InlineKeyboardButton('💳 Subs', callback_data='subscription'),
            types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast')
        )
        markup.add(
            types.InlineKeyboardButton('🔒 Lock' if not bot_locked else '🔓 Unlock',
                                       callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('🟢 Run All', callback_data='run_all_scripts')
        )
        markup.add(
            types.InlineKeyboardButton('👑 Admin', callback_data='admin_panel'),
            types.InlineKeyboardButton('📢 Channels', callback_data='manage_mandatory_channels')
        )
        markup.add(
            types.InlineKeyboardButton('👥 Users', callback_data='user_management'),
            types.InlineKeyboardButton('⚙️ Settings', callback_data='admin_settings')
        )
    markup.add(types.InlineKeyboardButton('📞 Contact Owner',
               url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if user_id in admin_ids:
        rows = [
            ["📢 Updates Channel"],
            ["📤 Upload File", "📂 Check Files"],
            ["⚡ Bot Speed", "📊 Statistics"],
            ["💳 Subscriptions", "📢 Broadcast"],
            ["🔒 Lock Bot", "🟢 Running All Code"],
            ["👑 Admin Panel", "📞 Contact Owner"],
            ["📢 Channel Add", "🛠️ Manual Install"],
            ["👥 User Management", "⚙️ Settings"]
        ]
    else:
        rows = [
            ["📢 Updates Channel"],
            ["📤 Upload File", "📂 Check Files"],
            ["⚡ Bot Speed", "📊 Statistics"],
            ["📞 Contact Owner"],
            ["📦 Manual Install", "🆘 Help"]
        ]
    for row in rows:
        markup.add(*[types.KeyboardButton(t) for t in row])
    return markup

def create_control_buttons(owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{owner_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{owner_id}_{file_name}')
        )
        markup.row(types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{owner_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Admin', callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin')
    )
    markup.row(types.InlineKeyboardButton('📋 List', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_user_management_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('🚫 Ban', callback_data='ban_user'),
        types.InlineKeyboardButton('✅ Unban', callback_data='unban_user')
    )
    markup.row(
        types.InlineKeyboardButton('📊 Info', callback_data='user_info'),
        types.InlineKeyboardButton('👥 All', callback_data='all_users')
    )
    markup.row(
        types.InlineKeyboardButton('🔧 Set Limit', callback_data='set_user_limit'),
        types.InlineKeyboardButton('🗑️ Remove', callback_data='remove_user_limit')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove', callback_data='remove_subscription')
    )
    markup.row(types.InlineKeyboardButton('🔍 Check', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_admin_settings_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('📊 System', callback_data='system_info'),
        types.InlineKeyboardButton('📈 Performance', callback_data='bot_performance')
    )
    markup.row(
        types.InlineKeyboardButton('🧹 Cleanup', callback_data='cleanup_files'),
        types.InlineKeyboardButton('📋 Logs', callback_data='install_logs')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

# ============================================================
# RUN SCRIPTS
# ============================================================
def run_python_script(script_path, owner_id, user_folder, file_name, reply_msg, attempt=1):
    max_attempts = 3
    if attempt > max_attempts:
        try:
            bot.reply_to(reply_msg, f"❌ Failed after {max_attempts} attempts.")
        except:
            pass
        return

    script_key = f"{owner_id}_{file_name}"
    logger.info(f"[PY] Attempt {attempt}: {file_name}")

    try:
        if not os.path.exists(script_path):
            try:
                bot.reply_to(reply_msg, "❌ File not found!")
            except:
                pass
            remove_user_file_db(owner_id, file_name)
            return

        if attempt == 1:
            try:
                import ast
                with open(script_path, 'r', encoding='utf-8', errors='replace') as f:
                    src = f.read()
                original = src
                if src.startswith('\ufeff'):
                    src = src[1:]
                if '\u00a0' in src:
                    src = src.replace('\u00a0', ' ')
                if '\r\n' in src:
                    src = src.replace('\r\n', '\n')
                if src != original:
                    try:
                        with open(script_path, 'w', encoding='utf-8') as f:
                            f.write(src)
                    except:
                        pass
                try:
                    ast.parse(src, filename=file_name)
                    logger.info(f"Syntax OK: {file_name}")
                except SyntaxError as se:
                    line = se.lineno or 0
                    msg = se.msg or "Syntax error"
                    lines = src.split('\n')
                    cs = max(0, line - 3)
                    ce = min(len(lines), line + 2)
                    ctx = ""
                    for i in range(cs, ce):
                        marker = ">>> " if i == line - 1 else "    "
                        ctx += f"{marker}{i+1}: {lines[i][:120]}\n" if i < len(lines) else ""
                    err_text = (f"❌ **Syntax Error**\n\n"
                                f"📍 Line {line}: `{msg}`\n\n"
                                f"```python\n{ctx}```\n\n"
                                f"💡 Fix and re-upload!")
                    try:
                        bot.reply_to(reply_msg, err_text, parse_mode='Markdown')
                    except:
                        bot.reply_to(reply_msg, f"Syntax Error at line {line}: {msg}")
                    return
            except Exception as e:
                logger.warning(f"AST: {e}")

            try:
                check_script = """
import sys, ast, importlib.util
try:
    with open(sys.argv[1], "r", encoding="utf-8", errors="ignore") as f:
        tree = ast.parse(f.read())
except:
    print("OK"); sys.exit(0)
imports = set()
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        for a in n.names: imports.add(a.name.split(".")[0])
    elif isinstance(n, ast.ImportFrom):
        if n.module: imports.add(n.module.split(".")[0])
CORE = set("os sys re json time datetime math random logging threading subprocess zipfile tempfile shutil sqlite3 atexit signal socket ssl hashlib hmac base64 struct collections itertools functools operator copy pickle io codecs string textwrap glob pathlib argparse platform ctypes multiprocessing concurrent contextlib abc types typing enum dataclasses inspect traceback warnings weakref gc builtins __future__ calendar locale secrets uuid decimal fractions statistics ipaddress mimetypes ftplib smtplib poplib imaplib telnetlib xml html webbrowser urllib http email csv configparser netrc plistlib ast token keyword tokenize importlib pkgutil modulefinder runpy site code codeop zipimport unittest test pdb cProfile timeit trace doctest distutils venv asyncio queue binascii errno stat fcntl pwd grp crypt termios tty pty select selectors mmap array cmath unicodedata stringprep readline rlcompleter pprint reprlib numbers getopt getpass fileinput filecmp fnmatch linecache binhex quopri uu cgi cgitb wsgiref xmlrpc mailbox mailcap smtpd nntplib socketserver".split())
missing = []
for m in imports:
    if m in CORE: continue
    try:
        if importlib.util.find_spec(m) is None: missing.append(m)
    except: missing.append(m)
if missing: print("MISSING:" + ",".join(sorted(set(missing))))
else: print("OK")
"""
                check_path = os.path.join(user_folder, f"_chk_{owner_id}.py")
                with open(check_path, 'w', encoding='utf-8') as f:
                    f.write(check_script)
                result = subprocess.run(
                    [sys.executable, check_path, script_path],
                    capture_output=True, text=True, timeout=30,
                    cwd=user_folder, encoding='utf-8', errors='ignore'
                )
                output = (result.stdout or "").strip()
                try:
                    if os.path.exists(check_path):
                        os.remove(check_path)
                except:
                    pass
                if output.startswith("MISSING:"):
                    missing = [m.strip() for m in output.replace("MISSING:", "").split(",") if m.strip()]
                    missing = [m for m in missing if m and len(m) < 50 and m.isidentifier()]
                    if missing:
                        try:
                            bot.reply_to(reply_msg, f"📦 Missing: `{', '.join(missing)}`\n🔄 Installing...", parse_mode='Markdown')
                        except:
                            pass
                        all_ok = True
                        for mod in missing:
                            ok, _ = install_python_package(mod, reply_msg, owner_id)
                            if not ok:
                                all_ok = False
                        if all_ok:
                            try:
                                bot.reply_to(reply_msg, f"✅ Installed! Starting...", parse_mode='Markdown')
                            except:
                                pass
                            time.sleep(2)
                            threading.Thread(
                                target=run_python_script,
                                args=(script_path, owner_id, user_folder, file_name, reply_msg, attempt + 1),
                                daemon=True
                            ).start()
                            return
            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                logger.error(f"Import check: {e}")

        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        try:
            log_file = open(log_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Log open: {e}")
            return

        env = os.environ.copy()
        env['PYTHONPATH'] = user_folder + os.pathsep + env.get('PYTHONPATH', '')
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONDONTWRITEBYTECODE'] = '1'

        popen_kwargs = {
            'cwd': user_folder,
            'stdout': log_file,
            'stderr': subprocess.STDOUT,
            'stdin': subprocess.DEVNULL,
            'encoding': 'utf-8',
            'errors': 'ignore',
            'env': env,
        }

        if os.name == 'nt':
            popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            popen_kwargs['start_new_session'] = True

        try:
            process = subprocess.Popen([sys.executable, '-u', script_path], **popen_kwargs)
        except Exception as e:
            logger.error(f"Popen failed: {e}")
            try:
                log_file.close()
            except:
                pass
            try:
                bot.reply_to(reply_msg, f"❌ Cannot start: {str(e)[:200]}")
            except:
                pass
            return

        logger.info(f"[PY] Started PID={process.pid} for {script_key}")

        bot_scripts[script_key] = {
            'process': process,
            'log_file': log_file,
            'file_name': file_name,
            'chat_id': reply_msg.chat.id if hasattr(reply_msg, 'chat') else None,
            'script_owner_id': owner_id,
            'start_time': datetime.now(),
            'user_folder': user_folder,
            'type': 'py',
            'script_key': script_key,
        }

        time.sleep(3)

        if process.poll() is not None:
            try:
                log_file.flush()
                log_file.close()
            except:
                pass
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as lf:
                    err = lf.read()[-2000:]
            except:
                err = "(no log)"
            _cleanup_dead_script(script_key)
            display = err.strip()[-1200:] if err.strip() else "(no output)"
            try:
                bot.reply_to(reply_msg,
                             f"❌ Script crashed (exit {process.returncode}):\n```\n{display}\n```",
                             parse_mode='Markdown')
            except:
                try:
                    bot.reply_to(reply_msg, f"❌ Script crashed.")
                except:
                    pass
            return

        try:
            bot.reply_to(reply_msg, f"✅ Script '{file_name}' started! (PID: {process.pid})")
        except:
            pass

    except Exception as e:
        logger.error(f"run_python_script error: {e}", exc_info=True)
        try:
            bot.reply_to(reply_msg, f"❌ Error: {str(e)[:200]}")
        except:
            pass

def run_js_script(script_path, owner_id, user_folder, file_name, reply_msg, attempt=1):
    max_attempts = 3
    if attempt > max_attempts:
        try:
            bot.reply_to(reply_msg, f"❌ Failed after {max_attempts} attempts.")
        except:
            pass
        return

    script_key = f"{owner_id}_{file_name}"
    logger.info(f"[JS] Attempt {attempt}: {file_name}")

    try:
        if not os.path.exists(script_path):
            try:
                bot.reply_to(reply_msg, "❌ File not found!")
            except:
                pass
            remove_user_file_db(owner_id, file_name)
            return

        if attempt == 1:
            try:
                result = subprocess.run(
                    ['node', script_path],
                    capture_output=True, text=True, timeout=10,
                    cwd=user_folder, encoding='utf-8', errors='ignore'
                )
                stderr = result.stderr or ""
                missing = re.findall(r"Cannot find module '([^']+)'", stderr)
                missing = [m for m in missing if not m.startswith('.') and not m.startswith('/')]
                if missing and result.returncode != 0:
                    try:
                        bot.reply_to(reply_msg, f"📦 Missing npm: `{', '.join(missing)}`\n🔄 Installing...", parse_mode='Markdown')
                    except:
                        pass
                    all_ok = True
                    for mod in missing:
                        ok, _ = install_npm_package(mod, user_folder, reply_msg, owner_id)
                        if not ok:
                            all_ok = False
                    if all_ok:
                        try:
                            bot.reply_to(reply_msg, f"✅ Installed! Starting...", parse_mode='Markdown')
                        except:
                            pass
                        time.sleep(2)
                        threading.Thread(
                            target=run_js_script,
                            args=(script_path, owner_id, user_folder, file_name, reply_msg, attempt + 1),
                            daemon=True
                        ).start()
                        return
            except subprocess.TimeoutExpired:
                pass
            except FileNotFoundError:
                try:
                    bot.reply_to(reply_msg, "❌ Node.js not installed!")
                except:
                    pass
                return
            except Exception as e:
                logger.error(f"JS check: {e}")

        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        try:
            log_file = open(log_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Log open: {e}")
            return

        popen_kwargs = {
            'cwd': user_folder,
            'stdout': log_file,
            'stderr': subprocess.STDOUT,
            'stdin': subprocess.DEVNULL,
            'encoding': 'utf-8',
            'errors': 'ignore',
        }

        if os.name == 'nt':
            popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            popen_kwargs['start_new_session'] = True

        try:
            process = subprocess.Popen(['node', script_path], **popen_kwargs)
        except FileNotFoundError:
            try:
                log_file.close()
            except:
                pass
            try:
                bot.reply_to(reply_msg, "❌ Node.js not installed!")
            except:
                pass
            return
        except Exception as e:
            logger.error(f"Popen failed: {e}")
            try:
                log_file.close()
            except:
                pass
            return

        logger.info(f"[JS] Started PID={process.pid} for {script_key}")

        bot_scripts[script_key] = {
            'process': process,
            'log_file': log_file,
            'file_name': file_name,
            'chat_id': reply_msg.chat.id if hasattr(reply_msg, 'chat') else None,
            'script_owner_id': owner_id,
            'start_time': datetime.now(),
            'user_folder': user_folder,
            'type': 'js',
            'script_key': script_key,
        }

        time.sleep(3)
        if process.poll() is not None:
            try:
                log_file.flush()
                log_file.close()
            except:
                pass
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as lf:
                    err = lf.read()[-2000:]
            except:
                err = "(no log)"
            _cleanup_dead_script(script_key)
            display = err.strip()[-1200:] if err.strip() else "(no output)"
            try:
                bot.reply_to(reply_msg, f"❌ JS crashed (exit {process.returncode}):\n```\n{display}\n```", parse_mode='Markdown')
            except:
                pass
            return

        try:
            bot.reply_to(reply_msg, f"✅ JS Script '{file_name}' started! (PID: {process.pid})")
        except:
            pass

    except Exception as e:
        logger.error(f"run_js_script error: {e}", exc_info=True)
        try:
            bot.reply_to(reply_msg, f"❌ Error: {str(e)[:200]}")
        except:
            pass

# ============================================================
# FILE HANDLING
# ============================================================
def sanitize_filename(name):
    name = re.sub(r'[^a-zA-Z0-9._-]', '_', name)
    name = name.lstrip('._')
    if not name:
        name = f"script_{int(time.time())}.py"
    if not name.endswith(('.py', '.js', '.zip')):
        name = name + '.py'
    return name

def handle_zip_file(content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"zip_{user_id}_")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as f:
            f.write(content)

        is_safe, msg = is_zip_safe(zip_path)
        if not is_safe:
            bot.reply_to(message, f"⚠️ Security: {msg}")
            return

        process_zip_file(zip_path, user_id, user_folder, file_name_zip, message, temp_dir)
    except zipfile.BadZipFile as e:
        bot.reply_to(message, f"❌ Invalid ZIP: {e}")
    except Exception as e:
        logger.error(f"ZIP error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

def process_zip_file(zip_path, user_id, user_folder, file_name_zip, message, temp_dir=None):
    cleanup = False
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp(prefix=f"zip_{user_id}_")
        cleanup = True

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for member in zf.infolist():
                mp = os.path.abspath(os.path.join(temp_dir, member.filename))
                if not mp.startswith(os.path.abspath(temp_dir)):
                    raise zipfile.BadZipFile(f"Unsafe path: {member.filename}")
            zf.extractall(temp_dir)

        items = os.listdir(temp_dir)
        py_files = [f for f in items if f.endswith('.py')]
        js_files = [f for f in items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in items else None
        pkg_json = 'package.json' if 'package.json' in items else None

        if req_file:
            req_path = os.path.join(temp_dir, req_file)
            bot.reply_to(message, f"🔄 Installing deps from `{req_file}`...")
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '-r', req_path],
                    capture_output=True, text=True, check=True,
                    encoding='utf-8', errors='ignore', timeout=300
                )
                bot.reply_to(message, f"✅ Python deps installed.")
            except Exception as e:
                bot.reply_to(message, f"⚠️ Deps: {str(e)[:200]}")
                return

        if pkg_json:
            bot.reply_to(message, f"🔄 Installing npm deps...")
            try:
                subprocess.run(
                    ['npm', 'install'],
                    capture_output=True, text=True, check=True,
                    cwd=temp_dir, encoding='utf-8', errors='ignore', timeout=300
                )
                bot.reply_to(message, f"✅ npm deps installed.")
            except FileNotFoundError:
                bot.reply_to(message, "⚠️ npm not found.")
                return
            except Exception as e:
                bot.reply_to(message, f"⚠️ npm: {str(e)[:200]}")
                return

        main_script = None
        file_type = None
        for p in ['main.py', 'bot.py', 'app.py', 'run.py', 'start.py']:
            if p in py_files:
                main_script = p
                file_type = 'py'
                break
        if not main_script:
            for p in ['index.js', 'main.js', 'bot.js', 'app.js', 'server.js']:
                if p in js_files:
                    main_script = p
                    file_type = 'js'
                    break
        if not main_script:
            if py_files:
                main_script = py_files[0]
                file_type = 'py'
            elif js_files:
                main_script = js_files[0]
                file_type = 'js'
        if not main_script:
            bot.reply_to(message, "❌ No .py or .js in archive!")
            return

        for item in os.listdir(temp_dir):
            src = os.path.join(temp_dir, item)
            dst = os.path.join(user_folder, item)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            elif os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)

        save_user_file(user_id, main_script, file_type)
        main_path = os.path.join(user_folder, main_script)
        bot.reply_to(message, f"✅ Starting `{main_script}`...", parse_mode='Markdown')

        if file_type == 'py':
            threading.Thread(
                target=run_python_script,
                args=(main_path, user_id, user_folder, main_script, message),
                daemon=True
            ).start()
        else:
            threading.Thread(
                target=run_js_script,
                args=(main_path, user_id, user_folder, main_script, message),
                daemon=True
            ).start()

    except Exception as e:
        logger.error(f"ZIP process: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")
    finally:
        if cleanup and temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

def handle_js_file(file_path, owner_id, user_folder, file_name, message):
    try:
        save_user_file(owner_id, file_name, 'js')
        threading.Thread(
            target=run_js_script,
            args=(file_path, owner_id, user_folder, file_name, message),
            daemon=True
        ).start()
    except Exception as e:
        logger.error(f"JS file: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

def handle_py_file(file_path, owner_id, user_folder, file_name, message):
    try:
        save_user_file(owner_id, file_name, 'py')
        threading.Thread(
            target=run_python_script,
            args=(file_path, owner_id, user_folder, file_name, message),
            daemon=True
        ).start()
    except Exception as e:
        logger.error(f"PY file: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ============================================================
# COMMANDS
# ============================================================
@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    if message.text == '/help':
        _help(message)
    else:
        _welcome(message)

def _welcome(message):
    uid = message.from_user.id
    chat = message.chat.id
    name = message.from_user.first_name

    if is_user_banned(uid):
        bot.send_message(chat, "❌ Banned.")
        return

    is_sub, not_joined = check_mandatory_subscription(uid)
    if not is_sub and uid not in admin_ids:
        msg, markup = create_subscription_check_message(not_joined)
        bot.send_message(chat, msg, reply_markup=markup, parse_mode='Markdown')
        return

    if bot_locked and uid not in admin_ids:
        bot.send_message(chat, "⚠️ Bot locked.")
        return

    if uid not in active_users:
        add_active_user(uid)
        try:
            bot.send_message(OWNER_ID, f"🎉 New user: {name} (`{uid}`)", parse_mode='Markdown')
        except:
            pass

    limit = get_user_file_limit(uid)
    count = get_user_file_count(uid)
    limit_str = str(limit) if limit != float('inf') else "Unlimited"
    expiry_info = ""

    if uid == OWNER_ID:
        status = "👑 Owner"
    elif uid in admin_ids:
        status = "🛡️ Admin"
    elif uid in user_subscriptions:
        exp = user_subscriptions[uid].get('expiry')
        if exp and exp > datetime.now():
            status = "⭐ Premium"
            expiry_info = f"\n⏳ {(exp - datetime.now()).days} days left"
        else:
            status = "🆓 Free"
            remove_subscription_db(uid)
    else:
        status = "🆓 Free"

    text = (f"〽️ Welcome, {name}!\n\n"
            f"🆔 `{uid}`\n"
            f"🔰 {status}{expiry_info}\n"
            f"📁 {count} / {limit_str}\n\n"
            f"🤖 Host Python & JS scripts\n"
            f"📦 Auto-install modules!\n\n"
            f"👇 Use buttons or type commands.")

    markup = create_reply_keyboard_main_menu(uid)
    try:
        bot.send_message(chat, text, reply_markup=markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Welcome error: {e}")

def _help(message):
    text = """
🤖 **Hosting Bot Help**

**Commands:**
• /start - Start
• /help - Help
• /status - Stats
• /ping - Latency

**Files:**
• Upload `.py`, `.js`, `.zip`
• Auto-installs missing modules

**Support:** @M_JITENDRA
"""
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['status', 'statistics'])
def cmd_status(message):
    _stats_logic(message)

@bot.message_handler(commands=['ping'])
def cmd_ping(message):
    uid = message.from_user.id
    if is_user_banned(uid):
        bot.reply_to(message, "❌ Banned.")
        return
    is_sub, nj = check_mandatory_subscription(uid)
    if not is_sub and uid not in admin_ids:
        msg, markup = create_subscription_check_message(nj)
        bot.reply_to(message, msg, reply_markup=markup, parse_mode='Markdown')
        return
    start = time.time()
    msg = bot.reply_to(message, "Pong!")
    latency = round((time.time() - start) * 1000, 2)
    bot.edit_message_text(f"Pong! {latency} ms", message.chat.id, msg.message_id)

# ============================================================
# BUTTON HANDLERS
# ============================================================
@bot.message_handler(func=lambda m: m.text in [
    "📢 Updates Channel", "📤 Upload File", "📂 Check Files",
    "⚡ Bot Speed", "📊 Statistics", "📞 Contact Owner",
    "📦 Manual Install", "🛠️ Manual Install", "🆘 Help",
    "💳 Subscriptions", "📢 Broadcast", "🔒 Lock Bot",
    "🟢 Running All Code", "👑 Admin Panel", "📢 Channel Add",
    "👥 User Management", "⚙️ Settings"
])
def handle_button(message):
    try:
        t = message.text
        if t == "📢 Updates Channel":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('📢 Updates', url=f'https://t.me/{UPDATE_CHANNEL.replace("@", "")}'))
            bot.reply_to(message, "Visit Updates:", reply_markup=markup)
        elif t == "📤 Upload File":
            _upload_logic(message)
        elif t == "📂 Check Files":
            _check_logic(message)
        elif t == "⚡ Bot Speed":
            _speed_logic(message)
        elif t == "📊 Statistics":
            _stats_logic(message)
        elif t == "📞 Contact Owner":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('📞 Contact', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
            bot.reply_to(message, "Contact Owner:", reply_markup=markup)
        elif t in ["📦 Manual Install", "🛠️ Manual Install"]:
            _manual_install(message)
        elif t == "🆘 Help":
            _help(message)
        elif t == "💳 Subscriptions":
            if message.from_user.id in admin_ids:
                bot.reply_to(message, "💳 Subs", reply_markup=create_subscription_menu())
        elif t == "📢 Broadcast":
            if message.from_user.id in admin_ids:
                msg = bot.reply_to(message, "📢 Send broadcast message.\n/cancel to abort.")
                bot.register_next_step_handler(msg, process_broadcast)
        elif t == "🔒 Lock Bot":
            if message.from_user.id in admin_ids:
                global bot_locked
                bot_locked = not bot_locked
                bot.reply_to(message, f"🔒 Bot {'locked' if bot_locked else 'unlocked'}.")
        elif t == "🟢 Running All Code":
            if message.from_user.id in admin_ids:
                _run_all(message)
        elif t == "👑 Admin Panel":
            if message.from_user.id in admin_ids:
                bot.reply_to(message, "👑 Admin", reply_markup=create_admin_panel())
        elif t == "📢 Channel Add":
            if message.from_user.id in admin_ids:
                bot.reply_to(message, "📢 Channels", reply_markup=create_mandatory_channels_menu())
        elif t == "👥 User Management":
            if message.from_user.id in admin_ids:
                bot.reply_to(message, "👥 Users", reply_markup=create_user_management_menu())
        elif t == "⚙️ Settings":
            if message.from_user.id in admin_ids:
                bot.reply_to(message, "⚙️ Settings", reply_markup=create_admin_settings_menu())
    except Exception as e:
        logger.error(f"Button: {e}", exc_info=True)

def _upload_logic(m):
    uid = m.from_user.id
    if is_user_banned(uid):
        bot.reply_to(m, "❌ Banned.")
        return
    is_sub, nj = check_mandatory_subscription(uid)
    if not is_sub and uid not in admin_ids:
        msg, markup = create_subscription_check_message(nj)
        bot.reply_to(m, msg, reply_markup=markup, parse_mode='Markdown')
        return
    if bot_locked and uid not in admin_ids:
        bot.reply_to(m, "⚠️ Bot locked.")
        return
    limit = get_user_file_limit(uid)
    count = get_user_file_count(uid)
    if count >= limit:
        bot.reply_to(m, f"⚠️ Limit reached ({count}/{limit})")
        return
    bot.reply_to(m, "📤 Send your .py, .js, or .zip file.")

def _check_logic(m):
    uid = m.from_user.id
    if is_user_banned(uid):
        bot.reply_to(m, "❌ Banned.")
        return
    is_sub, nj = check_mandatory_subscription(uid)
    if not is_sub and uid not in admin_ids:
        msg, markup = create_subscription_check_message(nj)
        bot.reply_to(m, msg, reply_markup=markup, parse_mode='Markdown')
        return
    files = user_files.get(uid, [])
    if not files:
        bot.reply_to(m, "📂 No files.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for fn, ft in sorted(files):
        running = is_bot_running(uid, fn)
        icon = "🟢" if running else "🔴"
        markup.add(types.InlineKeyboardButton(f"{icon} {fn} ({ft})", callback_data=f'file_{uid}_{fn}'))
    bot.reply_to(m, "📂 Your Files:", reply_markup=markup)

def _speed_logic(m):
    uid = m.from_user.id
    chat = m.chat.id
    if is_user_banned(uid):
        bot.reply_to(m, "❌ Banned.")
        return
    is_sub, nj = check_mandatory_subscription(uid)
    if not is_sub and uid not in admin_ids:
        msg, markup = create_subscription_check_message(nj)
        bot.reply_to(m, msg, reply_markup=markup, parse_mode='Markdown')
        return
    start = time.time()
    wait = bot.reply_to(m, "🏃 Testing...")
    try:
        bot.send_chat_action(chat, 'typing')
        rt = round((time.time() - start) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if uid == OWNER_ID:
            level = "👑 Owner"
        elif uid in admin_ids:
            level = "🛡️ Admin"
        elif uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now():
            level = "⭐ Premium"
        else:
            level = "🆓 Free"
        bot.edit_message_text(f"⚡ {rt} ms\n🚦 {status}\n👤 {level}", chat, wait.message_id)
    except Exception as e:
        logger.error(f"Speed: {e}")

def _stats_logic(m):
    uid = m.from_user.id
    if is_user_banned(uid):
        bot.reply_to(m, "❌ Banned.")
        return
    is_sub, nj = check_mandatory_subscription(uid)
    if not is_sub and uid not in admin_ids:
        msg, markup = create_subscription_check_message(nj)
        bot.reply_to(m, msg, reply_markup=markup, parse_mode='Markdown')
        return
    total_users = len(active_users)
    total_files = sum(len(f) for f in user_files.values())
    running = sum(1 for k in list(bot_scripts.keys()) if is_script_alive(k))
    user_running = sum(1 for k in list(bot_scripts.keys()) if k.startswith(f"{uid}_") and is_script_alive(k))
    text = (f"📊 Stats:\n\n"
            f"👥 Users: {total_users}\n"
            f"🚫 Banned: {len(banned_users)}\n"
            f"📂 Files: {total_files}\n"
            f"🟢 Running: {running}\n")
    if uid in admin_ids:
        text += (f"🔒 Bot: {'Locked' if bot_locked else 'Unlocked'}\n"
                 f"📢 Channels: {len(mandatory_channels)}\n"
                 f"⚙️ Limits: {len(user_limits)}\n"
                 f"🤖 Your Running: {user_running}")
    else:
        text += f"🤖 Your Running: {user_running}"
    bot.reply_to(m, text)

def _manual_install(m):
    uid = m.from_user.id
    if is_user_banned(uid):
        bot.reply_to(m, "❌ Banned.")
        return
    is_sub, nj = check_mandatory_subscription(uid)
    if not is_sub and uid not in admin_ids:
        msg, markup = create_subscription_check_message(nj)
        bot.reply_to(m, msg, reply_markup=markup, parse_mode='Markdown')
        return
    if bot_locked and uid not in admin_ids:
        bot.reply_to(m, "⚠️ Bot locked.")
        return
    msg = bot.reply_to(m, "📦 Send module name\nExamples:\n• `requests`\n• `aiogram`\n• `npm:express`\n\n/cancel to cancel", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_manual_install)

def process_manual_install(message):
    uid = message.from_user.id
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    mod = message.text.strip()
    if mod.lower().startswith('npm:'):
        mod = mod[4:].strip()
        folder = get_user_folder(uid)
        install_npm_package(mod, folder, message, uid)
    else:
        install_python_package(mod, message, uid)

def _run_all(m):
    uid = m.from_user.id
    if uid not in admin_ids:
        bot.reply_to(m, "⚠️ Admin only.")
        return
    bot.reply_to(m, "⏳ Starting all scripts...")
    started = 0
    for target_uid, files in dict(user_files).items():
        if not files:
            continue
        folder = get_user_folder(target_uid)
        for fn, ft in files:
            if not is_bot_running(target_uid, fn):
                fp = os.path.join(folder, fn)
                if os.path.exists(fp):
                    try:
                        if ft == 'py':
                            threading.Thread(target=run_python_script, args=(fp, target_uid, folder, fn, m), daemon=True).start()
                        else:
                            threading.Thread(target=run_js_script, args=(fp, target_uid, folder, fn, m), daemon=True).start()
                        started += 1
                        time.sleep(0.3)
                    except:
                        pass
    bot.send_message(m.chat.id, f"✅ Started {started} scripts.")

# ============================================================
# DOCUMENT HANDLER
# ============================================================
@bot.message_handler(content_types=['document'])
def handle_document(message):
    uid = message.from_user.id
    chat = message.chat.id
    if is_user_banned(uid):
        bot.reply_to(message, "❌ Banned.")
        return
    is_sub, nj = check_mandatory_subscription(uid)
    if not is_sub and uid not in admin_ids:
        msg, markup = create_subscription_check_message(nj)
        bot.reply_to(message, msg, reply_markup=markup, parse_mode='Markdown')
        return

    doc = message.document
    logger.info(f"Doc from {uid}: {doc.file_name}")

    if bot_locked and uid not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked.")
        return

    limit = get_user_file_limit(uid)
    count = get_user_file_count(uid)
    if count >= limit:
        bot.reply_to(message, f"⚠️ Limit ({count}/{limit})")
        return

    if not doc.file_name:
        bot.reply_to(message, "⚠️ No name.")
        return
    ext = os.path.splitext(doc.file_name)[1].lower()
    if ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Only .py, .js, .zip")
        return
    if doc.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "⚠️ Max 20 MB")
        return

    try:
        try:
            bot.forward_message(OWNER_ID, chat, message.message_id)
        except:
            pass

        wait = bot.reply_to(message, f"⏳ Downloading...")
        fi = bot.get_file(doc.file_id)
        content = bot.download_file(fi.file_path)
        bot.edit_message_text(f"✅ Processing...", chat, wait.message_id)

        file_name = sanitize_filename(doc.file_name)
        user_folder = get_user_folder(uid)

        if ext == '.zip':
            handle_zip_file(content, file_name, message)
        else:
            fp = os.path.join(user_folder, file_name)
            with open(fp, 'wb') as f:
                f.write(content)

            is_safe, msg = is_code_safe(fp)
            if not is_safe:
                bot.reply_to(message, f"⚠️ Security: {msg}")
                try:
                    os.remove(fp)
                except:
                    pass
                return

            if ext == '.js':
                handle_js_file(fp, uid, user_folder, file_name, message)
            else:
                handle_py_file(fp, uid, user_folder, file_name, message)

    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"TG error: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)[:200]}")
    except Exception as e:
        logger.error(f"Doc error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)[:200]}")

# ============================================================
# CALLBACKS
# ============================================================
@bot.callback_query_handler(func=lambda c: True)
def handle_callback(call):
    uid = call.from_user.id
    data = call.data
    logger.info(f"CB: {uid} -> {data}")

    if is_user_banned(uid) and data != 'back_to_main':
        bot.answer_callback_query(call.id, "❌ Banned.", show_alert=True)
        return

    if data not in ['check_subscription_status', 'back_to_main', 'manual_install']:
        is_sub, nj = check_mandatory_subscription(uid)
        if not is_sub and uid not in admin_ids:
            msg, markup = create_subscription_check_message(nj)
            bot.answer_callback_query(call.id)
            try:
                bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
            except:
                bot.send_message(call.message.chat.id, msg, reply_markup=markup, parse_mode='Markdown')
            return

    if bot_locked and uid not in admin_ids and data not in ['back_to_main', 'speed', 'stats', 'check_subscription_status', 'manual_install']:
        bot.answer_callback_query(call.id, "⚠️ Locked.", show_alert=True)
        return

    try:
        if data == 'upload':
            bot.answer_callback_query(call.id)
            _upload_logic(call.message)
        elif data == 'check_files':
            _cb_check_files(call)
        elif data.startswith('file_'):
            _cb_file_control(call)
        elif data.startswith('start_'):
            _cb_start(call)
        elif data.startswith('stop_'):
            _cb_stop(call)
        elif data.startswith('restart_'):
            _cb_restart(call)
        elif data.startswith('delete_'):
            _cb_delete(call)
        elif data.startswith('logs_'):
            _cb_logs(call)
        elif data == 'speed':
            bot.answer_callback_query(call.id)
            _speed_logic(call.message)
        elif data == 'back_to_main':
            _cb_back_main(call)
        elif data == 'manual_install':
            bot.answer_callback_query(call.id)
            _manual_install(call.message)
        elif data == 'stats':
            bot.answer_callback_query(call.id)
            _stats_logic(call.message)
        elif data == 'subscription':
            _cb_admin(call, lambda c: bot.send_message(c.message.chat.id, "💳 Subs", reply_markup=create_subscription_menu()))
        elif data == 'broadcast':
            _cb_admin(call, lambda c: _broadcast_admin(c.message))
        elif data == 'lock_bot':
            _cb_admin(call, _cb_do_lock)
        elif data == 'unlock_bot':
            _cb_admin(call, _cb_do_unlock)
        elif data == 'run_all_scripts':
            _cb_admin(call, lambda c: _run_all(c.message))
        elif data == 'admin_panel':
            _cb_admin(call, lambda c: bot.send_message(c.message.chat.id, "👑 Admin", reply_markup=create_admin_panel()))
        elif data == 'add_admin':
            _cb_owner(call, lambda c: _prompt(c, "Add Admin ID", process_add_admin))
        elif data == 'remove_admin':
            _cb_owner(call, lambda c: _prompt(c, "Remove Admin ID", process_remove_admin))
        elif data == 'list_admins':
            _cb_admin(call, _cb_list_admins)
        elif data == 'add_subscription':
            _cb_admin(call, lambda c: _prompt(c, "User ID & days", process_add_sub))
        elif data == 'remove_subscription':
            _cb_admin(call, lambda c: _prompt(c, "User ID", process_remove_sub))
        elif data == 'check_subscription':
            _cb_admin(call, lambda c: _prompt(c, "User ID", process_check_sub))
        elif data == 'user_management':
            _cb_admin(call, lambda c: bot.send_message(c.message.chat.id, "👥 Users", reply_markup=create_user_management_menu()))
        elif data == 'ban_user':
            _cb_admin(call, lambda c: _prompt(c, "User ID and reason", process_ban))
        elif data == 'unban_user':
            _cb_admin(call, lambda c: _prompt(c, "User ID", process_unban))
        elif data == 'user_info':
            _cb_admin(call, lambda c: _prompt(c, "User ID", process_user_info))
        elif data == 'all_users':
            _cb_admin(call, _cb_all_users)
        elif data == 'set_user_limit':
            _cb_admin(call, lambda c: _prompt(c, "User ID & limit", process_set_limit))
        elif data == 'remove_user_limit':
            _cb_admin(call, lambda c: _prompt(c, "User ID", process_remove_limit))
        elif data == 'admin_settings':
            _cb_admin(call, lambda c: bot.send_message(c.message.chat.id, "⚙️ Settings", reply_markup=create_admin_settings_menu()))
        elif data == 'system_info':
            _cb_admin(call, _cb_sys_info)
        elif data == 'bot_performance':
            _cb_admin(call, _cb_performance)
        elif data == 'cleanup_files':
            _cb_admin(call, _cb_cleanup)
        elif data == 'install_logs':
            _cb_admin(call, _cb_logs_view)
        elif data == 'manage_mandatory_channels':
            _cb_admin(call, lambda c: bot.send_message(c.message.chat.id, "📢 Channels", reply_markup=create_mandatory_channels_menu()))
        elif data == 'add_mandatory_channel':
            _cb_admin(call, lambda c: _prompt(c, "Channel ID/username", process_add_channel))
        elif data == 'remove_mandatory_channel':
            _cb_admin(call, _cb_remove_channel_menu)
        elif data == 'list_mandatory_channels':
            _cb_admin(call, _cb_list_channels)
        elif data.startswith('remove_channel_'):
            _cb_admin(call, _cb_do_remove_channel)
        elif data == 'check_subscription_status':
            _cb_check_sub(call)
        elif data.startswith('confirm_broadcast_'):
            _cb_confirm_broadcast(call)
        elif data == 'cancel_broadcast':
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            bot.answer_callback_query(call.id, "Cancelled.")
        else:
            bot.answer_callback_query(call.id, "Unknown.")
    except Exception as e:
        logger.error(f"CB error: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "Error.", show_alert=True)
        except:
            pass

def _cb_admin(call, fn):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    try:
        fn(call)
    except Exception as e:
        logger.error(f"Admin cb: {e}", exc_info=True)

def _cb_owner(call, fn):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner only.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    try:
        fn(call)
    except Exception as e:
        logger.error(f"Owner cb: {e}", exc_info=True)

def _prompt(call, prompt, handler):
    try:
        msg = bot.send_message(call.message.chat.id, prompt + "\n/cancel to cancel")
        bot.register_next_step_handler(msg, handler)
    except:
        pass

def _cb_check_files(call):
    uid = call.from_user.id
    chat = call.message.chat.id
    files = user_files.get(uid, [])
    if not files:
        bot.answer_callback_query(call.id, "⚠️ No files.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    for fn, ft in sorted(files):
        running = is_bot_running(uid, fn)
        icon = "🟢" if running else "🔴"
        markup.add(types.InlineKeyboardButton(f"{icon} {fn} ({ft})", callback_data=f'file_{uid}_{fn}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    try:
        bot.edit_message_text("📂 Files:", chat, call.message.message_id, reply_markup=markup)
    except:
        pass

def _cb_file_control(call):
    try:
        parts = call.data.split('_', 2)
        owner = int(parts[1])
        fn = parts[2]
        uid = call.from_user.id
        if not (uid == owner or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
            return
        files = user_files.get(owner, [])
        info = next((f for f in files if f[0] == fn), None)
        if not info:
            bot.answer_callback_query(call.id, "⚠️ Not found.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        running = is_bot_running(owner, fn)
        status = '🟢 Running' if running else '🔴 Stopped'
        try:
            bot.edit_message_text(
                f"⚙️ `{fn}` ({info[1]}) of `{owner}`\nStatus: {status}",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(owner, fn, running),
                parse_mode='Markdown'
            )
        except:
            pass
    except Exception as e:
        logger.error(f"File ctrl: {e}")

def _cb_start(call):
    try:
        parts = call.data.split('_', 2)
        owner = int(parts[1])
        fn = parts[2]
        uid = call.from_user.id
        if not (uid == owner or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
            return
        files = user_files.get(owner, [])
        info = next((f for f in files if f[0] == fn), None)
        if not info:
            bot.answer_callback_query(call.id, "⚠️ Not found.", show_alert=True)
            return
        folder = get_user_folder(owner)
        fp = os.path.join(folder, fn)
        if not os.path.exists(fp):
            bot.answer_callback_query(call.id, "⚠️ Missing.", show_alert=True)
            remove_user_file_db(owner, fn)
            return
        if is_bot_running(owner, fn):
            bot.answer_callback_query(call.id, "⚠️ Already running.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "⏳ Starting...")
        ft = info[1]
        if ft == 'py':
            threading.Thread(target=run_python_script, args=(fp, owner, folder, fn, call.message), daemon=True).start()
        else:
            threading.Thread(target=run_js_script, args=(fp, owner, folder, fn, call.message), daemon=True).start()
    except Exception as e:
        logger.error(f"Start: {e}")

def _cb_stop(call):
    try:
        parts = call.data.split('_', 2)
        owner = int(parts[1])
        fn = parts[2]
        uid = call.from_user.id
        if not (uid == owner or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "⏳ Stopping...")
        key = f"{owner}_{fn}"
        info = bot_scripts.get(key)
        if info:
            kill_process_tree(info)
            bot_scripts.pop(key, None)
        files = user_files.get(owner, [])
        ftype = next((f[1] for f in files if f[0] == fn), '?')
        try:
            bot.edit_message_text(
                f"⚙️ `{fn}` ({ftype})\nStatus: 🔴 Stopped",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(owner, fn, False),
                parse_mode='Markdown'
            )
        except:
            pass
    except Exception as e:
        logger.error(f"Stop: {e}")

def _cb_restart(call):
    try:
        parts = call.data.split('_', 2)
        owner = int(parts[1])
        fn = parts[2]
        uid = call.from_user.id
        if not (uid == owner or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "⏳ Restarting...")
        folder = get_user_folder(owner)
        fp = os.path.join(folder, fn)
        key = f"{owner}_{fn}"
        if is_bot_running(owner, fn):
            info = bot_scripts.get(key)
            if info:
                kill_process_tree(info)
            bot_scripts.pop(key, None)
            time.sleep(1)
        files = user_files.get(owner, [])
        ft = next((f[1] for f in files if f[0] == fn), 'py')
        if ft == 'py':
            threading.Thread(target=run_python_script, args=(fp, owner, folder, fn, call.message), daemon=True).start()
        else:
            threading.Thread(target=run_js_script, args=(fp, owner, folder, fn, call.message), daemon=True).start()
    except Exception as e:
        logger.error(f"Restart: {e}")

def _cb_delete(call):
    try:
        parts = call.data.split('_', 2)
        owner = int(parts[1])
        fn = parts[2]
        uid = call.from_user.id
        if not (uid == owner or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "🗑️ Deleting...")
        key = f"{owner}_{fn}"
        if is_bot_running(owner, fn):
            info = bot_scripts.get(key)
            if info:
                kill_process_tree(info)
            bot_scripts.pop(key, None)
            time.sleep(0.5)
        folder = get_user_folder(owner)
        for p in [os.path.join(folder, fn), os.path.join(folder, f"{os.path.splitext(fn)[0]}.log")]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass
        remove_user_file_db(owner, fn)
        try:
            bot.edit_message_text(f"🗑️ `{fn}` deleted!", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        except:
            pass
    except Exception as e:
        logger.error(f"Delete: {e}")

def _cb_logs(call):
    try:
        parts = call.data.split('_', 2)
        owner = int(parts[1])
        fn = parts[2]
        uid = call.from_user.id
        if not (uid == owner or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
            return
        folder = get_user_folder(owner)
        lp = os.path.join(folder, f"{os.path.splitext(fn)[0]}.log")
        if not os.path.exists(lp):
            bot.answer_callback_query(call.id, "⚠️ No logs.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        try:
            with open(lp, 'r', encoding='utf-8', errors='ignore') as f:
                c = f.read()
            if len(c) > 4000:
                c = "...(truncated)\n" + c[-4000:]
            if not c.strip():
                c = "(empty)"
            bot.send_message(call.message.chat.id, f"📜 `{fn}`:\n```\n{c}\n```", parse_mode='Markdown')
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Log error: {e}")
    except Exception as e:
        logger.error(f"Logs: {e}")

def _cb_back_main(call):
    uid = call.from_user.id
    if is_user_banned(uid):
        bot.answer_callback_query(call.id, "❌ Banned.", show_alert=True)
        return
    is_sub, nj = check_mandatory_subscription(uid)
    if not is_sub and uid not in admin_ids:
        msg, markup = create_subscription_check_message(nj)
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        except:
            pass
        return
    try:
        limit = get_user_file_limit(uid)
        count = get_user_file_count(uid)
        limit_str = str(limit) if limit != float('inf') else "Unlimited"
        if uid == OWNER_ID:
            status = "👑 Owner"
        elif uid in admin_ids:
            status = "🛡️ Admin"
        elif uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now():
            status = "⭐ Premium"
        else:
            status = "🆓 Free"
        text = (f"〽️ Welcome!\n\n🆔 `{uid}`\n🔰 {status}\n📁 {count}/{limit_str}\n\n👇 Use buttons.")
        bot.answer_callback_query(call.id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=create_main_menu_inline(uid), parse_mode='Markdown')
    except:
        pass

def _cb_do_lock(call):
    global bot_locked
    bot_locked = True
    bot.send_message(call.message.chat.id, "🔒 Locked.")

def _cb_do_unlock(call):
    global bot_locked
    bot_locked = False
    bot.send_message(call.message.chat.id, "🔓 Unlocked.")

def _cb_list_admins(call):
    lines = "\n".join(f"- `{a}` {'(Owner)' if a == OWNER_ID else ''}" for a in sorted(admin_ids))
    bot.send_message(call.message.chat.id, f"👑 Admins:\n{lines or '(none)'}", parse_mode='Markdown')

def _cb_all_users(call):
    if not active_users:
        bot.send_message(call.message.chat.id, "No users.")
        return
    users = sorted(active_users)
    text = "👥 Users:\n"
    for i, u in enumerate(users[:50], 1):
        icon = "👑" if u == OWNER_ID else "🛡️" if u in admin_ids else "🚫" if u in banned_users else "⭐" if u in user_subscriptions else "🆓"
        text += f"{i}. `{u}` {icon}\n"
    if len(users) > 50:
        text += f"\n...and {len(users) - 50} more"
    bot.send_message(call.message.chat.id, text, parse_mode='Markdown')

def _cb_sys_info(call):
    import platform
    text = f"📊 System:\n• Python: {platform.python_version()}\n• OS: {platform.system()}\n"
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        text += f"• CPU: {cpu}%\n• RAM: {mem.percent}%\n• Disk: {disk.percent}%\n"
    except:
        pass
    text += f"\n🤖 Bot:\n• Users: {len(active_users)}\n• Scripts: {len(bot_scripts)}\n• Status: {'🔒' if bot_locked else '🔓'}"
    bot.send_message(call.message.chat.id, text)

def _cb_performance(call):
    text = f"📈 Performance:\n• Running: {len(bot_scripts)}\n• Files: {sum(len(f) for f in user_files.values())}\n"
    try:
        proc = psutil.Process()
        mem = proc.memory_info().rss / 1024 / 1024
        text += f"• Bot RAM: {mem:.1f} MB"
    except:
        pass
    bot.send_message(call.message.chat.id, text)

def _cb_cleanup(call):
    cleaned_dirs = 0
    cleaned_files = 0
    try:
        for d in os.listdir(UPLOAD_BOTS_DIR):
            p = os.path.join(UPLOAD_BOTS_DIR, d)
            if os.path.isdir(p):
                if not os.listdir(p):
                    try:
                        os.rmdir(p)
                        cleaned_dirs += 1
                    except:
                        pass
                else:
                    for fn in os.listdir(p):
                        if fn.endswith('.log'):
                            fp = os.path.join(p, fn)
                            try:
                                if time.time() - os.path.getmtime(fp) > 7 * 24 * 3600:
                                    os.remove(fp)
                                    cleaned_files += 1
                            except:
                                pass
        bot.send_message(call.message.chat.id, f"🧹 Cleaned: {cleaned_dirs} dirs, {cleaned_files} logs")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ {e}")

def _cb_logs_view(call):
    try:
        logs = db_execute('SELECT user_id, module_name, package_name, status FROM install_logs ORDER BY install_date DESC LIMIT 20', fetch=True) or []
        if not logs:
            bot.send_message(call.message.chat.id, "📋 No logs.")
            return
        text = "📋 Install Logs:\n\n"
        for u, mn, pn, st in logs:
            icon = "✅" if st == "success" else "❌"
            text += f"{icon} `{u}`: {mn} -> {pn}\n"
        bot.send_message(call.message.chat.id, text, parse_mode='Markdown')
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ {e}")

def _cb_remove_channel_menu(call):
    if not mandatory_channels:
        bot.send_message(call.message.chat.id, "❌ No channels.")
        return
    markup = types.InlineKeyboardMarkup()
    for cid, cinfo in mandatory_channels.items():
        markup.add(types.InlineKeyboardButton(f"🗑️ {cinfo.get('name', 'Unknown')}", callback_data=f'remove_channel_{cid}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='manage_mandatory_channels'))
    bot.send_message(call.message.chat.id, "Choose to delete:", reply_markup=markup)

def _cb_list_channels(call):
    if not mandatory_channels:
        bot.send_message(call.message.chat.id, "📢 No channels.")
        return
    text = "📢 Channels:\n\n"
    for cid, cinfo in mandatory_channels.items():
        text += f"• **{cinfo.get('name', 'Unknown')}**\n  {cinfo.get('username', cid)}\n\n"
    bot.send_message(call.message.chat.id, text, parse_mode='Markdown')

def _cb_do_remove_channel(call):
    cid = call.data.replace('remove_channel_', '')
    if cid in mandatory_channels:
        name = mandatory_channels[cid].get('name', 'Unknown')
        remove_mandatory_channel_db(cid)
        bot.send_message(call.message.chat.id, f"✅ Removed: {name}")

def _cb_check_sub(call):
    uid = call.from_user.id
    is_sub, nj = check_mandatory_subscription(uid)
    if is_sub or uid in admin_ids:
        bot.answer_callback_query(call.id, "✅ Verified!", show_alert=True)
        try:
            _welcome(call.message)
        except:
            _cb_back_main(call)
    else:
        bot.answer_callback_query(call.id, "❌ Not verified!", show_alert=True)
        msg, markup = create_subscription_check_message(nj)
        try:
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        except:
            pass

def _cb_confirm_broadcast(call):
    uid = call.from_user.id
    if uid not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    try:
        orig = call.message.reply_to_message
        if not orig:
            raise ValueError("No original")
        text = orig.text
        if not text:
            raise ValueError("No text")
        bot.answer_callback_query(call.id, "🚀 Sending...")
        bot.edit_message_text(f"📢 Broadcasting to {len(active_users)}...", call.message.chat.id, call.message.message_id)
        threading.Thread(target=_do_broadcast, args=(text, call.message.chat.id), daemon=True).start()
    except Exception as e:
        logger.error(f"BC confirm: {e}")
        try:
            bot.edit_message_text(f"❌ {e}", call.message.chat.id, call.message.message_id)
        except:
            pass

def _do_broadcast(text, chat_id):
    sent = failed = blocked = 0
    for u in list(active_users):
        try:
            bot.send_message(u, text, parse_mode='Markdown')
            sent += 1
        except telebot.apihelper.ApiTelegramException as e:
            err = str(e).lower()
            if any(s in err for s in ["blocked", "deactivated", "not found", "kicked"]):
                blocked += 1
            elif "flood" in err or "too many" in err:
                time.sleep(5)
                try:
                    bot.send_message(u, text, parse_mode='Markdown')
                    sent += 1
                except:
                    failed += 1
            else:
                failed += 1
        except:
            failed += 1
        time.sleep(0.05)
    try:
        bot.send_message(chat_id, f"📢 Done!\n✅ {sent}\n❌ {failed}\n🚫 {blocked}")
    except:
        pass

def _broadcast_admin(m):
    uid = m.from_user.id
    if uid not in admin_ids:
        bot.reply_to(m, "⚠️ Admin only.")
        return
    msg = bot.reply_to(m, "📢 Send broadcast message.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    uid = message.from_user.id
    if uid not in admin_ids:
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    text = message.text
    if not text:
        bot.reply_to(message, "⚠️ Empty.")
        return
    count = len(active_users)
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Send", callback_data=f"confirm_broadcast_{message.message_id}"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")
    )
    bot.reply_to(message, f"⚠️ Send to {count} users?\n\n```\n{text[:400]}\n```", reply_markup=markup, parse_mode='Markdown')

# Next-step handlers
def process_add_admin(m):
    if m.from_user.id != OWNER_ID: return
    if m.text.lower() == '/cancel':
        bot.reply_to(m, "Cancelled.")
        return
    try:
        nid = int(m.text.strip())
        if nid <= 0 or nid in admin_ids:
            bot.reply_to(m, "❌ Invalid/already admin.")
            return
        add_admin_db(nid, OWNER_ID)
        bot.reply_to(m, f"✅ Added admin: `{nid}`", parse_mode='Markdown')
    except:
        bot.reply_to(m, "❌ Invalid ID.")

def process_remove_admin(m):
    if m.from_user.id != OWNER_ID: return
    if m.text.lower() == '/cancel':
        return
    try:
        nid = int(m.text.strip())
        if nid == OWNER_ID:
            bot.reply_to(m, "Cannot remove Owner.")
            return
        if remove_admin_db(nid):
            bot.reply_to(m, f"✅ Removed: `{nid}`", parse_mode='Markdown')
        else:
            bot.reply_to(m, "❌ Not admin.")
    except:
        bot.reply_to(m, "❌ Invalid ID.")

def process_add_sub(m):
    if m.from_user.id not in admin_ids: return
    if m.text.lower() == '/cancel': return
    try:
        parts = m.text.split()
        if len(parts) != 2: raise ValueError()
        uid = int(parts[0]); days = int(parts[1])
        if uid <= 0 or days <= 0: raise ValueError()
        cur = user_subscriptions.get(uid, {}).get('expiry')
        start = datetime.now()
        if cur and cur > start: start = cur
        exp = start + timedelta(days=days)
        save_subscription(uid, exp)
        bot.reply_to(m, f"✅ Sub `{uid}`: {days} days\n{exp:%Y-%m-%d}", parse_mode='Markdown')
    except:
        bot.reply_to(m, "❌ Format: `user_id days`")

def process_remove_sub(m):
    if m.from_user.id not in admin_ids: return
    if m.text.lower() == '/cancel': return
    try:
        uid = int(m.text.strip())
        remove_subscription_db(uid)
        bot.reply_to(m, f"✅ Removed: `{uid}`", parse_mode='Markdown')
    except:
        bot.reply_to(m, "❌ Invalid.")

def process_check_sub(m):
    if m.from_user.id not in admin_ids: return
    if m.text.lower() == '/cancel': return
    try:
        uid = int(m.text.strip())
        if uid in user_subscriptions:
            exp = user_subscriptions[uid].get('expiry')
            if exp and exp > datetime.now():
                bot.reply_to(m, f"✅ `{uid}`: {exp:%Y-%m-%d} ({(exp-datetime.now()).days} days)", parse_mode='Markdown')
            else:
                bot.reply_to(m, "⚠️ Expired.")
        else:
            bot.reply_to(m, "No sub.")
    except:
        bot.reply_to(m, "❌ Invalid.")

def process_ban(m):
    if m.from_user.id not in admin_ids: return
    if m.text.lower() == '/cancel': return
    try:
        parts = m.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(m, "Format: `user_id reason`")
            return
        uid = int(parts[0]); reason = parts[1]
        if uid == OWNER_ID or uid in admin_ids:
            bot.reply_to(m, "Cannot ban Owner/Admin.")
            return
        ban_user_db(uid, reason, m.from_user.id)
        bot.reply_to(m, f"✅ Banned: `{uid}`", parse_mode='Markdown')
    except:
        bot.reply_to(m, "❌ Invalid.")

def process_unban(m):
    if m.from_user.id not in admin_ids: return
    if m.text.lower() == '/cancel': return
    try:
        uid = int(m.text.strip())
        unban_user_db(uid)
        bot.reply_to(m, f"✅ Unbanned: `{uid}`", parse_mode='Markdown')
    except:
        bot.reply_to(m, "❌ Invalid.")

def process_user_info(m):
    if m.from_user.id not in admin_ids: return
    if m.text.lower() == '/cancel': return
    try:
        uid = int(m.text.strip())
        text = f"👤 `{uid}`\n"
        if uid == OWNER_ID: text += "👑 Owner\n"
        elif uid in admin_ids: text += "🛡️ Admin\n"
        elif uid in banned_users: text += "🚫 Banned\n"
        elif uid in user_subscriptions: text += "⭐ Premium\n"
        else: text += "🆓 Free\n"
        text += f"📁 Files: {get_user_file_count(uid)}\n⚙️ Limit: {get_user_file_limit(uid)}"
        bot.reply_to(m, text, parse_mode='Markdown')
    except:
        bot.reply_to(m, "❌ Invalid.")

def process_set_limit(m):
    if m.from_user.id not in admin_ids: return
    if m.text.lower() == '/cancel': return
    try:
        parts = m.text.split()
        if len(parts) != 2: raise ValueError()
        uid = int(parts[0]); lim = int(parts[1])
        set_user_limit_db(uid, lim, m.from_user.id)
        bot.reply_to(m, f"✅ Limit {lim} for `{uid}`", parse_mode='Markdown')
    except:
        bot.reply_to(m, "❌ Format: `user_id limit`")

def process_remove_limit(m):
    if m.from_user.id not in admin_ids: return
    if m.text.lower() == '/cancel': return
    try:
        uid = int(m.text.strip())
        remove_user_limit_db(uid)
        bot.reply_to(m, f"✅ Removed limit: `{uid}`", parse_mode='Markdown')
    except:
        bot.reply_to(m, "❌ Invalid.")

def process_add_channel(m):
    if m.from_user.id not in admin_ids: return
    if m.text and m.text.lower() == '/cancel': return
    try:
        cid_input = m.text.strip()
        chat = bot.get_chat(cid_input)
        cid = str(chat.id)
        cu = f"@{chat.username}" if chat.username else ""
        cn = chat.title
        try:
            bm = bot.get_chat_member(cid, bot.get_me().id)
            if bm.status not in ['administrator', 'creator']:
                bot.reply_to(m, "❌ Bot not admin in channel!")
                return
        except:
            bot.reply_to(m, "❌ Cannot access. Make bot admin.")
            return
        save_mandatory_channel(cid, cu, cn, m.from_user.id)
        bot.reply_to(m, f"✅ Added: **{cn}**", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(m, f"❌ {str(e)}")

# ============================================================
# CLEANUP + STARTUP
# ============================================================
def cleanup_all():
    logger.warning("Shutdown - killing scripts...")
    for key in list(bot_scripts.keys()):
        try:
            kill_process_tree(bot_scripts[key])
        except:
            pass

atexit.register(cleanup_all)

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("HOSTING BOT STARTING")
    logger.info(f"Owner: {OWNER_ID} | Admins: {len(admin_ids)}")
    logger.info(f"Channel: @{UPDATE_CHANNEL}")
    logger.info("=" * 50)

    keep_alive()

    while True:
        try:
            logger.info("Starting polling...")
            bot.infinity_polling(
                logger_level=logging.INFO,
                timeout=60,
                long_polling_timeout=30,
                none_stop=True
            )
        except KeyboardInterrupt:
            logger.info("Stopped.")
            break
        except Exception as e:
            logger.error(f"Polling error: {e}")
            logger.info("Restarting in 5s...")
            time.sleep(5)
