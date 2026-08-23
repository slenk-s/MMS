"""
网络监测模块（QThread 优化版）
检测网络连接状态，管理在线/离线切换

优化点：
1. 单后台 QThread 长期运行，避免频繁创建销毁线程
2. 内部 QTimer 做周期性检测，结果通过信号传回主线程
3. 抖动抑制：连续稳定后才切换状态
4. v20: 修复跨线程停止 QTimer 的安全问题
"""
import socket
from typing import Optional
from PySide6.QtCore import QObject, Signal, QTimer, QThread, QMetaObject, Qt, Slot

from config import NETWORK_CHECK_INTERVAL_SECONDS, NETWORK_CHECK_TIMEOUT_SECONDS, NETWORK_STABLE_THRESHOLD
from logger import get_logger

_log = get_logger(__name__)


class _NetworkWorker(QObject):
    """后台 Worker：在独立线程中执行网络检测"""

    check_done = Signal(bool)

    def __init__(self, check_host: str, check_port: int, parent=None):
        super().__init__(parent)
        self.check_host = check_host
        self.check_port = check_port
        self._timer: Optional[QTimer] = None
        self._should_stop = False

    def start(self):
        self._should_stop = False
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._do_check)
        self._timer.start(NETWORK_CHECK_INTERVAL_SECONDS * 1000)
        self._do_check()  # 立即检测一次

    @Slot()
    def stop_timer_sync(self):
        """在 Worker 线程中同步停止定时器（由主线程通过 invokeMethod 调用）"""
        self._should_stop = True
        if self._timer and self._timer.isActive():
            self._timer.stop()

    def stop(self):
        """安全停止：在主线程中调用，通过 invokeMethod 同步在 Worker 线程中停止定时器"""
        self._should_stop = True
        # 同步调用：确保 timer 在 Worker 线程中已停止后再返回
        if self._timer and self._timer.isActive():
            QMetaObject.invokeMethod(self, "stop_timer_sync", Qt.BlockingQueuedConnection)

    def _do_check(self):
        """执行 TCP 连通性检测"""
        if self._should_stop:
            return
        result = False
        # 保存并恢复全局默认超时，避免影响其他模块
        saved_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(NETWORK_CHECK_TIMEOUT_SECONDS)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((self.check_host, self.check_port))
                result = True
        except OSError:
            pass
        finally:
            socket.setdefaulttimeout(saved_timeout)

        self.check_done.emit(result)


class NetworkMonitor(QObject):
    """网络状态监测器 - QThread 优化版

    内部维护单后台线程，避免高频创建销毁 threading.Thread。
    """

    online = Signal()                  # 网络恢复信号
    offline = Signal()                 # 网络断开信号
    status_changed = Signal(bool)      # 状态变更信号（参数：是否在线）

    # 抖动抑制阈值（连续稳定多少次才切换，避免频繁同步）
    _STABLE_THRESHOLD = NETWORK_STABLE_THRESHOLD

    def __init__(self, check_host: str = "8.8.8.8", check_port: int = 53):
        super().__init__()
        self.check_host = check_host
        self.check_port = check_port
        self._is_online: bool = False
        self._stable_count: int = self._STABLE_THRESHOLD
        self._last_state: bool = False
        self._is_started = False

        # 创建后台线程和 Worker
        self._thread = QThread(self)
        self._worker = _NetworkWorker(check_host, check_port)
        self._worker.moveToThread(self._thread)
        self._worker.check_done.connect(self._handle_result)
        self._thread.started.connect(self._worker.start)

    @property
    def is_online(self) -> bool:
        """当前网络状态"""
        return self._is_online

    def start(self):
        """启动网络监测（安全：多次调用不重复启动）"""
        if self._is_started:
            return
        self._is_started = True
        if not self._thread.isRunning():
            self._thread.start()
        else:
            # 线程已运行，直接启动 Worker
            QMetaObject.invokeMethod(self._worker, "start", Qt.QueuedConnection)

    def stop(self):
        """停止网络监测（安全：多次调用不重复停止）"""
        if not self._is_started:
            return
        self._is_started = False
        if self._thread.isRunning():
            self._worker.stop()
            self._thread.quit()
            if not self._thread.wait(3000):
                self._thread.terminate()  # 强制终止
                self._thread.wait(1000)

    def _handle_result(self, is_reachable: bool):
        """在主线程处理检测结果 + 抖动抑制"""
        # 防御：确保 is_reachable 为 bool 类型，避免 None 等异常值触发 Shiboken 警告
        if not isinstance(is_reachable, bool):
            _log.warning("网络检测收到非布尔结果: %r", is_reachable)
            is_reachable = bool(is_reachable)

        # 状态发生变化，重置计数
        if is_reachable != self._last_state:
            self._last_state = is_reachable
            self._stable_count = 1
            return

        # 状态未变，增加稳定计数
        self._stable_count += 1
        if self._stable_count < self._STABLE_THRESHOLD:
            return

        # 连续稳定达到阈值，触发状态切换
        if is_reachable != self._is_online:
            self._is_online = is_reachable
            self.status_changed.emit(is_reachable)
            if is_reachable:
                self.online.emit()
            else:
                self.offline.emit()
