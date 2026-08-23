"""同步引擎模块
负责云端(MySQL)与本地数据的同步：拉取、推送、冲突检测

网络 IO 全部在后台线程中执行，不阻塞主线程 UI。
"""
import json
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Callable
from PySide6.QtCore import QObject, Signal, QTimer, QThread, Slot

from config import (
    SYNC_INTERVAL_SECONDS, SYNC_RETRY_MAX, SYNC_BATCH_SIZE,
    FULL_SYNC_INTERVAL_MINUTES, LOCAL_DB_PATH,
    TABLE_MATERIALS, TABLE_BORROW_RECORDS, TABLE_FIXED_ASSETS,
    TABLE_CONFIG_ITEMS, TABLE_USERS, TABLE_EMPLOYEE_RECORDS,
)
from logger import get_logger

_log = get_logger(__name__)


class SyncWorker(QObject):
    """后台工作线程：只执行网络 IO，不触碰主线程的 SQLite

    持有独立的 MySQLClient 实例（在 Worker 线程中初始化），
    所有网络请求都在工作线程中顺序执行，主线程保持响应。
    """

    # 结果信号（Worker → Engine，跨线程安全）
    health_result = Signal(bool)                 # 网络是否可达
    push_result = Signal(object, int, str)       # results, total_pushed, error
    pull_result = Signal(str, object, str)      # table, records, error
    full_sync_result = Signal(str, object, str)  # table, records, error

    def __init__(self):
        super().__init__()
        self._mysql = None
        self._sync_tables = [
            TABLE_MATERIALS, TABLE_BORROW_RECORDS, TABLE_FIXED_ASSETS,
            TABLE_CONFIG_ITEMS, TABLE_USERS, TABLE_EMPLOYEE_RECORDS,
        ]

    def _ensure_init(self):
        """懒加载：确保在 Worker 线程中初始化 MySQLClient"""
        if self._mysql is not None:
            return
        from mysql_client import MySQLClient
        self._mysql = MySQLClient()

    # ---------- 槽函数：由 Engine 通过信号触发（跨线程） ----------

    @Slot()
    def check_health(self):
        """检测网络及 MySQL 连通性（后台线程执行，不阻塞主线程）"""
        self._ensure_init()
        try:
            self._mysql._ensure_conn()  # 尝试建立/恢复连接
            ok = self._mysql.health_check()
            self.health_result.emit(ok)
        except (RuntimeError, OSError, ValueError) as e:
            _log.warning("健康检查失败: %s", e)
            self.health_result.emit(False)
        except Exception as e:
            _log.warning("健康检查未预期异常: %s", e)
            self.health_result.emit(False)

    @Slot(list)
    def push_items(self, queue_items: list):
        """推送队列项到云端(MySQL)"""
        self._ensure_init()
        results = []
        total = 0
        error_msg = ""
        try:
            for item in queue_items:
                success, conflict_info = self._process_item(item)
                # 冲突时视为已处理（云端版本优先），同时传回冲突信息
                if conflict_info is not None:
                    success = True
                results.append((
                    item["id"], success, conflict_info,
                    "" if success else "网络异常"
                ))
                if success:
                    total += 1
        except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            error_msg = str(e)
            _log.error("推送批量失败: %s", e)
        except Exception as e:
            error_msg = str(e)
            _log.error("推送批量未预期异常: %s", e)
        self.push_result.emit(results, total, error_msg)

    @Slot(str, str, str)
    def pull_table(self, table: str, last_sync: str, workshop: str):
        self._ensure_init()
        self._mysql.set_workshop(workshop)
        try:
            if last_sync:
                records = self._mysql.fetch_since(table, last_sync)
            else:
                records = self._mysql.fetch_all(table)
            self.pull_result.emit(table, records or [], "")
        except (RuntimeError, OSError, ValueError) as e:
            err_msg = str(e)
            _log.error("拉取 %s 失败: %s", table, err_msg)
            self.pull_result.emit(table, [], err_msg)
        except Exception as e:
            err_msg = str(e)
            _log.error("拉取 %s 未预期异常: %s", table, err_msg)
            self.pull_result.emit(table, [], err_msg)

    @Slot(str, str)
    def full_sync_table(self, table: str, workshop: str):
        self._ensure_init()
        self._mysql.set_workshop(workshop)
        try:
            records = self._mysql.fetch_all(table)
            self.full_sync_result.emit(table, records or [], "")
        except (RuntimeError, OSError, ValueError) as e:
            err_msg = str(e)
            _log.error("全量同步 %s 失败: %s", table, err_msg)
            self.full_sync_result.emit(table, [], err_msg)
        except Exception as e:
            err_msg = str(e)
            _log.error("全量同步 %s 未预期异常: %s", table, err_msg)
            self.full_sync_result.emit(table, [], err_msg)

    # ---------- 内部处理 ----------

    def _process_item(self, item: Dict) -> tuple:
        """处理单条同步队列项

        返回: (success: bool, conflict_info: dict or None)
        """
        table = item["table_name"]
        operation = item["operation"]
        record_id = item["record_id"]
        payload = json.loads(item["payload"])
        try:
            if operation == "INSERT":
                existing = self._mysql.fetch_by_id(table, record_id)
                if existing is None and self._mysql.is_connected():
                    _log.debug("表 %s 记录 %s 不存在，尝试插入", table, record_id)
                    pass
                if existing:
                    conflict = self._check_conflict(table, record_id, existing, payload)
                    if conflict:
                        return True, conflict
                    result = self._mysql.update(table, record_id, payload)
                    if result is None:
                        _log.warning("INSERT 转为 UPDATE 失败: %s/%s", table, record_id)
                        return False, None
                else:
                    # 业务唯一字段查重（如 asset_no / material_code）
                    biz_key, biz_col = self._get_biz_unique_key(table, payload)
                    if biz_key and biz_col:
                        dup = self._mysql.fetch_by_condition(table, biz_col, biz_key)
                        if dup:
                            dup_id = dup[0].get("id", record_id)
                            conflict = self._check_conflict(table, dup_id, dup[0], payload)
                            if conflict:
                                return True, conflict
                            result = self._mysql.update(table, dup_id, payload)
                            if result is None:
                                _log.warning("业务键查重后 UPDATE 失败: %s/%s", table, record_id)
                                return False, None
                            return True, None
                    result = self._mysql.insert(table, payload)
                    if result is None:
                        _log.warning("INSERT 失败: %s/%s", table, record_id)
                        return False, None
            elif operation == "UPDATE":
                existing = self._mysql.fetch_by_id(table, record_id)
                if existing is None and self._mysql.is_connected():
                    _log.debug("表 %s 记录 %s 在 MySQL 不存在，跳过 UPDATE", table, record_id)
                    return True, None
                if existing:
                    conflict = self._check_conflict(table, record_id, existing, payload)
                    if conflict:
                        return True, conflict
                    result = self._mysql.update(table, record_id, payload)
                    if result is None:
                        _log.warning("UPDATE 失败: %s/%s", table, record_id)
                        return False, None
                else:
                    result = self._mysql.insert(table, payload)
                    if result is None:
                        _log.warning("UPDATE 转为 INSERT 失败: %s/%s", table, record_id)
                        return False, None
            elif operation == "DELETE":
                result = self._mysql.delete(table, record_id)
                if not result:
                    _log.warning("DELETE 失败: %s/%s", table, record_id)
                    return False, None
            return True, None
        except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            _log.warning("同步处理失败: %s/%s/%s — %s", table, operation, record_id, e, exc_info=True)
            return False, None
        except Exception as e:
            _log.warning("同步处理未预期异常: %s/%s/%s — %s", table, operation, record_id, e, exc_info=True)
            return False, None

    @staticmethod
    def _get_biz_unique_key(table: str, payload: Dict) -> tuple:
        """获取业务唯一键（字段名, 值），用于 INSERT 前查重

        返回 (key_value, key_column) 或 (None, None)
        """
        biz_keys = {
            TABLE_FIXED_ASSETS: ("asset_no", "asset_no"),
            TABLE_MATERIALS: ("material_code", "material_code"),
            TABLE_CONFIG_ITEMS: ("config_name", "config_name"),
        }
        if table in biz_keys:
            col, alias = biz_keys[table]
            if col in payload and payload[col]:
                return (payload[col], alias)
        return (None, None)

    def _check_conflict(self, table: str, record_id: str,
                        cloud_record: Dict, local_payload: Dict) -> Optional[Dict]:
        """冲突检测：云端版本比本地更新时发生

        仅检测，不写入本地 SQLite（避免跨线程并发写）。
        冲突信息回传主线程后由 Engine 统一处理本地覆盖。
        """
        from utils.helpers import parse_datetime_flexible

        cloud_time = parse_datetime_flexible(cloud_record.get("updated_at") or cloud_record.get("created_at"))
        local_time = parse_datetime_flexible(local_payload.get("updated_at") or local_payload.get("created_at"))
        if cloud_time and local_time and cloud_time > local_time:
            conflict_fields = []
            for key in local_payload:
                if key in cloud_record and cloud_record[key] != local_payload[key]:
                    conflict_fields.append(key)
            if conflict_fields:
                return {
                    "table": table,
                    "record_id": record_id,
                    "cloud": cloud_record,
                    "local": local_payload,
                    "fields": conflict_fields,
                }
        return None


