"""Cython 编译版 - 凭证管理器

优先级：
  读取: config.ini(加密) → keyring → fallback(.mms_creds.json) → env
  写入: config.ini(加密) + keyring + fallback 三路同步
"""
from __future__ import print_function
import os
import sys
import hashlib
import hmac
import base64
import json
import time

import configparser

try:
    from logger import get_logger
except Exception:
    import logging
    get_logger = logging.getLogger

_log = get_logger(__name__)

try:
    import keyring
    KEYRING_OK = True
except ImportError:
    keyring = None
    KEYRING_OK = False
    _log.info("keyring 未安装，使用加密文件后备")

SVC_NAME = "mms"
USER_NAME = "db_user"
FTP_USER_NAME = "ftp_user"
SEED_USER_NAME = "seed_user"

INI_DB_FIELD = "mysql_password_enc"
INI_FTP_FIELD = "ftp_pass_enc"

try:
    from .app_config import get_config_path as _get_config_path_func
except Exception:
    _get_config_path_func = None


def _get_ini_path() -> str:
    if _get_config_path_func:
        return _get_config_path_func()
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "config.ini")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config.ini")


_INI_PATH = _get_ini_path()


def _ini_get_encrypted(section: str, field: str) -> str:
    if not os.path.isfile(_INI_PATH):
        return ""
    try:
        cp = configparser.ConfigParser()
        cp.read(_INI_PATH, encoding="utf-8-sig")
        if not cp.has_section(section) or not cp.has_option(section, field):
            return ""
        blob = cp.get(section, field).strip()
        if not blob:
            return ""
        return _decrypt(blob)
    except (configparser.Error, Exception) as e:
        _log.warning("config.ini 读取 %s/%s 失败: %s", section, field, e)
        return ""


def _ini_set_encrypted(section: str, field: str, pw: str) -> bool:
    try:
        os.makedirs(os.path.dirname(_INI_PATH), exist_ok=True)
        cp = configparser.ConfigParser()
        cp.read(_INI_PATH, encoding="utf-8-sig")
        if not cp.has_section(section):
            cp.add_section(section)
        cp.set(section, field, _encrypt(pw))
        with open(_INI_PATH, "w", encoding="utf-8", newline="") as f:
            cp.write(f)
        _log.info("加密密码已写入 config.ini [%s]%s", section, field)
        return True
    except Exception as e:
        _log.error("config.ini 写入 %s/%s 失败: %s", section, field, e)
        return False


