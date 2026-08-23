"""
客户端配置模块
存储 MySQL 连接参数、本地数据库路径等配置

所有配置从 config.ini 读取（通过 utils/app_config.py 的 load_xxx_config 函数）。
config.ini 位于 exe 同目录（打包模式）或项目根目录（调试模式）。
"""
import os
import sys

try:
    from utils.credential_manager import _get_password_raw as _get_db_pw, get_ftp_password as _get_ftp_pw
except Exception:
    _get_db_pw = None
    _get_ftp_pw = None


def _resolve_db_password():
    if _get_db_pw is not None:
        return _get_db_pw() or ""
    try:
        from utils.credential_manager import _get_password_raw
        return _get_password_raw() or ""
    except Exception:
        return ""


def _resolve_ftp_password():
    if _get_ftp_pw is not None:
        return _get_ftp_pw() or ""
    try:
        from utils.credential_manager import get_ftp_password
        return get_ftp_password() or ""
    except Exception:
        return ""

try:
    from utils.app_config import load_mysql_config
    _MYSQL_INI = load_mysql_config()
    MYSQL_HOST = _MYSQL_INI.get("mysql_host") or "localhost"
    MYSQL_PORT = int(_MYSQL_INI.get("mysql_port") or "3306")
    MYSQL_USER = _MYSQL_INI.get("mysql_user") or "root"
    MYSQL_PASSWORD = _resolve_db_password()
    MYSQL_DATABASE = _MYSQL_INI.get("mysql_database") or "mms"
    MYSQL_CHARSET = _MYSQL_INI.get("mysql_charset") or "utf8mb4"
except Exception:
    MYSQL_HOST = "localhost"
    MYSQL_PORT = 3306
    MYSQL_USER = "root"
    MYSQL_PASSWORD = _resolve_db_password()
    MYSQL_DATABASE = "mms"
    MYSQL_CHARSET = "utf8mb4"

# ---------- 图片存储路径 ----------
_CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    _DATA_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _DATA_DIR = _CLIENT_DIR

LOCAL_DB_PATH = os.path.join(_DATA_DIR, "local_cache.db")
DEFAULT_WORKSHOP = "默认车间"


def get_local_db_path(workshop: str = None) -> str:
    """根据车间名返回对应的本地数据库路径。
    workshop=None 时从 config.ini [workshops] 读取 current_workshop。
    config.ini 中是什么车间就用什么车间，不写"默认车间"。
    仅当 config.ini 完全缺失或车间名为空时才用 DEFAULT_WORKSHOP 兜底。
    """
    if workshop is None:
        try:
            from utils.app_config import load_workshop_config
            cfg = load_workshop_config()
            workshop = cfg.get("current_workshop", "")
        except Exception:
            workshop = ""
    if not workshop:
        workshop = DEFAULT_WORKSHOP
    safe_name = os.path.basename(workshop.replace("/", "_").replace("\\", "_"))
    return os.path.join(_DATA_DIR, f"local_cache_{safe_name}.db")

# ---------- 数据库表名常量 ----------
TABLE_MATERIALS       = "MMS_库存明细"
TABLE_BORROW_RECORDS  = "MMS_领用记录"
TABLE_FIXED_ASSETS    = "MMS_固定资产"
TABLE_CONFIG_ITEMS    = "MMS_系统配置"
TABLE_USERS           = "MMS_用户台账"
TABLE_EMPLOYEE_RECORDS= "MMS_员工台账"

# ---------- 同步配置 ----------
SYNC_INTERVAL_SECONDS = 30
SYNC_RETRY_MAX = 3
SYNC_BATCH_SIZE = 50
FULL_SYNC_INTERVAL_MINUTES = 30

# ---------- 网络检测配置 ----------
NETWORK_CHECK_INTERVAL_SECONDS = 2
NETWORK_CHECK_TIMEOUT_SECONDS = 1

