"""Cython 编译版 - 应用配置模块
从 config.ini 读取系统核心配置：[mysql] [app] [web_query] [serial]
"""
from __future__ import print_function
import logging
import configparser
import os
import sys

_log = logging.getLogger(__name__)


def _get_config_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "config.ini")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config.ini")


_CONFIG_PATH = _get_config_path()


def _read_ini(section: str) -> dict:
    try:
        cp = configparser.ConfigParser()
        cp.read(_CONFIG_PATH, encoding="utf-8-sig")
        if cp.has_section(section):
            return dict(cp.items(section))
    except Exception:
        pass
    return {}


def _write_ini(section: str, values: dict) -> bool:
    try:
        cp = configparser.ConfigParser()
        cp.read(_CONFIG_PATH, encoding="utf-8-sig")
        if not cp.has_section(section):
            cp.add_section(section)
        for key, value in values.items():
            cp.set(section, key, str(value))
        with open(_CONFIG_PATH, "w", encoding="utf-8", newline="") as f:
            cp.write(f)
        return True
    except Exception:
        return False


MYSQL_DEFAULTS = {
    "mysql_host": "localhost",
    "mysql_port": "3306",
    "mysql_user": "root",
    "mysql_password": "",
    "mysql_database": "mms",
    "mysql_charset": "utf8mb4",
}


def load_mysql_config() -> dict:
    raw = _read_ini("mysql")
    port_str = raw.get("mysql_port", MYSQL_DEFAULTS["mysql_port"])
    try:
        mysql_port = int(port_str)
    except (ValueError, TypeError):
        mysql_port = int(MYSQL_DEFAULTS["mysql_port"])
    return {
        "mysql_host": raw.get("mysql_host", MYSQL_DEFAULTS["mysql_host"]),
        "mysql_port": mysql_port,
        "mysql_user": raw.get("mysql_user", MYSQL_DEFAULTS["mysql_user"]),
        "mysql_password": "",
        "mysql_database": raw.get("mysql_database", MYSQL_DEFAULTS["mysql_database"]),
        "mysql_charset": raw.get("mysql_charset", MYSQL_DEFAULTS["mysql_charset"]),
    }


def save_mysql_config(config: dict):
    result = {"password_stored": False, "store": "error", "verified": False, "ini_ok": False}
    pw = config.get("mysql_password", "")
    if pw:
        from .credential_manager import set_password as _set_pw
        if _set_pw:
            pw_result = _set_pw(pw)
            result["password_stored"] = bool(pw_result.get("ok", False))
            result["store"] = pw_result.get("store", "error")
            result["verified"] = pw_result.get("verified", False)
            if not pw_result.get("ok", False):
                _log.error("密码写入失败，详见 credential_manager 日志")
        try:
            import config as _cfg
            _cfg.MYSQL_PASSWORD = pw
            _cfg.MYSQL_HOST = config.get("mysql_host", _cfg.MYSQL_HOST)
            _cfg.MYSQL_PORT = int(config.get("mysql_port") or str(_cfg.MYSQL_PORT))
            _cfg.MYSQL_USER = config.get("mysql_user", _cfg.MYSQL_USER)
            _cfg.MYSQL_DATABASE = config.get("mysql_database", _cfg.MYSQL_DATABASE)
        except Exception:
            pass
    else:
        _log.warning("save_mysql_config: mysql_password 为空，跳过密钥库写入")
    values = {
        "mysql_host": config.get("mysql_host", "localhost"),
        "mysql_port": str(config.get("mysql_port", 3306)),
        "mysql_user": config.get("mysql_user", "root"),
        "mysql_database": config.get("mysql_database", "mms"),
        "mysql_charset": config.get("mysql_charset", "utf8mb4"),
    }
    try:
        cp = configparser.ConfigParser()
        cp.read(_CONFIG_PATH, encoding="utf-8-sig")
        for old_key in ("mysql_password", "mysql_password_enc"):
            if cp.has_section("mysql") and cp.has_option("mysql", old_key) and old_key == "mysql_password":
                cp.remove_option("mysql", old_key)
        for k, v in values.items():
            if not cp.has_section("mysql"):
                cp.add_section("mysql")
            cp.set("mysql", k, str(v))
        with open(_CONFIG_PATH, "w", encoding="utf-8", newline="") as f:
            cp.write(f)
        result["ini_ok"] = True
    except Exception:
        result["ini_ok"] = False
    return result


SERIAL_DEFAULTS = {
    "fingerprint_enabled": "0",
    "nfc_enabled": "0",
    "fingerprint_device": "COM3",
    "nfc_device": "COM4",
    "fingerprint_baud_rate": "9600",
    "nfc_baud_rate": "9600",
}