class SyncEngine(QObject):
    """同步引擎 - 主线程控制器

    所有网络 IO 通过 SyncWorker 在后台线程执行，
    本地 SQLite 操作在主线程完成，避免并发写冲突。
    """

    # 对外信号（供 MainWindow 连接，保持不变）
    sync_started = Signal(str)
    sync_completed = Signal(str, int)
    sync_failed = Signal(str, str)
    sync_status_changed = Signal(str)
    batch_conflict_detected = Signal(object)
    queue_updated = Signal(int)

    STATUS_ONLINE = "online"
    STATUS_OFFLINE = "offline"
    STATUS_SYNCING = "syncing"

    # 内部调度信号（Engine → Worker，跨线程）
    _request_health_check = Signal()
    _request_push = Signal(object)
    _request_pull = Signal(str, str, str)
    _request_full_sync = Signal(str, str)

    def __init__(self, mysql_client, local_db, workshop: str = None):
        super().__init__()
        self._main_thread = QThread.currentThread()
        self.mysql_client = mysql_client
        self.local_db = local_db
        self._workshop = workshop or ""
        self._sync_status: str = self.STATUS_OFFLINE
        self._is_running: bool = False
        self._timer: Optional[QTimer] = None
        self._full_sync_timer: Optional[QTimer] = None
        self._on_conflict_callback: Optional[Callable] = None
        self._sync_tables = [
            TABLE_MATERIALS, TABLE_BORROW_RECORDS, TABLE_FIXED_ASSETS,
            TABLE_CONFIG_ITEMS, TABLE_USERS, TABLE_EMPLOYEE_RECORDS,
        ]

        # 创建后台工作线程
        self._worker_thread = QThread()
        self._worker = SyncWorker()
        self._worker.moveToThread(self._worker_thread)

        # 连接 Worker 结果信号 → Engine 槽
        self._worker.health_result.connect(self._on_worker_health)
        self._worker.push_result.connect(self._on_worker_push_result)
        self._worker.pull_result.connect(self._on_worker_pull_result)
        self._worker.full_sync_result.connect(self._on_worker_full_sync_result)

        # 连接 Engine 调度信号 → Worker 槽
        self._request_health_check.connect(self._worker.check_health)
        self._request_push.connect(self._worker.push_items)
        self._request_pull.connect(self._worker.pull_table)
        self._request_full_sync.connect(self._worker.full_sync_table)

        self._worker_thread.start()

        # 同步流程控制状态
        self._pull_table_index = 0
        self._pull_total = 0
        self._full_sync_pending: set = set()  # 全量同步中待处理的表集合
        self._full_sync_total = 0
        self._full_sync_failed: list = []
        # 已全量拉取但云端返回空的表集合：避免对云端空表的重复全量拉取
        # 当本地有数据或全量同步触发时清空，重新尝试
        self._empty_pull_tables: set = set()

    def _assert_main_thread(self):
        """架构约束：所有 LocalDB 操作必须在主线程执行。
        SyncWorker（后台线程）只发射信号，由 Engine 的 Slot 在主线程中处理本地数据。
        生产环境无开销（QThread 比较是 O(1)）。
        """
        assert QThread.currentThread() == self._main_thread, \
            f"LocalDB 操作必须在主线程，当前线程: {QThread.currentThread()}"

    @property
    def sync_status(self) -> str:
        return self._sync_status

    def set_conflict_callback(self, callback: Callable):
        self._on_conflict_callback = callback

    def start(self):
        if self._is_running:
            return
        self._is_running = True
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._sync_cycle)
        self._timer.start(SYNC_INTERVAL_SECONDS * 1000)
        if self._full_sync_timer is None:
            self._full_sync_timer = QTimer(self)
            self._full_sync_timer.timeout.connect(self._full_sync)
        self._full_sync_timer.start(FULL_SYNC_INTERVAL_MINUTES * 60 * 1000)
        self._sync_cycle()

    def pause_auto_sync(self):
        """暂停自动定时同步（半离线模式使用）
        停止定时器但保持 Worker 线程，force_sync() 仍可手动触发"""
        self._is_running = False
        if self._timer:
            self._timer.stop()
        if self._full_sync_timer:
            self._full_sync_timer.stop()
        self._set_status(self.STATUS_OFFLINE)

    def resume_auto_sync(self):
        """恢复自动定时同步（从半离线切回在线模式使用）"""
        if self._is_running:
            return
        self._is_running = True
        # 确保 Worker 线程仍在运行
        if not self._worker_thread.isRunning():
            self._worker_thread.start()
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._sync_cycle)
        self._timer.start(SYNC_INTERVAL_SECONDS * 1000)
        if self._full_sync_timer is None:
            self._full_sync_timer = QTimer(self)
            self._full_sync_timer.timeout.connect(self._full_sync)
        self._full_sync_timer.start(FULL_SYNC_INTERVAL_MINUTES * 60 * 1000)
        self._sync_cycle()

    def stop(self):
        """完全停止同步引擎（离线模式使用）"""
        self._is_running = False
        if self._timer:
            self._timer.stop()
            self._timer = None
        if self._full_sync_timer:
            self._full_sync_timer.stop()
            self._full_sync_timer = None
        # 确保 worker 线程中的事件处理完毕后再退出
        if self._worker_thread.isRunning():
            self._worker_thread.quit()
            if not self._worker_thread.wait(5000):
                self._worker_thread.terminate()
                self._worker_thread.wait(1000)

    def _set_status(self, status: str):
        if self._sync_status != status:
            self._sync_status = status
            self.sync_status_changed.emit(status)

    # ---------- 同步周期调度 ----------

    def _sync_cycle(self):
        """触发同步周期：先健康检查 → 推 → 拉"""
        self._request_health_check.emit()

    def refresh_pull(self):
        """刷新专用：只拉取不推送，不依赖定时器"""
        if not self._is_running:
            return
        self._set_status(self.STATUS_SYNCING)
        self._start_pull()

    def _on_worker_health(self, ok: bool):
        """Worker 健康检查完成 — Qt Slot，运行在主线程"""
        self._assert_main_thread()
        if not ok:
            self._set_status(self.STATUS_OFFLINE)
            return
        self._set_status(self.STATUS_SYNCING)
        # 先推送
        queue = self.local_db.get_sync_queue(SYNC_BATCH_SIZE)
        if queue:
            self.sync_started.emit("push")
            self._request_push.emit(queue)
        else:
            # 无推送，直接拉取
            self._start_pull()

    def _start_pull(self):
        """开始拉取流程"""
        self._pull_table_index = 0
        self._pull_total = 0
        self.sync_started.emit("pull")
        self._pull_next_table()

    def _pull_next_table(self):
        """拉取下一张表（智能基准选择：本地为空→全量，否则→取本地最新时间为增量基准）"""
        if self._pull_table_index >= len(self._sync_tables):
            # 拉取完成
            self.local_db.add_sync_log("pull", "success", self._pull_total)
            self.sync_completed.emit("cycle", self._pull_total)
            self._set_status(self.STATUS_ONLINE)
            self.queue_updated.emit(self.local_db.get_sync_queue_count())
            return

        table = self._sync_tables[self._pull_table_index]

        # 智能基准选择
        local_count = self.local_db.get_table_count(table)
        if local_count == 0:
            # 本地为空，但上次全量拉取已确认云端也为空 → 跳过，避免无意义的重复请求
            if table in self._empty_pull_tables:
                _log.debug("表 %s 本地为空，云端上次已确认无数据，跳过拉取", table)
                self._pull_table_index += 1
                self._pull_next_table()
                return
            # 本地为空 → 强制全量拉取（避免 sync_log 有旧记录导致只拉增量）
            _log.info("表 %s 本地为空，强制全量拉取", table)
            self._request_pull.emit(table, "", self._workshop)
        else:
            # 本地有数据 → 从空表集合中移除（可能之前云端为空，现在有数据了）
            self._empty_pull_tables.discard(table)
            # 取两个时间中较早的一个作为基准，确保不漏数据：
            # - 本地表最新 updated_at（数据层面的基准，更准确）
            # - sync_log 上次成功拉取时间（流程层面的基准）
            local_latest = self.local_db.get_table_max_updated_at(table)
            sync_time = self.local_db.get_last_sync_time("pull")
            # 取较早的时间作为基准（宁可多拉，不可漏拉）
            if local_latest and sync_time:
                last_sync = local_latest if local_latest < sync_time else sync_time
            else:
                last_sync = local_latest or sync_time or ""
            _log.debug("表 %s 增量拉取基准: local=%s sync=%s 使用=%s",
                       table, local_latest, sync_time, last_sync)
            self._request_pull.emit(table, last_sync, self._workshop)

    def _on_worker_push_result(self, results: list, total: int, error: str):
        """Worker 推送完成回调 — Qt Slot，运行在主线程"""
        self._assert_main_thread()
        # 防御：确保 results 为 list，total 为 int，避免 None 等异常值
        if results is None:
            results = []
        elif not isinstance(results, list):
            _log.warning("push_result 收到非 list results: %r", type(results))
            results = []
        if not isinstance(total, int):
            try:
                total = int(total) if total is not None else 0
            except (TypeError, ValueError):
                total = 0

        if error:
            self.sync_failed.emit("push", error)
            self.local_db.add_sync_log("push", "failed", 0, error)

        conflicts = []
        for queue_id, success, conflict_info, _ in results:
            if conflict_info is not None:
                # 冲突：记录冲突信息，稍后三路合并处理
                conflicts.append(conflict_info)
                self.local_db.remove_sync_queue(queue_id)
            elif success:
                # 推送成功：保存快照作为下次三路合并的基线
                item = self.local_db.get_sync_queue_item(queue_id)
                if item:
                    payload = json.loads(item["payload"])
                    self.local_db.save_snapshot(item["table_name"], item["record_id"], payload)
                self.local_db.remove_sync_queue(queue_id)
            else:
                self.local_db.increment_retry(queue_id)
                updated = self.local_db.get_sync_queue_item(queue_id)
                current_retry = updated["retry_count"] if updated else 999
                if current_retry >= SYNC_RETRY_MAX:
                    _log.warning("推送记录重试超限，已丢弃: %s/%s (重试 %d 次)",
                                 updated.get("table_name", "?"), updated.get("record_id", "?"), current_retry)
                    self.local_db.remove_sync_queue(queue_id)
                    self.local_db.add_sync_log("push", "failed", 0,
                                               f"记录重试超限: {updated.get('table_name', '?')}/{updated.get('record_id', '?')}")

        # 三路合并处理冲突：有基线的可自动合并，无基线或真正冲突时云端优先
        conflict_tables = set()
        for conflict in conflicts:
            table = conflict["table"]
            record_id = conflict["record_id"]
            cloud_record = conflict["cloud"]
            local_payload = conflict["local"]

            base = self.local_db.get_snapshot(table, record_id)
            if base:
                result = self._three_way_merge(base, local_payload, cloud_record)
                if result["action"] == "merge":
                    # 自动合并：本地和云端改了不同字段，合并后写入本地
                    merged = self._convert_record(result["merged"])
                    self.local_db.update(table, record_id, merged)
                    self.local_db.save_snapshot(table, record_id, merged)
                    _log.info("三路合并自动合并: %s/%s", table, record_id)
                    continue
                elif result["action"] == "noop":
                    # 三方一致，仅更新快照时间戳
                    self.local_db.save_snapshot(table, record_id, self._convert_record(cloud_record))
                    continue
                # conflict: 真正冲突（同一字段两边都变了），云端优先
                _log.info("检测到真正冲突，云端版本优先: %s/%s 冲突字段: %s",
                          table, record_id, result.get("fields", []))

            # 无基线或真正冲突 → 云端版本优先，更新快照
            conflict_tables.add(table)
            self.local_db.update(table, record_id, self._convert_record(cloud_record))
            self.local_db.save_snapshot(table, record_id, self._convert_record(cloud_record))

        # 发送冲突通知（主窗口在状态栏显示提示）
        if conflict_tables:
            self.batch_conflict_detected.emit({"tables": list(conflict_tables)})

        if total > 0 and not error:
            self.local_db.add_sync_log("push", "success", total)

        # 推送完继续拉取
        self._start_pull()

    def _on_worker_pull_result(self, table: str, records: list, error: str):
        """Worker 单表拉取完成回调 — Qt Slot，运行在主线程"""
        self._assert_main_thread()
        # 防御：确保 records 为 list，避免 None 等异常值触发 Shiboken NoneType 转换
        if records is None:
            records = []
        elif not isinstance(records, list):
            _log.warning("pull_result 收到非 list records: %r", type(records))
            records = []

        if error:
            self.sync_failed.emit("pull", f"{table}: {error}")
            self.local_db.add_sync_log("pull", "failed", 0, f"{table}: {error}")
        elif records:
            converted = [self._convert_record(r) for r in records]
            self.local_db.batch_insert(table, converted)
            self.local_db.save_snapshots_batch(table, converted)
            self._pull_total += len(records)
        else:
            # 云端返回空列表：记录到空表集合，避免下次同步重复全量拉取
            local_count = self.local_db.get_table_count(table)
            if local_count == 0:
                self._empty_pull_tables.add(table)
                _log.info("表 %s 云端无数据，本地仍为空，下次同步将跳过", table)

        self._pull_table_index += 1
        self._pull_next_table()

    # ---------- 全量同步 ----------

    def _full_sync(self):
        """全量同步：逐表拉取并替换本地数据"""
        self._full_sync_pending = set(self._sync_tables)  # 跟踪未完成的表
        self._full_sync_total = 0
        self._full_sync_failed = []
        self._empty_pull_tables.clear()  # 清空空表记录，全量同步时重新尝试所有表
        self.sync_started.emit("full_sync")
        for table in self._sync_tables:
            self._request_full_sync.emit(table, self._workshop)

    def _on_worker_full_sync_result(self, table: str, records: list, error: str):
        """Worker 全量同步单表完成回调 — Qt Slot，运行在主线程"""
        self._assert_main_thread()
        # 防御：确保 records 为 list，避免 None 等异常值
        if records is None:
            records = []
        elif not isinstance(records, list):
            _log.warning("full_sync_result 收到非 list records: %r", type(records))
            records = []

        if error:
            _log.error("全量同步表 %s 失败，保留旧数据: %s", table, error)
            self._full_sync_failed.append(table)
        elif records:
            converted = [self._convert_record(r) for r in records]
            try:
                self.local_db.replace_table_transactional(table, converted)
                self.local_db.save_snapshots_batch(table, converted)
                self._full_sync_total += len(records)
            except (RuntimeError, sqlite3.Error, OSError, ValueError) as e:
                _log.error("全量同步表 %s 本地替换失败: %s", table, e)
                self._full_sync_failed.append(table)
            except Exception as e:
                _log.error("全量同步表 %s 本地替换未预期异常: %s", table, e)
                self._full_sync_failed.append(table)

        self._full_sync_pending.discard(table)  # 标记该表已完成
        if not self._full_sync_pending:  # 所有表都有了响应
            # 全部完成
            if self._full_sync_failed:
                self.local_db.add_sync_log(
                    "pull", "full_sync_partial", self._full_sync_total,
                    f"部分表失败: {','.join(self._full_sync_failed)}"
                )
            else:
                self.local_db.add_sync_log(
                    "pull", "full_sync", self._full_sync_total, "全量同步完成"
                )
            self.sync_completed.emit("full_sync", self._full_sync_total)

    # ---------- 本地操作（主线程，快速）----------

    def offline_insert(self, table: str, record_id: str, data: Dict,
                         add_to_queue: bool = True):
        self.local_db.insert(table, self._convert_record(data))
        if add_to_queue:
            self.local_db.add_sync_queue(table, "INSERT", record_id, data)
            self.queue_updated.emit(self.local_db.get_sync_queue_count())

    def offline_update(self, table: str, record_id: str, data: Dict,
                       add_to_queue: bool = True):
        self.local_db.update(table, record_id, self._convert_record(data))
        if add_to_queue:
            self.local_db.add_sync_queue(table, "UPDATE", record_id, data)
            self.queue_updated.emit(self.local_db.get_sync_queue_count())

    def offline_delete(self, table: str, record_id: str,
                       add_to_queue: bool = True):
        self.local_db.delete(table, record_id)
        if add_to_queue:
            self.local_db.add_sync_queue(table, "DELETE", record_id, {})
            self.queue_updated.emit(self.local_db.get_sync_queue_count())

    @staticmethod
    def _convert_record(record: Dict) -> Dict:
        """转换记录类型，保持数值语义；确保中文编码正确"""
        converted = {}
        for key, value in record.items():
            if value is None:
                converted[key] = None
            elif isinstance(value, bool):
                converted[key] = 1 if value else 0
            elif isinstance(value, (int, float)):
                converted[key] = value
            elif isinstance(value, bytes):
                # 处理 pymysql 可能返回的 bytes 类型（如编码异常时）
                try:
                    converted[key] = value.decode("utf-8")
                except UnicodeDecodeError:
                    converted[key] = value.decode("utf-8", errors="replace")
            else:
                converted[key] = str(value)
        return converted

    @staticmethod
    def _three_way_merge(base: Dict, local: Dict, cloud: Dict) -> Dict:
        """三路合并：比较 local/cloud 分别相对于 base 的变化

        Returns:
            {"action": "merge", "merged": {...}}  — 自动合并，无冲突
            {"action": "conflict", "fields": [...]} — 真正冲突（同一字段两边都变了）
            {"action": "noop"}                     — 三方一致，无需操作
        """
        _SKIP_KEYS = {"id", "created_at", "updated_at"}

        local_changes = {}
        for key, value in local.items():
            if key in _SKIP_KEYS:
                continue
            if key in base and value != base[key]:
                local_changes[key] = value
            elif key not in base and value is not None:
                local_changes[key] = value

        cloud_changes = {}
        for key, value in cloud.items():
            if key in _SKIP_KEYS:
                continue
            if key in base and value != base[key]:
                cloud_changes[key] = value
            elif key not in base and value is not None:
                cloud_changes[key] = value

        conflict_fields = set(local_changes.keys()) & set(cloud_changes.keys())
        if conflict_fields:
            return {"action": "conflict", "fields": list(conflict_fields)}

        if not local_changes and not cloud_changes:
            return {"action": "noop"}

        # 自动合并：基线 + 本地变更 + 云端变更（无交集，可安全合并）
        merged = dict(base)
        merged.update(local_changes)
        merged.update(cloud_changes)
        merged["updated_at"] = datetime.now().isoformat()
        return {"action": "merge", "merged": merged}

    def force_sync(self):
        if not self._is_running:
            return
        self._sync_cycle()
