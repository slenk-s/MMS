"""Toast 轻提示组件
用于成功、警告、错误等简单提示，右上角淡入淡出，不阻塞操作
"""
import enum
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, QPoint
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QApplication
from PySide6.QtGui import QFont


class ToastLevel(enum.Enum):
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"


LEVEL_STYLE = {
    ToastLevel.SUCCESS: {
        "bg": "#ecfdf5",
        "border": "#10b981",
        "text": "#065f46",
        "icon": "🎉",
    },
    ToastLevel.WARNING: {
        "bg": "#fffbeb",
        "border": "#f59e0b",
        "text": "#92400e",
        "icon": "⚠️",
    },
    ToastLevel.ERROR: {
        "bg": "#fef2f2",
        "border": "#ef4444",
        "text": "#991b1b",
        "icon": "❌",
    },
    ToastLevel.INFO: {
        "bg": "#eff6ff",
        "border": "#3b82f6",
        "text": "#1e40af",
        "icon": "ℹ️",
    },
}


class Toast(QFrame):
    """Toast 通知：窗口水平居中，距离顶部 52px，淡入淡出，不阻塞操作"""

    def __init__(self, parent, message: str, level: ToastLevel = ToastLevel.INFO, duration: int = 2000):
        super().__init__(parent)
        self._parent = parent
        self._message = message
        self._duration = duration
        self._level = level
        self._opacity = 0.0
        self._init_ui()
        self._position()
        self._setup_animation()
        self._show_and_auto_hide()

    def _init_ui(self):
        style = LEVEL_STYLE[self._level]
        self.setStyleSheet(f"""
            Toast {{
                background-color: {style['bg']};
                border: none;
                border-radius: 8px;
                padding: 0px;
            }}
            QLabel {{
                color: {style['text']};
                background: transparent;
                border: none;
            }}
        """)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        icon_lbl = QLabel(style["icon"])
        icon_lbl.setStyleSheet(f"font-size: 18px; color: {style['text']}; background: transparent;")
        layout.addWidget(icon_lbl)

        msg_lbl = QLabel(self._message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setFont(QFont("Microsoft YaHei", 12))
        msg_lbl.setStyleSheet(f"color: {style['text']}; background: transparent; border: none;")
        layout.addWidget(msg_lbl, 1)

        self.setMinimumWidth(260)
        self.setMaximumWidth(420)

    def _get_screen_pos(self):
        """计算 Toast 在屏幕上的正确位置：主窗口水平居中，紧贴顶部"""
        self.adjustSize()
        w = self.width()
        # 获取顶层主窗口（QMainWindow）作为定位基准
        top = self._parent.window() if self._parent else None
        if top and top.isVisible():
            parent_pos = top.mapToGlobal(QPoint(0, 0))
            x = parent_pos.x() + (top.width() - w) // 2
            y = parent_pos.y() + 0  # 紧贴主窗口顶部
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            x = (screen.width() - w) // 2
            y = 0
        return x, y

    def _position(self):
        x, y = self._get_screen_pos()
        self.move(x, y + 24)

    def _setup_animation(self):
        self._fade_in = QPropertyAnimation(self, b"windowOpacity")
        self._fade_in.setDuration(300)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.InOutQuad)

        self._fade_out = QPropertyAnimation(self, b"windowOpacity")
        self._fade_out.setDuration(400)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade_out.finished.connect(self.close)

    def _show_and_auto_hide(self):
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._fade_in.start()
        QTimer.singleShot(self._duration, self._fade_out.start)


class ToastManager:
    """Toast 管理器，避免多个 Toast 重叠"""
    _queue = []
    _gap = 56  # 垂直间距

    @classmethod
    def show(cls, parent, message: str, level: ToastLevel = ToastLevel.INFO, duration: int = 2000):
        toast = Toast(parent, message, level, duration)
        cls._queue.append(toast)
        cls._reposition()
        toast._fade_out.finished.connect(lambda: cls._remove(toast))
        return toast

    @classmethod
    def _reposition(cls):
        # ????????? C++ ???login_view fade_out ????? Toast?
        alive = []
        for item in cls._queue:
            try:
                if item and hasattr(item, "_parent") and item._parent is not None and item.isVisible():
                    alive.append(item)
            except (RuntimeError, AttributeError):
                continue
        cls._queue = alive
        if not cls._queue:
            return
        try:
            first = cls._queue[0]
            base_y = first.y()
        except (RuntimeError, AttributeError):
            cls._queue.clear()
            return
        for i, t in enumerate(cls._queue):
            t.adjustSize()
            # 用顶层主窗口重新水平居中
            top = t._parent.window() if t._parent else None
            if top and top.isVisible():
                parent_pos = top.mapToGlobal(QPoint(0, 0))
                x = parent_pos.x() + (top.width() - t.width()) // 2
            else:
                screen = QApplication.primaryScreen().availableGeometry()
                x = (screen.width() - t.width()) // 2
            t.move(x, base_y + i * cls._gap)

    @classmethod
    def _remove(cls, toast):
        if toast in cls._queue:
            cls._queue.remove(toast)
            cls._reposition()


def toast_success(parent, message: str, duration: int = 2000):
    ToastManager.show(parent, message, ToastLevel.SUCCESS, duration)


def toast_warning(parent, message: str, duration: int = 2500):
    ToastManager.show(parent, message, ToastLevel.WARNING, duration)


def toast_error(parent, message: str, duration: int = 3000):
    ToastManager.show(parent, message, ToastLevel.ERROR, duration)


def toast_info(parent, message: str, duration: int = 2000):
    ToastManager.show(parent, message, ToastLevel.INFO, duration)
