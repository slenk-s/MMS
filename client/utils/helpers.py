"""
通用工具函数模块
提供业务单号生成、数据验证、时间处理、密码哈希等通用功能
"""
import os
import uuid
import hashlib
import secrets
from datetime import datetime, date
from typing import Optional, Any


# ==================== 密码哈希（v20 安全加固）====================

_PWD_HASH_ITERATIONS = 600000
_PWD_HASH_ALGO = "sha256"
_PWD_HASH_SEP = "$"


def hash_password(password: str) -> str:
    """对明文密码进行 PBKDF2 哈希，返回 salt$hash 格式字符串"""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        _PWD_HASH_ALGO,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PWD_HASH_ITERATIONS,
    ).hex()
    return f"{salt}{_PWD_HASH_SEP}{pwd_hash}"


def verify_password(password: str, stored: str) -> tuple:
    """验证密码，返回 (是否匹配, 是否需要升级)

    兼容旧版明文密码：
    - stored 不含 '$' 视为明文，匹配后返回 need_upgrade=True
    - stored 含 '$' 按 PBKDF2 哈希比对

    Returns:
        (bool: 是否匹配, bool: 是否需要升级为哈希存储)
    """
    if not stored:
        return False, False

    # 旧版明文密码（不含分隔符）
    if _PWD_HASH_SEP not in stored:
        matched = secrets.compare_digest(stored, password)
        return matched, matched  # 匹配后需要升级

    parts = stored.split(_PWD_HASH_SEP, 1)
    if len(parts) != 2:
        return False, False

    salt, expected_hash = parts
    actual_hash = hashlib.pbkdf2_hmac(
        _PWD_HASH_ALGO,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PWD_HASH_ITERATIONS,
    ).hex()
    return secrets.compare_digest(actual_hash, expected_hash), False


def generate_uuid() -> str:
    """生成 UUID 字符串"""
    return str(uuid.uuid4())