# ---------- 预警配置 ----------
STALE_DAYS_THRESHOLD = 90
CHECK_EXPIRE_DAYS = 7

# ---------- 界面配置 ----------
WINDOW_MIN_WIDTH = 1200
WINDOW_MIN_HEIGHT = 700

# ---------- 运行模式 ----------
try:
    from utils.app_config import load_app_config
    _APP_INI = load_app_config()
    APP_MODE = _APP_INI.get("app_mode", "online")
    LOG_LEVEL = _APP_INI.get("log_level", "INFO")
except Exception:
    APP_MODE = "online"
    LOG_LEVEL = "INFO"

# ---------- Web 查询服务配置 ----------
try:
    from utils.app_config import load_web_query_config
    _WEB_INI = load_web_query_config()
    WEB_QUERY_ENABLED = _WEB_INI.get("web_query_enabled", "0") == "1"
    WEB_QUERY_HOST = _WEB_INI.get("web_query_host", "localhost")
    WEB_QUERY_PORT = int(_WEB_INI.get("web_query_port", "8000"))
    WEB_QUERY_API_BASE = _WEB_INI.get("web_query_api_base", "/api")
    WEB_QUERY_API_KEY = _WEB_INI.get("web_query_api_key", "")
    WEB_QUERY_TIMEOUT = int(_WEB_INI.get("web_query_timeout", "10"))
    WEB_QUERY_USE_HTTPS = _WEB_INI.get("web_query_use_https", "0") == "1"
except Exception:
    WEB_QUERY_ENABLED = False
    WEB_QUERY_HOST = "localhost"
    WEB_QUERY_PORT = 8000
    WEB_QUERY_API_BASE = "/api"
    WEB_QUERY_API_KEY = ""
    WEB_QUERY_TIMEOUT = 10
    WEB_QUERY_USE_HTTPS = False

# ---------- 硬件模块配置（指纹 / NFC） ----------
try:
    from utils.app_config import load_serial_config
    _SERIAL_INI = load_serial_config()
    FINGERPRINT_ENABLED = _SERIAL_INI.get("fingerprint_enabled", "0") == "1"
    NFC_ENABLED = _SERIAL_INI.get("nfc_enabled", "0") == "1"
    FINGERPRINT_DEVICE = _SERIAL_INI.get("fingerprint_device", "COM3")
    NFC_DEVICE = _SERIAL_INI.get("nfc_device", "COM4")
    FINGERPRINT_BAUD_RATE = int(_SERIAL_INI.get("fingerprint_baud_rate", "9600"))
    NFC_BAUD_RATE = int(_SERIAL_INI.get("nfc_baud_rate", "9600"))
except Exception:
    FINGERPRINT_ENABLED = False
    NFC_ENABLED = False
    FINGERPRINT_DEVICE = "COM3"
    NFC_DEVICE = "COM4"
    FINGERPRINT_BAUD_RATE = 9600
    NFC_BAUD_RATE = 9600

# ---------- 图片存储路径 ----------
if getattr(sys, "frozen", False):
    _internal_img = os.path.join(_DATA_DIR, "_internal", "Image")
    IMAGES_DIR = _internal_img if os.path.isdir(_internal_img) else os.path.join(_DATA_DIR, "Image")
else:
    IMAGES_DIR = os.path.join(_DATA_DIR, "Image")
REAL_IMAGES_DIR = os.path.join(IMAGES_DIR, "real")
LOCATION_IMAGES_DIR = os.path.join(IMAGES_DIR, "location")

# ---------- 版本信息 ----------
APP_VERSION = "v4305"

# ---------- 文件路径常量（集中管理，避免散落硬编码）----------
LOGIN_COMPLETED_FILE = ".login_completed.json"
REMEMBER_LOGIN_FILE = ".remember_login.json"
AUTO_EXPORT_MARKER_FILE = ".auto_export.json"

SYNC_COOLDOWN_SECONDS = 10
NETWORK_STABLE_THRESHOLD = 2