"""
MySQL 数据库连接管理器
从 config.ini 读取配置（[mysql] 节），密码通过 credential_manager 读取（config.ini 解密 → keyring → fallback）
提供领料记录查询方法，自动检测表字段，兼容不同版本的表结构
"""
import os
import sys
import threading
import configparser
from typing import Optional, List, Dict, Tuple
import pymysql
from pymysql.cursors import DictCursor
from pymysql.err import OperationalError


# 确保 client/ 在搜索路径上（utils/logger 在此）
for _p in [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "client"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
]:
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from utils.credential_manager import get_password as _get_pw
except Exception:
    try:
        import credential_manager as _cm
        _get_pw = _cm.get_password
    except Exception:
        _get_pw = None


try:
    from utils.app_config import get_config_path as _get_config_path_func
except Exception:
    try:
        from app_config import get_config_path as _get_config_path_func
    except Exception:
        _get_config_path_func = None


try:
    from logger import get_logger as _get_logger
except Exception:
    _get_logger = None

_log = _get_logger(__name__) if _get_logger else __import__("logging").getLogger(__name__)


_CONFIG_PATH = _get_config_path_func() if _get_config_path_func else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini"
)

if not os.path.isfile(_CONFIG_PATH):
    _log.warning("config.ini not found at %s, MySQL will use default values", _CONFIG_PATH)
else:
    _log.info("Loaded config.ini: %s", _CONFIG_PATH)

cp = configparser.ConfigParser()
cp.read(_CONFIG_PATH, encoding="utf-8-sig")

MYSQL_HOST = cp.get("mysql", "mysql_host", fallback="localhost")
MYSQL_PORT = int(cp.get("mysql", "mysql_port", fallback="3306"))
MYSQL_USER = cp.get("mysql", "mysql_user", fallback="root")
_mysql_pw, _ = _get_pw() if _get_pw else ("", "")
MYSQL_PASSWORD = _mysql_pw or ""
MYSQL_DATABASE = cp.get("mysql", "mysql_database", fallback="mms")
MYSQL_CHARSET = cp.get("mysql", "mysql_charset", fallback="utf8mb4")

try:
    from config import TABLE_BORROW_RECORDS
    _BORROW_TBL_SQL = f"`{TABLE_BORROW_RECORDS}`"
except Exception:
    _BORROW_TBL_SQL = "`borrow_records`"
    TABLE_BORROW_RECORDS = "borrow_records"

_WEB_QUERY_API_KEY = (cp.get("web_query", "web_query_api_key", fallback="") or "").strip() or None


def get_web_query_api_key() -> Optional[str]:
    """获取当前 Web 查询 API Key

    直接从 config.ini 读取最新值，使配置页修改 API Key 后无需重启服务即可生效。
    """
    try:
        cp2 = configparser.ConfigParser()
        cp2.read(_CONFIG_PATH, encoding="utf-8-sig")
        val = cp2.get("web_query", "web_query_api_key", fallback="").strip()
        return val if val else None
    except Exception:
        return _WEB_QUERY_API_KEY


WEB_QUERY_API_KEY = _WEB_QUERY_API_KEY


