"""?????? v2.4 ??????? config.ini
????? config.ini??? utils/app_config.py save_xxx_config ???????? .env ??

v2.3 ????
- MySQL ????????????????????
- ???????????setText????????
- ???????????????????
- ?????? LocalDB ????????????
- SQLite ?????????????
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QFormLayout, QSpinBox, QComboBox,
    QScrollArea, QGridLayout, QFileDialog, QSizePolicy,
    QApplication, QDialog, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread, QProcess, QEvent
from PySide6.QtGui import QFont, QGuiApplication, QColor

from i18n import tr
from widgets.toast import toast_success, toast_error, toast_info
from utils.dialogs import show_confirm
from utils.credential_manager import get_password
from config import (
    APP_VERSION, APP_MODE, MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, DEFAULT_WORKSHOP,
    TABLE_MATERIALS, TABLE_BORROW_RECORDS, TABLE_FIXED_ASSETS, TABLE_CONFIG_ITEMS,
)
from logger import get_logger

_log = get_logger(__name__)


# ==================== 样式常量 ====================
GROUP_COLORS = {
    "database": {"border": "#3b82f6", "bg": "#eff6ff", "icon": "\U0001f5c4"},
    "sync": {"border": "#10b981", "bg": "#ecfdf5", "icon": "\U0001f504"},
    "alert": {"border": "#f59e0b", "bg": "#fffbeb", "icon": "⚠️"},
    "web_query": {"border": "#0ea5e9", "bg": "#f0f9ff", "icon": "\U0001f310"},
    "hardware": {"border": "#8b5cf6", "bg": "#f5f3ff", "icon": "🔧"},
    "update": {"border": "#f59e0b", "bg": "#fffbeb", "icon": "🔄"},
}

INPUT_STYLE = """
    QLineEdit, QComboBox, QSpinBox {
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        padding: 7px 10px;
        font-size: 13px;
        min-height: 18px;
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
        border: 2px solid #2563eb;
    }
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
        background-color: #f1f5f9;
        color: #94a3b8;
    }
