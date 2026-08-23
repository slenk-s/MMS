import sys
import os
import socket
import json
import logging
import sqlite3
import glob
import shutil
import configparser
from datetime import datetime, timedelta
import uuid
import random
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QStatusBar, QMessageBox, QLabel, QPushButton,
    QInputDialog, QLineEdit, QDialog, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QTimer, QThread
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QIcon, QFont, QColor

from utils.theme import apply_theme
from utils.helpers import get_current_timestamp, generate_uuid
from config import (
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    MYSQL_HOST, MYSQL_PORT, LOCAL_DB_PATH, APP_VERSION,
    LOGIN_COMPLETED_FILE, REMEMBER_LOGIN_FILE, AUTO_EXPORT_MARKER_FILE,
    SYNC_COOLDOWN_SECONDS, DEFAULT_WORKSHOP, get_local_db_path,
    TABLE_MATERIALS, TABLE_BORROW_RECORDS, TABLE_FIXED_ASSETS,
    TABLE_CONFIG_ITEMS, TABLE_USERS, TABLE_EMPLOYEE_RECORDS,
)
from logger import get_logger
from utils.credential_manager import (
    get_password as _get_db_pw_tuple,
    _get_password_raw as _get_db_pw,
    set_password as _set_db_pw,
    has_password,
    has_user_seed,
    set_user_seed,
    get_user_seed,
)
from i18n import get_manager, tr, set_language

_log = get_logger(__name__)

from mysql_client import MySQLClient
from local_db import LocalDB
from sync_engine import SyncEngine
from network_monitor import NetworkMonitor

from widgets.navigation import NavigationBar
from widgets.sync_status_bar import SyncStatusBar

from views.login_view import LoginView
from views.inventory_detail_view import InventoryDetailView
from views.register_view import RegisterView
from views.asset_view import AssetView
from views.config_view import ConfigView
from views.user_manage_view import UserManageView

# 记住登录状态的文件路径
REMEMBER_FILE = os.path.join(os.path.dirname(LOCAL_DB_PATH), REMEMBER_LOGIN_FILE)


def _cleanup_ini_plaintext_passwords():
    """删除 config.ini 中历史遗留的明文密码字段"""
    try:
        from utils.credential_manager import _get_ini_path
        ini_path = _get_ini_path()
        if not os.path.isfile(ini_path):
            return
        cp = configparser.ConfigParser()
        cp.read(ini_path, encoding="utf-8-sig")
        cleaned = False
        for sec, keys in [("mysql", ["mysql_password"]), ("update", ["ftp_pass", "ftp_password"])]:
            if cp.has_section(sec):
                for key in keys:
                    if cp.has_option(sec, key):
                        cp.remove_option(sec, key)
                        cleaned = True
        if cleaned:
            with open(ini_path, "w", encoding="utf-8", newline="") as f:
                cp.write(f)
    except Exception as e:
        _log.warning("清理 config.ini 明文密码字段失败: %s", e)


def _migrate_local_db_to_workshop():
    """首次启动时，将旧版 local_cache.db 迁移为 local_cache_{车间}.db"""
    from utils.app_config import load_workshop_config, save_workshop_config
    try:
        ws_cfg = load_workshop_config()
        if ws_cfg.get("current_workshop"):
            return
        old_path = LOCAL_DB_PATH
        if not os.path.isfile(old_path):
            return
        new_path = get_local_db_path()
        if os.path.isfile(new_path):
            return
        import shutil
        shutil.copy2(old_path, new_path)
        _log.info("本地数据库已迁移: %s -> %s", old_path, new_path)
        save_workshop_config({
            "workshops": DEFAULT_WORKSHOP,
            "current_workshop": DEFAULT_WORKSHOP,
        })
    except Exception as e:
        _log.warning("本地数据库车间迁移失败: %s", e)

def restart_self():
    """Close resources and restart MMS-Main.exe (车间切换等场景)"""
    try:
        from utils.updater import restart_main as _rm
        _rm()
    except Exception:
        pass