class Database:
    """MySQL 数据库连接管理器（自动检测表字段）"""

    def __init__(self):
        self._conn = None
        self._fields = set()
        self._table_ok = False
        self._lock = threading.RLock()

    def _connect(self):
        if not MYSQL_PASSWORD:
            raise RuntimeError(
                "数据库连接失败：MYSQL_PASSWORD 为空。\n"
                "请在 MMS 主程序的系统配置中设置 MySQL 密码并保存，\n"
                "密码将存储到 config.ini 中供 Web 服务读取。"
            )
        try:
            self._conn = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE,
                charset=MYSQL_CHARSET,
                cursorclass=DictCursor,
                connect_timeout=5,
                read_timeout=10,
                write_timeout=10,
                autocommit=True,
            )
        except OperationalError as e:
            raise RuntimeError(
                f"数据库连接失败: {e}\n"
                "请检查系统配置中的 MySQL 主机、端口、用户名、密码及数据库名是否正确。"
            ) from e

    def _ensure_conn(self):
        with self._lock:
            try:
                if self._conn:
                    self._conn.ping(reconnect=True)
                    return
            except Exception:
                self._conn = None
            self._connect()

    def _detect_fields(self):
        with self._lock:
            if self._fields:
                return
            self._ensure_conn()
            try:
                with self._conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                        (MYSQL_DATABASE, TABLE_BORROW_RECORDS),
                    )
                    self._fields = {row["COLUMN_NAME"] for row in cursor.fetchall()}
                    self._table_ok = bool(self._fields)
            except Exception:
                self._fields = set()
                self._table_ok = False

    def _execute(self, sql: str, params: tuple = ()) -> List[Dict]:
        with self._lock:
            self._ensure_conn()
            try:
                with self._conn.cursor() as cursor:
                    cursor.execute(sql, params)
                    return cursor.fetchall()
            except OperationalError:
                self._connect()
                with self._conn.cursor() as cursor:
                    cursor.execute(sql, params)
                    return cursor.fetchall()

    def _execute_count(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            self._ensure_conn()
            try:
                with self._conn.cursor() as cursor:
                    cursor.execute(sql, params)
                    row = cursor.fetchone()
                    return row["count"] if row else 0
            except OperationalError:
                self._connect()
                with self._conn.cursor() as cursor:
                    cursor.execute(sql, params)
                    row = cursor.fetchone()
                    return row["count"] if row else 0

    def search_borrow_records(
        self,
        card_no: str = "",
        user_name: str = "",
        material_code: str = "",
        material_name: str = "",
        date_from: str = "",
        date_to: str = "",
        unreturned_only: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Dict], int]:
        with self._lock:
            self._detect_fields()
            if not self._table_ok:
                return [], 0

            conditions = []
            params = []

            if card_no:
                conditions.append("card_no LIKE %s")
                params.append(f"%{card_no}%")
            if user_name:
                conditions.append("user_name LIKE %s")
                params.append(f"%{user_name}%")
            if material_code:
                conditions.append("material_code LIKE %s")
                params.append(f"%{material_code}%")
            if material_name:
                conditions.append("material_name LIKE %s")
                params.append(f"%{material_name}%")
            if date_from:
                conditions.append("out_time >= %s")
                params.append(date_from)
            if date_to:
                conditions.append("out_time <= %s")
                params.append(date_to)
            if unreturned_only and "is_returned" in self._fields:
                conditions.append("(is_returned IS NULL OR is_returned = 0)")

            where = " AND ".join(conditions) if conditions else "1=1"

            count_sql = f"SELECT COUNT(*) as count FROM {_BORROW_TBL_SQL} WHERE {where}"
            total = self._execute_count(count_sql, tuple(params))

            order_parts = []
            if "out_time" in self._fields:
                order_parts.append("out_time DESC")
            if "created_at" in self._fields:
                order_parts.append("created_at DESC")
            if "id" in self._fields:
                order_parts.append("id DESC")
            order_by = ", ".join(order_parts) if order_parts else "id DESC"

            offset = max(0, (page - 1) * page_size)
            data_sql = (
                f"SELECT * FROM {_BORROW_TBL_SQL} "
                f"WHERE {where} "
                f"ORDER BY {order_by} "
                f"LIMIT %s OFFSET %s"
            )
            data_params = tuple(params) + (page_size, offset)
            records = self._execute(data_sql, data_params)

            return records, total

    def get_filtered_stats(
        self,
        card_no: str = "",
        user_name: str = "",
        material_code: str = "",
        material_name: str = "",
        date_from: str = "",
        date_to: str = "",
        unreturned_only: bool = False,
    ) -> Dict:
        with self._lock:
            self._detect_fields()
            if not self._table_ok:
                return {"total_count": 0, "unreturned_count": 0, "returned_count": 0}

            conditions = []
            params = []

            if card_no:
                conditions.append("card_no LIKE %s")
                params.append(f"%{card_no}%")
            if user_name:
                conditions.append("user_name LIKE %s")
                params.append(f"%{user_name}%")
            if material_code:
                conditions.append("material_code LIKE %s")
                params.append(f"%{material_code}%")
            if material_name:
                conditions.append("material_name LIKE %s")
                params.append(f"%{material_name}%")
            if date_from:
                conditions.append("out_time >= %s")
                params.append(date_from)
            if date_to:
                conditions.append("out_time <= %s")
                params.append(date_to)
            if unreturned_only and "is_returned" in self._fields:
                conditions.append("(is_returned IS NULL OR is_returned = 0)")

            where = " AND ".join(conditions) if conditions else "1=1"

            total_count = self._execute_count(
                f"SELECT COUNT(*) as count FROM {_BORROW_TBL_SQL} WHERE {where}",
                tuple(params),
            )

            unreturned_count = 0
            if "is_returned" in self._fields:
                unreturned_where = where + " AND (is_returned IS NULL OR is_returned = 0)"
                unreturned_count = self._execute_count(
                    f"SELECT COUNT(*) as count FROM {_BORROW_TBL_SQL} WHERE {unreturned_where}",
                    tuple(params),
                )

            returned_count = 0
            if "is_returned" in self._fields:
                returned_where = where + " AND is_returned = 1"
                returned_count = self._execute_count(
                    f"SELECT COUNT(*) as count FROM {_BORROW_TBL_SQL} WHERE {returned_where}",
                    tuple(params),
                )

            return {
                "total_count": total_count,
                "unreturned_count": unreturned_count,
                "returned_count": returned_count,
            }

    def close(self):
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None


db = Database()