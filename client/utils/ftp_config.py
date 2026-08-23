"""FTP 更新配置读取模块"""
import configparser
import os
import sys


def _get_project_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


_CONFIG_PATH = os.path.join(_get_project_root(), "config.ini")


def load_update_config() -> dict:
    default = {
        "enabled": False,
        "host": "",
        "port": 21,
        "user": "",
        "pass": "",
        "directory": "",
    }
    try:
        cp = configparser.ConfigParser()
        cp.read(_CONFIG_PATH, encoding="utf-8-sig")
        if not cp.has_section("update"):
            return default
        config = {
            "enabled": cp.getboolean("update", "update_enabled", fallback=False),
            "host": cp.get("update", "ftp_host", fallback="").strip(),
            "port": cp.getint("update", "ftp_port", fallback=21),
            "user": cp.get("update", "ftp_user", fallback="").strip(),
            "pass": "",
            "directory": cp.get("update", "ftp_dir", fallback="").strip(),
        }
        try:
            try:
                from .credential_manager import get_ftp_password
            except ImportError:
                from utils.credential_manager import get_ftp_password
            ftp_pw = get_ftp_password()
            if ftp_pw:
                config["pass"] = ftp_pw
        except Exception:
            pass
        return config
    except Exception:
        return default


def save_update_config(config: dict) -> bool:
    try:
        cp = configparser.ConfigParser()
        cp.read(_CONFIG_PATH, encoding="utf-8-sig")
        if not cp.has_section("update"):
            cp.add_section("update")
        # 清理历史遗留明文 FTP 密码字段
        for old_key in ("ftp_pass", "ftp_password"):
            if cp.has_section("update") and cp.has_option("update", old_key):
                cp.remove_option("update", old_key)
        cp.set("update", "update_enabled", str(1 if config.get("enabled") else 0))
        cp.set("update", "ftp_host", str(config.get("host", "")))
        cp.set("update", "ftp_port", str(int(config.get("port", 21))))
        cp.set("update", "ftp_user", str(config.get("user", "")))
        cp.set("update", "ftp_dir", str(config.get("directory", "")))
        with open(_CONFIG_PATH, "w", encoding="utf-8", newline="") as f:
            cp.write(f)
        if config.get("pass"):
            try:
                try:
                    from .credential_manager import set_ftp_password
                except ImportError:
                    from utils.credential_manager import set_ftp_password
                set_ftp_password(config["pass"])
            except Exception:
                pass
        return True
    except Exception:
        return False


def is_update_enabled() -> bool:
    return load_update_config().get("enabled", False)
