"""指纹读取器（真实串口读取）"""
import logging
from .base import HardwareReader

logger = logging.getLogger(__name__)


def _decode_fingerprint(raw: bytes) -> str:
    """将设备返回的指纹数据解码为十进制字符串。

    三种常见格式：
      1. 纯数字 ASCII（如 b"123"）     → 直接返回 "123"
      2. hex 字符串 ASCII（如 b"01A2")  → hex→dec 返回 "418"
      3. 二进制原始数据（如 b"\x01\x23")→ hex→dec 返回 "27427"
    """
    clean = raw.strip(b"\r\n\t ")
    if not clean:
        return ""

    if all(0x20 <= b <= 0x7e for b in clean):
        text = clean.decode("ascii").strip().upper()
        if text.isdigit():
            return text
        if all(c in "0123456789ABCDEF" for c in text):
            try:
                return str(int(text, 16))
            except ValueError:
                pass
        # 可打印 ASCII 但不符合数字或 hex 格式（如 "ERR"/"FAIL"）→ 非有效指纹
        return ""

    hex_str = clean.hex()
    try:
        return str(int(hex_str, 16))
    except ValueError:
        return hex_str


class FingerprintReader(HardwareReader):
    def __init__(self, device: str = "", baud_rate: int = 9600):
        super().__init__(device, baud_rate)

    def _parse_response(self, raw: bytes) -> str:
        if b"\r\n" in raw:
            first = raw.split(b"\r\n")[0]
        else:
            first = raw
        result = _decode_fingerprint(first)
        return result if result else ""

    def read(self, timeout: float = 5.0) -> str:
        result = super().read(timeout)
        logger.info(f"FingerprintReader read result: {result}")
        return result
