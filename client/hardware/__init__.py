"""硬件读取模块

提供指纹和NFC设备的抽象接口。
当前为预留框架，真实硬件驱动接入时只需继承 HardwareReader。
"""
from .base import HardwareReader, ReaderType, get_reader

__all__ = ["HardwareReader", "ReaderType", "get_reader"]