def load_serial_config() -> dict:
    raw = _read_ini("serial")
    return {
        "fingerprint_enabled": raw.get("fingerprint_enabled", SERIAL_DEFAULTS["fingerprint_enabled"]),
        "nfc_enabled": raw.get("nfc_enabled", SERIAL_DEFAULTS["nfc_enabled"]),
        "fingerprint_device": raw.get("fingerprint_device", SERIAL_DEFAULTS["fingerprint_device"]),
        "nfc_device": raw.get("nfc_device", SERIAL_DEFAULTS["nfc_device"]),
        "fingerprint_baud_rate": raw.get("fingerprint_baud_rate", SERIAL_DEFAULTS["fingerprint_baud_rate"]),
        "nfc_baud_rate": raw.get("nfc_baud_rate", SERIAL_DEFAULTS["nfc_baud_rate"]),
    }


def save_serial_config(config: dict) -> bool:
    values = {
        "fingerprint_enabled": config.get("fingerprint_enabled", "0"),
        "nfc_enabled": config.get("nfc_enabled", "0"),
        "fingerprint_device": config.get("fingerprint_device", "COM3"),
        "nfc_device": config.get("nfc_device", "COM4"),
        "fingerprint_baud_rate": config.get("fingerprint_baud_rate", "9600"),
        "nfc_baud_rate": config.get("nfc_baud_rate", "9600"),
    }
    return _write_ini("serial", values)


APP_DEFAULTS = {
    "app_mode": "online",
    "log_level": "INFO",
}


def load_app_config() -> dict:
    raw = _read_ini("app")
    return {
        "app_mode": raw.get("app_mode", APP_DEFAULTS["app_mode"]),
        "log_level": raw.get("log_level", APP_DEFAULTS["log_level"]),
    }


def save_app_config(config: dict) -> bool:
    values = {
        "app_mode": config.get("app_mode", APP_DEFAULTS["app_mode"]),
        "log_level": config.get("log_level", APP_DEFAULTS["log_level"]),
    }
    return _write_ini("app", values)


WEB_QUERY_DEFAULTS = {
    "web_query_enabled": "0",
    "web_query_host": "localhost",
    "web_query_port": "8000",
    "web_query_api_base": "/api",
    "web_query_api_key": "",
    "web_query_timeout": "10",
    "web_query_use_https": "1",
}


def load_web_query_config() -> dict:
    raw = _read_ini("web_query")
    return {
        "web_query_enabled": raw.get("web_query_enabled", WEB_QUERY_DEFAULTS["web_query_enabled"]),
        "web_query_host": raw.get("web_query_host", WEB_QUERY_DEFAULTS["web_query_host"]),
        "web_query_port": raw.get("web_query_port", WEB_QUERY_DEFAULTS["web_query_port"]),
        "web_query_api_base": raw.get("web_query_api_base", WEB_QUERY_DEFAULTS["web_query_api_base"]),
        "web_query_api_key": raw.get("web_query_api_key", WEB_QUERY_DEFAULTS["web_query_api_key"]),
        "web_query_timeout": raw.get("web_query_timeout", WEB_QUERY_DEFAULTS["web_query_timeout"]),
        "web_query_use_https": raw.get("web_query_use_https", WEB_QUERY_DEFAULTS["web_query_use_https"]),
    }


def save_web_query_config(config: dict) -> bool:
    values = {
        "web_query_enabled": config.get("web_query_enabled", WEB_QUERY_DEFAULTS["web_query_enabled"]),
        "web_query_host": config.get("web_query_host", WEB_QUERY_DEFAULTS["web_query_host"]),
        "web_query_port": str(config.get("web_query_port", WEB_QUERY_DEFAULTS["web_query_port"])),
        "web_query_api_base": config.get("web_query_api_base", WEB_QUERY_DEFAULTS["web_query_api_base"]),
        "web_query_api_key": config.get("web_query_api_key", ""),
        "web_query_timeout": str(config.get("web_query_timeout", WEB_QUERY_DEFAULTS["web_query_timeout"])),
        "web_query_use_https": config.get("web_query_use_https", WEB_QUERY_DEFAULTS["web_query_use_https"]),
    }
    return _write_ini("web_query", values)


WORKSHOP_DEFAULTS = {
    "workshops": "",
    "current_workshop": "",
}


def load_workshop_config() -> dict:
    raw = _read_ini("workshops")
    return {
        "workshops": raw.get("workshops", WORKSHOP_DEFAULTS["workshops"]),
        "current_workshop": raw.get("current_workshop", WORKSHOP_DEFAULTS["current_workshop"]),
    }


def save_workshop_config(config: dict) -> bool:
    existing = _read_ini("workshops")
    merged = {
        "workshops": existing.get("workshops", WORKSHOP_DEFAULTS["workshops"]),
        "current_workshop": existing.get("current_workshop", WORKSHOP_DEFAULTS["current_workshop"]),
    }
    if "workshops" in config:
        merged["workshops"] = config["workshops"]
    if "current_workshop" in config:
        merged["current_workshop"] = config["current_workshop"]
    return _write_ini("workshops", merged)


def get_config_path() -> str:
    return _CONFIG_PATH