def format_datetime(dt: Optional[datetime] = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化日期时间"""
    if dt is None:
        dt = datetime.now()
    return dt.strftime(fmt)


def format_date(d: Optional[date] = None, fmt: str = "%Y-%m-%d") -> str:
    """格式化日期"""
    if d is None:
        d = date.today()
    return d.strftime(fmt)


def parse_datetime(date_str: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> Optional[datetime]:
    """解析日期时间字符串"""
    try:
        return datetime.strptime(date_str, fmt)
    except ValueError:
        return None


def parse_date(date_str: str, fmt: str = "%Y-%m-%d") -> Optional[date]:
    """解析日期字符串"""
    try:
        return datetime.strptime(date_str, fmt).date()
    except ValueError:
        return None


def parse_datetime_flexible(val: Any) -> Optional[datetime]:
    """灵活解析日期时间值，兼容多种格式

    支持的输入：
    - datetime 对象（直接返回）
    - ISO 格式字符串（含 `Z` 后缀或 `T` 分隔符）
    - MySQL 格式字符串（`%Y-%m-%d %H:%M:%S`）
    - 其他 strptime 可解析的字符串

    Args:
        val: 待解析的值（datetime/str/None）

    Returns:
        datetime 对象，解析失败时返回 None
    """
    if isinstance(val, datetime):
        return val
    if not isinstance(val, str) or not val:
        return None
    # 优先使用 fromisoformat 处理 ISO 格式（含 T 和 Z）
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass
    # 回退：兼容常见格式
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.split(".")[0], fmt)
        except (ValueError, AttributeError):
            continue
    return None


def get_current_timestamp() -> str:
    """获取当前时间戳字符串（ISO格式）"""
    return datetime.now().isoformat()


def timestamp_to_datetime(timestamp: str) -> Optional[datetime]:
    """将 ISO 时间戳字符串转为 datetime"""
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


# ==================== LRU 图片缓存（P1-3 优化 + V4 双层缓存）====================

class ImageCache:
    """双层 LRU 图片缓存：缩略图（快速显示）+ 原图（高质量缩放）

    设计:
    - _thumb_cache: 较大容量，存储适配视图大小的缩略图，即时显示
    - _full_cache: 较小容量，存储原图，仅在需要高质量缩放时使用
    - 加载策略：先返回缩略图（快），后台异步解码原图，用户缩放时无缝升级

    用法:
        cache = ImageCache(max_size=8)
        thumb = cache.load_thumbnail(path, w, h)  # 快速获取缩略图
        full  = cache.load_full_res(path)          # 获取原图（较慢）
    """

    def __init__(self, max_size: int = 8, thumb_size: int = 16):
        self._max_size = max_size          # 原图缓存上限
        self._thumb_size = thumb_size      # 缩略图缓存上限
        self._cache: dict = {}             # 原图缓存: path -> QPixmap
        self._order: list = []             # 原图 LRU 顺序
        self._thumb_cache: dict = {}       # 缩略图缓存: path -> QPixmap
        self._thumb_order: list = []       # 缩略图 LRU 顺序
        self._loading_paths: set = set()   # 正在异步加载的路径

    def get(self, path: str):
        """获取缓存的原图 QPixmap，命中时更新 LRU 顺序"""
        if path not in self._cache:
            return None
        if path in self._order:
            self._order.remove(path)
        self._order.append(path)
        return self._cache[path]

    def set(self, path: str, pixmap) -> None:
        """缓存原图 QPixmap，超出上限时淘汰最旧的"""
        if path in self._cache and path in self._order:
            self._order.remove(path)
        while len(self._order) >= self._max_size:
            old = self._order.pop(0)
            self._cache.pop(old, None)
        self._cache[path] = pixmap
        self._order.append(path)

    def get_thumb(self, path: str):
        """获取缓存的缩略图"""
        if path not in self._thumb_cache:
            return None
        if path in self._thumb_order:
            self._thumb_order.remove(path)
        self._thumb_order.append(path)
        return self._thumb_cache[path]

    def set_thumb(self, path: str, pixmap) -> None:
        """缓存缩略图"""
        if path in self._thumb_cache and path in self._thumb_order:
            self._thumb_order.remove(path)
        while len(self._thumb_order) >= self._thumb_size:
            old = self._thumb_order.pop(0)
            self._thumb_cache.pop(old, None)
        self._thumb_cache[path] = pixmap
        self._thumb_order.append(path)

    def load_pixmap(self, path: str, max_width: int = 0, max_height: int = 0):
        """加载并缓存图片（保持向后兼容）

        max_width=0, max_height=0 时加载原图并存入原图缓存
        指定尺寸时加载缩略图并存入缩略图缓存

        Returns:
            QPixmap 对象，加载失败时返回 None
        """
        if not path or not os.path.exists(path):
            return None

        if max_width > 0 and max_height > 0:
            thumb = self.get_thumb(path)
            if thumb is not None:
                return thumb
            from PySide6.QtGui import QPixmap
            from PySide6.QtCore import Qt
            pixmap = QPixmap(path)
            if pixmap.isNull():
                return None
            scaled = pixmap.scaled(
                max_width, max_height,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.set_thumb(path, scaled)
            return scaled
        else:
            full = self.get(path)
            if full is not None:
                return full
            from PySide6.QtGui import QPixmap
            pixmap = QPixmap(path)
            if pixmap.isNull():
                return None
            self.set(path, pixmap)
            return pixmap

    def load_thumbnail(self, path: str, width: int, height: int):
        """快速加载缩略图（优先使用缩略图缓存）

        Args:
            path: 图片路径
            width: 缩略图目标宽度
            height: 缩略图目标高度

        Returns:
            QPixmap 缩略图，失败返回 None
        """
        if not path or not os.path.exists(path):
            return None
        thumb = self.get_thumb(path)
        if thumb is not None:
            return thumb
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import Qt
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return None
        scaled = pixmap.scaled(
            width, height,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.set_thumb(path, scaled)
        return scaled

    def load_full_res(self, path: str):
        """加载原图（优先使用原图缓存）

        Returns:
            原图 QPixmap，失败返回 None
        """
        if not path or not os.path.exists(path):
            return None
        full = self.get(path)
        if full is not None:
            return full
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return None
        self.set(path, pixmap)
        return pixmap

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
        self._order.clear()
        self._thumb_cache.clear()
        self._thumb_order.clear()

    def remove(self, path: str) -> None:
        """移除指定路径的缓存"""
        self._cache.pop(path, None)
        if path in self._order:
            self._order.remove(path)
        self._thumb_cache.pop(path, None)
        if path in self._thumb_order:
            self._thumb_order.remove(path)


def save_image_to_storage(source_path: str, target_dir: str, prefix: str = "") -> str:
    """将图片复制到指定存储目录，返回新路径

    如果图片已在该目录中，则直接返回原路径不做复制。
    图片文件名格式: {prefix}{uuid4}.{ext}

    Args:
        source_path: 源文件路径
        target_dir: 目标目录（如 SHELF_IMAGES_DIR）
        prefix: 文件名前缀（如 "shelf_", "real_", "location_"）

    Returns:
        复制后的完整文件路径，失败时返回空字符串
    """
    import shutil
    from pathlib import Path

    if not source_path or not os.path.isfile(source_path):
        return ""

    # 如果文件已在目标目录中，不做复制（避免重复复制）
    if os.path.dirname(os.path.abspath(source_path)) == os.path.abspath(target_dir):
        return source_path

    # 确保目标目录存在
    os.makedirs(target_dir, exist_ok=True)

    # 生成唯一文件名
    ext = Path(source_path).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"):
        return ""
    new_name = f"{prefix}{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(target_dir, new_name)

    try:
        shutil.copy2(source_path, dest_path)
        return os.path.abspath(dest_path)
    except Exception:
        return ""
