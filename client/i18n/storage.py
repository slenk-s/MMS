# -*- coding: utf-8 -*-
"""语言偏好持久化存储"""

import json
import os

from config import LOCAL_DB_PATH
from logger import get_logger

_log = get_logger(__name__)

# 持久化文件：与 .remember_login.json 同级
_PREF_FILE = os.path.join(os.path.dirname(LOCAL_DB_PATH), ".language.json")


def load_preference() -> str:
    """读取语言偏好，默认返回 zh_CN"""
    try:
        with open(_PREF_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            lang = data.get("lang", "zh_CN")
            return lang if lang in ("zh_CN", "es_ES") else "zh_CN"
    except Exception:
        return "zh_CN"


def save_preference(lang: str) -> None:
    """保存语言偏好到 .language.json"""
    try:
        with open(_PREF_FILE, "w", encoding="utf-8") as f:
            json.dump({"lang": lang}, f)
    except (OSError, IOError, UnicodeEncodeError) as e:
        _log.warning("保存语言偏好失败: %s", e)
    except Exception as e:
        _log.warning("保存语言偏好未预期异常: %s", e)