"""

BTN_PRIMARY = """
    QPushButton {
        background-color: #2563eb; color: white; font-weight: bold;
        border: none; border-radius: 6px; padding: 8px 20px;
        font-size: 13px; min-height: 32px;
    }
    QPushButton:hover { background-color: #1d4ed8; }
    QPushButton:pressed { background-color: #1e40af; }
    QPushButton:disabled { background-color: #cbd5e1; color: #94a3b8; }
"""

BTN_SECONDARY = """
    QPushButton {
        background-color: #f3f4f6; color: #4b5563;
        border: 1px solid #d1d5db; border-radius: 6px;
        padding: 8px 16px; font-size: 13px; min-height: 32px;
    }
    QPushButton:hover { background-color: #e5e7eb; }
"""

BTN_SUCCESS = """
    QPushButton {
        background-color: #10b981; color: white; font-weight: bold;
        border: none; border-radius: 6px; padding: 8px 16px;
        font-size: 13px; min-height: 32px;
    }
    QPushButton:hover { background-color: #059669; }
    QPushButton:pressed { background-color: #047857; }
"""

BTN_DANGER = """
    QPushButton {
        background-color: #fef2f2; color: #dc2626;
        border: 1px solid #fecaca; border-radius: 6px;
        padding: 6px 14px; font-size: 12px; min-height: 28px;
    }
    QPushButton:hover { background-color: #fee2e2; border-color: #f87171; }
"""

BTN_WARN = """
    QPushButton {
        background-color: #fffbeb; color: #b45309;
        border: 1px solid #fde68a; border-radius: 6px;
        padding: 6px 14px; font-size: 12px; min-height: 28px;
    }
    QPushButton:hover { background-color: #fef3c7; border-color: #f59e0b; }
"""


# ==================== MySQL 连接棢测工作线====================

class MySQLTestThread(QThread):
    """后台线程执行 MySQL 连接测试，完成后发射信号"""
    test_finished = Signal(bool, str)  # (is_online, detail)

    def __init__(self, host: str, port: int, user: str, password: str,
                 database: str, charset: str, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._charset = charset

    def run(self):
        try:
            import pymysql
            from pymysql.cursors import DictCursor
            conn = pymysql.connect(
                host=self._host, port=self._port,
                user=self._user, password=self._password,
                database=self._database, charset=self._charset,
                cursorclass=DictCursor, autocommit=True,
                connect_timeout=3,
            )
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION()")
                version = cur.fetchone()["VERSION()"]
            conn.close()
            self.test_finished.emit(True, version)
        except (pymysql.err.OperationalError, pymysql.err.ProgrammingError, OSError, RuntimeError) as e:
            self.test_finished.emit(False, str(e)[:200])
        except Exception as e:
            _log.warning("MySQL 测试线程未预期异 %s", e)
            self.test_finished.emit(False, str(e)[:200])


class PortCheckThread(QThread):
    """后台线程执行端口棢测，避免阻塞主线程（未监听时 connect_ex 会等待超时）"""
    check_finished = Signal(int, bool)  # (port, is_in_use)

    def __init__(self, port: int, timeout: float = 0.05, parent=None):
        super().__init__(parent)
        self._port = port
        self._timeout = timeout

    def run(self):
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self._timeout)
                result = s.connect_ex(("127.0.0.1", self._port))
                in_use = (result == 0)
        except Exception:
            in_use = False
        self.check_finished.emit(self._port, in_use)


class ConfigGroup(QFrame):
    """可折叠的配置分组卡片（手风琴模式：同丢时间只展弢丢个）"""

    expanded_changed = Signal(object, bool)  # (self, is_expanded)

    def __init__(self, title: str, group_type: str, parent=None):
        super().__init__(parent)
        self._group_type = group_type
        self._expanded = False
        self._init_ui(title)

    def _init_ui(self, title: str):
        colors = GROUP_COLORS.get(self._group_type, GROUP_COLORS["database"])
        self.setStyleSheet(f"""
            ConfigGroup {{
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-left: 4px solid {colors['border']};
                border-radius: 8px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # 标题栏（可点击折叠）
        self._header = QFrame()
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setStyleSheet(f"""
            QFrame {{
                background-color: {colors['bg']};
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }}
        """)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(14, 10, 14, 10)

        self._title_lbl = QLabel(f"{colors['icon']} {title}")
        self._title_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet("color: #374151; background: transparent;")
        header_layout.addWidget(self._title_lbl)
        header_layout.addStretch()

        self._toggle_btn = QLabel("▶")
        self._toggle_btn.setStyleSheet("color: #6b7280; font-size: 12px; background: transparent;")
        header_layout.addWidget(self._toggle_btn)

        self._header.mousePressEvent = self._on_toggle
        self._layout.addWidget(self._header)

        # 内容区域（默认收起）
        self._content = QFrame()
        self._content.setStyleSheet("background-color: #ffffff; border: none;")
        self._content.setVisible(False)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(14, 10, 14, 14)
        self._content_layout.setSpacing(10)
        self._layout.addWidget(self._content)

    def _on_toggle(self, event):
        self._expanded = not self._expanded
        self._toggle_btn.setText("▲" if self._expanded else "▶")
        self._content.setVisible(self._expanded)
        self.expanded_changed.emit(self, self._expanded)

    def content_layout(self):
        return self._content_layout

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self._toggle_btn.setText("▲" if expanded else "▶")
        self._content.setVisible(expanded)

    def set_title(self, title: str):
        colors = GROUP_COLORS.get(self._group_type, GROUP_COLORS["database"])
        self._title_lbl.setText(f"{colors['icon']} {title}")


class StatusCard(QFrame):
    """???????????v2.3 ???"""

    def __init__(self, title: str, icon: str, accent_color: str, parent=None):
        super().__init__(parent)
        self._accent = accent_color
        self._icon = icon
        self._title = title
        self._rows = {}  # 缓存行控件引用，避免重建
        self._init_ui(title, icon, accent_color)

    def _init_ui(self, title: str, icon: str, accent_color: str):
        self.setStyleSheet("""
            StatusCard {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # 标题
        header = QHBoxLayout()
        header.setSpacing(6)
        self._title_lbl = QLabel(f"{icon} {title}")
        self._title_lbl.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {accent_color};")
        header.addWidget(self._title_lbl)
        header.addStretch()
        layout.addLayout(header)

        # 分割
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #e5e7eb;")
        layout.addWidget(line)

        self._body_layout = QVBoxLayout()
        self._body_layout.setSpacing(6)
        layout.addLayout(self._body_layout)

    def set_title(self, title: str):
        self._title_lbl.setText(f"{self._icon} {title}")

    def set_row(self, row_id: str, label: str, value: str, value_color: str = "#1f2937"):
        """???????????????????"""
        safe_label = label or ""
        safe_value = value or ""
        if row_id in self._rows:
            # 更新已有
            lbl, val = self._rows[row_id]
            lbl.setText(safe_label)
            val.setText(safe_value)
            val.setStyleSheet(f"color: {value_color}; font-size: 12px; font-weight: bold;")
        else:
            # 创建新行
            row = QHBoxLayout()
            row.setSpacing(8)

            lbl = QLabel(safe_label)
            lbl.setFixedWidth(70)
            lbl.setStyleSheet("color: #6b7280; font-size: 12px;")
            lbl.setWordWrap(False)

            val_lbl = QLabel(safe_value)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet(f"color: {value_color}; font-size: 12px; font-weight: bold;")
            val_lbl.setWordWrap(False)

            row.addWidget(lbl)
            row.addWidget(val_lbl, 1)
            self._body_layout.addLayout(row)
            self._rows[row_id] = (lbl, val_lbl)

    def set_status_row(self, row_id: str, status_text: str, is_online: bool):
        """设置或更新带圆点指示器的状行"""
        safe_text = status_text or ""
        if row_id in self._rows:
            val = self._rows[row_id]
            dot = "\U0001f7e2" if is_online else "\U0001f534"
            color = "#059669" if is_online else "#dc2626"
            val.setText(f"{dot} {safe_text}")
            val.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
        else:
            row = QHBoxLayout()
            row.setSpacing(6)

            dot = "\U0001f7e2" if is_online else "\U0001f534"
            color = "#059669" if is_online else "#dc2626"
            lbl = QLabel(f"{dot} {safe_text}")
            lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
            row.addWidget(lbl)
            row.addStretch()
            self._body_layout.addLayout(row)
            self._rows[row_id] = lbl

    def set_error_row(self, row_id: str, text: str):
        """设置或更新错误提示行"""
        err_prefix = tr("config.error_prefix")
        safe_text = text or ""
        if row_id in self._rows:
            self._rows[row_id].setText(f"{err_prefix}{safe_text}")
        else:
            lbl = QLabel(f"{err_prefix}{safe_text}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color: #dc2626; font-size: 11px;")
            self._body_layout.addWidget(lbl)
            self._rows[row_id] = lbl

    def clear_row(self, row_id: str):
        """?????"""
        if row_id in self._rows:
            widget = self._rows.pop(row_id)
            if hasattr(widget, 'deleteLater'):
                widget.deleteLater()

    def get_row_value(self, row_id: str) -> str:
        """????????????"""
        if row_id not in self._rows:
            return ""
        widget = self._rows[row_id]
        if isinstance(widget, tuple):
            return widget[1].text()
        return widget.text()

    def body(self):
        """返回内部 body 布局，供外部添加自定义控布局"""
        return self._body_layout


class MiniStatCard(QFrame):
    """迷你统计卡片 用于 2x2 网格"""

    def __init__(self, label: str, value: str, color: str = "#2563eb", parent=None):
        super().__init__(parent)
        self._color = color
        self._label_text = label
        self._value_text = value
        self.setStyleSheet(f"""
            MiniStatCard {{
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        self._lbl = QLabel(label)
        self._lbl.setAlignment(Qt.AlignCenter)
        self._lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(self._lbl)

        self._val_lbl = QLabel(value)
        self._val_lbl.setAlignment(Qt.AlignCenter)
        self._val_lbl.setFont(QFont("Microsoft YaHei", 15, QFont.Weight.Bold))
        self._val_lbl.setStyleSheet(f"color: {color};")
        layout.addWidget(self._val_lbl)

    def set_value(self, value: str):
        self._val_lbl.setText(value)

    def set_label(self, label: str):
        self._lbl.setText(label)


class ConfigView(QWidget):
    """?????? v2.3 ????"""

    config_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._local_db = None
        self._mysql_test_thread = None
        self._port_check_thread = None
        self._ftp_test_thread = None
        self._web_process = None
        self._web_stopping_intentionally = False
        self._is_syncing_web_status = False
        self._web_just_started = 0.0  # 防止 _sync_web_service_status 重入
        self._url_map = {}
        self._stats_cache = None
        self._stats_cache_time = 0
        self._prog_dialog = None
        self._init_ui()

    # v2.3: 支持外部注入 LocalDB 实例
    def set_local_db(self, local_db):
        """注入外部 LocalDB 实例，避免重复创建连接池"""
        self._local_db = local_db

    # ==================== 页面可见性控制（v2.3 新增===================

    def showEvent(self, event):
        """?????????????????????????????????"""
        super().showEvent(event)
        # 轻量操作：立即刷新（不涉I/O
        self._refresh_web_urls()
        self._refresh_autostart_status()
        self._start_status_timer()
        # 重操作：延迟到事件循环下丢次空闲时执行（消除切换时的卡顿感
        QTimer.singleShot(0, self._sync_web_service_status)
        QTimer.singleShot(0, self._update_status_panel)

    def hideEvent(self, event):
        """????????????????????? Web ???"""
        super().hideEvent(event)
        self._stop_status_timer()
        self._cleanup_mysql_test_thread()
        self._cleanup_port_check_thread()

    def _start_status_timer(self):
        """启动状面板定时刷新（仅在可见时有效）"""
        if not hasattr(self, '_status_timer'):
            self._status_timer = QTimer(self)
            self._status_timer.timeout.connect(self._update_status_panel)
        if not self._status_timer.isActive():
            self._status_timer.start(5000)

    def _stop_status_timer(self):
        """??????????"""
        if hasattr(self, '_status_timer') and self._status_timer.isActive():
            self._status_timer.stop()

    # ==================== UI 初始化（v2.4 响应式布屢===================

    def _init_ui(self):
        # 外层使用垂直布局，便于窄屏时在下方插入同步状态和快捷操作
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(16, 16, 16, 16)
        outer_layout.setSpacing(12)

        # 水平区域：左侧配置表+ 右侧状面板（宽屏模式
        self._horizontal_area = QWidget()
        self._horizontal_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        h_layout = QHBoxLayout(self._horizontal_area)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(16)

        # ==================== 左侧：配置表====================
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # 标题
        header = QHBoxLayout()
        self._page_title = QLabel(tr("config.page_title"))
        self._page_title.setFont(QFont("Microsoft YaHei", 17, QFont.Weight.Bold))
        self._page_title.setStyleSheet("color: #2563eb;")
        header.addWidget(self._page_title)
        header.addStretch()

        self.btn_save = QPushButton(tr("config.btn_save"))
        self.btn_save.setStyleSheet(BTN_PRIMARY)
        self.btn_save.clicked.connect(self._on_save_clicked)
        header.addWidget(self.btn_save)

        self.btn_reset = QPushButton(tr("config.btn_reset"))
        self.btn_reset.setStyleSheet(BTN_SECONDARY)
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        header.addWidget(self.btn_reset)
        left_layout.addLayout(header)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout.setSpacing(14)
        self._scroll_layout.setContentsMargins(0, 8, 8, 0)

        # ---------- 分组 ----------
        self._config_groups = {}

        group_db = ConfigGroup(tr("config.group_database"), "database")
        self._config_groups["database"] = group_db
        self._build_db_form(group_db.content_layout())
        self._scroll_layout.addWidget(group_db)

        group_sync = ConfigGroup(tr("config.group_sync"), "sync")
        self._config_groups["sync"] = group_sync
        self._build_sync_form(group_sync.content_layout())
        self._scroll_layout.addWidget(group_sync)

        group_alert = ConfigGroup(tr("config.group_alert"), "alert")
        self._config_groups["alert"] = group_alert
        self._build_alert_form(group_alert.content_layout())
        self._scroll_layout.addWidget(group_alert)

        group_web = ConfigGroup(tr("config.group_web_query"), "web_query")
        self._config_groups["web_query"] = group_web
        self._build_web_query_form(group_web.content_layout())
        self._scroll_layout.addWidget(group_web)

        group_hw = ConfigGroup(tr("config.group_hardware"), "hardware")
        self._config_groups["hardware"] = group_hw
        self._build_hardware_form(group_hw.content_layout())
        self._scroll_layout.addWidget(group_hw)

        group_update = ConfigGroup(tr("update.title"), "update")
        self._config_groups["update"] = group_update
        self._build_update_form(group_update.content_layout())
        self._scroll_layout.addWidget(group_update)

        # 手风琴模式：连接扢有分组的展开信号，同丢时间只展弢丢
        for grp in self._config_groups.values():
            grp.expanded_changed.connect(self._on_group_expanded)

        self._scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)

        h_layout.addWidget(left_widget, stretch=7)

        # ==================== 右侧：状态面====================
        self._right_widget = QWidget()
        self._right_widget.setFixedWidth(320)
        self._right_layout = QVBoxLayout(self._right_widget)
        self._right_layout.setContentsMargins(0, 0, 0, 0)
        self._right_layout.setSpacing(12)

        # 卡片 1：系统概
        self.card_overview = StatusCard(tr("config.card_overview"), "\U0001f4ca", "#2563eb")
        self.card_overview.set_row("version", tr("config.label_version"), APP_VERSION)
        self.card_overview.set_row("mode", tr("config.label_mode"), APP_MODE)
        self.card_overview.set_row("db_file", tr("config.label_db_file"), "...")
        self.card_overview.set_row("total", tr("config.label_total"), "0")
        self._right_layout.addWidget(self.card_overview)

        # 卡片 2：MySQL 连接
        self.card_mysql = StatusCard(tr("config.card_mysql"), "\U0001f5c4", "#10b981")
        self.card_mysql.set_status_row("status", tr("config.status_checking"), False)
        self.card_mysql.set_row("host", tr("config.label_host"), "..." )
        self.card_mysql.set_row("port", tr("config.label_port"), "..." )
        self.card_mysql.set_row("db", tr("config.label_db"), "..." )
        self._right_layout.addWidget(self.card_mysql)

        # 卡片 3：同步状态（移到右侧
        self.card_sync = StatusCard(tr("config.card_sync"), "\U0001f504", "#f59e0b")
        self.card_sync.set_row("queue", tr("config.label_queue"), tr("config.records_count", count=0), "#059669")
        self.card_sync.set_row("last_push", tr("config.label_last_push"), "..." )
        self.card_sync.set_row("last_pull", tr("config.label_last_pull"), "..." )
        self._right_layout.addWidget(self.card_sync)

        # 卡片 4：FTP 状
        self.card_ftp = StatusCard(tr("config.card_ftp"), "\U0001f4e1", "#06b6d4")
        self.card_ftp.set_status_row("status", tr("config.status_checking"), False)
        self.card_ftp.set_row("host", tr("config.label_ftp_host"), "..." )
        self._right_layout.addWidget(self.card_ftp)

        # 卡片 4：数据量统计（移到底部，不占用右侧分栏）
        stat_card = StatusCard(tr("config.card_stats"), "\U0001f4c8", "#8b5cf6")
        self._stat_grid = QGridLayout()
        self._stat_grid.setSpacing(8)
        self._stat_grid.setContentsMargins(0, 0, 0, 0)
        self._mini_stats = {}
        stats_meta = [
            ("materials", tr("config.stat_materials"), "0", "#2563eb"),
            ("borrow", tr("config.stat_borrow"), "0", "#10b981"),
            ("assets", tr("config.stat_assets"), "0", "#f59e0b"),
            ("configs", tr("config.stat_configs"), "0", "#8b5cf6"),
        ]
        for i, (key, label, val, color) in enumerate(stats_meta):
            row, col = divmod(i, 2)
            mini = MiniStatCard(label, val, color)
            self._mini_stats[key] = mini
            self._stat_grid.addWidget(mini, row, col)
        stat_card.body().addLayout(self._stat_grid)
        self.card_stats = stat_card

        # 卡片 5：快捷操作（始终在底部，不占用右侧分栏）
        self.card_actions = StatusCard(tr("config.card_actions"), "⚡", "#ec4899")
        self.btn_export = QPushButton(tr("config.btn_export"))
        self.btn_export.setStyleSheet(BTN_SECONDARY.replace("padding: 8px 16px", "padding: 6px 12px"))
        self.btn_export.clicked.connect(self._export_config)
        self.card_actions.body().addWidget(self.btn_export)

        self.btn_import = QPushButton(tr("config.btn_import"))
        self.btn_import.setStyleSheet(BTN_SECONDARY.replace("padding: 8px 16px", "padding: 6px 12px"))
        self.btn_import.clicked.connect(self._import_config)
        self.card_actions.body().addWidget(self.btn_import)

        self.btn_clear_queue = QPushButton(tr("config.btn_clear_queue"))
        self.btn_clear_queue.setStyleSheet(BTN_DANGER)
        self.btn_clear_queue.clicked.connect(self._clear_sync_queue)
        self.card_actions.body().addWidget(self.btn_clear_queue)

        # 车间切换区域
        self._init_workshop_selector()

        self._right_layout.addStretch()
        h_layout.addWidget(self._right_widget, stretch=0)

        outer_layout.addWidget(self._horizontal_area, stretch=1)

        # ==================== 底部区域（数据统+ 快捷操作，两列布屢====================
        self._bottom_area = QWidget()
        bottom_layout = QHBoxLayout(self._bottom_area)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(12)
        bottom_layout.addWidget(self.card_stats, stretch=1)
        bottom_layout.addWidget(self.card_actions, stretch=1)
        outer_layout.addWidget(self._bottom_area, stretch=0)

    # ==================== 手风琴模====================

    def _on_group_expanded(self, group, is_expanded):
        """??????????????????????"""
        if not is_expanded:
            return
        for grp in self._config_groups.values():
            if grp is not group:
                grp.set_expanded(False)

    # ==================== 表单构建（与 v2.2 丢致）====================

    def _build_db_form(self, layout):
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._form_labels = {}

        self.db_host = QLineEdit()
        self.db_host.setPlaceholderText(tr("config.placeholder_db_host"))
        self.db_host.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_db_host"))
        self._form_labels["db_host"] = lbl
        grid.addWidget(lbl, 0, 0)
        grid.addWidget(self.db_host, 0, 1)

        self.db_port = QSpinBox()
        self.db_port.setRange(1, 65535)
        self.db_port.setValue(3306)
        self.db_port.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_db_port"))
        self._form_labels["db_port"] = lbl
        grid.addWidget(lbl, 0, 2)
        grid.addWidget(self.db_port, 0, 3)

        self.db_user = QLineEdit()
        self.db_user.setPlaceholderText(tr("config.placeholder_db_user"))
        self.db_user.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_db_user"))
        self._form_labels["db_user"] = lbl
        grid.addWidget(lbl, 1, 0)
        grid.addWidget(self.db_user, 1, 1)

        self.db_password = QLineEdit()
        self.db_password.setEchoMode(QLineEdit.Password)
        self.db_password.setPlaceholderText(tr("config.placeholder_db_password"))
        self.db_password.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_db_password"))
        self._form_labels["db_password"] = lbl
        grid.addWidget(lbl, 1, 2)
        grid.addWidget(self.db_password, 1, 3)

        self.db_name = QLineEdit()
        self.db_name.setPlaceholderText(tr("config.placeholder_db_name"))
        self.db_name.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_db_name"))
        self._form_labels["db_name"] = lbl
        grid.addWidget(lbl, 2, 0)
        grid.addWidget(self.db_name, 2, 1)

        self.db_charset = QComboBox()
        self.db_charset.addItems(["utf8mb4", "utf8"])
        self.db_charset.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_db_charset"))
        self._form_labels["db_charset"] = lbl
        grid.addWidget(lbl, 2, 2)
        grid.addWidget(self.db_charset, 2, 3)

        layout.addLayout(grid)

        self.btn_test = QPushButton(tr("config.btn_test"))
        self.btn_test.setStyleSheet(BTN_SUCCESS)
        self.btn_test.clicked.connect(self._test_db_connection)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.btn_test)
        layout.addLayout(btn_row)

    def _build_sync_form(self, layout):
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.app_mode = QComboBox()
        self.app_mode.addItems(["online", "semi_offline", "offline"])
        self.app_mode.setStyleSheet(INPUT_STYLE)
        self.app_mode.setToolTip(tr("config.tooltip_app_mode"))
        lbl = QLabel(tr("config.param_app_mode"))
        self._form_labels["app_mode"] = lbl
        grid.addWidget(lbl, 0, 0)
        grid.addWidget(self.app_mode, 0, 1)

        self.sync_interval = QSpinBox()
        self.sync_interval.setRange(5, 3600)
        self.sync_interval.setSuffix(tr("config.unit_seconds"))
        self.sync_interval.setValue(30)
        self.sync_interval.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_sync_interval"))
        self._form_labels["sync_interval"] = lbl
        grid.addWidget(lbl, 0, 2)
        grid.addWidget(self.sync_interval, 0, 3)

        self.sync_retry = QSpinBox()
        self.sync_retry.setRange(1, 10)
        self.sync_retry.setSuffix(tr("config.unit_times"))
        self.sync_retry.setValue(3)
        self.sync_retry.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_sync_retry"))
        self._form_labels["sync_retry"] = lbl
        grid.addWidget(lbl, 1, 0)
        grid.addWidget(self.sync_retry, 1, 1)

        self.sync_batch = QSpinBox()
        self.sync_batch.setRange(10, 200)
        self.sync_batch.setSuffix(tr("config.unit_items"))
        self.sync_batch.setValue(50)
        self.sync_batch.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_sync_batch"))
        self._form_labels["sync_batch"] = lbl
        grid.addWidget(lbl, 1, 2)
        grid.addWidget(self.sync_batch, 1, 3)

        self.full_sync_interval = QSpinBox()
        self.full_sync_interval.setRange(5, 1440)
        self.full_sync_interval.setSuffix(tr("config.unit_minutes"))
        self.full_sync_interval.setValue(30)
        self.full_sync_interval.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_full_sync_interval"))
        self._form_labels["full_sync_interval"] = lbl
        grid.addWidget(lbl, 2, 0)
        grid.addWidget(self.full_sync_interval, 2, 1)

        self.network_check = QSpinBox()
        self.network_check.setRange(5, 60)
        self.network_check.setSuffix(tr("config.unit_seconds"))
        self.network_check.setValue(10)
        self.network_check.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_network_check"))
        self._form_labels["network_check"] = lbl
        grid.addWidget(lbl, 2, 2)
        grid.addWidget(self.network_check, 2, 3)

        layout.addLayout(grid)

    def _build_alert_form(self, layout):
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.stale_days = QSpinBox()
        self.stale_days.setRange(30, 365)
        self.stale_days.setSuffix(tr("config.unit_days"))
        self.stale_days.setValue(90)
        self.stale_days.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_stale_days"))
        self._form_labels["stale_days"] = lbl
        grid.addWidget(lbl, 0, 0)
        grid.addWidget(self.stale_days, 0, 1)

        self.expire_days = QSpinBox()
        self.expire_days.setRange(1, 30)
        self.expire_days.setSuffix(tr("config.unit_days"))
        self.expire_days.setValue(7)
        self.expire_days.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_expire_days"))
        self._form_labels["expire_days"] = lbl
        grid.addWidget(lbl, 0, 2)
        grid.addWidget(self.expire_days, 0, 3)

        self.low_stock = QSpinBox()
        self.low_stock.setRange(1, 100)
        self.low_stock.setSuffix(tr("config.unit_count"))
        self.low_stock.setValue(10)
        self.low_stock.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_low_stock"))
        self._form_labels["low_stock"] = lbl
        grid.addWidget(lbl, 1, 0)
        grid.addWidget(self.low_stock, 1, 1)

        self.auto_export = QComboBox()
        self.auto_export.addItems([tr("config.auto_export_off"), tr("config.auto_export_on")])
        self.auto_export.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("config.param_auto_export"))
        self._form_labels["auto_export"] = lbl
        grid.addWidget(lbl, 1, 2)
        grid.addWidget(self.auto_export, 1, 3)

        layout.addLayout(grid)

    def _build_hardware_form(self, layout):
        # 三列布局：左指纹 / 中NFC / 右刷新端竖排)
        main = QHBoxLayout()
        main.setSpacing(20)

        # === 左列：指纹设===
        fp_frame, fp_grid = self._make_device_frame(
            title=tr("config.fingerprint_section_title"),
            attr_enabled="fingerprint_enabled",
            attr_device="fingerprint_device",
            attr_baud="fingerprint_baud_rate",
        )
        main.addWidget(fp_frame, 1)

        # === 中列：NFC设备 ===
        nfc_frame, nfc_grid = self._make_device_frame(
            title=tr("config.nfc_section_title"),
            attr_enabled="nfc_enabled",
            attr_device="nfc_device",
            attr_baud="nfc_baud_rate",
        )
        main.addWidget(nfc_frame, 1)

        # === 右列：刷新端口按钮（竖排文字===
        btn_refresh = QPushButton(tr("config.btn_refresh_ports"))
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.setMaximumWidth(48)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #6366f1; color: #ffffff; border: none;
                border-radius: 8px; font-size: 16px; font-weight: bold;
                padding: 8px 4px; line-height: 28px;
            }
            QPushButton:hover { background-color: #4f46e5; }
            QPushButton:pressed { background-color: #4338ca; }
        """)
        # 竖排文字：按字符拆分，每字一
        label_text = btn_refresh.text()
        btn_refresh.setText("\n".join(label_text))
        btn_refresh.clicked.connect(self._refresh_com_ports)
        btn_vbox = QVBoxLayout()
        btn_vbox.addStretch()
        btn_vbox.addWidget(btn_refresh, alignment=Qt.AlignCenter)
        btn_vbox.addStretch()
        main.addLayout(btn_vbox)

        layout.addLayout(main)
        self._refresh_com_ports()

    def _make_device_frame(self, title, *, attr_enabled, attr_device, attr_baud):
        """构建丢个设备配置卡片（QFrame + QGridLayout），属直接挂self """
        if getattr(self, attr_enabled, None) is None:
            combo = QComboBox()
            if attr_enabled.startswith("fingerprint"):
                combo.addItems([tr("config.fingerprint_off"), tr("config.fingerprint_on")])
            else:
                combo.addItems([tr("config.nfc_off"), tr("config.nfc_on")])
            combo.setStyleSheet(INPUT_STYLE)
            setattr(self, attr_enabled, combo)
        else:
            getattr(self, attr_enabled).setStyleSheet(INPUT_STYLE)

        if getattr(self, attr_device, None) is None:
            combo = QComboBox()
            combo.setEditable(True)
            combo.setStyleSheet(INPUT_STYLE)
            setattr(self, attr_device, combo)
        else:
            getattr(self, attr_device).setStyleSheet(INPUT_STYLE)

        if getattr(self, attr_baud, None) is None:
            combo = QComboBox()
            for val in [9600, 115200, 57600, 38400, 19200]:
                combo.addItem(str(val))
            combo.setCurrentIndex(0)
            combo.setStyleSheet(INPUT_STYLE)
            setattr(self, attr_baud, combo)
        else:
            getattr(self, attr_baud).setStyleSheet(INPUT_STYLE)

        enabled = getattr(self, attr_enabled)
        device = getattr(self, attr_device)
        baud = getattr(self, attr_baud)

        prefix = "fingerprint" if attr_enabled.startswith("fingerprint") else "nfc"
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.addWidget(QLabel(tr(f"config.{prefix}_label")), 0, 0)
        grid.addWidget(enabled, 0, 1)
        grid.addWidget(QLabel(tr(f"config.{prefix}_device_label")), 1, 0)
        grid.addWidget(device, 1, 1)
        grid.addWidget(QLabel(tr(f"config.{prefix}_baud_rate_label")), 2, 0)
        grid.addWidget(baud, 2, 1)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #4338ca; font-weight: bold; font-size: 13px; padding-bottom: 4px;")
        vbox.addWidget(title_lbl)
        vbox.addLayout(grid)

        frame = QFrame()
        frame.setStyleSheet("background-color: #f5f3ff; border: 1px solid #c4b5fd; border-radius: 8px; padding: 8px;")
        frame.setLayout(vbox)
        return frame, grid

    def _refresh_com_ports(self):
        """扫描系统可用 COM 端口并填充下拉框"""
        try:
            from utils.serial_port_utils import get_available_com_ports
            ports = get_available_com_ports()
        except Exception:
            ports = ["COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8"]

        old_fp = self.fingerprint_device.currentText()
        old_nfc = self.nfc_device.currentText()

        self.fingerprint_device.clear()
        self.nfc_device.clear()
        self.fingerprint_device.addItems(ports)
        self.nfc_device.addItems(ports)

        if old_fp and old_fp in ports:
            self.fingerprint_device.setCurrentText(old_fp)
        elif ports:
            self.fingerprint_device.setCurrentIndex(0)
        if old_nfc and old_nfc in ports:
            self.nfc_device.setCurrentText(old_nfc)
        elif ports:
            self.nfc_device.setCurrentIndex(0)

    def _build_web_query_form(self, layout):
        # ========== ???????? + API ??????? ==========
        row1 = QHBoxLayout()
        row1.setSpacing(32)
        row1.setContentsMargins(0, 0, 0, 0)

        lbl_port = QLabel(tr("config.param_web_port"))
        lbl_port.setFixedWidth(70)
        lbl_port.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(lbl_port)

        self.web_port = QSpinBox()
        self.web_port.setRange(1, 65535)
        self.web_port.setValue(8000)
        self.web_port.setFixedWidth(100)
        self.web_port.setStyleSheet(INPUT_STYLE + """
            QSpinBox::up-button, QSpinBox::down-button { width: 0px; }
        """)
        row1.addWidget(self.web_port)

        lbl_key = QLabel(tr("config.param_web_api_key"))
        lbl_key.setFixedWidth(70)
        lbl_key.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(lbl_key)

        self.web_api_key = QLineEdit()
        self.web_api_key.setPlaceholderText(tr("config.placeholder_web_api_key"))
        self.web_api_key.setFixedWidth(280)
        row1.addWidget(self.web_api_key)

        # 服务运行状态标签（左）
        self._web_status_label = QLabel("\U0001f7e2 " + tr("config.web_status_stopped"))
        self._web_status_label.setStyleSheet("color: #6b7280; font-size: 12px; padding: 2px 6px;")
        self._web_status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(self._web_status_label)

        row1.addStretch()

        # 开机自启状态标签（右）
        self._web_autostart_label = QLabel("\U0001f512 " + tr("config.web_autostart_disabled"))
        self._web_autostart_label.setStyleSheet("color: #dc2626; font-size: 12px; padding: 2px 6px;")
        self._web_autostart_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(self._web_autostart_label)

        layout.addLayout(row1)

        self._form_labels["web_port"] = QLabel(tr("config.param_web_port"))
        self._form_labels["web_api_key"] = QLabel(tr("config.param_web_api_key"))

        # ========== ????HTTPS ?? + 3 ??????????? ==========
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(10)
        ctrl_layout.setContentsMargins(0, 4, 0, 0)

        BTN_FIXED = 148
        BTN_PURPLE = """
            QPushButton {
                background-color: #7c3aed; color: white; font-weight: bold;
                border: none; border-radius: 6px;
                padding: 7px 12px; font-size: 12px; min-height: 30px;
            }
            QPushButton:hover { background-color: #6d28d9; }
            QPushButton:pressed { background-color: #5b21b6; }
        """
        BTN_SEC = """
            QPushButton {
                background-color: #ffffff; color: #374151;
                border: 1px solid #d1d5db; border-radius: 6px;
                padding: 7px 12px; font-size: 12px; min-height: 30px;
            }
            QPushButton:hover { background-color: #f3f4f6; border-color: #9ca3af; }
            QPushButton:pressed { background-color: #e5e7eb; }
        """

        self.web_use_https = QPushButton("HTTPS")
        self.web_use_https.setFixedWidth(BTN_FIXED)
        self.web_use_https.setStyleSheet(BTN_PURPLE)
        ctrl_layout.addWidget(self.web_use_https)
        self._form_labels["web_use_https"] = QLabel("")

        self.btn_toggle_web = QPushButton()
        self.btn_toggle_web.setFixedWidth(BTN_FIXED)
        self.btn_toggle_web.clicked.connect(self._toggle_web_service)
        self._set_web_toggle_button(False)
        ctrl_layout.addWidget(self.btn_toggle_web)

        self.btn_toggle_autostart = QPushButton()
        self.btn_toggle_autostart.setFixedWidth(BTN_FIXED)
        self.btn_toggle_autostart.clicked.connect(self._toggle_autostart)
        self._set_autostart_toggle_button(False)
        ctrl_layout.addWidget(self.btn_toggle_autostart)

        self.btn_refresh_urls = QPushButton(tr("config.btn_refresh_urls"))
        self.btn_refresh_urls.setStyleSheet(BTN_SEC)
        self.btn_refresh_urls.setFixedWidth(BTN_FIXED)
        self.btn_refresh_urls.clicked.connect(self._refresh_web_urls)
        ctrl_layout.addWidget(self.btn_refresh_urls)

        layout.addLayout(ctrl_layout)
        self._refresh_autostart_status()

        # ========== ???? ==========
        hidden_layout = QVBoxLayout()
        hidden_layout.setSpacing(0)
        hidden_layout.setContentsMargins(0, 0, 0, 0)

        self.web_enabled = QComboBox()
        self.web_enabled.addItems([tr("config.web_off"), tr("config.web_on")])
        self.web_enabled.setVisible(False)
        lbl = QLabel(tr("config.param_web_enabled"))
        self._form_labels["web_enabled"] = lbl
        lbl.setVisible(False)
        hidden_layout.addWidget(lbl)
        hidden_layout.addWidget(self.web_enabled)

        self.web_host = QLineEdit()
        self.web_host.setPlaceholderText(tr("config.placeholder_web_host"))
        self.web_host.setText("0.0.0.0")
        self.web_host.setVisible(False)
        lbl = QLabel(tr("config.param_web_host"))
        self._form_labels["web_host"] = lbl
        lbl.setVisible(False)
        hidden_layout.addWidget(lbl)
        hidden_layout.addWidget(self.web_host)

        self.web_api_base = QLineEdit()
        self.web_api_base.setPlaceholderText(tr("config.placeholder_web_api_base"))
        self.web_api_base.setText("/api")
        self.web_api_base.setVisible(False)
        lbl = QLabel(tr("config.param_web_api_base"))
        self._form_labels["web_api_base"] = lbl
        lbl.setVisible(False)
        hidden_layout.addWidget(lbl)
        hidden_layout.addWidget(self.web_api_base)

        self.web_timeout = QSpinBox()
        self.web_timeout.setRange(1, 300)
        self.web_timeout.setSuffix(tr("config.unit_seconds"))
        self.web_timeout.setValue(10)
        self.web_timeout.setVisible(False)
        lbl = QLabel(tr("config.param_web_timeout"))
        self._form_labels["web_timeout"] = lbl
        lbl.setVisible(False)
        hidden_layout.addWidget(lbl)
        hidden_layout.addWidget(self.web_timeout)

        hidden_layout.addWidget(QLabel(""))
        layout.addLayout(hidden_layout)

        # ========== ?????? ==========
        self._web_urls_card = QFrame()
        self._web_urls_card.setStyleSheet("""
            QFrame {
                background-color: #f0f9ff;
                border: 1px solid #bae6fd;
                border-radius: 8px;
            }
        """)
        urls_layout = QVBoxLayout(self._web_urls_card)
        urls_layout.setContentsMargins(14, 12, 14, 12)
        urls_layout.setSpacing(8)

        self._web_urls_title = QLabel("\U0001f310 " + tr("config.web_urls_title"))
        self._web_urls_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self._web_urls_title.setStyleSheet("color: #0369a1;")
        urls_layout.addWidget(self._web_urls_title)

        for name in ("_web_url_lan", "_web_url_mdns", "_web_url_netbios"):
            lbl = QLabel()
            lbl.setStyleSheet(
                "color: #1d4ed8; font-size: 13px; font-weight: bold;"
                "font-family: Consolas, monospace;"
                "padding: 6px 10px; background-color: #ffffff;"
                "border: 1px solid #dbeafe; border-radius: 4px;"
            )
            lbl.setWordWrap(True)
            lbl.setCursor(Qt.PointingHandCursor)
            lbl.installEventFilter(self)
            urls_layout.addWidget(lbl)
            setattr(self, name, lbl)

        layout.addWidget(self._web_urls_card)

        self.web_port.valueChanged.connect(self._refresh_web_urls)
        self.web_use_https.clicked.connect(self._toggle_https_mode)
        self._refresh_web_urls()

    # ==================== 工具函数 ====================

    @staticmethod
    def _get_lan_ip() -> str:
        """获取当前屢域网 IP 地址"""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return ""

    def _refresh_web_urls(self):
        """刷新 Web 查询服务访问地址显示"""
        import socket
        hostname = socket.gethostname()
        port = self.web_port.value()
        # 根据 HTTPS 弢关决定协
        try:
            use_https = (
                hasattr(self, 'web_use_https')
                and self.web_use_https.text() == "HTTPS"
            )
        except Exception:
            use_https = False
        scheme = 'https' if use_https else 'http'

        lan_ip = self._get_lan_ip()
        if lan_ip:
            lan_url = f"{scheme}://{lan_ip}:{port}"
            self._web_url_lan.setText(lan_url)
            self._url_map[self._web_url_lan] = lan_url
        else:
            self._web_url_lan.setText("")
            self._url_map.pop(self._web_url_lan, None)

        mdns_url = f"{scheme}://{hostname}.local:{port}"
        self._web_url_mdns.setText(mdns_url)
        self._url_map[self._web_url_mdns] = mdns_url

        netbios_url = f"{scheme}://{hostname}:{port}"
        self._web_url_netbios.setText(netbios_url)
        self._url_map[self._web_url_netbios] = netbios_url

    # ==================== Web 服务控制 ====================

    def _toggle_https_mode(self):
        """HTTPS ?????????????????"""
        current = self.web_use_https.text()
        if current == "HTTPS":
            self.web_use_https.setText("HTTP")
        else:
            self.web_use_https.setText("HTTPS")
        self._refresh_web_urls()


    def _is_port_in_use(self, port: int) -> bool:
        """棢查端口是否已被占用（本地回环，超50ms，不阻塞主线程太久）"""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.05)
                result = s.connect_ex(("127.0.0.1", port))
                return result == 0
        except Exception:
            return False

    def _find_web_exe(self, exe_dir: str) -> str:
        """在指定目录中查找 Web 服务 EXE"""
        import glob
        patterns = [
            os.path.join(exe_dir, "MMS-WebServices.exe"),
            os.path.join(exe_dir, "物料管理系统-MMS_Web查询*.exe"),
            os.path.join(exe_dir, "MMS_Web服务.exe"),
            os.path.join(exe_dir, "MMS_Web*.exe"),
            os.path.join(exe_dir, "MMSWebQuery.exe"),
        ]
        for pat in patterns:
            matches = glob.glob(pat)
            if matches:
                return matches[0]
        return ""

    def _resolve_web_launcher(self, port: int):
        """?? Web ?????????????????????"""

        if getattr(sys, "frozen", False):
            # 打包模式：使用同目录下的 Web 服务 EXE（动态查找，支持带版本号命名
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            web_exe = self._find_web_exe(exe_dir)
            if not web_exe:
                web_exe = os.path.join(exe_dir, "MMS_Web服务.exe")
            # 设置 PYTHONIOENCODING 确保中文输出正常
            return web_exe, ["--host", "0.0.0.0", "--port", str(port)], ["PYTHONIOENCODING=utf-8"]
        else:
            # 弢发模式：使用 python + run.py
            run_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web_", "run.py")
            run_script = os.path.normpath(run_script)
            return run_script, ["--host", "0.0.0.0", "--port", str(port)], ["PYTHONIOENCODING=utf-8"]

    def _start_web_service(self):
        """启动 Web 查询服务"""
        if self._web_process is not None and self._web_process.state() != QProcess.ProcessState.NotRunning:
            toast_info(self, tr("config.web_already_running"))
            return

        port = self.web_port.value()

        # 先检查端口是否已被占用（可能是之前启动的进程
        if self._is_port_in_use(port):
            self._update_web_service_ui(True)
            toast_info(self, tr("config.web_port_in_use").format(port=port))
            return

        program, arguments, env_extra = self._resolve_web_launcher(port)

        if getattr(sys, "frozen", False):
            # 打包模式：检exe 是否存在
            if not os.path.isfile(program):
                toast_error(self, tr("config.web_script_not_found"))
                return
        else:
            # 弢发模式：棢查脚本是否存
            if not os.path.isfile(program):
                toast_error(self, tr("config.web_script_not_found"))
                return

        self._web_stopping_intentionally = False
        self._web_process = QProcess(self)
        env = QProcess.systemEnvironment()
        for e in env_extra:
            env.append(e)
        self._web_process.setEnvironment(env)
        if getattr(sys, "frozen", False):
            self._web_process.setProgram(program)
            self._web_process.setArguments(arguments)
        else:
            self._web_process.setProgram(sys.executable)
            self._web_process.setArguments([program] + arguments)

        # 使用 startDetached() 启动独立进程，使其不MMS.exe 逢出终
        # 之后通过端口棢+ netstat/taskkill 进行状管
        try:
            result = self._web_process.startDetached()
            # PySide6: startDetached() 返回 Tuple[bool, int] 或单bool
            if isinstance(result, tuple):
                started, _pid = result
            else:
                started = bool(result)
            if not started:
                toast_error(self, tr("config.web_start_failed"))
                self._web_process = None
                self._sync_web_service_status()
                return
        except (OSError, RuntimeError, ValueError) as e:
            toast_error(self, f"{tr('config.web_start_failed')}: {e}")
            self._web_process = None
            self._sync_web_service_status()
            return
        except Exception as e:
            _log.warning("启动 Web 服务未预期异 %s", e)
            toast_error(self, f"{tr('config.web_start_failed')}: {e}")
            self._web_process = None
            self._sync_web_service_status()
            return

        # 延迟丢小段时间再同步状态，确保端口确实被监
        self._web_just_started = time.time()
        self._update_web_service_ui(True)
        toast_success(self, tr("config.web_started"))
        QTimer.singleShot(1500, self._sync_web_service_status)

    def _stop_web_service(self):
        """停止 Web 查询服务"""
        port = self.web_port.value()
        stopped = False

        # 场景1：有 QProcess 管理的进
        if self._web_process is not None and self._web_process.state() != QProcess.ProcessState.NotRunning:
            self._web_stopping_intentionally = True
            try:
                self._web_process.terminate()
                if not self._web_process.waitForFinished(3000):
                    self._web_process.kill()
                    self._web_process.waitForFinished(2000)
                stopped = True
            except (RuntimeError, OSError) as e:
                _log.warning(f"停止 Web 服务时出 {e}")
            except Exception as e:
                _log.warning("停止 Web 服务未预期异 %s", e)

        # 场景2：没QProcess 但端口被占用（外部启动的进程
        if not stopped and self._is_port_in_use(port):
            # 安全防护：禁止终止系统端口（1-1024），避免误杀 MySQL、远程桌面等服务
            if port <= 1024:
                _log.warning(f"端口 {port} 属于系统端口范围，为安全起见不自动终止进程")
                toast_error(self, tr("config.web_port_system_protected").format(port=port))
                self._sync_web_service_status()
                return
            try:
                import subprocess
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace"
                )
                target_pid = None
                for line in result.stdout.splitlines():
                    # netstat 输出格式：协 本地地址           外部地址           状       PID
                    # 只匹LISTENING 状且本地地址包含该端
                    if "LISTENING" not in line:
                        continue
                    parts = line.strip().split()
                    if len(parts) < 5:
                        continue
                    # 本地地址是第 2 列（索引 1），例如 0.0.0.0:8000 [::]:8000
                    local_addr = parts[1]
                    # 精准匹配本地端口号：取最后一个冒号后的数
                    # 兼容 IPv4 (0.0.0.0:8000) IPv6 ([::]:8000)
                    if ":" in local_addr:
                        local_port_str = local_addr.rsplit(":", 1)[-1]
                        if local_port_str.isdigit() and int(local_port_str) == port:
                            pid_candidate = parts[-1]
                            if pid_candidate.isdigit():
                                target_pid = int(pid_candidate)
                                break
                if target_pid is not None:
                    # 二次校验：确认进程名MMSWebQuery（或 python），避免误杀
                    try:
                        result2 = subprocess.run(
                            ["tasklist", "/FI", f"PID eq {target_pid}", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace"
                        )
                        proc_line = result2.stdout.strip()
                        safe_names = ("MMSWebQuery", "物料管理系统-MMS", "python", "uvicorn")
                        is_safe = any(name.lower() in proc_line.lower() for name in safe_names)
                        if not is_safe:
                            _log.warning(
                                f"检测到端口 {port} 被进程(PID={target_pid}) 占用，"
                                f"但进程名不匹配（输出: {proc_line[:100]}），为安全起见不终止"
                            )
                            toast_error(self, tr("config.web_port_foreign_process").format(
                                port=port, pid=target_pid
                            ))
                            self._sync_web_service_status()
                            return
                    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
                        _log.warning(f"进程名校验失败，跳过终止: {e}")
                        self._sync_web_service_status()
                        return
                    except Exception as e:
                        _log.warning("进程名校验未预期异常: %s", e)
                        self._sync_web_service_status()
                        return
                    subprocess.run(["taskkill", "/F", "/PID", str(target_pid)], capture_output=True)
                    _log.info(f"已终止占用端{port} 的进PID={target_pid}")
                    stopped = True
            except (OSError, RuntimeError, subprocess.SubprocessError) as e:
                _log.warning(f"停止外部 Web 服务时出 {e}")
            except Exception as e:
                _log.warning("停止外部 Web 服务未预期异 %s", e)

        # 延迟丢小段时间再同步状态，确保端口确实释放
        if stopped:
            toast_success(self, tr("config.web_stopped"))
            QTimer.singleShot(800, self._sync_web_service_status)
        else:
            self._sync_web_service_status()
            toast_info(self, tr("config.web_not_running"))

    def _cleanup_web_process(self):
        """清理 Web 服务进程"""
        if self._web_process is not None:
            self._web_stopping_intentionally = True
            try:
                if self._web_process.state() != QProcess.ProcessState.NotRunning:
                    self._web_process.terminate()
                    self._web_process.waitForFinished(2000)
                    if self._web_process.state() != QProcess.ProcessState.NotRunning:
                        self._web_process.kill()
            except (RuntimeError, OSError):
                pass
            self._web_process = None
        self._sync_web_service_status()

    def _on_web_process_output(self):
        """处理 Web 服务进程输出"""
        if self._web_process is None:
            return
        try:
            data = bytes(self._web_process.readAllStandardOutput()).decode("utf-8", errors="replace")
            _log.info(f"[Web服务] {data.strip()}")
        except Exception:
            pass

    def _on_web_process_finished(self, exit_code: int, exit_status):
        """Web 服务进程结束回调"""
        port = self.web_port.value()
        was_running = self._is_port_in_use(port) or (
            self._web_process is not None
            and self._web_process.state() != QProcess.ProcessState.NotRunning
        )
        self._sync_web_service_status()
        # 只有非主动停止且逢出码0 时才提示异常
        if was_running and not self._web_stopping_intentionally and exit_code != 0:
            toast_error(self, tr("config.web_crashed"))
        self._web_stopping_intentionally = False

    def _sync_web_service_status(self):
        """同步 Web 服务实际运行状态到启动/停止 UI"""
        if self._is_syncing_web_status:
            return
        try:
            self._is_syncing_web_status = True
            port = self.web_port.value()
            # Grace period: 服务刚启动后3秒内跳过检测（避免竞态）
            if time.time() - self._web_just_started < 3.0:
                return
            has_process = (
                self._web_process is not None
                and self._web_process.state() != QProcess.ProcessState.NotRunning
            )
            # 场景1：QProcess 状已经是运行中，直接更新 UI（无霢棢测端口）
            if has_process:
                self._update_web_service_ui(True)
                return
            # 场景2：QProcess 不在运行，用后台线程棢测端口（未监听时 connect_ex 会阻塞）
            # 先确认没有已在运行的 PortCheckThread
            if self._port_check_thread is not None and self._port_check_thread.isRunning():
                return  # 已有棢测线程在跑，跳过
            try:
                if self._port_check_thread is not None:
                    self._port_check_thread.quit()
                    self._port_check_thread.wait(500)
            except (RuntimeError, AttributeError):
                pass
            self._port_check_thread = PortCheckThread(port, timeout=0.5, parent=self)
            self._port_check_thread.check_finished.connect(self._on_port_check_finished)
            self._port_check_thread.start()
        except (RuntimeError, AttributeError):
            pass
        finally:
            self._is_syncing_web_status = False

    def _on_port_check_finished(self, port: int, is_in_use: bool):
        """端口棢测完成回调（来自后台线程"""
        try:
            # 仅当端口配置未变更时才应用检测结果（避免用户改了端口后旧结果覆盖
            current_port = self.web_port.value()
            if current_port == port:
                self._update_web_service_ui(is_in_use)
        except (RuntimeError, AttributeError):
            pass

    def _update_web_service_ui(self, running: bool):
        """更新 Web 服务相关 UI 状"""
        try:
            if running:
                self._web_status_label.setText("🟢 " + tr("config.web_status_running"))
                self._web_status_label.setStyleSheet("color: #059669; font-size: 12px; padding: 2px 6px;")
                self._set_web_toggle_button(True)
                self.web_host.setEnabled(False)
                self.web_port.setEnabled(False)
            else:
                self._web_status_label.setText("🔴 " + tr("config.web_status_stopped"))
                self._web_status_label.setStyleSheet("color: #6b7280; font-size: 12px; padding: 2px 6px;")
                self._set_web_toggle_button(False)
                self.web_host.setEnabled(True)
                self.web_port.setEnabled(True)
            # ??????????
            self._refresh_autostart_status()
        except (RuntimeError, AttributeError):
            pass

    def _set_web_toggle_button(self, running: bool):
        """Set Web service toggle button text and color"""
        try:
            if running:
                text = "停止服务"
                bg, hover, pressed = "#F15E5E", "#e04949", "#c93030"
            else:
                text = "启动服务"
                bg, hover, pressed = "#10B981", "#059669", "#047857"
            self.btn_toggle_web.setText(text)
            self.btn_toggle_web.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg}; color: white; font-weight: bold;
                    border: none; border-radius: 6px;
                    padding: 7px 12px; font-size: 12px; min-height: 30px;
                }}
                QPushButton:hover {{ background-color: {hover}; }}
                QPushButton:pressed {{ background-color: {pressed}; }}
            """)
            self.btn_toggle_web.update()
            _log.info("Web服务按钮: %s (running=%s)", text, running)
        except (RuntimeError, AttributeError) as e:
            _log.warning("设置Web服务按钮失败: %s", e)


    def _toggle_web_service(self):
        """切换 Web 服务启动/停止"""
        port = self.web_port.value()
        is_running = self._is_port_in_use(port) or (
            self._web_process is not None
            and self._web_process.state() != QProcess.ProcessState.NotRunning
        )
        if is_running:
            self._stop_web_service()
        else:
            self._start_web_service()

    # ==================== 弢机自启管====================

    _AUTOSTART_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _AUTOSTART_KEY_NAME = "物料管理系统-MMS_Web查询"

    def _get_autostart_command(self) -> str:
        """?????????"""
        port = self.web_port.value()
        if getattr(sys, "frozen", False):
            # 打包模式：动态查Web 服务 EXE（支持带版本号命名）
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            web_exe = self._find_web_exe(exe_dir)
            if not web_exe:
                web_exe = os.path.join(exe_dir, "MMS_Web服务.exe")
            return f'"{web_exe}" --host 0.0.0.0 --port {port}'
        else:
            # 弢发模式：使用 python + run.py
            run_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web_", "run.py")
            run_script = os.path.normpath(run_script)
            python_exe = sys.executable
            return f'"{python_exe}" "{run_script}" --host 0.0.0.0 --port {port}'

    def _refresh_autostart_status(self):
        """??????????"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._AUTOSTART_REG_PATH, 0, winreg.KEY_READ)
            try:
                value, _ = winreg.QueryValueEx(key, self._AUTOSTART_KEY_NAME)
                is_enabled = True
            except FileNotFoundError:
                is_enabled = False
            finally:
                winreg.CloseKey(key)
        except Exception:
            is_enabled = False

        try:
            if is_enabled:
                self._web_autostart_label.setText("🔓 " + tr("config.web_autostart_enabled"))
                self._web_autostart_label.setStyleSheet("color: #059669; font-size: 12px; padding: 2px 6px;")
                self._set_autostart_toggle_button(True)
            else:
                self._web_autostart_label.setText("🔒 " + tr("config.web_autostart_disabled"))
                self._web_autostart_label.setStyleSheet("color: #6b7280; font-size: 12px; padding: 2px 6px;")
                self._set_autostart_toggle_button(False)
        except (RuntimeError, AttributeError):
            pass

    def _set_autostart_toggle_button(self, enabled: bool):
        """Set autostart toggle button text and color"""
        try:
            if enabled:
                text = "关闭自启"
                bg, hover, pressed = "#f87171", "#ef4444", "#dc2626"
            else:
                text = "开机自启"
                bg, hover, pressed = "#10b981", "#059669", "#047857"
            self.btn_toggle_autostart.setText(text)
            self.btn_toggle_autostart.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg}; color: white; font-weight: bold;
                    border: none; border-radius: 6px;
                    padding: 7px 12px; font-size: 12px; min-height: 30px;
                }}
                QPushButton:hover {{ background-color: {hover}; }}
                QPushButton:pressed {{ background-color: {pressed}; }}
            """)
            self.btn_toggle_autostart.update()
            _log.info("开机自启按钮: %s (enabled=%s)", text, enabled)
        except (RuntimeError, AttributeError) as e:
            _log.warning("设置开机自启按钮失败: %s", e)


    def _toggle_autostart(self):
        """切换弢机自启注取消"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._AUTOSTART_REG_PATH, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, self._AUTOSTART_KEY_NAME)
                is_enabled = True
            except FileNotFoundError:
                is_enabled = False
            finally:
                winreg.CloseKey(key)
        except (OSError, RuntimeError, FileNotFoundError):
            is_enabled = False
        if is_enabled:
            self._unregister_autostart()
        else:
            self._register_autostart()

    def _register_autostart(self):
        """??????"""
        if sys.platform != "win32":
            toast_error(self, tr("config.autostart_windows_only"))
            return

        try:
            import winreg
            command = self._get_autostart_command()
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE)
            try:
                winreg.SetValueEx(key, self._AUTOSTART_KEY_NAME, 0, winreg.REG_SZ, command)
            finally:
                winreg.CloseKey(key)
            _log.info(f"已注册开机自 {command}")
            toast_success(self, tr("config.autostart_registered"))
            self._refresh_autostart_status()
        except (OSError, RuntimeError, winreg.error) as e:
            toast_error(self, f"{tr('config.autostart_register_failed')}: {e}")
        except Exception as e:
            _log.warning("注册弢机自启未预期异常: %s", e)
            toast_error(self, f"{tr('config.autostart_register_failed')}: {e}")

    def _unregister_autostart(self):
        """??????"""
        if sys.platform != "win32":
            toast_error(self, tr("config.autostart_windows_only"))
            return

        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, self._AUTOSTART_KEY_NAME)
            finally:
                winreg.CloseKey(key)
            _log.info("已取消开机自启")
            toast_success(self, tr("config.autostart_unregistered"))
            self._refresh_autostart_status()
        except FileNotFoundError:
            toast_info(self, tr("config.autostart_not_registered"))
            self._refresh_autostart_status()
        except (OSError, RuntimeError, winreg.error) as e:
            toast_error(self, f"{tr('config.autostart_unregister_failed')}: {e}")
        except Exception as e:
            _log.warning("取消弢机自启未预期异常: %s", e)
            toast_error(self, f"{tr('config.autostart_unregister_failed')}: {e}")

    # ==================== 数据加载 ====================

    def set_data(self, data: list):
        self._data = data
        db_map = {item.get("config_name", ""): item.get("content", "") for item in data}
        config_map = dict(db_map)
        # MySQL 配置优先config.ini 读取
        try:
            from utils.app_config import load_mysql_config
            mysql_ini = load_mysql_config()
            for key, ini_key in [("MYSQL_HOST", "mysql_host"), ("MYSQL_PORT", "mysql_port"),
                                  ("MYSQL_USER", "mysql_user"), ("MYSQL_DATABASE", "mysql_database"),
                                  ("MYSQL_CHARSET", "mysql_charset")]:
                if mysql_ini.get(ini_key):
                    config_map[key] = mysql_ini[ini_key]
        except Exception:
            pass
        # APP 配置config.ini [app] 节读
        try:
            from utils.app_config import load_app_config
            app_ini = load_app_config()
            config_map["APP_MODE"] = app_ini.get("app_mode", "online")
            config_map["LOG_LEVEL"] = app_ini.get("log_level", "INFO")
        except Exception:
            pass
        # Web 查询配置config.ini [web_query] 节读
        try:
            from utils.app_config import load_web_query_config
            web_ini = load_web_query_config()
            config_map["WEB_QUERY_ENABLED"] = web_ini.get("web_query_enabled", "0")
            config_map["WEB_QUERY_HOST"] = web_ini.get("web_query_host", "localhost")
            config_map["WEB_QUERY_PORT"] = web_ini.get("web_query_port", "8000")
            config_map["WEB_QUERY_API_BASE"] = web_ini.get("web_query_api_base", "/api")
            config_map["WEB_QUERY_API_KEY"] = web_ini.get("web_query_api_key", "")
            config_map["WEB_QUERY_TIMEOUT"] = web_ini.get("web_query_timeout", "10")
            config_map["WEB_QUERY_USE_HTTPS"] = web_ini.get("web_query_use_https", "0")
        except Exception:
            pass
        # 串口/硬件配置优先config.ini 读取
        try:
            from utils.app_config import load_serial_config
            serial_ini = load_serial_config()
            config_map["FINGERPRINT_ENABLED"] = serial_ini.get("fingerprint_enabled", "0")
            config_map["NFC_ENABLED"] = serial_ini.get("nfc_enabled", "0")
            config_map["FINGERPRINT_DEVICE"] = serial_ini.get("fingerprint_device", "")
            config_map["NFC_DEVICE"] = serial_ini.get("nfc_device", "")
            config_map["FINGERPRINT_BAUD_RATE"] = serial_ini.get("fingerprint_baud_rate", "9600")
            config_map["NFC_BAUD_RATE"] = serial_ini.get("nfc_baud_rate", "9600")
        except Exception:
            pass
        # FTP 更新配置（config.ini [update] 节读
        try:
            from utils.ftp_config import load_update_config
            ftp_ini = load_update_config()
            if ftp_ini.get("host"):
                config_map["UPDATE_FTP_HOST"] = ftp_ini["host"]
            if ftp_ini.get("port"):
                config_map["UPDATE_FTP_PORT"] = str(ftp_ini["port"])
            if ftp_ini.get("user"):
                config_map["UPDATE_FTP_USER"] = ftp_ini["user"]
            if ftp_ini.get("directory"):
                config_map["UPDATE_FTP_DIR"] = ftp_ini["directory"]
        except Exception:
            pass

        self.db_host.setText(config_map.get("MYSQL_HOST", "localhost"))
        self.db_port.setValue(self._to_int(config_map.get("MYSQL_PORT", "3306"), 3306))
        self.db_user.setText(config_map.get("MYSQL_USER", "root"))
        pw, _ = get_password()
        self.db_password.setText(pw)
        self.db_name.setText(config_map.get("MYSQL_DATABASE", "mms"))
        idx = self.db_charset.findText(config_map.get("MYSQL_CHARSET", "utf8mb4"))
        self.db_charset.setCurrentIndex(max(0, idx))

        self.sync_interval.setValue(self._to_int(config_map.get("SYNC_INTERVAL_SECONDS", "30"), 30))
        self.sync_retry.setValue(self._to_int(config_map.get("SYNC_RETRY_MAX", "3"), 3))
        self.sync_batch.setValue(self._to_int(config_map.get("SYNC_BATCH_SIZE", "50"), 50))
        self.full_sync_interval.setValue(self._to_int(config_map.get("FULL_SYNC_INTERVAL_MINUTES", "30"), 30))

        self.stale_days.setValue(self._to_int(config_map.get("STALE_DAYS_THRESHOLD", "90"), 90))
        self.expire_days.setValue(self._to_int(config_map.get("CHECK_EXPIRE_DAYS", "7"), 7))
        self.low_stock.setValue(self._to_int(config_map.get("LOW_STOCK_THRESHOLD", "10"), 10))
        idx = self.auto_export.findText(
            tr("config.auto_export_on") if config_map.get("AUTO_EXPORT_ENABLED") == "1" else tr("config.auto_export_off")
        )
        self.auto_export.setCurrentIndex(max(0, idx))

        self.network_check.setValue(self._to_int(config_map.get("NETWORK_CHECK_INTERVAL_SECONDS", "10"), 10))
        mode = config_map.get("APP_MODE", "online")
        idx = self.app_mode.findText(mode)
        self.app_mode.setCurrentIndex(max(0, idx))

        web_enabled = config_map.get("WEB_QUERY_ENABLED", "0") == "1"
        idx = self.web_enabled.findText(tr("config.web_on") if web_enabled else tr("config.web_off"))
        self.web_enabled.setCurrentIndex(max(0, idx))
        self.web_host.setText(config_map.get("WEB_QUERY_HOST", "localhost"))
        self.web_port.setValue(self._to_int(config_map.get("WEB_QUERY_PORT", "8000"), 8000))
        self.web_api_base.setText(config_map.get("WEB_QUERY_API_BASE", "/api"))
        self.web_api_key.setText(config_map.get("WEB_QUERY_API_KEY", ""))
        self.web_timeout.setValue(self._to_int(config_map.get("WEB_QUERY_TIMEOUT", "10"), 10))
        web_https = config_map.get("WEB_QUERY_USE_HTTPS", "0") == "1"
        self.web_use_https.setText("HTTPS" if web_https else "HTTP")

        if config_map.get("FINGERPRINT_ENABLED", "0") == "1":
            self.fingerprint_enabled.setCurrentText(tr("config.fingerprint_on"))
        else:
            self.fingerprint_enabled.setCurrentText(tr("config.fingerprint_off"))
        if config_map.get("NFC_ENABLED", "0") == "1":
            self.nfc_enabled.setCurrentText(tr("config.nfc_on"))
        else:
            self.nfc_enabled.setCurrentText(tr("config.nfc_off"))
        fp_port = config_map.get("FINGERPRINT_DEVICE", "")
        if fp_port and fp_port in [str(self.fingerprint_device.itemText(i)) for i in range(self.fingerprint_device.count())]:
            self.fingerprint_device.setCurrentText(fp_port)
        else:
            self.fingerprint_device.setCurrentIndex(0)
        nfc_port = config_map.get("NFC_DEVICE", "")
        if nfc_port and nfc_port in [str(self.nfc_device.itemText(i)) for i in range(self.nfc_device.count())]:
            self.nfc_device.setCurrentText(nfc_port)
        else:
            self.nfc_device.setCurrentIndex(0)
        # 指纹波特
        fp_baud_val = config_map.get("FINGERPRINT_BAUD_RATE", "9600")
        try:
            idx = self.fingerprint_baud_rate.findText(str(int(fp_baud_val)))
            if idx >= 0:
                self.fingerprint_baud_rate.setCurrentIndex(idx)
        except (ValueError, TypeError):
            pass
        # NFC波特
        nfc_baud_val = config_map.get("NFC_BAUD_RATE", "9600")
        try:
            idx = self.nfc_baud_rate.findText(str(int(nfc_baud_val)))
            if idx >= 0:
                self.nfc_baud_rate.setCurrentIndex(idx)
        except (ValueError, TypeError):
            pass

        # 更新配置
        self.update_host.setText(config_map.get("UPDATE_FTP_HOST", ""))
        self.update_port.setValue(self._to_int(config_map.get("UPDATE_FTP_PORT", "21"), 21))
        self.update_user.setText(config_map.get("UPDATE_FTP_USER", ""))
        # FTP 密码优先keyring/fallback（与 MySQL 同构），config_map 不含明文
        ftp_pass = config_map.get("UPDATE_FTP_PASS", "")
        if not ftp_pass:
            try:
                from utils.credential_manager import get_ftp_password
                ftp_pass = get_ftp_password()
            except Exception:
                pass
        self.update_pass.setText(ftp_pass)
        self.update_dir.setText(config_map.get("UPDATE_FTP_DIR", "/updates/mms/"))

        # 加载配置后自动检Web 服务状
        self._sync_web_service_status()

    def _to_int(self, val, default: int) -> int:
        try:
            return int(val) if val else default
        except (ValueError, TypeError):
            return default

    def _build_update_form(self, layout):
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.update_host = QLineEdit()
        self.update_host.setPlaceholderText(tr("update.host"))
        self.update_host.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("update.host"))
        self._form_labels["update_host"] = lbl
        grid.addWidget(lbl, 0, 0)
        grid.addWidget(self.update_host, 0, 1)

        self.update_port = QSpinBox()
        self.update_port.setRange(1, 65535)
        self.update_port.setValue(21)
        self.update_port.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("update.port"))
        self._form_labels["update_port"] = lbl
        grid.addWidget(lbl, 0, 2)
        grid.addWidget(self.update_port, 0, 3)

        self.update_user = QLineEdit()
        self.update_user.setPlaceholderText(tr("update.user"))
        self.update_user.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("update.user"))
        self._form_labels["update_user"] = lbl
        grid.addWidget(lbl, 1, 0)
        grid.addWidget(self.update_user, 1, 1)

        self.update_pass = QLineEdit()
        self.update_pass.setEchoMode(QLineEdit.Password)
        self.update_pass.setPlaceholderText(tr("update.pass"))
        self.update_pass.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("update.pass"))
        self._form_labels["update_pass"] = lbl
        grid.addWidget(lbl, 1, 2)
        grid.addWidget(self.update_pass, 1, 3)

        self.update_dir = QLineEdit()
        self.update_dir.setPlaceholderText(tr("update.dir"))
        self.update_dir.setText("/updates/mms/")
        self.update_dir.setStyleSheet(INPUT_STYLE)
        lbl = QLabel(tr("update.dir"))
        self._form_labels["update_dir"] = lbl
        grid.addWidget(lbl, 2, 0)
        grid.addWidget(self.update_dir, 2, 1, 1, 3)

        layout.addLayout(grid)

    def _collect_configs(self) -> list:
        return [
            {"config_name": "APP_MODE", "item_type": "sync", "content": self.app_mode.currentText(), "sort_order": 0},
            {"config_name": "MYSQL_HOST", "item_type": "database", "content": self.db_host.text().strip(), "sort_order": 1},
            {"config_name": "MYSQL_PORT", "item_type": "database", "content": str(self.db_port.value()), "sort_order": 2},
            {"config_name": "MYSQL_USER", "item_type": "database", "content": self.db_user.text().strip(), "sort_order": 3},
            {"config_name": "MYSQL_PASSWORD", "item_type": "database", "content": self.db_password.text(), "sort_order": 4},
            {"config_name": "MYSQL_DATABASE", "item_type": "database", "content": self.db_name.text().strip(), "sort_order": 5},
            {"config_name": "MYSQL_CHARSET", "item_type": "database", "content": self.db_charset.currentText(), "sort_order": 6},
            {"config_name": "SYNC_INTERVAL_SECONDS", "item_type": "sync", "content": str(self.sync_interval.value()), "sort_order": 10},
            {"config_name": "SYNC_RETRY_MAX", "item_type": "sync", "content": str(self.sync_retry.value()), "sort_order": 11},
            {"config_name": "SYNC_BATCH_SIZE", "item_type": "sync", "content": str(self.sync_batch.value()), "sort_order": 12},
            {"config_name": "FULL_SYNC_INTERVAL_MINUTES", "item_type": "sync", "content": str(self.full_sync_interval.value()), "sort_order": 13},
            {"config_name": "STALE_DAYS_THRESHOLD", "item_type": "alert", "content": str(self.stale_days.value()), "sort_order": 20},
            {"config_name": "CHECK_EXPIRE_DAYS", "item_type": "alert", "content": str(self.expire_days.value()), "sort_order": 21},
            {"config_name": "LOW_STOCK_THRESHOLD", "item_type": "alert", "content": str(self.low_stock.value()), "sort_order": 22},
            {"config_name": "AUTO_EXPORT_ENABLED", "item_type": "alert", "content": "1" if self.auto_export.currentText() == tr("config.auto_export_on") else "0", "sort_order": 23},
            {"config_name": "NETWORK_CHECK_INTERVAL_SECONDS", "item_type": "sync", "content": str(self.network_check.value()), "sort_order": 14},
            {"config_name": "WEB_QUERY_ENABLED", "item_type": "web_query", "content": "1" if self.web_enabled.currentText() == tr("config.web_on") else "0", "sort_order": 50},
            {"config_name": "WEB_QUERY_HOST", "item_type": "web_query", "content": self.web_host.text().strip(), "sort_order": 51},
            {"config_name": "WEB_QUERY_PORT", "item_type": "web_query", "content": str(self.web_port.value()), "sort_order": 52},
            {"config_name": "WEB_QUERY_API_BASE", "item_type": "web_query", "content": self.web_api_base.text().strip(), "sort_order": 53},
            {"config_name": "WEB_QUERY_API_KEY", "item_type": "web_query", "content": self.web_api_key.text(), "sort_order": 54},
            {"config_name": "WEB_QUERY_TIMEOUT", "item_type": "web_query", "content": str(self.web_timeout.value()), "sort_order": 55},
            {"config_name": "WEB_QUERY_USE_HTTPS", "item_type": "web_query", "content": "1" if self.web_use_https.text() == "HTTPS" else "0", "sort_order": 56},
            {"config_name": "FINGERPRINT_ENABLED", "item_type": "hardware", "content": "1" if self.fingerprint_enabled.currentText() == tr("config.fingerprint_on") else "0", "sort_order": 70},
            {"config_name": "NFC_ENABLED", "item_type": "hardware", "content": "1" if self.nfc_enabled.currentText() == tr("config.nfc_on") else "0", "sort_order": 71},
            {"config_name": "FINGERPRINT_DEVICE", "item_type": "hardware", "content": self.fingerprint_device.currentText().strip(), "sort_order": 72},
            {"config_name": "NFC_DEVICE", "item_type": "hardware", "content": self.nfc_device.currentText().strip(), "sort_order": 73},
            {"config_name": "FINGERPRINT_BAUD_RATE", "item_type": "hardware", "content": self.fingerprint_baud_rate.currentText(), "sort_order": 74},
            {"config_name": "NFC_BAUD_RATE", "item_type": "hardware", "content": self.nfc_baud_rate.currentText(), "sort_order": 75},
        ]

    def collect_configs(self) -> list:
        """?????????? API ?????"""
        return self._collect_configs()

    # ==================== 事件处理 ====================

    def _on_save_clicked(self):
        if show_confirm(self, tr("confirm.save_title"), tr("confirm.save_message"), "info"):
            self._save_all_configs()

    def _save_all_configs(self):
        configs = self._collect_configs()
        self._data = configs

        # MySQL 配置写入 config.ini
        try:
            from utils.app_config import save_mysql_config
            save_result = save_mysql_config({
                "mysql_host": self.db_host.text().strip() or "localhost",
                "mysql_port": str(self.db_port.value() or 3306),
                "mysql_user": self.db_user.text().strip() or "root",
                "mysql_password": self.db_password.text() or "",
                "mysql_database": self.db_name.text().strip() or "mms",
                "mysql_charset": self.db_charset.currentText(),
            })
            saved_pw = bool(save_result.get("password_stored", False))
            store = save_result.get("store", "error")
            verified = save_result.get("verified", False)
            if self.db_password.text() and not saved_pw:
                toast_error(self, "密码保存失败：系统密钥库不可用")
            elif self.db_password.text() and store == "fallback":
                toast_warning(self, "密码已保存到本地加密文件（系统密钥库不可用，建议检查凭据管理器）")
        except Exception as e:
            _log.error("保存 MySQL 配置异常: %s", e)
            toast_error(self, f"保存 MySQL 配置失败: {e}")
        # 串口/硬件配置写入 config.ini
        try:
            from utils.app_config import save_serial_config
            save_serial_config({
                "fingerprint_enabled": "1" if self.fingerprint_enabled.currentText() == tr("config.fingerprint_on") else "0",
                "nfc_enabled": "1" if self.nfc_enabled.currentText() == tr("config.nfc_on") else "0",
                "fingerprint_device": self.fingerprint_device.currentText().strip(),
                "nfc_device": self.nfc_device.currentText().strip(),
                "fingerprint_baud_rate": self.fingerprint_baud_rate.currentText(),
                "nfc_baud_rate": self.nfc_baud_rate.currentText(),
            })
        except Exception:
            pass
        # FTP 更新配置写入 config.ini
        try:
            from utils.ftp_config import save_update_config
            save_update_config({
                "enabled": False,
                "host": self.update_host.text().strip(),
                "port": self.update_port.value(),
                "user": self.update_user.text().strip(),
                "pass": self.update_pass.text(),
                "directory": self.update_dir.text().strip(),
            })
        except Exception:
            pass

        # APP 配置（APP_MODE, LOG_LEVEL）写config.ini
        try:
            from utils.app_config import save_app_config
            save_app_config({
                "app_mode": self.app_mode.currentText() or "online",
                "log_level": "INFO",
            })
        except Exception:
            pass
        # Web 查询配置写入 config.ini
        try:
            from utils.app_config import save_web_query_config
            save_web_query_config({
                "web_query_enabled": "1" if self.web_enabled.currentText() == tr("config.web_on") else "0",
                "web_query_host": self.web_host.text().strip() or "localhost",
                "web_query_port": str(self.web_port.value() or 8000),
                "web_query_api_base": self.web_api_base.text().strip() or "/api",
                "web_query_api_key": self.web_api_key.text(),
                "web_query_timeout": str(self.web_timeout.value() or 10),
                "web_query_use_https": "1" if self.web_use_https.text() == "HTTPS" else "0",
            })
        except Exception:
            pass

        toast_success(self, tr("toast.save_success"))
        self.config_saved.emit()

    def _on_reset_clicked(self):
        if show_confirm(self, tr("confirm.reset_title"), tr("confirm.reset_message"), "warning"):
            self._reset_configs()

    def _reset_configs(self):
        self.db_host.setText("localhost")
        self.db_port.setValue(3306)
        self.db_user.setText("root")
        self.db_password.setText("")
        self.db_name.setText("mms")
        self.db_charset.setCurrentIndex(0)
        self.sync_interval.setValue(30)
        self.sync_retry.setValue(3)
        self.sync_batch.setValue(50)
        self.full_sync_interval.setValue(30)
        self.stale_days.setValue(90)
        self.expire_days.setValue(7)
        self.low_stock.setValue(10)
        self.auto_export.setCurrentIndex(0)
        self.network_check.setValue(10)
        self.web_enabled.setCurrentIndex(0)
        self.web_host.setText("localhost")
        self.web_port.setValue(8000)
        self.web_api_base.setText("/api")
        self.web_api_key.setText("")
        self.web_timeout.setValue(10)
        self.web_use_https.setText("HTTPS")
        toast_success(self, tr("toast.reset_success"))

    # ==================== 数据库连接测====================

    def _test_db_connection(self):
        """连接测试 使用后台线程，避免阻塞主线程 UI"""
        host = self.db_host.text().strip()
        port = self.db_port.value()
        user = self.db_user.text().strip()
        password = self.db_password.text()
        database = self.db_name.text().strip()
        charset = self.db_charset.currentText()

        if not host or not user:
            toast_error(self, tr("toast.test_need_host"))
            return

        toast_info(self, tr("toast.test_connecting"), 2000)

        # 使用后台线程执行连接测试，完成后通过信号返回结果
        self._mysql_test_thread = MySQLTestThread(
            host=host, port=port, user=user, password=password,
            database=database, charset=charset, parent=self
        )

        def _on_result(is_online: bool, detail: str):
            if is_online:
                toast_success(self, tr("toast.test_success", detail=detail), 3000)
            else:
                toast_error(self, tr("toast.test_fail", detail=detail), 4000)
            self._on_mysql_test_result(is_online, detail)

        self._mysql_test_thread.test_finished.connect(_on_result)
        self._mysql_test_thread.finished.connect(self._cleanup_mysql_thread)
        self._mysql_test_thread.start()

    # ==================== 状面板更新（v2.3 核心优化===================

    def _update_status_panel(self):
        """状面板更仅在页面可见时调"""
        if self._local_db is None:
            return

        # v2.3: 合并 SQLite 查询，减I/O 次数
        stats = self._get_all_stats()

        # 系统概览（增量更新）
        self._update_card_overview(stats)

        # 数据量统计（迷你卡片
        self._update_mini_stats(stats)

        # 同步状
        self._update_card_sync(stats)

        # MySQL 状：后台线程异步棢
        self._async_update_mysql_status()

        # FTP 状：后台线程异步棢
        self._async_update_ftp_status()

        # Web 服务状：端口棢+ QProcess 状
        self._sync_web_service_status()

    def _get_all_stats(self) -> dict:
        """v2.3 新增：合并所SQLite 统计查询为单次批量查询（带缓存）"""
        import time as _time
        # 2 秒缓存，避免短时间内重复查询
        now = _time.time()
        if self._stats_cache and (now - self._stats_cache_time) < 2.0:
            return self._stats_cache

        stats = {
            "materials": 0, "borrow": 0, "assets": 0, "configs": 0,
            "sync_queue": 0, "last_push": "...", "last_pull": "...",
            "db_file": "...", "total": 0,
        }
        _STATS_TABLE_MAP = {
            "materials": TABLE_MATERIALS,
            "borrow": TABLE_BORROW_RECORDS,
            "assets": TABLE_FIXED_ASSETS,
            "configs": TABLE_CONFIG_ITEMS,
        }
        _ALLOWED_STATS_TABLES = set(_STATS_TABLE_MAP.values())
        try:
            from config import LOCAL_DB_PATH
            stats["db_file"] = os.path.basename(LOCAL_DB_PATH)
        except (ImportError, AttributeError, OSError) as e:
            _log.warning("获取数据库路径失 %s", e)
        except Exception as e:
            _log.warning("获取数据库路径未预期异常: %s", e)

        try:
            import sqlite3
            conn = self._local_db._get_conn()

            # 合并 COUNT 查询：单UNION ALL 查询扢有表的记录数
            try:
                _q = lambda t: f'"{t}"'
                union_sql = " UNION ALL ".join(
                    f"SELECT '{k}' as tbl, COUNT(*) as cnt FROM {_q(v)}"
                    for k, v in _STATS_TABLE_MAP.items()
                ) + " UNION ALL SELECT 'sync_queue' as tbl, COUNT(*) as cnt FROM sync_queue"
                cursor = conn.execute(union_sql)
                for row in cursor.fetchall():
                    stats[row["tbl"]] = row["cnt"]
            except (sqlite3.Error, RuntimeError) as e:
                _log.warning("合并统计查询失败，回逢到单表查 %s", e)
                # 回：个查询
                _q = lambda t: f'"{t}"'
                for k, v in _STATS_TABLE_MAP.items():
                    try:
                        cursor = conn.execute(f"SELECT COUNT(*) as count FROM {_q(v)}")
                        stats[k] = cursor.fetchone()["count"]
                    except (sqlite3.Error, RuntimeError):
                        pass
                try:
                    cursor = conn.execute("SELECT COUNT(*) as count FROM sync_queue")
                    stats["sync_queue"] = cursor.fetchone()["count"]
                except (sqlite3.Error, RuntimeError):
                    pass
            except Exception as e:
                _log.warning("合并统计查询未预期异 %s", e)

            # 朢后同步时间（丢次查push pull
            try:
                cursor = conn.execute(
                    "SELECT direction, MAX(created_at) as last_time FROM sync_log "
                    "WHERE status = 'success' AND direction IN ('push','pull') GROUP BY direction"
                )
                for row in cursor.fetchall():
                    key = f"last_{row['direction']}"
                    if row["last_time"]:
                        stats[key] = row["last_time"][:19]
            except (sqlite3.Error, RuntimeError) as e:
                _log.warning("查询朢后同步时间失 %s", e)
            except Exception as e:
                _log.warning("查询朢后同步时间未预期异常: %s", e)

        except (sqlite3.Error, RuntimeError, AttributeError) as e:
            _log.warning("获取数据库统计信息失 %s", e)
        except Exception as e:
            _log.warning("获取数据库统计信息未预期异常: %s", e)

        stats["total"] = sum(stats.get(k, 0) for k in _STATS_TABLE_MAP)

        self._stats_cache = stats
        self._stats_cache_time = now
        return stats

    def _update_card_overview(self, stats: dict):
        """系统概览 增量更新"""
        mode = self.app_mode.currentText() if hasattr(self, "app_mode") else "online"
        mode_labels = {
            "online": (tr("config.mode_online"), "#059669"),
            "semi_offline": (tr("config.mode_semi_offline"), "#d97706"),
            "offline": (tr("config.mode_offline"), "#dc2626"),
        }
        label, color = mode_labels.get(mode, (mode, "#1f2937"))

        self.card_overview.set_row("version", tr("config.label_version"), APP_VERSION)
        self.card_overview.set_row("mode", tr("config.label_mode"), label, color)
        self.card_overview.set_row("db_file", tr("config.label_db_file"), stats.get("db_file", "..."))
        self.card_overview.set_row("total", tr("config.label_total"), tr("config.records_count", count=stats.get("total", 0)))

    def _update_mini_stats(self, stats: dict):
        """更新 2x2 迷你统计卡片"""
        values = {
            "materials": str(stats.get("materials", 0)),
            "borrow": str(stats.get("borrow", 0)),
            "assets": str(stats.get("assets", 0)),
            "configs": str(stats.get("configs", 0)),
        }
        for key, mini in self._mini_stats.items():
            mini.set_value(values.get(key, "0"))

    def _update_card_sync(self, stats: dict):
        """同步状增量更新"""
        queue_count = stats.get("sync_queue", 0)
        color = "#059669" if queue_count == 0 else "#d97706"
        self.card_sync.set_row("queue", tr("config.label_queue"), tr("config.records_count", count=queue_count), color)
        self.card_sync.set_row("last_push", tr("config.label_last_push"), stats.get("last_push", "..."))
        self.card_sync.set_row("last_pull", tr("config.label_last_pull"), stats.get("last_pull", "..."))

    def _async_update_mysql_status(self):
        """v2.3 核心优化：后台线程异步检MySQL，彻底消除主线程阻塞"""
        # 安全棢测并清理已完成的旧线程（防止 RuntimeError: already deleted
        if self._mysql_test_thread is not None:
            try:
                if self._mysql_test_thread.isRunning():
                    return
            except RuntimeError:
                # C++ 对象已被外部 deleteLater 锢毁，安全重置引用即可
                pass
            self._mysql_test_thread = None

        host = self.db_host.text().strip()
        port = self.db_port.value()
        user = self.db_user.text().strip()
        password = self.db_password.text()
        database = self.db_name.text().strip()
        charset = self.db_charset.currentText()

        if not host or not user:
            self._on_mysql_test_result(False, tr("config.no_host_or_user"))
            return
        if not password:
            self._on_mysql_test_result(False, tr("config.no_password"))
            return

        # 创建并启动后台线
        self._mysql_test_thread = MySQLTestThread(
            host=host, port=port, user=user, password=password,
            database=database, charset=charset, parent=self
        )
        self._mysql_test_thread.test_finished.connect(self._on_mysql_test_result)
        self._mysql_test_thread.finished.connect(self._cleanup_mysql_thread)
        self._mysql_test_thread.start()

    def _on_mysql_test_result(self, is_online: bool, detail: str):
        """MySQL 棢测完成的回调（在主线程执行，安全更新 UI"""
        self.card_mysql.set_status_row("status", tr("config.status_online") if is_online else tr("config.status_offline"), is_online)

        host = self.db_host.text().strip() or ""
        port = str(self.db_port.value())
        db = self.db_name.text().strip() or ""
        self.card_mysql.set_row("host", tr("config.label_host"), host)
        self.card_mysql.set_row("port", tr("config.label_port"), port)
        self.card_mysql.set_row("db", tr("config.label_db"), db)

        if detail and not is_online:
            self.card_mysql.set_error_row("error", detail[:200])
        else:
            # 清除错误
            self.card_mysql.clear_row("error")

    def _cleanup_mysql_thread(self):
        """线程完成后的清理（在主线程执行，安全重置引用"""
        self._mysql_test_thread = None

    def _async_update_ftp_status(self):
        """后台线程异步棢FTP 状"""
        if self._ftp_test_thread is not None:
            try:
                if self._ftp_test_thread.isRunning():
                    return
            except RuntimeError:
                pass
            self._ftp_test_thread = None
        try:
            from utils.ftp_config import load_update_config
            cfg = load_update_config()
        except Exception:
            self._on_ftp_test_result(False, "配置读取失败")
            return
        host = cfg.get("host", "")
        port = cfg.get("port", 21)
        user = cfg.get("user", "")
        password = cfg.get("pass", "")
        if not host or not user:
            self._on_ftp_test_result(False, "未配FTP")
            return
        self.card_ftp.set_status_row("status", tr("config.status_checking"), False)
        self.card_ftp.set_row("host", tr("config.label_ftp_host"), f"{host}:{port}")
        self._ftp_test_thread = _FtpTestThread(host, port, user, password, directory=cfg.get("directory", ""), parent=self)
        self._ftp_test_thread.test_finished.connect(self._on_ftp_test_result)
        self._ftp_test_thread.finished.connect(self._cleanup_ftp_thread)
        self._ftp_test_thread.start()

    def _on_ftp_test_result(self, is_online: bool, detail: str):
        """FTP 棢测完成的回调"""
        if is_online:
            self.card_ftp.set_status_row("status", tr("config.status_online"), True)
            self.card_ftp.clear_row("error")
        else:
            self.card_ftp.set_status_row("status", tr("config.status_offline"), False)
            if detail:
                self.card_ftp.set_error_row("error", detail[:200])

    def _cleanup_ftp_thread(self):
        self._ftp_test_thread = None

    # ==================== 配置导入导出（与 v2.2 丢致）====================

    def _export_config(self):
        configs = self._collect_configs()
        export_data = {
            "export_time": datetime.now().isoformat(),
            "version": APP_VERSION,
            "configs": configs,
        }
        path, _ = QFileDialog.getSaveFileName(
            self, tr("config.export_dialog"), "mms_config_backup.json", tr("config.json_filter")
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                toast_success(self, tr("toast.export_success", name=os.path.basename(path)))
            except (OSError, IOError, UnicodeEncodeError) as e:
                toast_error(self, tr("toast.export_fail", error=str(e)))
            except Exception as e:
                _log.warning("导出配置未预期异 %s", e)
                toast_error(self, tr("toast.export_fail", error=str(e)))

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("config.import_dialog"), "", tr("config.json_filter")
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            configs = data.get("configs", [])
            if not configs:
                toast_error(self, tr("toast.import_invalid"))
                return
            config_map = {c["config_name"]: c["content"] for c in configs}

            if "APP_MODE" in config_map:
                idx = self.app_mode.findText(config_map["APP_MODE"])
                self.app_mode.setCurrentIndex(max(0, idx))
            if "MYSQL_HOST" in config_map:
                self.db_host.setText(config_map["MYSQL_HOST"])
            if "MYSQL_PORT" in config_map:
                self.db_port.setValue(self._to_int(config_map["MYSQL_PORT"], 3306))
            if "MYSQL_USER" in config_map:
                self.db_user.setText(config_map["MYSQL_USER"])
            if "MYSQL_PASSWORD" in config_map:
                pw = config_map["MYSQL_PASSWORD"]
                if not pw:
                    pw, _ = get_password()
                self.db_password.setText(pw)
            if "MYSQL_DATABASE" in config_map:
                self.db_name.setText(config_map["MYSQL_DATABASE"])
            if "MYSQL_CHARSET" in config_map:
                idx = self.db_charset.findText(config_map["MYSQL_CHARSET"])
                self.db_charset.setCurrentIndex(max(0, idx))
            if "SYNC_INTERVAL_SECONDS" in config_map:
                self.sync_interval.setValue(self._to_int(config_map["SYNC_INTERVAL_SECONDS"], 30))
            if "SYNC_RETRY_MAX" in config_map:
                self.sync_retry.setValue(self._to_int(config_map["SYNC_RETRY_MAX"], 3))
            if "SYNC_BATCH_SIZE" in config_map:
                self.sync_batch.setValue(self._to_int(config_map["SYNC_BATCH_SIZE"], 50))
            if "FULL_SYNC_INTERVAL_MINUTES" in config_map:
                self.full_sync_interval.setValue(self._to_int(config_map["FULL_SYNC_INTERVAL_MINUTES"], 30))
            if "STALE_DAYS_THRESHOLD" in config_map:
                self.stale_days.setValue(self._to_int(config_map["STALE_DAYS_THRESHOLD"], 90))
            if "CHECK_EXPIRE_DAYS" in config_map:
                self.expire_days.setValue(self._to_int(config_map["CHECK_EXPIRE_DAYS"], 7))
            if "LOW_STOCK_THRESHOLD" in config_map:
                self.low_stock.setValue(self._to_int(config_map["LOW_STOCK_THRESHOLD"], 10))
            if "NETWORK_CHECK_INTERVAL_SECONDS" in config_map:
                self.network_check.setValue(self._to_int(config_map["NETWORK_CHECK_INTERVAL_SECONDS"], 10))
            if "WEB_QUERY_ENABLED" in config_map:
                enabled = config_map["WEB_QUERY_ENABLED"] == "1"
                idx = self.web_enabled.findText(tr("config.web_on") if enabled else tr("config.web_off"))
                self.web_enabled.setCurrentIndex(max(0, idx))
            if "WEB_QUERY_HOST" in config_map:
                self.web_host.setText(config_map["WEB_QUERY_HOST"])
            if "WEB_QUERY_PORT" in config_map:
                self.web_port.setValue(self._to_int(config_map["WEB_QUERY_PORT"], 8000))
            if "WEB_QUERY_API_BASE" in config_map:
                self.web_api_base.setText(config_map["WEB_QUERY_API_BASE"])
            if "WEB_QUERY_API_KEY" in config_map:
                self.web_api_key.setText(config_map["WEB_QUERY_API_KEY"])
            if "WEB_QUERY_TIMEOUT" in config_map:
                self.web_timeout.setValue(self._to_int(config_map["WEB_QUERY_TIMEOUT"], 10))
            if "WEB_QUERY_USE_HTTPS" in config_map:
                https = config_map["WEB_QUERY_USE_HTTPS"] == "1"
                self.web_use_https.setText("HTTPS" if https else "HTTP")

            toast_success(self, tr("toast.config_import_success", name=os.path.basename(path)))
        except (OSError, IOError, json.JSONDecodeError, KeyError, ValueError) as e:
            toast_error(self, tr("toast.import_fail", error=str(e)))
        except Exception as e:
            _log.warning("导入配置未预期异 %s", e)
            toast_error(self, tr("toast.import_fail", error=str(e)))

    def _clear_sync_queue(self):
        if not show_confirm(self, tr("confirm.clear_title"), tr("confirm.clear_message"), "error"):
            return
        if self._local_db is None:
            toast_error(self, tr("toast.db_not_ready"))
            return
        try:
            self._local_db.clear_table("sync_queue")
            toast_success(self, tr("toast.clear_success"))
            self._update_status_panel()
        except (RuntimeError, AttributeError, ValueError) as e:
            toast_error(self, tr("toast.clear_fail", error=str(e)))
        except Exception as e:
            _log.warning("清空同步队列未预期异 %s", e)
            toast_error(self, tr("toast.clear_fail", error=str(e)))

    # ==================== 国际 重新翻译界面 ====================

    def retranslate_ui(self):
        """重新应用当前语言的文"""
        # 页面标题
        self._page_title.setText(tr("config.page_title"))

        # 顶部按钮
        self.btn_save.setText(tr("config.btn_save"))
        self.btn_reset.setText(tr("config.btn_reset"))

        # 配置分组标题
        group_titles = {
            "database": "config.group_database",
            "sync": "config.group_sync",
            "alert": "config.group_alert",
            "web_query": "config.group_web_query",
            "hardware": "config.group_hardware",
            "update": "update.title",
        }
        for key, group in self._config_groups.items():
            group.set_title(tr(group_titles[key]))

        # 表单标签
        form_label_map = {
            "db_host": "config.param_db_host",
            "db_port": "config.param_db_port",
            "db_user": "config.param_db_user",
            "db_password": "config.param_db_password",
            "db_name": "config.param_db_name",
            "db_charset": "config.param_db_charset",
            "app_mode": "config.param_app_mode",
            "sync_interval": "config.param_sync_interval",
            "sync_retry": "config.param_sync_retry",
            "sync_batch": "config.param_sync_batch",
            "full_sync_interval": "config.param_full_sync_interval",
            "stale_days": "config.param_stale_days",
            "expire_days": "config.param_expire_days",
            "low_stock": "config.param_low_stock",
            "auto_export": "config.param_auto_export",
            "network_check": "config.param_network_check",
            "web_enabled": "config.param_web_enabled",
            "web_host": "config.param_web_host",
            "web_port": "config.param_web_port",
            "web_api_base": "config.param_web_api_base",
            "web_api_key": "config.param_web_api_key",
            "web_timeout": "config.param_web_timeout",
            "web_use_https": "config.param_web_use_https",
        }
        for key, lbl in self._form_labels.items():
            if key in form_label_map:
                lbl.setText(tr(form_label_map[key]))

        # 占位文本
        self.db_host.setPlaceholderText(tr("config.placeholder_db_host"))
        self.db_user.setPlaceholderText(tr("config.placeholder_db_user"))
        self.db_password.setPlaceholderText(tr("config.placeholder_db_password"))
        self.db_name.setPlaceholderText(tr("config.placeholder_db_name"))
        self.web_host.setPlaceholderText(tr("config.placeholder_web_host"))
        self.web_api_base.setPlaceholderText(tr("config.placeholder_web_api_base"))
        self.web_api_key.setPlaceholderText(tr("config.placeholder_web_api_key"))

        # 工具提示
        self.app_mode.setToolTip(tr("config.tooltip_app_mode"))

        # SpinBox 后缀
        self.sync_interval.setSuffix(tr("config.unit_seconds"))
        self.sync_retry.setSuffix(tr("config.unit_times"))
        self.sync_batch.setSuffix(tr("config.unit_items"))
        self.full_sync_interval.setSuffix(tr("config.unit_minutes"))
        self.stale_days.setSuffix(tr("config.unit_days"))
        self.expire_days.setSuffix(tr("config.unit_days"))
        self.low_stock.setSuffix(tr("config.unit_count"))
        self.network_check.setSuffix(tr("config.unit_seconds"))
        self.web_timeout.setSuffix(tr("config.unit_seconds"))

        # 自动导出弢关：保存当前选择，更新项文本，恢复择
        auto_current = self.auto_export.currentText()
        self.auto_export.clear()
        self.auto_export.addItems([tr("config.auto_export_off"), tr("config.auto_export_on")])
        idx = self.auto_export.findText(auto_current)
        self.auto_export.setCurrentIndex(max(0, idx))

        # Web 服务弢关：保存当前选择，更新项文本，恢复择
        web_enabled_current = self.web_enabled.currentText()
        self.web_enabled.clear()
        self.web_enabled.addItems([tr("config.web_off"), tr("config.web_on")])
        idx = self.web_enabled.findText(web_enabled_current)
        self.web_enabled.setCurrentIndex(max(0, idx))

        # HTTPS ???????????????? i18n ???
        pass

        # Web 服务访问地址标题和刷新按
        self._web_urls_title.setText("\U0001f310 " + tr("config.web_urls_title"))
        self.btn_refresh_urls.setText(tr("config.btn_refresh_urls"))
        self._refresh_web_urls()

        # 测试连接按钮
        self.btn_test.setText(tr("config.btn_test"))

        # 状卡片标
        self.card_overview.set_title(tr("config.card_overview"))
        self.card_mysql.set_title(tr("config.card_mysql"))
        stat_card = self._find_stat_card()
        if stat_card:
            stat_card.set_title(tr("config.card_stats"))
        self.card_sync.set_title(tr("config.card_sync"))
        self.card_actions.set_title(tr("config.card_actions"))

        # 状卡片行标签
        self.card_overview.set_row("version", tr("config.label_version"), APP_VERSION)
        self.card_overview.set_row("mode", tr("config.label_mode"), self.card_overview.get_row_value("mode") or "")
        self.card_overview.set_row("db_file", tr("config.label_db_file"), self.card_overview.get_row_value("db_file") or "...")
        self.card_overview.set_row("total", tr("config.label_total"), self.card_overview.get_row_value("total") or "0")

        self.card_mysql.set_row("host", tr("config.label_host"), self.card_mysql.get_row_value("host") or "")
        self.card_mysql.set_row("port", tr("config.label_port"), self.card_mysql.get_row_value("port") or "")
        self.card_mysql.set_row("db", tr("config.label_db"), self.card_mysql.get_row_value("db") or "")

        # 迷你统计卡片标签
        stat_labels = {
            "materials": "config.stat_materials",
            "borrow": "config.stat_borrow",
            "assets": "config.stat_assets",
            "configs": "config.stat_configs",
        }
        for key, mini in self._mini_stats.items():
            mini.set_label(tr(stat_labels.get(key, key)))

        # 快捷操作按钮
        self.btn_export.setText(tr("config.btn_export"))
        self.btn_import.setText(tr("config.btn_import"))
        self.btn_clear_queue.setText(tr("config.btn_clear_queue"))

        # 车间切换器翻译
        if hasattr(self, "lbl_workshop"):
            self.lbl_workshop.setText(tr("workshop.select"))
        if hasattr(self, "btn_workshop_manage"):
            self.btn_workshop_manage.setText(tr("workshop.manage"))

        # 刷新状面板（确保标签翻译后立即更新）
        if self._local_db is not None:
            self._update_status_panel()

    def _find_stat_card(self):
        """查找右侧的统计数据卡片（StatusCard 实例"""
        for child in self.findChildren(StatusCard):
            if child is not self.card_overview and child is not self.card_mysql and child is not self.card_sync and child is not self.card_actions:
                return child
        return None

    # ==================== 生命周期 ====================

    def _cleanup_mysql_test_thread(self):
        """清理 MySQL 测试线程（安全停止并释放资源"""
        if self._mysql_test_thread is not None:
            try:
                if self._mysql_test_thread.isRunning():
                    self._mysql_test_thread.quit()
                    if not self._mysql_test_thread.wait(3000):
                        self._mysql_test_thread.terminate()
                        self._mysql_test_thread.wait(1000)
            except RuntimeError:
                # C++ 对象已被锢毁，安全忽略
                pass
            self._mysql_test_thread = None

    def _cleanup_port_check_thread(self):
        """清理端口棢测线程（安全停止并释放资源）"""
        if self._port_check_thread is not None:
            try:
                if self._port_check_thread.isRunning():
                    self._port_check_thread.quit()
                    if not self._port_check_thread.wait(1000):
                        self._port_check_thread.terminate()
                        self._port_check_thread.wait(500)
            except RuntimeError:
                # C++ 对象已被锢毁，安全忽略
                pass
            self._port_check_thread = None

    def eventFilter(self, obj, event):
        """双击 URL 标签即可复制到剪贴板"""
        if event.type() == QEvent.MouseButtonDblClick and obj in self._url_map:
            url = self._url_map[obj]
            if url:
                QGuiApplication.clipboard().setText(url)
                toast_success(self, tr("config.url_copied"))
            return True
        return super().eventFilter(obj, event)

    def clear_memory(self):
        """清理资源"""
        self._stop_status_timer()
        self._cleanup_mysql_test_thread()
        self._cleanup_port_check_thread()
        self._cleanup_web_process()

    # ==================== 车间管理 ====================

    def _init_workshop_selector(self):
        """初始化车间切换选择器（下拉框 + 管理按钮）"""
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet("background-color: #e5e7eb; max-height: 1px;")
        self.card_actions.body().addWidget(sep)

        ws_layout = QHBoxLayout()
        ws_layout.setSpacing(6)

        self.lbl_workshop = QLabel(tr("workshop.select"))
        self.lbl_workshop.setFont(QFont("Microsoft YaHei", 9))
        self.lbl_workshop.setStyleSheet("color: #6b7280; background: transparent; border: none;")
        ws_layout.addWidget(self.lbl_workshop)

        self.cbx_workshop = QComboBox()
        self.cbx_workshop.setMinimumHeight(28)
        self.cbx_workshop.setStyleSheet("""
            QComboBox {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 2px 6px;
                background-color: #ffffff;
            }
            QComboBox::drop-down { border: none; }
        """)
        self.cbx_workshop.currentIndexChanged.connect(self._on_workshop_changed)
        ws_layout.addWidget(self.cbx_workshop, stretch=1)

        self.btn_workshop_manage = QPushButton(tr("workshop.manage"))
        self.btn_workshop_manage.setStyleSheet(BTN_SECONDARY.replace("padding: 8px 16px", "padding: 4px 8px"))
        self.btn_workshop_manage.clicked.connect(self._show_workshop_manager)
        ws_layout.addWidget(self.btn_workshop_manage)

        self.card_actions.body().addLayout(ws_layout)
        self._load_workshops()

    def _load_workshops(self):
        """从 config.ini 读取车间列表并填充下拉框"""
        try:
            from utils.app_config import load_workshop_config
            cfg = load_workshop_config()
            workshops_str = cfg.get("workshops", "")
            current = cfg.get("current_workshop", "")
            workshops = [w.strip() for w in workshops_str.split(",") if w.strip()] if workshops_str else []
            if not workshops:
                from config import DEFAULT_WORKSHOP
                workshops = [DEFAULT_WORKSHOP]
                current = current or DEFAULT_WORKSHOP
            self.cbx_workshop.blockSignals(True)
            self.cbx_workshop.clear()
            for w in workshops:
                self.cbx_workshop.addItem(w)
            idx = self.cbx_workshop.findText(current)
            if idx < 0:
                idx = 0
            self.cbx_workshop.setCurrentIndex(idx)
            self.cbx_workshop.blockSignals(False)
        except Exception as e:
            _log.warning("加载车间列表失败: %s", e)

    def _on_workshop_changed(self, index: int):
        """车间切换：保存选择，提示重启"""
        new_workshop = self.cbx_workshop.currentText()
        try:
            from utils.app_config import save_workshop_config
            save_workshop_config({"current_workshop": new_workshop})
            _log.info("车间已切换为: %s", new_workshop)
        except Exception as e:
            _log.warning("保存车间选择失败: %s", e)

        if show_confirm(self, tr("workshop.restart_title"), tr("workshop.restart_prompt"), "info"):
            self._restart_app()

    def _restart_app(self):
        """重启应用程序"""
        try:
            from main import restart_self
            restart_self()
        except Exception as e:
            toast_error(self, "重启失败: %s" % e)

    def _show_workshop_manager(self):
        """打开车间管理对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("workshop.manage"))
        dlg.setMinimumSize(420, 480)
        dlg.setModal(True)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title_lbl = QLabel("🏭 车间管理    Gestionar talleres")
        title_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #1d4ed8; background: transparent; border: none;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        self._ws_list = QListWidget()
        self._ws_list.setFont(QFont("Microsoft YaHei", 11))
        self._ws_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                background-color: #ffffff;
                padding: 4px;
            }
            QListWidget::item { padding: 6px 8px; }
            QListWidget::item:selected { background-color: #dbeafe; color: #1d4ed8; }
        """)
        layout.addWidget(self._ws_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_add = QPushButton(tr("workshop.add"))
        btn_add.setStyleSheet(BTN_PRIMARY.replace("padding: 8px 16px", "padding: 6px 12px"))
        btn_add.clicked.connect(lambda: self._ws_add_dialog(dlg))
        btn_row.addWidget(btn_add)

        btn_rename = QPushButton(tr("workshop.rename"))
        btn_rename.setStyleSheet(BTN_SECONDARY.replace("padding: 8px 16px", "padding: 6px 12px"))
        btn_rename.clicked.connect(lambda: self._ws_rename_dialog(dlg))
        btn_row.addWidget(btn_rename)

        btn_delete = QPushButton(tr("workshop.delete"))
        btn_delete.setStyleSheet(BTN_DANGER.replace("padding: 8px 16px", "padding: 6px 12px"))
        btn_delete.clicked.connect(lambda: self._ws_delete_dialog(dlg))
        btn_row.addWidget(btn_delete)

        btn_row.addStretch()
        btn_close = QPushButton(tr("dialog.confirm"))
        btn_close.setStyleSheet(BTN_PRIMARY.replace("padding: 8px 16px", "padding: 6px 16px"))
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._ws_load_list()
        dlg.exec()

        # 关闭后刷新下拉框
        self._load_workshops()

    def _ws_load_list(self):
        try:
            from utils.app_config import load_workshop_config
            cfg = load_workshop_config()
            workshops_str = cfg.get("workshops", "")
            workshops = [w.strip() for w in workshops_str.split(",") if w.strip()] if workshops_str else []
            self._ws_list.clear()
            for w in workshops:
                item = QListWidgetItem(w)
                if w == cfg.get("current_workshop", ""):
                    item.setBackground(QColor("#dbeafe"))
                self._ws_list.addItem(item)
        except Exception as e:
            _log.warning("加载车间列表（对话框）失败: %s", e)

    def _ws_add_dialog(self, parent_dialog):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(parent_dialog, tr("workshop.add"), tr("workshop.name_placeholder"))
        if not ok or not name.strip():
            return
        name = name.strip()
        if len(name) > 20:
            toast_error(parent_dialog, tr("workshop.name_too_long"))
            return
        from utils.app_config import load_workshop_config, save_workshop_config
        cfg = load_workshop_config()
        workshops = [w.strip() for w in cfg.get("workshops", "").split(",") if w.strip()]
        if name in workshops:
            toast_error(parent_dialog, tr("workshop.duplicate"))
            return
        workshops.append(name)
        current = cfg.get("current_workshop", "") or name
        save_workshop_config({"workshops": ",".join(workshops), "current_workshop": current})
        toast_success(parent_dialog, tr("workshop.added", name=name))
        self._ws_load_list()

    def _ws_rename_dialog(self, parent_dialog):
        curr = self._ws_list.currentRow()
        if curr < 0:
            toast_error(parent_dialog, "请先选中要重命名的车间")
            return
        old_name = self._ws_list.item(curr).text()
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(parent_dialog, tr("workshop.rename"), tr("workshop.name_placeholder"))
        if not ok or not name.strip():
            return
        name = name.strip()
        if len(name) > 20:
            toast_error(parent_dialog, tr("workshop.name_too_long"))
            return
        from utils.app_config import load_workshop_config, save_workshop_config
        cfg = load_workshop_config()
        workshops = [w.strip() for w in cfg.get("workshops", "").split(",") if w.strip()]
        if name in workshops:
            toast_error(parent_dialog, tr("workshop.duplicate"))
            return
        idx = workshops.index(old_name)
        workshops[idx] = name
        current = cfg.get("current_workshop", "")
        if current == old_name:
            current = name
        save_workshop_config({"workshops": ",".join(workshops), "current_workshop": current})
        toast_success(parent_dialog, tr("workshop.renamed"))
        self._ws_load_list()

    def _ws_delete_dialog(self, parent_dialog):
        curr = self._ws_list.currentRow()
        if curr < 0:
            toast_error(parent_dialog, "请先选中要删除的车间")
            return
        name = self._ws_list.item(curr).text()
        from utils.app_config import load_workshop_config
        cfg = load_workshop_config()
        if name == cfg.get("current_workshop", ""):
            toast_error(parent_dialog, tr("workshop.cannot_delete_current"))
            return
        workshops = [w.strip() for w in cfg.get("workshops", "").split(",") if w.strip()]
        if len(workshops) <= 1:
            toast_error(parent_dialog, tr("workshop.cannot_delete_last"))
            return
        if show_confirm(parent_dialog, "确认删除", tr("workshop.delete_confirm", name=name), "error"):
            self._ws_do_delete(name, parent_dialog)

    def _ws_do_delete(self, name: str, parent_dialog):
        from utils.app_config import load_workshop_config, save_workshop_config
        cfg = load_workshop_config()
        workshops = [w.strip() for w in cfg.get("workshops", "").split(",") if w.strip()]
        workshops = [w for w in workshops if w != name]
        current = cfg.get("current_workshop", "")
        if current == name:
            current = workshops[0] if workshops else ""
        save_workshop_config({"workshops": ",".join(workshops), "current_workshop": current})
        toast_success(parent_dialog, tr("workshop.deleted", name=name))
        self._ws_load_list()


class _FtpTestThread(QThread):
    test_finished = Signal(bool, str)

    def __init__(self, host, port, user, password, directory="", parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.directory = directory

    def run(self):
        try:
            from utils.updater import _connect_ftp, _close_ftp
            ftp, _, status = _connect_ftp({
                "host": self.host, "port": self.port,
                "user": self.user, "pass": self.password,
                "directory": self.directory,
            })
            if ftp is not None:
                _close_ftp(ftp)
                self.test_finished.emit(True, "")
            elif status == "NO_FILES":
                self.test_finished.emit(True, "")
            else:
                self.test_finished.emit(False, "连接失败")
        except Exception as e:
            self.test_finished.emit(False, str(e))