class MainWindow(QMainWindow):
    @property
    def _sync_queue_enabled(self) -> bool:
        """离线模式下不加入同步队列"""
        return getattr(self, "_app_mode", "online") != "offline"

    def _show_first_time_admin_dialog(self, admin_pwd: str):
        """首次启动：弹窗显示默认管理员密码（双语，可复制，置顶模态）"""
        from PySide6.QtGui import QFont, QColor
        from PySide6.QtWidgets import QGraphicsDropShadowEffect, QApplication

        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        dlg.setAttribute(Qt.WA_TranslucentBackground)
        dlg.setModal(True)
        dlg.setMinimumWidth(420)

        container = QWidget(dlg)
        container.setStyleSheet("""
            QWidget {
                background-color: #f0fdf4;
                border: 1px solid #22c55e;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title_lbl = QLabel("🔑 管理员初始密码\nContraseña inicial del administrador")
        title_lbl.setFont(QFont("Microsoft YaHei", 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #15803d; background: transparent; border: none;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        msg = QLabel(
            "已创建默认管理员账号，请登录后立即修改密码。\n"
            "Se ha creado la cuenta de administrador. "
            "Cambie la contraseña después de iniciar sesión."
        )
        msg.setWordWrap(True)
        msg.setFont(QFont("Microsoft YaHei", 11))
        msg.setStyleSheet("color: #166534; background: transparent; border: none; line-height: 1.6;")
        msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg)

        user_lbl = QLabel("用户名:  admin        Usuario:  admin")
        user_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        user_lbl.setStyleSheet("color: #14532d; background: transparent; border: none;")
        user_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(user_lbl)

        pwd_input = QLineEdit(admin_pwd)
        pwd_input.setReadOnly(True)
        pwd_input.selectAll()
        pwd_input.setAlignment(Qt.AlignCenter)
        pwd_input.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        pwd_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #22c55e;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 16px;
                background-color: #ffffff;
                color: #15803d;
                min-height: 20px;
            }
            QLineEdit:focus {
                border-color: #16a34a;
            }
        """)
        pwd_input.setMinimumHeight(44)
        layout.addWidget(pwd_input)

        QApplication.clipboard().setText(admin_pwd)

        copy_hint = QLabel("✅ 已自动复制到剪贴板    ✅ Copiado al portapapeles")
        copy_hint.setAlignment(Qt.AlignCenter)
        copy_hint.setFont(QFont("Microsoft YaHei", 11))
        copy_hint.setStyleSheet("color: #16a34a; background: transparent; border: none;")
        layout.addWidget(copy_hint)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn = QPushButton("确认    Confirmar")
        btn.setStyleSheet("""
            QPushButton {
                background-color: #22c55e;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 40px;
                min-width: 120px;
                min-height: 36px;
                font-size: 14px;
                font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #16a34a;
            }
            QPushButton:pressed {
                background-color: #15803d;
            }
        """)
        btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        shadow = QGraphicsDropShadowEffect(dlg)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 6)
        container.setGraphicsEffect(shadow)

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(container)
        try:
            dlg.exec()
        finally:
            dlg.deleteLater()

    def _prompt_set_user_seed(self):
        """首次启动或种子丢失时弹窗要求设置用户种子"""
        from PySide6.QtGui import QFont, QColor
        from PySide6.QtWidgets import QGraphicsDropShadowEffect

        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        dlg.setAttribute(Qt.WA_TranslucentBackground)
        dlg.setModal(True)
        dlg.setMinimumWidth(440)

        container = QWidget(dlg)
        container.setStyleSheet("""
            QWidget {
                background-color: #f0f7ff;
                border: 1px solid #3b82f6;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title_lbl = QLabel("🔐 设置安全种子\nConfigurar semilla de seguridad")
        title_lbl.setFont(QFont("Microsoft YaHei", 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #1d4ed8; background: transparent; border: none;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        msg = QLabel(
            "为确保您的数据安全可靠，请设置一个安全种子。\n"
            "安全种子将存储于 Windows 凭据管理器中。\n\n"
            "Para garantizar la seguridad de sus datos, configure una semilla.\n"
            "Se almacenará en el Administrador de credenciales de Windows."
        )
        msg.setWordWrap(True)
        msg.setFont(QFont("Microsoft YaHei", 11))
        msg.setStyleSheet("color: #1e40af; background: transparent; border: none; line-height: 1.6;")
        msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg)

        seed_input = QLineEdit()
        seed_input.setPlaceholderText("请输入安全种子（至少 6 位字符）    Ingrese semilla (mín. 6 caracteres)")
        seed_input.setFont(QFont("Consolas", 14))
        seed_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #3b82f6;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
                background-color: #ffffff;
                color: #1d4ed8;
                min-height: 20px;
            }
            QLineEdit:focus {
                border-color: #2563eb;
            }
        """)
        seed_input.setMinimumHeight(44)
        layout.addWidget(seed_input)

        error_lbl = QLabel("")
        error_lbl.setAlignment(Qt.AlignCenter)
        error_lbl.setFont(QFont("Microsoft YaHei", 10))
        error_lbl.setStyleSheet("color: #dc2626; background: transparent; border: none;")
        layout.addWidget(error_lbl)

        from utils.credential_manager import rekey_config_passwords

        def on_confirm():
            seed = seed_input.text().strip()
            if len(seed) < 6:
                error_lbl.setText("安全种子长度不足，请至少输入 6 个字符    Mín. 6 caracteres")
                return
            if not set_user_seed(seed):
                error_lbl.setText("写入安全种子失败    Error al guardar la semilla")
                return
            try:
                rekey_config_passwords(seed)
            except Exception as e:
                _log.warning("密码重加密失败: %s", e)
            error_lbl.setStyleSheet("color: #16a34a; background: transparent; border: none;")
            error_lbl.setText("✅ 安全种子已设置    ✅ Semilla configurada")
            import time
            time.sleep(0.5)
            dlg.accept()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn = QPushButton("确认设置    Confirmar")
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 40px;
                min-width: 140px;
                min-height: 36px;
                font-size: 14px;
                font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
        """)
        btn.clicked.connect(on_confirm)
        btn_layout.addWidget(btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        shadow = QGraphicsDropShadowEffect(dlg)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 6)
        container.setGraphicsEffect(shadow)

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(container)
        try:
            dlg.exec()
        finally:
            dlg.deleteLater()


    def __init__(self):
        super().__init__()

        # 语言管理器初始化（必须在 tr() 调用之前，确保使用已保存的语言偏好）
        self._lang_manager = get_manager()
        self._lang_manager.language_changed.connect(self._on_language_changed)

        self.setWindowTitle(tr("common.app_title"))
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        # 恢复窗口几何
        from utils.ui_settings import restore_window_geometry
        geo, state = restore_window_geometry()
        if geo:
            self.restoreGeometry(geo)
            if state:
                self.restoreState(state)

        self._operator = os.getenv("USERNAME", socket.gethostname())
        self._current_page = "inventory"

        # 当前登录用户信息
        self._current_user: Optional[dict] = None

        # 运行模式：online / semi_offline / offline
        # 如果 MySQL 密码未配置，强制进入离线模式
        # 用户种子检查：种子存在后才用新密钥解密密码
        if not has_user_seed():
            self._prompt_set_user_seed()

        mysql_password = _get_db_pw()
        # 若 config.ini 无密码，尝试从旧存储（keyring/fallback/.env）迁移
        if not mysql_password:
            try:
                from utils.credential_manager import migrate_from_old_stores
                migrated = migrate_from_old_stores()
                if migrated:
                    mysql_password = _get_db_pw()
                    _log.info("MySQL 密码已从旧存储迁移到 config.ini（加密）")
            except Exception as e:
                _log.warning("迁移旧密码失败: %s", e)
        # 清理 config.ini 中历史遗留的明文密码字段
        _cleanup_ini_plaintext_passwords()

        if not mysql_password:
            self._app_mode = "offline"
            _log.warning("MySQL 密码未配置，自动启用离线模式")
        else:
            self._app_mode = os.getenv("APP_MODE", "online")

        self.mysql_client = MySQLClient()

        _migrate_local_db_to_workshop()
        from utils.app_config import load_workshop_config
        _ws_cfg = load_workshop_config()
        self._current_workshop = _ws_cfg.get("current_workshop", "") or DEFAULT_WORKSHOP
        _db_path = get_local_db_path(self._current_workshop)
        self.mysql_client.set_workshop(self._current_workshop)
        self.local_db = LocalDB(db_path=_db_path, workshop=self._current_workshop)
        self._library_name = os.path.splitext(os.path.basename(_db_path))[0]
        # 先仅记录是否需要弹窗，真正展示推迟到 _init_ui() 之后
        self._pending_admin_pwd: Optional[str] = self.local_db.create_default_admin()
        self.sync_engine = SyncEngine(self.mysql_client, self.local_db, workshop=self._current_workshop)
        # 网络检测目标改为 MySQL 主机：直接反映应用依赖的数据库服务可达性
        # 注意：MySQL 端口通但密码错误时仍会判为在线，由 SyncEngine 单独处理认证失败
        self.network_monitor = NetworkMonitor(
            check_host=MYSQL_HOST, check_port=MYSQL_PORT
        )

        # 同步冷却：网络恢复后 10 秒内不重复触发同步，避免频繁同步
        self._last_online_sync_time: Optional[datetime] = None
        self._SYNC_COOLDOWN_SECONDS = SYNC_COOLDOWN_SECONDS

        # 刷新同步标志：标记刷新请求，同步完成后自动刷新页面
        self._refresh_pending: bool = False

        # 延迟刷新定时器：合并短时间内多次刷新请求
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh)

        self._init_ui()
        self._connect_signals()
        # 注入认证回调，避免明文密码通过 Qt 信号传递
        self.login_view.set_auth_callback(self._on_login_callback)
        # MainWindow 已完全构建后，再展示首次管理员密码弹窗
        # 避免模态事件循环访问未初始化的控件
        if self._pending_admin_pwd:
            self._show_first_time_admin_dialog(self._pending_admin_pwd)
            self._pending_admin_pwd = None
        self.network_monitor.start()

        # 尝试自动登录
        if not self._try_auto_login():
            self._show_login_overlay()
        else:
            self._enter_main_ui()

    def _init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.nav_bar = NavigationBar()
        self.main_layout.addWidget(self.nav_bar)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        self.sync_status_bar = SyncStatusBar()
        self.content_layout.addWidget(self.sync_status_bar)

        self.stacked_widget = QStackedWidget()
        self.content_layout.addWidget(self.stacked_widget)

        self.main_layout.addWidget(self.content_area)

        self.inventory_view = InventoryDetailView()
        self.register_view = RegisterView()
        self.asset_view = AssetView()
        self.config_view = ConfigView()
        self.config_view.set_local_db(self.local_db) 
        self.user_manage_view = UserManageView()

        self.stacked_widget.addWidget(self.inventory_view)
        self.stacked_widget.addWidget(self.register_view)
        self.stacked_widget.addWidget(self.asset_view)
        self.stacked_widget.addWidget(self.config_view)
        self.stacked_widget.addWidget(self.user_manage_view)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(tr("common.ready"))

        # 右侧：版本号
        self.version_label = QLabel(APP_VERSION)
        self.version_label.setStyleSheet("color: #94a3b8; font-size: 11px; padding: 0 8px;")
        self.status_bar.addPermanentWidget(self.version_label)

        # 登录覆盖层
        self.login_view = LoginView(self.central_widget)
        self.login_view.setGeometry(self.central_widget.rect())
        self.login_view.hide()

    def resizeEvent(self, event):
        """窗口大小变化时调整登录覆盖层为全屏覆盖"""
        super().resizeEvent(event)
        if hasattr(self, "login_view") and self.login_view.isVisible():
            # 覆盖整个窗口（含状态栏）
            self.login_view.setGeometry(0, 0, self.width(), self.height())

    def _connect_signals(self):
        # 导航
        self.nav_bar.page_changed.connect(self._on_page_changed)
        self.nav_bar.logout_clicked.connect(self._on_logout)

        # 同步
        self.sync_engine.sync_status_changed.connect(self.sync_status_bar.set_sync_status)
        self.sync_engine.queue_updated.connect(self.sync_status_bar.set_queue_count)
        self.sync_engine.batch_conflict_detected.connect(self._on_conflict_notify)
        # sync_started 传的是同步类型(push/pull/full_sync)，不是状态值，统一映射为 syncing
        self.sync_engine.sync_started.connect(lambda _: self.sync_status_bar.set_sync_status("syncing"))
        self.sync_engine.sync_completed.connect(self._on_sync_completed)
        self.sync_status_bar.force_sync_clicked.connect(self.sync_engine.force_sync)
        self.sync_status_bar.language_switch_clicked.connect(self._on_switch_language)
        self.network_monitor.status_changed.connect(self._on_network_changed)

        # 登录
        self.login_view.login_success.connect(self._on_login_result)

        # 库存
        self.inventory_view.add_material.connect(self._on_add_material)
        self.inventory_view.update_material.connect(self._on_update_material)
        self.inventory_view.delete_material.connect(self._on_delete_material)
        self.inventory_view.import_materials.connect(self._on_import_materials)
        self.inventory_view.refresh_requested.connect(self._request_refresh)

        # 登记
        self.register_view.borrow_submitted.connect(self._on_borrow_submit)
        self.register_view.return_submitted.connect(self._on_return_submit)
        self.register_view.damage_status_update.connect(self._on_damage_status_update)
        self.register_view.refresh_requested.connect(self._request_refresh)

        # 资产
        self.asset_view.add_asset.connect(self._on_add_asset)
        self.asset_view.update_asset.connect(self._on_update_asset)
        self.asset_view.delete_asset.connect(self._on_delete_asset)
        self.asset_view.refresh_requested.connect(self._request_refresh)

        # 配置
        self.config_view.config_saved.connect(self._on_config_saved)

        # 用户管理
        self.user_manage_view.add_user.connect(self._on_add_user)
        self.user_manage_view.update_user.connect(self._on_update_user)
        self.user_manage_view.delete_user.connect(self._on_delete_user)
        self.user_manage_view.toggle_user_status.connect(self._on_toggle_user_status)
        self.user_manage_view.refresh_requested.connect(self._request_refresh)

        # 员工档案
        self.user_manage_view.employee_add_requested.connect(self._on_employee_add_requested)
        self.user_manage_view.employee_edit_requested.connect(self._on_employee_edit_requested)
        self.user_manage_view.employee_delete_requested.connect(self._on_employee_delete_requested)
        self.user_manage_view.employee_data_requested.connect(self._on_employee_data_requested)

    # ---------- 登录相关 ----------

    def _show_login_overlay(self):
        """显示登录覆盖层 — 全屏覆盖主窗口"""
        self.nav_bar.setVisible(False)
        self.sync_status_bar.setVisible(False)
        self.stacked_widget.setVisible(False)
        # 覆盖整个窗口区域（含状态栏）
        self.login_view.setGeometry(0, 0, self.width(), self.height())
        self.login_view.show_login()

    def _try_auto_login(self) -> bool:
        """尝试自动登录（记住状态30天）"""
        if not os.path.exists(REMEMBER_FILE):
            return False
        try:
            with open(REMEMBER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            expire_time = datetime.fromisoformat(data.get("expire", ""))
            if datetime.now() > expire_time:
                os.remove(REMEMBER_FILE)
                return False

            username = data.get("username", "")
            user = self.local_db.get_user_by_username(username)
            if user and user.get("is_active"):
                self._current_user = user
                return True
        except (OSError, IOError, json.JSONDecodeError, ValueError, KeyError) as e:
            _log.warning("自动登录失败: %s", e)
        except Exception as e:
            _log.warning("自动登录未预期异常: %s", e)
        return False

    def _save_remember_login(self, username: str):
        """保存记住登录状态（30天）"""
        try:
            expire = (datetime.now() + timedelta(days=30)).isoformat()
            with open(REMEMBER_FILE, "w", encoding="utf-8") as f:
                json.dump({"username": username, "expire": expire}, f)
        except (OSError, IOError, UnicodeEncodeError) as e:
            _log.warning("保存记住登录状态失败: %s", e)
        except Exception as e:
            _log.warning("保存记住登录状态未预期异常: %s", e)

    def _clear_remember_login(self):
        """清除记住登录状态"""
        if os.path.exists(REMEMBER_FILE):
            try:
                os.remove(REMEMBER_FILE)
            except (OSError, PermissionError) as e:
                _log.warning("清除记住登录状态失败: %s", e)
            except Exception as e:
                _log.warning("清除记住登录状态未预期异常: %s", e)

    def _on_login_callback(self, username: str, password: str, is_register: bool = False) -> Optional[dict]:
        """认证回调 — 在 LoginView 调用栈中执行，密码不经过 Qt 信号
        返回 None 表示认证失败，返回 dict 表示成功（不含密码字段）
        """
        from widgets.toast import toast_success, toast_error

        if is_register:
            # 注册模式
            if not self._current_user or self._current_user.get("role") != "admin":
                toast_error(self.login_view, tr("toast.only_admin_can_register"))
                return None
            if self.local_db.user_exists(username):
                toast_error(self.login_view, tr("toast.user_exists", name=username))
                return None
            user_id = uuid.uuid4().hex
            now = datetime.now().isoformat()
            from utils.helpers import hash_password
            data = {
                "id": user_id,
                "username": username,
                "password": hash_password(password),
                "display_name": "",
                "role": "user",
                "is_active": 1,
                "created_at": now,
                "updated_at": now,
            }
            self.sync_engine.offline_insert(TABLE_USERS, user_id, data, add_to_queue=self._sync_queue_enabled)
            toast_success(self.login_view, tr("toast.user_registered", name=username))
            return {"success": True, "is_register": True}

        # 登录模式
        user = self.local_db.get_user_by_username(username)
        if not user:
            # SQLite ???????? MySQL ???????????
            return self._try_mysql_login_fallback(username, password, toast_error)

        if not user.get("is_active"):
            toast_error(self.login_view, tr("toast.account_disabled"))
            return None

        from utils.helpers import verify_password
        stored_pwd = user.get("password", "")
        matched, need_upgrade = verify_password(password, stored_pwd)
        if not matched:
            toast_error(self.login_view, tr("toast.password_wrong"))
            return None

        self._current_user = user

        # 旧版明文密码自动升级（首次哈希登录时触发）
        if need_upgrade:
            from utils.helpers import hash_password
            new_hash = hash_password(password)
            self._current_user["password"] = new_hash
            self.sync_engine.offline_update(TABLE_USERS, user.get("id", ""), {
                "password": new_hash,
                "updated_at": datetime.now().isoformat(),
            }, add_to_queue=self._sync_queue_enabled)

        # 首次登录检测：只要用户从未完成过登录，就强制修改密码
        _login_flag = os.path.join(os.path.dirname(LOCAL_DB_PATH), LOGIN_COMPLETED_FILE)
        if not os.path.exists(_login_flag):
            return {"success": True, "force_change_pwd": True}

        return {"success": True, "force_change_pwd": False}

    def _try_mysql_login_fallback(self, username: str, password: str, toast_error_fn) -> Optional[dict]:
        """SQLite ?????? MySQL ???????????"""
        from utils.helpers import hash_password, verify_password

        try:
            result = self.mysql_client.fetch_by_condition(TABLE_USERS, "username", username)
        except Exception as e:
            _log.warning("MySQL ??????: %s", e)
            toast_error_fn(self.login_view, tr("toast.user_not_found"))
            return None

        users = result if isinstance(result, list) else []
        if not users:
            toast_error_fn(self.login_view, tr("toast.user_not_found"))
            return None

        mysql_user = users[0]
        stored_hash = mysql_user.get("password", "") or ""
        user_id = mysql_user.get("id", username)
        role = mysql_user.get("role", "admin")

        # 场景1: MySQL 密码为空/占位，直接放行并强制改密码
        if not stored_hash.strip():
            _log.info("MySQL 用户 %s 密码为空/占位，直接放行，强制修改密码", username)
            now = datetime.now().isoformat()
            default_hash = hash_password("placeholder_password")
            self.sync_engine.offline_insert(TABLE_USERS, user_id, {
                "id": user_id,
                "username": username,
                "password": default_hash,
                "display_name": mysql_user.get("display_name", username),
                "role": role,
                "is_active": mysql_user.get("is_active", 1),
                "created_at": mysql_user.get("created_at", now),
                "updated_at": now,
            }, add_to_queue=False)
            self._current_user = {
                "id": user_id,
                "username": username,
                "password": default_hash,
                "display_name": mysql_user.get("display_name", username),
                "role": role,
                "is_active": 1,
            }
            return {"success": True, "force_change_pwd": True}

        # 场景3: MySQL 已有哈希密码，需要验证
        from utils.helpers import verify_password
        matched, need_upgrade = verify_password(password, stored_hash)
        if not matched:
            toast_error_fn(self.login_view, tr("toast.password_wrong"))
            return None

            _log.info("MySQL 用户 %s 密码验证通过，同步到本地", username)
        now = datetime.now().isoformat()
        self.sync_engine.offline_insert(TABLE_USERS, user_id, {
            "id": user_id,
            "username": username,
            "password": stored_hash,
            "display_name": mysql_user.get("display_name", username),
            "role": role,
            "is_active": mysql_user.get("is_active", 1),
            "created_at": mysql_user.get("created_at", now),
            "updated_at": now,
        }, add_to_queue=False)
        self._current_user = {
            "id": user_id,
            "username": username,
            "password": stored_hash,
            "display_name": mysql_user.get("display_name", username),
            "role": role,
            "is_active": 1,
        }

        _login_flag = os.path.join(os.path.dirname(LOCAL_DB_PATH), LOGIN_COMPLETED_FILE)
        if not os.path.exists(_login_flag):
            return {"success": True, "force_change_pwd": True}

        return {"success": True, "force_change_pwd": False}

    def _on_login_result(self, result: dict):
        """处理登录成功信号（不含密码的安全结果）"""
        from widgets.toast import toast_success

        # 防御：确保 result 为 dict，避免 Shiboken NoneType 转换
        if not isinstance(result, dict):
            _log.warning("login_success 收到非 dict 参数: %r", type(result))
            return

        if result.get("is_register"):
            self.login_view.show_login()
            return

        if result.get("force_change_pwd"):
            toast_success(self.login_view, tr("toast.first_login_change_pwd"))
            self._force_change_password()
            return

        # 处理记住登录
        if result.get("remember", False):
            username = self._current_user.get("username", "") if self._current_user else ""
            self._save_remember_login(username)
        else:
            self._clear_remember_login()

        # 淡出动画后进入主界面
        user = self._current_user or {}
        username = user.get("username", "")

        def _after_fade():
            # 确保登录完成标记已写入
            _login_flag = os.path.join(os.path.dirname(LOCAL_DB_PATH), LOGIN_COMPLETED_FILE)
            if not os.path.exists(_login_flag):
                try:
                    with open(_login_flag, "w", encoding="utf-8") as f:
                        json.dump({"completed": True}, f)
                except (OSError, IOError, UnicodeEncodeError) as e:
                    _log.warning("写入登录完成标记文件失败: %s", e)
                except Exception as e:
                    _log.warning("写入登录完成标记文件未预期异常: %s", e)
            self.login_view.hide()
            self._enter_main_ui()
            name = user.get('display_name', '') or username
            toast_success(self, tr("toast.welcome_back", name=name))

        self.login_view.fade_out(on_finished=_after_fade)

    def _force_change_password(self):
        """首次登录强制修改用户名和密码 - QDialog 弹框(用户名/新密码/确认密码)"""
        from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QPushButton, QVBoxLayout, QLabel, QHBoxLayout
        from PySide6.QtCore import Qt
        from utils.helpers import hash_password

        user = self._current_user or {}
        current_username = user.get("username", "")
        user_id = user.get("id", "")

        dialog = QDialog(self.login_view)
        dialog.setWindowTitle("首次登录 - 修改密码")
        dialog.setFixedSize(420, 260)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        form = QFormLayout()
        form.setSpacing(12)

        lbl_title = QLabel(tr("dialog.first_login_msg"))
        lbl_title.setStyleSheet("font-size:13px; color:#555; margin-bottom:8px;")

        edit_username = QLineEdit()
        edit_username.setText(current_username or "")
        edit_username.setPlaceholderText("可填写中文，如：管理员")
        edit_username.setMinimumHeight(32)

        edit_pwd = QLineEdit()
        edit_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        edit_pwd.setPlaceholderText("请输入新密码（必填）")
        edit_pwd.setMinimumHeight(32)

        edit_confirm = QLineEdit()
        edit_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        edit_confirm.setPlaceholderText("请再次输入新密码")
        edit_confirm.setMinimumHeight(32)

        # 标题与输入框之间的间隔通过 form.setSpacing(12) 控制
        form.addRow(QLabel("用户名:"), edit_username)
        form.addRow(QLabel("新密码:"), edit_pwd)
        form.addRow(QLabel("确认密码:"), edit_confirm)

        btn_ok = QPushButton("确定")
        btn_ok.setMinimumHeight(36)
        btn_ok.setStyleSheet(
            "QPushButton { background-color:#10B981; color:white; font-size:14px; font-weight:bold; "
            "border-radius:6px; padding:8px; }"
            "QPushButton:hover { background-color:#059669; }"
        )
        btn_cancel = QPushButton("取消")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(
            "QPushButton { background-color:#94A3B8; color:white; font-size:13px; "
            "border-radius:6px; padding:8px; }"
            "QPushButton:hover { background-color:#64748B; }"
        )

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)

        layout = QVBoxLayout(dialog)
        layout.addWidget(lbl_title)
        layout.addLayout(form)
        layout.addLayout(btn_row)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 16)

        from PySide6.QtWidgets import QMessageBox
        from widgets.toast import toast_success

        def on_ok():
            new_username = edit_username.text().strip()
            new_pass = edit_pwd.text()
            confirm = edit_confirm.text()
            if not new_username:
                QMessageBox.warning(dialog, "提示", "用户名不能为空")
                return
            if not new_pass:
                QMessageBox.warning(dialog, "提示", "密码为必填项，请输入新密码")
                return
            if new_pass != confirm:
                QMessageBox.warning(dialog, "提示", "两次输入的密码不一致")
                return

            hashed = hash_password(new_pass)
            now = datetime.now().isoformat()
            role = user.get("role", "admin")

            self.sync_engine.offline_update(TABLE_USERS, user_id, {
                "username": new_username,
                "password": hashed,
                "display_name": new_username,
                "role": role,
                "updated_at": now,
            }, add_to_queue=self._sync_queue_enabled)
            self._current_user["username"] = new_username
            self._current_user["password"] = hashed
            self._current_user["display_name"] = new_username

            # ?? MySQL
            try:
                from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
                self.mysql_client.upsert(TABLE_USERS, {
                    "id": user_id,
                    "username": new_username,
                    "password": hashed,
                    "display_name": new_username,
                    "role": role,
                    "is_active": 1,
                    "created_at": now,
                    "updated_at": now,
                })
                _log.info("FIRST_LOGIN_USER_%s_WROTE_TO_MYSQL", user_id)
            except Exception as mysql_e:
                _log.error("FIRST_LOGIN_MYSQL_WRITE_FAILED: %s", mysql_e)

            toast_success(dialog, "密码修改成功，即将进入系统")
            dialog.accept()

        def on_cancel():
            import sys
            sys.exit(0)

        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(on_cancel)

        if dialog.exec() != 1:
            return

        # 写登录完成标记
        _login_flag = os.path.join(os.path.dirname(LOCAL_DB_PATH), LOGIN_COMPLETED_FILE)
        try:
            with open(_login_flag, "w", encoding="utf-8") as f:
                json.dump({"completed": True}, f)
        except (OSError, IOError, UnicodeEncodeError) as e:
            _log.warning("????????????: %s", e)
        except Exception as e:
            _log.warning("????????????: %s", e)

        def _after_pwd_fade():
            self.login_view.hide()
            self._enter_main_ui()

        self.login_view.fade_out(on_finished=_after_pwd_fade)

    def _on_logout(self):
        """退出登录 — 隐藏主界面所有元素，全屏显示登录层"""
        self._current_user = None
        self._clear_remember_login()
        # 隐藏主界面所有元素
        self.nav_bar.setVisible(False)
        self.sync_status_bar.setVisible(False)
        self.stacked_widget.setVisible(False)
        self.nav_bar.clear_user_info()
        # 全屏覆盖显示登录层
        self.login_view.setGeometry(0, 0, self.width(), self.height())
        self.login_view.show_login()
        self.status_bar.showMessage(tr("status.logged_out"))

    # ---------- 主界面入口 ----------

    def _enter_main_ui(self):
        """进入主界面 — 根据用户角色配置可见权限

        权限矩阵：
        ┌─────────────┬──────────┬──────────┐
        │   功能模块   │  管理员  │ 普通用户 │
        ├─────────────┼──────────┼──────────┤
        │  库存明细    │    ✓    │    ✓    │
        │  物料登记    │    ✓    │    ✓    │
        │  固定资产    │    ✓    │    ✓    │
        │  系统配置    │    ✓    │    ✗    │ ← 仅管理员可见
        │  用户管理    │    ✓    │    ✗    │ ← 仅管理员可见
        └─────────────┴──────────┴──────────┘
        """
        is_admin = bool(self._current_user and self._current_user.get("role") == "admin")
        username = self._current_user.get("username", "") if self._current_user else ""
        role = self._current_user.get("role", "user") if self._current_user else "user"

        # 显示主界面所有元素
        self.nav_bar.setVisible(True)
        self.sync_status_bar.setVisible(True)
        self.stacked_widget.setVisible(True)

        self.nav_bar.set_library_name(self._library_name)
        self.nav_bar.set_user_info(username, role)
        self.nav_bar.set_admin_visible(is_admin)

        self._apply_saved_configs()  # v21: 从数据库读取已保存的配置并应用到UI
        self._load_data_for_page("inventory")
        self._apply_app_mode()  # 根据运行模式启动/停止同步和网络监测
        self._on_page_changed("inventory")
        self._check_auto_export()  # v22: 三个月自动导出检测
        self._auto_backup_config_on_login()  # v23: 登录时自动备份配置
        self._check_sync_health_on_login()   # v23: 登录时检查同步状态

    # ---------- 加载数据（按需加载） ----------

    def _request_refresh(self):
        """请求刷新（延迟300ms执行，合并多次请求）"""
        self._refresh_timer.stop()
        self._refresh_timer.start(300)

    def _do_refresh(self):
        """执行刷新：先重新加载本地数据，再尝试云端拉取（如同步引擎已启动）"""
        self._refresh_pending = True
        self._load_data_for_page(self._current_page)
        # 尝试云端拉取，获取其他客户端的最新数据（仅在同步引擎运行时有效）
        if self.sync_engine._is_running:
            self.status_bar.showMessage(tr("status.pulling_cloud"))
            self.sync_engine.refresh_pull()

    def _on_sync_completed(self, sync_type: str, count: int):
        """同步完成回调

        - 主动刷新（_refresh_pending=True）：通知用户刷新成功
        - 周期同步拉取到新数据（count>0）：静默刷新当前页面，让其他电脑录入的数据自动可见
        """
        if self._refresh_pending:
            self._refresh_pending = False
            self._load_data_for_page(self._current_page)
            msg = tr("toast.records_pulled", count=count) if count > 0 else tr("toast.data_refreshed")
            from widgets.toast import toast_success
            toast_success(self, msg)
            self.status_bar.showMessage(msg)
        elif sync_type == "cycle" and count > 0:
            # 其他电脑录入的数据已拉取到本地，静默刷新当前页面
            self._load_data_for_page(self._current_page)
            self.status_bar.showMessage(tr("toast.records_pulled", count=count))

    def _load_data_for_page(self, page_id: str):
        """按需加载当前视图所需数据（v4.1 性能优化核心）"""
        if page_id == "inventory":
            materials = self.local_db.query(TABLE_MATERIALS, order_by="last_update DESC")
            self.inventory_view.set_data(materials)

        elif page_id == "register":
            materials = self.local_db.query(TABLE_MATERIALS)
            borrow_records = self.local_db.query(
                TABLE_BORROW_RECORDS,
                conditions="is_archived IS NULL OR is_archived = 0",
                order_by="created_at DESC"
            )
            self.register_view.set_materials(materials)
            self.register_view.set_records(borrow_records)

        elif page_id == "asset":
            fixed_assets = self.local_db.query(TABLE_FIXED_ASSETS, order_by="updated_at DESC")
            self.asset_view.set_data(fixed_assets)

        elif page_id == "config":
            config_items = self.local_db.query(TABLE_CONFIG_ITEMS, order_by="sort_order")
            self.config_view.set_data(config_items)

        elif page_id == "user_manage":
            users = self.local_db.get_all_users()
            self.user_manage_view.set_data(users)
            self.user_manage_view.set_current_user(self._current_user or {})
            employees = self.local_db.get_all_employees()
            self.user_manage_view.set_employee_data(employees)

        page_name = tr(f"nav.{page_id}")
        self.status_bar.showMessage(tr("status.data_refreshed", page=page_name))

    def _on_page_changed(self, page_id: str):
        """页面切换事件 — 带权限拦截"""
        # 权限拦截：非管理员禁止访问系统配置和用户管理
        admin_only_pages = {"config", "user_manage"}
        if page_id in admin_only_pages:
            is_admin = self._current_user and self._current_user.get("role") == "admin"
            if not is_admin:
                page_name = tr("nav.config") if page_id == "config" else tr("nav.user_manage")
                from widgets.toast import toast_error
                toast_error(self, tr("toast.no_permission", page=page_name))
                return

        self._current_page = page_id
        self.nav_bar.set_active_page(page_id)
        page_map = {
            "inventory": 0, "register": 1, "asset": 2,
            "config": 3, "user_manage": 4,
        }
        self.stacked_widget.setCurrentIndex(page_map.get(page_id, 0))
        self._load_data_for_page(page_id)

    def _apply_app_mode(self):
        """根据运行模式配置同步引擎和网络监测

        online       : 同步引擎自动运行 + 网络监测开启
        semi_offline : 同步引擎暂停定时同步 + 网络监测开启（可手动同步）
        offline      : 同步引擎完全停止 + 网络监测完全关闭
        """
        # 更新同步状态栏模式标签
        if hasattr(self, "sync_status_bar"):
            self.sync_status_bar.set_mode(self._app_mode)

        if self._app_mode == "online":
            self.network_monitor.start()
            self.sync_engine.resume_auto_sync()
            self.status_bar.showMessage(tr("status.online_mode"))
        elif self._app_mode == "semi_offline":
            self.network_monitor.start()
            self.sync_engine.pause_auto_sync()
            self.status_bar.showMessage(tr("status.semi_offline_mode"))
        elif self._app_mode == "offline":
            self.network_monitor.stop()
            self.sync_engine.stop()
            self.status_bar.showMessage(tr("status.offline_mode"))

    def _apply_saved_configs(self):
        """从 config_items 表读取已保存的配置，应用到 UI"""
        try:
            config_items = self.local_db.query(TABLE_CONFIG_ITEMS, order_by="sort_order")
        except sqlite3.OperationalError:
            return  # 首次启动时 config_items 表可能尚未创建
        except (sqlite3.Error, RuntimeError, ValueError) as e:
            _log.warning("加载已保存配置失败: %s", e)
            return
        except Exception as e:
            _log.warning("加载已保存配置未预期异常: %s", e)
            return
        config_map = {item["config_name"]: item["content"] for item in config_items}
        return config_map

    def _on_network_changed(self, is_online: bool):
        self.sync_status_bar.set_network_status(is_online)
        if is_online:
            self.status_bar.showMessage(tr("status.network_recovered"))
            # 半离线/离线模式下，网络恢复不自动触发同步
            if self._app_mode == "semi_offline":
                self.status_bar.showMessage(tr("status.network_recovered_semi"))
                return
            if self._app_mode == "offline":
                self.status_bar.showMessage(tr("status.network_recovered_offline"))
                return
            now = datetime.now()
            if (self._last_online_sync_time is None or
                    (now - self._last_online_sync_time).total_seconds() > self._SYNC_COOLDOWN_SECONDS):
                self._last_online_sync_time = now
                self.sync_engine.force_sync()
        else:
            self.status_bar.showMessage(tr("status.network_down"))

    def _on_conflict_notify(self, info: dict):
        """同步冲突通知：在状态栏显示提示"""
        tables = info.get("tables", [])
        if tables:
            tables_str = "、".join(tables)
            self.status_bar.showMessage(tr("status.conflict", table=tables_str), 5000)

    def _check_auto_export(self):
        """v22: 三个月自动导出领用记录并清除数据"""
        try:
            config_items = self.local_db.query(TABLE_CONFIG_ITEMS, order_by="sort_order")
            config_map = {item["config_name"]: item["content"] for item in config_items}
        except (sqlite3.Error, RuntimeError, ValueError) as e:
            _log.warning("读取自动导出配置失败: %s", e)
            return
        except Exception as e:
            _log.warning("读取自动导出配置未预期异常: %s", e)
            return

        auto_export = config_map.get("AUTO_EXPORT_ENABLED", "")
        if auto_export != "1":
            return

        # 检查上次自动导出时间
        export_marker = os.path.join(os.path.dirname(LOCAL_DB_PATH), AUTO_EXPORT_MARKER_FILE)
        now = datetime.now()
        last_export = None
        if os.path.exists(export_marker):
            try:
                with open(export_marker, "r", encoding="utf-8") as f:
                    data = json.load(f)
                last_export = datetime.fromisoformat(data.get("last_export", ""))
            except (OSError, IOError, json.JSONDecodeError, ValueError) as e:
                _log.warning("读取自动导出标记文件失败: %s", e)
            except Exception as e:
                _log.warning("读取自动导出标记文件未预期异常: %s", e)

        if last_export and (now - last_export).days < 90:
            return

        # 执行自动导出
        records = self.local_db.query(TABLE_BORROW_RECORDS)
        if not records:
            return

        # 弹出确认对话框，询问用户是否继续
        reply = QMessageBox.question(
            self,
            tr("dialog.auto_export_title"),
            tr("dialog.auto_export_msg", count=len(records)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            _log.info("用户取消了自动导出，推迟 7 天再提示")
            # 写入标记文件，推迟 7 天
            defer_date = (now + timedelta(days=7)).isoformat()
            with open(export_marker, "w", encoding="utf-8") as f:
                json.dump({"last_export": defer_date}, f)
            return

        try:
            from utils.excel_exporter import ExcelExporter
            from widgets.toast import toast_success
            exporter = ExcelExporter()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            filepath = exporter.export_inventory_records(records, f"领用记录自动备份_{timestamp}.xlsx")
            _log.info("自动导出领用记录: %s", filepath)

            # 软删除：标记为已归档，保留审计轨迹
            now_iso = now.isoformat()
            for rec in records:
                self.local_db.update(TABLE_BORROW_RECORDS, rec["id"], {
                    "is_archived": 1,
                    "updated_at": now_iso,
                })
            self.local_db.add_sync_log("push", "auto_export_cleared", len(records), f"备份: {filepath}")
            self.status_bar.showMessage(tr("toast.auto_export_success", path=filepath))
            toast_success(self, tr("toast.auto_export_cleared", count=len(records)))

            # 写入标记文件
            with open(export_marker, "w", encoding="utf-8") as f:
                json.dump({"last_export": now.isoformat()}, f)
        except (OSError, IOError, sqlite3.Error, UnicodeEncodeError, ValueError) as e:
            _log.error("自动导出领用记录失败: %s", e)
        except Exception as e:
            _log.error("自动导出领用记录未预期异常: %s", e)

    # ---------- 登录后自动备份配置 ----------

    def _auto_backup_config_on_login(self):
        """每次登录自动备份当前配置到 JSON 文件，保留最近 10 份"""
        try:
            config_items = self.local_db.query(TABLE_CONFIG_ITEMS)
            if not config_items:
                _log.info("没有配置项可备份，跳过")
                return

            backup_dir = os.path.join(os.path.dirname(LOCAL_DB_PATH), "config_backups")
            os.makedirs(backup_dir, exist_ok=True)

            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            username = (self._current_user or {}).get("username", "unknown")
            backup_data = {
                "backup_time": now.isoformat(),
                "username": username,
                "app_version": APP_VERSION,
                "configs": config_items,
            }

            # 从上一次备份中继承 UI 状态（窗口几何、列宽）
            existing_files = sorted(glob.glob(os.path.join(backup_dir, "config_*.json")), reverse=True)
            if existing_files:
                try:
                    with open(existing_files[0], "r", encoding="utf-8") as ef:
                        prev = json.load(ef)
                    if "ui_settings" in prev:
                        backup_data["ui_settings"] = prev["ui_settings"]
                except (json.JSONDecodeError, OSError):
                    pass

            backup_path = os.path.join(backup_dir, f"config_{timestamp}.json")
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)

            _log.info("配置已自动备份: %s (用户: %s)", backup_path, username)

            # 清理旧备份：只保留最近 10 个
            existing = sorted(glob.glob(os.path.join(backup_dir, "config_*.json")), reverse=True)
            for old_file in existing[10:]:
                try:
                    os.remove(old_file)
                    _log.info("已清理旧配置备份: %s", old_file)
                except OSError as e:
                    _log.warning("清理旧备份失败: %s — %s", old_file, e)
        except (OSError, IOError, sqlite3.Error, UnicodeEncodeError, glob.error) as e:
            _log.warning("自动备份配置失败: %s", e)
        except Exception as e:
            _log.warning("自动备份配置未预期异常: %s", e)

    # ---------- 登录后检查同步状态 ----------

    def _check_sync_health_on_login(self):
        """登录后检查同步设置是否正常启用"""
        from widgets.toast import toast_success, toast_warning, toast_info

        mode = self._app_mode
        pwd_ok = has_password()
        sync_running = getattr(self.sync_engine, "_is_running", False)
        net_started = getattr(self.network_monitor, "_is_started", False)
        queue_count = self.local_db.get_sync_queue_count()

        if mode == "offline":
            toast_info(self, tr("toast.offline_mode_sync_disabled"), 3000)
            return

        if mode == "online":
            issues = []
            if not pwd_ok:
                issues.append(tr("toast.sync_issue_no_pwd"))
            if not sync_running:
                issues.append(tr("toast.sync_issue_engine_stopped"))
            if not net_started:
                issues.append(tr("toast.sync_issue_network_monitor"))

            if issues:
                msg = "⚠️ " + "；".join(issues)
                toast_warning(self, msg, 4000)
            else:
                extra = ""
                if queue_count > 0:
                    extra = tr("toast.sync_queue_pending", count=queue_count)
                toast_success(self, tr("toast.sync_healthy_online") + extra, 3000)

        elif mode == "semi_offline":
            issues = []
            if not pwd_ok:
                issues.append(tr("toast.sync_issue_no_pwd"))
            if not net_started:
                issues.append(tr("toast.sync_issue_network_monitor"))

            if issues:
                msg = "⚠️ " + "；".join(issues)
                toast_warning(self, msg, 4000)
            else:
                extra = ""
                if queue_count > 0:
                    extra = tr("toast.sync_queue_pending", count=queue_count)
                toast_info(self, tr("toast.sync_healthy_semi") + extra, 3000)

    # ---------- 库存操作 ----------

    def _on_add_material(self, data: dict):
        material_id = uuid.uuid4().hex
        now = datetime.now().isoformat()
        data["id"] = material_id
        data["created_at"] = now
        data["updated_at"] = now
        data["last_update"] = now
        self.sync_engine.offline_insert(TABLE_MATERIALS, material_id, data, add_to_queue=self._sync_queue_enabled)
        self._refresh_current_view()

    def _on_update_material(self, material_id: str, data: dict):
        now = datetime.now().isoformat()
        data["updated_at"] = now
        data["last_update"] = now
        self.sync_engine.offline_update(TABLE_MATERIALS, material_id, data, add_to_queue=self._sync_queue_enabled)
        self._refresh_current_view()

    def _on_delete_material(self, material_id: str):
        self.sync_engine.offline_delete(TABLE_MATERIALS, material_id, add_to_queue=self._sync_queue_enabled)
        self._refresh_current_view()

    def _on_import_materials(self, items: list):
        """批量导入物料（v4.2 优化：O(1) 查重）"""
        from widgets.toast import toast_success
        count = 0

        # 构建 O(1) 查重字典：material_code -> material
        all_materials = self.local_db.query(TABLE_MATERIALS)
        materials_by_code = {}
        for m in all_materials:
            code = m.get("material_code", "")
            if code:
                materials_by_code[code] = m

        for item in items:
            material_code = item.get("material_code", "")
            material_name = item.get("material_name", "")
            if not material_code or not material_name:
                continue

            existing = materials_by_code.get(material_code)

            if existing:
                # 累加数量
                old_qty = existing.get("stock_qty", 0)
                add_qty = item.get("stock_qty", 0)
                new_qty = old_qty + add_qty
                update_data = dict(existing)
                update_data["stock_qty"] = new_qty
                update_data["material_name"] = material_name
                update_data["location"] = item.get("location", update_data.get("location", ""))
                update_data["shelf_no"] = item.get("shelf_no", update_data.get("shelf_no", ""))
                update_data["updated_at"] = datetime.now().isoformat()
                update_data["last_update"] = datetime.now().isoformat()
                self.sync_engine.offline_update(TABLE_MATERIALS, str(existing["id"]), update_data, add_to_queue=self._sync_queue_enabled)
            else:
                # 新增物料
                material_id = uuid.uuid4().hex
                now = datetime.now().isoformat()
                item["id"] = material_id
                item["created_at"] = now
                item["updated_at"] = now
                item["last_update"] = now
                item["unit"] = item.get("unit", "PCS")
                item["reserved_qty"] = 0
                self.sync_engine.offline_insert(TABLE_MATERIALS, material_id, item, add_to_queue=self._sync_queue_enabled)
            count += 1

        toast_success(self, tr("toast.imported", count=count))
        self._refresh_current_view()

    # ---------- 领用/归还操作 ----------

    def _on_borrow_submit(self, data: dict):
        # 1. 先查库存，校验数量合法性
        material = self.local_db.query_one(TABLE_MATERIALS, data.get("material_id"))
        if material:
            try:
                qty = int(data.get("qty", 0) or 0)
            except (ValueError, TypeError):
                from widgets.toast import toast_error
                toast_error(self, tr("toast.invalid_qty"))
                return
            new_stock = int(material.get("stock_qty", 0)) - qty
            if new_stock < 0:
                from widgets.toast import toast_warning
                toast_warning(self, tr("toast.stock_exceed", diff=abs(new_stock)), 2000)

        # 2. 创建领用记录
        record_id = uuid.uuid4().hex
        data["id"] = record_id
        data["record_no"] = f"LY{datetime.now().strftime('%Y%m%d%H%M%S')}{record_id[:6]}"
        data["created_at"] = datetime.now().isoformat()
        data["updated_at"] = data["created_at"]
        data["operator"] = self._operator
        self.sync_engine.offline_insert(TABLE_BORROW_RECORDS, record_id, data, add_to_queue=self._sync_queue_enabled)

        # 3. 扣减库存（允许负值，提示已超出）
        if material:
            material_id = data.get("material_id")
            if material_id:
                self.sync_engine.offline_update(TABLE_MATERIALS, material_id, {
                    "stock_qty": new_stock,
                    "updated_at": datetime.now().isoformat(),
                }, add_to_queue=self._sync_queue_enabled)
        self._request_refresh()

    def _on_return_submit(self, data: dict):
        """归还/刷新提交"""
        record_id = data.get("record_id")
        if not record_id:
            return

        now = datetime.now().isoformat()

        # v19: 完整归还字段
        return_person = data.get("return_person", "")
        confirm_person = data.get("confirm_person", "")
        return_qty = data.get("return_qty", 0)
        good_qty = data.get("good_qty", 0)
        damage_qty = data.get("damage_qty", 0)
        damage_status = data.get("damage_status", "")
        mixed_qty = data.get("mixed_qty", 0)
        mixed_remark = data.get("mixed_remark", "")

        self.sync_engine.offline_update(TABLE_BORROW_RECORDS, record_id, {
            "is_returned": True,
            "in_time": now,
            "confirm_person": confirm_person,          # 接收人（原确认人）
            "return_person": return_person,       # 归还人
            "return_qty": return_qty,             # 归还数量
            "good_qty": good_qty,                # 好板数
            "damage_qty": damage_qty,            # 坏板数
            "damage_status": damage_status,        # 补单状态
            "mixed_qty": mixed_qty,              # 混板数量
            "mixed_remark": mixed_remark,        # 混板备注
            "updated_at": now,
        }, add_to_queue=self._sync_queue_enabled)

        # 库存更新：仅好板回库；混板只做备注记录；坏板不归还（直接扣除）
        record = self.local_db.query_one(TABLE_BORROW_RECORDS, record_id)
        if record:
            material_id = record.get("material_id")
            material = self.local_db.query_one(TABLE_MATERIALS, material_id)
            if material:
                # 回库数量 = 好板数（混板只记录、坏板扣除）
                add_back = int(good_qty or 0)
                new_stock = int(material.get("stock_qty", 0)) + add_back
                self.sync_engine.offline_update(TABLE_MATERIALS, material_id, {
                    "stock_qty": new_stock,
                    "updated_at": now,
                }, add_to_queue=self._sync_queue_enabled)
        # 原地更新：直接修改 register_view._records，只重绘受影响的行，不触发整页刷新
        data["is_returned"] = 1
        self._refresh_return_row(record_id, data)

    def _on_damage_status_update(self, record_id: str, new_status: str):
        """双击操作列切换待补单/已补单"""
        if not record_id:
            return
        now = datetime.now().isoformat()
        self.sync_engine.offline_update(TABLE_BORROW_RECORDS, record_id, {
            "damage_status": new_status,
            "updated_at": now,
        }, add_to_queue=self._sync_queue_enabled)
        # 原地更新：只重绘受影响的行
        self._refresh_return_row(record_id, {"damage_status": new_status})

    def _generate_record_no(self) -> str:
        """生成领用记录编号"""
        return f"LY{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6]}"

    def _get_material_stock(self, material_id: str) -> int:
        """获取物料当前库存数量"""
        material = self.local_db.query_one(TABLE_MATERIALS, material_id)
        return int(material.get("stock_qty", 0) or 0) if material else 0


    # ---------- 资产操作 ----------

    def _on_add_asset(self, data: dict):
        asset_id = data.get("id")
        self.sync_engine.offline_insert(TABLE_FIXED_ASSETS, asset_id, data, add_to_queue=self._sync_queue_enabled)
        self._refresh_current_view()

    def _on_update_asset(self, asset_id: str, data: dict):
        self.sync_engine.offline_update(TABLE_FIXED_ASSETS, asset_id, data, add_to_queue=self._sync_queue_enabled)
        self._refresh_current_view()

    def _on_delete_asset(self, asset_id: str):
        self.sync_engine.offline_delete(TABLE_FIXED_ASSETS, asset_id, add_to_queue=self._sync_queue_enabled)
        self._refresh_current_view()

    def _refresh_current_view(self):
        """仅刷新当前视图的数据（避免全量加载所有表）"""
        self._load_data_for_page(self._current_page)

    def _refresh_return_row(self, record_id: str, updates: dict):
        """原地更新领用记录的一行，不重绘整页"""
        if self.register_view and record_id:
            self.register_view.refresh_return_row(record_id, updates)

    def _persist_configs(self, configs: list, now: str):
        """将配置项写入数据库（跳过 MySQL 密码，已存入系统密钥库）"""
        for cfg in configs:
            if cfg["config_name"] == "MYSQL_PASSWORD":
                continue
            record_id = f"cfg_{cfg['config_name']}"
            data = {
                "id": record_id,
                "config_name": cfg["config_name"],
                "item_type": cfg["item_type"],
                "content": cfg["content"],
                "sort_order": cfg["sort_order"],
                "is_active": 1,
                "updated_at": now,
                "created_at": now,
            }
            self.sync_engine.offline_insert(TABLE_CONFIG_ITEMS, record_id, data, add_to_queue=self._sync_queue_enabled)

    def _apply_mode_change(self, old_mode: str, new_mode: str):
        """模式变化时重新应用并提示用户"""
        if new_mode == old_mode:
            return
        self._app_mode = new_mode
        self._apply_app_mode()
        from widgets.toast import toast_success
        mode_labels = {
            "online": tr("ssb.mode_online"),
            "semi_offline": tr("ssb.mode_semi_offline"),
            "offline": tr("ssb.mode_offline"),
        }
        toast_success(self, tr("toast.mode_switched", mode=mode_labels.get(new_mode, new_mode)))

    def _on_config_saved(self):
        """系统配置保存回调 - 写入数据库并重新应用运行模式"""
        configs = self.config_view.collect_configs()
        now = datetime.now().isoformat()

        new_mode = "online"
        for cfg in configs:
            if cfg["config_name"] == "APP_MODE":
                new_mode = cfg["content"]
                break

        self._persist_configs(configs, now)
        self._apply_mode_change(self._app_mode, new_mode)
        # 配置保存后重新检查 MySQL 禁用状态（新密码/新host 生效）
        self.mysql_client.recheck_disabled()
        self.status_bar.showMessage(tr("status.config_saved"))

    # ---------- 用户管理操作 ----------

    def _on_add_user(self, data: dict):
        """新增用户"""
        from widgets.toast import toast_success, toast_error
        username = data.get("username", "")
        if self.local_db.user_exists(username):
            toast_error(self, tr("toast.user_exists", name=username))
            return
        user_id = uuid.uuid4().hex
        now = datetime.now().isoformat()
        data["id"] = user_id
        data["is_active"] = 1
        data["created_at"] = now
        data["updated_at"] = now
        self.sync_engine.offline_insert(TABLE_USERS, user_id, data, add_to_queue=self._sync_queue_enabled)
        toast_success(self, tr("toast.user_created", name=username))
        self._refresh_current_view()

    def _on_update_user(self, user_id: str, data: dict):
        """更新用户"""
        from widgets.toast import toast_success
        data["updated_at"] = datetime.now().isoformat()
        self.sync_engine.offline_update(TABLE_USERS, user_id, data, add_to_queue=self._sync_queue_enabled)
        # 如果修改的是当前用户，同步更新内存中的数据
        if self._current_user and str(self._current_user.get("id")) == str(user_id):
            self._current_user.update(data)
        toast_success(self, tr("toast.user_updated"))
        self._refresh_current_view()

    def _on_delete_user(self, user_id: str):
        """删除用户"""
        from widgets.toast import toast_success
        self.sync_engine.offline_delete(TABLE_USERS, user_id, add_to_queue=self._sync_queue_enabled)
        toast_success(self, tr("toast.user_deleted"))
        self._refresh_current_view()

    def _on_toggle_user_status(self, user_id: str, is_active: bool):
        """切换用户启用/禁用状态"""
        from widgets.toast import toast_success
        data = {
            "is_active": 1 if is_active else 0,
            "updated_at": datetime.now().isoformat(),
        }
        self.sync_engine.offline_update(TABLE_USERS, user_id, data, add_to_queue=self._sync_queue_enabled)
        status_text = tr("user.status_enabled") if is_active else tr("user.status_disabled")
        toast_success(self, status_text)
        self._refresh_current_view()

    # ---------- 员工档案操作 ----------

    def _on_employee_add_requested(self, data: dict):
        """新增员工"""
        from widgets.toast import toast_success, toast_error
        employee_no = data.get("employee_no", "")
        if self.local_db.employee_exists(employee_no):
            toast_error(self, tr("user_manage.emp_exists", emp_no=employee_no))
            return
        record_id = uuid.uuid4().hex
        data["id"] = record_id
        now = datetime.now().isoformat()
        data["created_at"] = now
        data["updated_at"] = now
        self.sync_engine.offline_insert(
            TABLE_EMPLOYEE_RECORDS, record_id, data,
            add_to_queue=self._sync_queue_enabled
        )
        toast_success(self, tr("user_manage.emp_created", name=data.get("name", "")))
        self._refresh_current_view()

    def _on_employee_edit_requested(self, record_id: str, data: dict):
        """更新员工"""
        from widgets.toast import toast_success
        now = datetime.now().isoformat()
        data["updated_at"] = now
        self.sync_engine.offline_update(
            TABLE_EMPLOYEE_RECORDS, record_id, data,
            add_to_queue=self._sync_queue_enabled
        )
        toast_success(self, tr("user_manage.emp_updated"))
        self._refresh_current_view()

    def _on_employee_delete_requested(self, record_id: str):
        """删除员工"""
        from widgets.toast import toast_success
        self.sync_engine.offline_delete(
            TABLE_EMPLOYEE_RECORDS, record_id,
            add_to_queue=self._sync_queue_enabled
        )
        toast_success(self, tr("user_manage.emp_deleted"))
        self._refresh_current_view()

    def _on_employee_data_requested(self):
        """重新加载员工数据"""
        employees = self.local_db.get_all_employees()
        self.user_manage_view.set_employee_data(employees)

    # ---------- 语言切换 ----------

    def _on_switch_language(self):
        """语言切换按钮点击"""
        self._lang_manager.toggle()

    def _on_language_changed(self, lang: str):
        """语言变更时重新翻译所有界面"""
        self.setWindowTitle(tr("common.app_title"))
        self.status_bar.showMessage(tr("common.ready"))
        # 更新所有组件
        self.sync_status_bar.retranslate_ui()
        self.sync_status_bar.update_lang_button(lang)
        self.nav_bar.retranslate_ui()
        self.login_view.retranslate_ui()
        self.inventory_view.retranslate_ui()
        self.register_view.retranslate_ui()
        self.asset_view.retranslate_ui()
        self.config_view.retranslate_ui()
        self.user_manage_view.retranslate_ui()
        # 重新加载当前页面数据（刷新表头/单元格文本）
        self._load_data_for_page(self._current_page)
        # 重新应用模式状态
        self.sync_status_bar.set_mode(self._app_mode)
        self._apply_app_mode()

    def closeEvent(self, event):
        # 保存窗口几何
        from utils.ui_settings import save_window_geometry
        save_window_geometry(self.saveGeometry(), self.saveState())
        self.sync_engine.stop()
        self.network_monitor.stop()
        self._refresh_timer.stop()
        # 通知子视图释放资源
        self.inventory_view.clear_memory()
        self.register_view.clear_memory()
        self.asset_view.clear_memory()
        self.user_manage_view.clear_memory()
        self.config_view.clear_memory()
        # 关闭本地数据库连接池
        self.local_db.close_all()
        event.accept()


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    app = QApplication(sys.argv)

    IPC_KEY = "MMS_V4.3_IPC"

    # 尝试连接已有实例
    sock = QLocalSocket()
    sock.connectToServer(IPC_KEY)
    if sock.waitForConnected(1000):
        # 已有实例在运行，发送激活消息后退出
        sock.write(b"activate")
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()
        sys.exit(0)

    # 清理可能残留的旧 Server
    QLocalServer.removeServer(IPC_KEY)

    # 创建本地 Server（第一个实例）
    ipc_server = QLocalServer()
    if not ipc_server.listen(IPC_KEY):
        # 创建失败，可能另一个实例刚创建，直接退出
        sys.exit(0)

    apply_theme(app)
    # 设置应用程序图标（支持多尺寸 ICO）
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Image", "app_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MainWindow()
    window.show()

    # IPC 连接：新实例启动时激活窗口
    def _on_ipc_connect():
        conn = ipc_server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(lambda: _on_ipc_message(conn))

    def _on_ipc_message(conn):
        data = conn.readAll().data()
        if data == b"activate":
            window.activateWindow()
            window.raise_()
        conn.disconnectFromServer()

    ipc_server.newConnection.connect(_on_ipc_connect)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()


