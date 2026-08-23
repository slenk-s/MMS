"""NFC卡读取器（真实串口读取）"""
import logging
from .base import HardwareReader

logger = logging.getLogger(__name__)


def _decode_card(raw: bytes) -> str:
    """将设备返回的卡号字节解码为十进制字符串。

    三种常见格式：
      1. 纯数字 ASCII（如 b"123"）     → 直接返回 "123"
      2. hex 字符串 ASCII（如 b"01A2B3")→ hex→dec 返回 "1690723"
      3. 二进制原始数据（如 b"\x01\x23")→ hex→dec 返回 "27427"
    """
    clean = raw.strip(b"\r\n\t ")
    if not clean:
        return ""

    if all(0x20 <= b <= 0x7e for b in clean):
        text = clean.decode("ascii").strip().upper()
        # 纯数字 ASCII → 直接当十进制卡号
        if text.isdigit():
            return text
        # hex 字符串（含 A-F 或长度可被 2 整除）→ hex→dec
        if all(c in "0123456789ABCDEF" for c in text):
            try:
                return str(int(text, 16))
            except ValueError:
                pass
        # 可打印 ASCII 但不符合数字或 hex 格式（如 "OK"/"ERR"）→ 非有效卡号
        return ""

    # 二进制原始数据 → hex→dec
    hex_str = clean.hex()
    try:
        return str(int(hex_str, 16))
    except ValueError:
        return hex_str


class NFCReader(HardwareReader):
    def __init__(self, device: str = "", baud_rate: int = 9600):
        super().__init__(device, baud_rate)

    def _parse_response(self, raw: bytes) -> str:
        """从原始字节流解析NFC卡号。

        不依赖 \\r\\n 结尾，只要收到合法卡号即返回。
        多条卡号用 \\r\\n 分隔时只取第一条。
        """
        # 支持 \\r\\n 分隔的多条
        if b"\r\n" in raw:
            first = raw.split(b"\r\n")[0]
        else:
            first = raw

        result = _decode_card(first)
        if result:
            return result
        return ""

    def read(self, timeout: float = 3.0) -> str:
        result = super().read(timeout)
        logger.info(f"NFCReader read result: {result}")
        return result
