"""硬件读取抽象基类"""
import time
from enum import Enum
from abc import ABC, abstractmethod
import logging

from config import TABLE_CONFIG_ITEMS

logger = logging.getLogger(__name__)

class ReaderType(Enum):
    FINGERPRINT = "fingerprint"
    NFC = "nfc"

class HardwareReader(ABC):
    def __init__(self, device: str = "", baud_rate: int = 9600):
        self.device = device
        self.baud_rate = baud_rate
        self._enabled = False
        self._serial = None
        self._pending = b""

    def _open_serial(self):
        """打开串口连接（不重复打开）"""
        if self._serial is not None:
            return
        if not self.device:
            logger.warning("device not set, cannot open serial")
            return
        try:
            import serial
            self._serial = serial.Serial(
                port=self.device,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.5,
            )
            # 新打开串口后等待设备初始化稳定，并清空缓冲区
            time.sleep(0.5)
            self._serial.reset_input_buffer()
            logger.info(f"{self.__class__.__name__} serial opened: {self.device} @ {self.baud_rate}")
        except Exception as e:
            logger.error(f"{self.__class__.__name__} serial open failed: {e}")
            self._serial = None

    def _close_serial(self):
        """关闭串口连接"""
        if self._serial is not None:
            try:
                self._serial.close()
                logger.info(f"{self.__class__.__name__} serial closed")
            except Exception as e:
                logger.error(f"{self.__class__.__name__} serial close error: {e}")
            self._serial = None

    def enable(self) -> bool:
        """启用设备并打开串口"""
        self._enabled = True
        logger.info(f"{self.__class__.__name__} enabled on {self.device or 'sim'}")
        self._open_serial()
        return True

    def disable(self):
        """关闭设备连接"""
        self._enabled = False
        self._close_serial()
        logger.info(f"{self.__class__.__name__} disabled")

    @abstractmethod
    def _parse_response(self, raw: bytes) -> str:
        """子类重写：从原始字节流解析出目标值（指纹ID / NFC卡号）"""
        pass

    def read(self, timeout: float = 5.0) -> str:
        """读取一次硬件输入，返回十六进制字符串。
        超时返回空字符串。
        """
        if not self._enabled:
            logger.warning(f"{self.__class__.__name__} not enabled")
            return ""
        self._open_serial()
        if self._serial is None:
            logger.warning(f"{self.__class__.__name__} serial not available")
            return ""

        deadline = time.time() + timeout
        buffer = self._pending
        self._pending = b""
        while time.time() < deadline:
            try:
                chunk = self._serial.read(64)
                if chunk:
                    buffer += chunk
                    hex_log = buffer.hex()
                    logger.info(f"{self.__class__.__name__} recv: {hex_log}")
                    result = self._parse_response(buffer)
                    if result:
                        nl = buffer.find(b"\r\n")
                        if nl >= 0:
                            self._pending = buffer[nl + 2:]
                        else:
                            self._pending = b""
                        logger.info(f"{self.__class__.__name__} parsed result: {result}")
                        return result
            except Exception as e:
                logger.error(f"{self.__class__.__name__} read error: {e}")
                return ""
        # 超时：丢弃残留数据，返回空字符串（不将垃圾数据当作有效扫描结果）
        if buffer:
            logger.warning(f"{self.__class__.__name__} timeout, discarding {len(buffer)} raw bytes")
        return ""

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def close(self):
        """显式关闭（调用者可在窗口关闭时调用）"""
        self._enabled = False
        self._close_serial()


# 工厂缓存
_reader_cache = {}

def get_reader(reader_type: ReaderType, device: str = "", baud_rate: int = 9600):
    """获取或创建硬件读取器实例（单例缓存），自动从 config_items 读取配置"""
    try:
        from local_db import LocalDB
        db = LocalDB()
        if reader_type == ReaderType.FINGERPRINT:
            enabled_name = "FINGERPRINT_ENABLED"
            device_name = "FINGERPRINT_DEVICE"
            baud_name = "FINGERPRINT_BAUD_RATE"
        else:
            enabled_name = "NFC_ENABLED"
            device_name = "NFC_DEVICE"
            baud_name = "NFC_BAUD_RATE"

        rows = db.query(TABLE_CONFIG_ITEMS, conditions="config_name = ?", params=(device_name,))
        if rows:
            device = rows[0].get("content", "") or device

        rows = db.query(TABLE_CONFIG_ITEMS, conditions="config_name = ?", params=(baud_name,))
        if rows:
            try:
                baud_rate = int(rows[0].get("content", baud_rate))
            except (ValueError, TypeError):
                pass
    except Exception as e:
        logger.warning("get_reader 读取设备配置失败: %s", e)

    key = (reader_type, device, baud_rate)
    if key not in _reader_cache:
        if reader_type == ReaderType.FINGERPRINT:
            from .fingerprint_reader import FingerprintReader
            _reader_cache[key] = FingerprintReader(device, baud_rate)
        elif reader_type == ReaderType.NFC:
            from .nfc_reader import NFCReader
            _reader_cache[key] = NFCReader(device, baud_rate)
    reader = _reader_cache[key]
    # 刷新 reader 的串口参数（缓存实例可能来自旧配置）
    reader.device = device
    reader.baud_rate = baud_rate
    try:
        from local_db import LocalDB
        db = LocalDB()
        rows = db.query(TABLE_CONFIG_ITEMS, conditions="config_name = ?", params=(enabled_name,))
        enabled = any(row.get("content") == "1" for row in rows)
        if enabled:
            reader.enable()
        else:
            reader.disable()
    except Exception as e:
        logger.warning("get_reader 读取启用状态失败: %s", e)
    return reader