_EXE_DIR = (
    os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
_APPDATA_MMS = os.path.join(os.environ.get("APPDATA", ""), "mms") if os.environ.get("APPDATA") else ""
_HOME_DIR = os.path.expanduser("~")

_FALLBACK_CANDIDATES = []
for _d in [_APPDATA_MMS, _HOME_DIR, _EXE_DIR]:
    if _d and _d not in _FALLBACK_CANDIDATES:
        _FALLBACK_CANDIDATES.append(os.path.join(_d, ".mms_creds.json"))

_ACTIVE_FALLBACK_FILE = ""


def _fallback_paths():
    return list(_FALLBACK_CANDIDATES)


def _active_fallback_file() -> str:
    return _ACTIVE_FALLBACK_FILE or (_FALLBACK_CANDIDATES[0] if _FALLBACK_CANDIDATES else "")


def _load_fallback_from(path: str) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _log.debug("读取 fallback 失败 (%s): %s", path, e)
        return {}


def _save_fallback_to(credentials: dict, path: str) -> bool:
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(credentials, f)
        _log.info("加密凭证文件已写入: %s", path)
        return True
    except Exception as e:
        _log.warning("fallback 写入失败 (%s): %s", path, e)
        return False


def _load_fallback() -> dict:
    for path in _fallback_paths():
        store = _load_fallback_from(path)
        if store:
            global _ACTIVE_FALLBACK_FILE
            if _ACTIVE_FALLBACK_FILE != path:
                _ACTIVE_FALLBACK_FILE = path
            return store
    return {}


def _save_fallback(credentials: dict) -> bool:
    for path in _fallback_paths():
        if _save_fallback_to(credentials, path):
            global _ACTIVE_FALLBACK_FILE
            _ACTIVE_FALLBACK_FILE = path
            return True
    _log.error("所有 fallback 路径均写入失败: %s", _fallback_paths())
    return False


# ---------- 用户种子（keyring 存储） ----------

def get_user_seed() -> str:
    if not KEYRING_OK:
        return ""
    try:
        seed = keyring.get_password(SVC_NAME, SEED_USER_NAME)
        return seed or ""
    except Exception as e:
        _log.warning("读取用户种子失败: %s", e)
        return ""


def set_user_seed(seed: str) -> bool:
    if not KEYRING_OK:
        return False
    if not seed:
        _log.warning("set_user_seed: 空种子，跳过")
        return False
    try:
        keyring.set_password(SVC_NAME, SEED_USER_NAME, seed)
        verify = keyring.get_password(SVC_NAME, SEED_USER_NAME)
        if verify == seed:
            _log.info("用户种子已写入系统密钥库（已验证）")
            return True
        _log.warning("用户种子写入后回读不一致")
        return False
    except Exception as e:
        _log.error("用户种子写入失败: %s", e)
        return False


def has_user_seed() -> bool:
    return bool(get_user_seed())


def rekey_config_passwords(seed: str) -> bool:
    if not seed or not set_user_seed(seed):
        _log.error("rekey_config_passwords: 无法写入用户种子")
        return False

    results = {}

    db_pw = ""
    if os.path.isfile(_INI_PATH):
        try:
            cp = configparser.ConfigParser()
            cp.read(_INI_PATH, encoding="utf-8-sig")
            if cp.has_section("mysql") and cp.has_option("mysql", INI_DB_FIELD):
                blob = cp.get("mysql", INI_DB_FIELD).strip()
                if blob:
                    db_pw = _decrypt(blob)
        except Exception as e:
            _log.warning("rekey: 读取 MySQL 密文失败: %s", e)

    ftp_pw = ""
    if os.path.isfile(_INI_PATH):
        try:
            cp = configparser.ConfigParser()
            cp.read(_INI_PATH, encoding="utf-8-sig")
            if cp.has_section("update") and cp.has_option("update", INI_FTP_FIELD):
                blob = cp.get("update", INI_FTP_FIELD).strip()
                if blob:
                    ftp_pw = _decrypt(blob)
        except Exception as e:
            _log.warning("rekey: 读取 FTP 密文失败: %s", e)

    if db_pw:
        results["mysql"] = _ini_set_encrypted("mysql", INI_DB_FIELD, db_pw)
    if ftp_pw:
        results["ftp"] = _ini_set_encrypted("update", INI_FTP_FIELD, ftp_pw)

    for path in _fallback_paths():
        if not os.path.isfile(path):
            continue
        store = _load_fallback_from(path)
        if not store:
            continue
        changed = False
        for user, blob in list(store.items()):
            pw = _decrypt(blob)
            if pw:
                store[user] = _encrypt(pw)
                changed = True
        if changed:
            _save_fallback_to(store, path)

    ok = all(results.values()) if results else True
    _log.info("密码重加密完成: %s", results)
    return ok


def _machine_key(include_seed: bool = True) -> bytes:
    parts = [os.environ.get("COMPUTERNAME", "unknown")]
    try:
        import uuid
        parts.append(str(uuid.getnode()))
    except Exception:
        pass
    if include_seed:
        try:
            seed = get_user_seed()
            if seed:
                parts.append(seed)
        except Exception:
            pass
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).digest()


