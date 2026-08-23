# -*- coding: utf-8 -*-
"""LanguageManager 单例 — 管理当前语言，发射 Qt 信号实现实时切换"""

from PySide6.QtCore import QObject, Signal
from . import translations
from .storage import load_preference, save_preference


class LanguageManager(QObject):
    """语言管理器单例

    信号:
        language_changed(lang_code): 语言切换时发射，携带新语言代码
    """

    language_changed = Signal(str)

    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lang = load_preference()  # "zh_CN" / "es_ES"

    @classmethod
    def instance(cls) -> "LanguageManager":
        if cls._instance is None:
            cls._instance = LanguageManager()
            # 初始化时设置 translations 的当前语言
            translations.set_current(cls._instance._lang)
        return cls._instance

    @property
    def language(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> None:
        """设置语言，持久化偏好并发射信号"""
        if lang not in ("zh_CN", "es_ES") or lang == self._lang:
            return
        self._lang = lang
        translations.set_current(lang)
        save_preference(lang)
        self.language_changed.emit(lang)

    def toggle(self) -> None:
        """在中文和西班牙语之间切换"""
        self.set_language("es_ES" if self._lang == "zh_CN" else "zh_CN")

    def other(self) -> str:
        """返回当前另一种语言的代码"""
        return "es_ES" if self._lang == "zh_CN" else "zh_CN"