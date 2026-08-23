# -*- coding: utf-8 -*-
"""翻译字典加载和查找"""

from .lang import zh_cn, es_es

_LANG_MODULES = {
    "zh_CN": zh_cn.TRANSLATIONS,
    "es_ES": es_es.TRANSLATIONS,
}

_current = "zh_CN"


def set_current(lang: str) -> None:
    """设置当前语言代码"""
    global _current
    if lang in _LANG_MODULES:
        _current = lang


def get_current() -> str:
    return _current


def translate(key: str, **kwargs) -> str:
    """查找翻译文本

    查找顺序: 当前语言 -> 中文(zh_CN) -> 返回键本身
    支持 {name} 模板插值

    Args:
        key: 点分隔的翻译键
        **kwargs: 模板格式化参数

    Returns:
        翻译后的文本
    """
    table = _LANG_MODULES.get(_current, _LANG_MODULES["zh_CN"])
    text = table.get(key)
    if text is None:
        # 回退到中文，再找不到就返回键本身
        text = _LANG_MODULES["zh_CN"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text