def _crypt(data: bytes, key: bytes) -> bytes:
    pad = (16 - len(data) % 16) % 16
    padded = data + (b"\x00" * pad)
    return bytes(a ^ b for a, b in zip(padded, (key * ((len(padded) // 16) + 1))[:len(padded)]))


def _encrypt(text: str) -> str:
    data = text.encode("utf-8")
    cipher = _crypt(data, _machine_key())
    mac = hmac.new(_machine_key(), cipher, hashlib.sha256).digest()[:8]
    return base64.b64encode(mac + cipher).decode("ascii")


def _decrypt(blob: str) -> str:
    try:
        raw = base64.b64decode(blob)
    except Exception:
        return ""
    mac, cipher = raw[:8], raw[8:]

    key = _machine_key(include_seed=True)
    mac_calc = hmac.new(key, cipher, hashlib.sha256).digest()[:8]
    if hmac.compare_digest(mac, mac_calc):
        plaintext = _crypt(cipher, key).rstrip(b"\x00")
        return plaintext.decode("utf-8", errors="replace")

    old_key = _machine_key(include_seed=False)
    mac_calc_old = hmac.new(old_key, cipher, hashlib.sha256).digest()[:8]
    if hmac.compare_digest(mac, mac_calc_old):
        plaintext = _crypt(cipher, old_key).rstrip(b"\x00")
        return plaintext.decode("utf-8", errors="replace")

    _log.error("凭证文件 MAC 校验失败，文件可能已被篡改")
    return ""


def _fallback_get(user: str) -> str:
    store = _load_fallback()
    blob = store.get(user, "")
    if not blob:
        return ""
    return _decrypt(blob)


def _fallback_set(user: str, pw: str) -> bool:
    try:
        store = _load_fallback()
        store[user] = _encrypt(pw)
        return _save_fallback(store)
    except Exception as e:
        _log.error("加密文件后备保存失败: %s", e)
        return False


def _fallback_has(user: str) -> bool:
    return bool(_fallback_get(user))


def get_password(source=None):
    if source != "fallback" and source != "keyring":
        ini_pw = _ini_get_encrypted("mysql", INI_DB_FIELD)
        if ini_pw:
            _log.info("MySQL 密码从 config.ini 读取（已解密）")
            return ini_pw, "ini"
    if source != "fallback" and KEYRING_OK:
        try:
            pw = keyring.get_password(SVC_NAME, USER_NAME)
            if pw:
                _log.info("MySQL 密码从系统密钥库读取")
                return pw, "keyring"
        except Exception as e:
            _log.warning("keyring 获取 MySQL 密码失败: %s", e)
    if source != "keyring":
        fb_pw = _fallback_get(USER_NAME)
        if fb_pw:
            _log.info("MySQL 密码从加密文件后备读取: %s", _active_fallback_file())
            return fb_pw, "fallback"
    if source != "keyring" and source != "fallback":
        env_pw = os.getenv("MYSQL_PASSWORD", "")
        if env_pw:
            _log.warning("MySQL 密码从环境变量读取（明文残留）")
            return env_pw, "env"
    return "", ""


def _get_password_raw() -> str:
    return get_password()[0]


def set_password(pw: str):
    result = {"ok": False, "store": "error", "verified": False}
    if not pw:
        _log.warning("set_password: 空密码，跳过")
        return result
    _log.info("保存 MySQL 密码 (长度=%d)", len(pw))
    ini_ok = _ini_set_encrypted("mysql", INI_DB_FIELD, pw)
    if not ini_ok:
        _log.error("密码写入 config.ini 失败")
        return result
    kr_ok = False
    if KEYRING_OK:
        try:
            keyring.set_password(SVC_NAME, USER_NAME, pw)
            verify = keyring.get_password(SVC_NAME, USER_NAME)
            if verify == pw:
                kr_ok = True
                _log.info("MySQL 密码已同步到 keyring（已验证）")
            else:
                _log.warning("keyring 写入后回读不一致")
        except Exception as e:
            _log.warning("keyring 写入失败: %s", e)
    fb_ok = _fallback_set(USER_NAME, pw)
    if kr_ok and fb_ok:
        result = {"ok": True, "store": "ini+keyring+fallback", "verified": True}
    elif kr_ok:
        result = {"ok": True, "store": "ini+keyring", "verified": True}
    elif fb_ok:
        result = {"ok": True, "store": "ini+fallback", "verified": False}
    else:
        result = {"ok": True, "store": "ini", "verified": False}
    _log.info("MySQL 密码保存结果: %s", result)
    return result


def has_password() -> bool:
    return bool(get_password()[0])


def get_ftp_password() -> str:
    pw = _ini_get_encrypted("update", INI_FTP_FIELD)
    if pw:
        _log.info("FTP 密码从 config.ini 读取（已解密）")
        return pw
    if KEYRING_OK:
        try:
            pw = keyring.get_password(SVC_NAME, FTP_USER_NAME)
            if pw:
                _log.info("FTP 密码从系统密钥库读取")
                return pw
        except Exception as e:
            _log.warning("keyring 获取 FTP 密码失败: %s", e)
    fb_pw = _fallback_get(FTP_USER_NAME)
    if fb_pw:
        _log.info("FTP 密码从加密文件后备读取")
        return fb_pw
    return ""


def set_ftp_password(pw: str):
    result = {"ok": False, "store": "error", "verified": False}
    if not pw:
        _log.warning("set_ftp_password: 空密码，跳过")
        return result
    _log.info("保存 FTP 密码 (长度=%d)", len(pw))
    ini_ok = _ini_set_encrypted("update", INI_FTP_FIELD, pw)
    if not ini_ok:
        return result
    kr_ok = False
    if KEYRING_OK:
        try:
            keyring.set_password(SVC_NAME, FTP_USER_NAME, pw)
            verify = keyring.get_password(SVC_NAME, FTP_USER_NAME)
            if verify == pw:
                kr_ok = True
        except Exception as e:
            _log.warning("FTP keyring 写入失败: %s", e)
    fb_ok = _fallback_set(FTP_USER_NAME, pw)
    if kr_ok and fb_ok:
        result = {"ok": True, "store": "ini+keyring+fallback", "verified": True}
    elif kr_ok:
        result = {"ok": True, "store": "ini+keyring", "verified": True}
    elif fb_ok:
        result = {"ok": True, "store": "ini+fallback", "verified": False}
    else:
        result = {"ok": True, "store": "ini", "verified": False}
    return result


def diagnose() -> dict:
    info = {
        "keyring_available": KEYRING_OK,
        "ini_file": _INI_PATH,
        "ini_exists": os.path.isfile(_INI_PATH),
        "ini_has_mysql": bool(_ini_get_encrypted("mysql", INI_DB_FIELD)),
        "ini_has_ftp": bool(_ini_get_encrypted("update", INI_FTP_FIELD)),
        "fallback_paths": _fallback_paths(),
        "fallback_file": _active_fallback_file(),
        "fallback_exists": os.path.isfile(_active_fallback_file()) if _active_fallback_file() else False,
        "keyring_has": False,
        "fallback_has": False,
        "password_source": "",
    }
    if KEYRING_OK:
        try:
            kr_pw = keyring.get_password(SVC_NAME, USER_NAME)
            info["keyring_has"] = bool(kr_pw)
        except Exception:
            pass
    info["fallback_has"] = _fallback_has(USER_NAME)
    pw, src = get_password()
    info["password_source"] = src
    return info


def migrate_from_old_stores() -> str:
    pw = ""
    if KEYRING_OK:
        try:
            pw = keyring.get_password(SVC_NAME, USER_NAME) or ""
            if pw:
                _log.info("从 keyring 迁移 MySQL 密码到 config.ini")
                if _ini_set_encrypted("mysql", INI_DB_FIELD, pw):
                    return pw
        except Exception as e:
            _log.warning("keyring 迁移失败: %s", e)
    for path in _fallback_paths():
        store = _load_fallback_from(path)
        blob = store.get(USER_NAME, "")
        if blob:
            pw = _decrypt(blob)
            if pw:
                _log.info("从 fallback (%s) 迁移 MySQL 密码到 config.ini", path)
                if _ini_set_encrypted("mysql", INI_DB_FIELD, pw):
                    return pw
    return ""