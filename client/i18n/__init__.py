"""i18n 国际化模块

提供语言管理、翻译查找和实时切换功能。
用法:
    from i18n import tr, get_manager, set_language, current_language

    label.setText(tr("common.app_title"))
    get_manager().language_changed.connect(self._on_lang_changed)
    set_language("es_ES")
"""
from .manager import LanguageManager
from .translations import translate as _translate


def tr(key: str, **kwargs) -> str:
    """翻译查找。在所有地方替代硬编码字符串。

    Args:
        key: 点分隔的翻译键，如 "common.app_title"
        **kwargs: 模板参数，如 name="张三"

    Returns:
        当前语言的翻译文本，找不到时返回键本身
    """
    return _translate(key, **kwargs)


def get_manager() -> LanguageManager:
    """获取 LanguageManager 单例"""
    return LanguageManager.instance()


def current_language() -> str:
    """获取当前语言代码，如 "zh_CN"、"es_ES" """
    return LanguageManager.instance().language


def set_language(lang: str) -> None:
    """设置当前语言"""
    LanguageManager.instance().set_language(lang)