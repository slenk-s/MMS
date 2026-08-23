"""登录覆盖层视图
v4.2 优化：全屏覆盖 + 淡入淡出过渡动画 + 视觉美化
"""
import os
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QCheckBox,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QFont, QPixmap

from i18n import tr
from config import IMAGES_DIR


class LoginView(QWidget):
    """登录覆盖层 — 全屏覆盖主窗口，支持淡入淡出过渡"""

    login_success = Signal(object)  # 发射 不含密码 的用户信息 dict
    logout = Signal()

    FADE_DURATION = 350

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("loginOverlay")
        self._is_register_mode = False
        self._auth_callback: Optional[Callable] = None
        self._init_ui()
        self._init_animation()

    def set_auth_callback(self, callback: Callable):
        """设置认证回调函数
        callback(username, password, is_register=False) -> dict or None
        返回 None 表示认证失败（已弹出 Toast），返回 dict 表示成功（不含密码字段）
        """
        self._auth_callback = callback

    def _init_ui(self):
        self.setStyleSheet("""
            #loginOverlay {
                background-color: rgba(240, 244, 248, 0.96);
                border: none;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        card.setMaximumWidth(420)
        card.setMinimumWidth(380)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(16)

        self.banner_label = QLabel()
        self.banner_label.setAlignment(Qt.AlignCenter)
        self.banner_label.setStyleSheet("margin-bottom: 4px;")
        banner_path = os.path.join(IMAGES_DIR, "login_banner.png")
        if os.path.exists(banner_path):
            pixmap = QPixmap(banner_path)
            if not pixmap.isNull():
                self.banner_label.setPixmap(pixmap.scaled(356, 999, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        card_layout.addWidget(self.banner_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText(tr("login.username_placeholder"))
        self.username_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
            }
            QLineEdit:focus { border: 2px solid #2563eb; }
        """)
        card_layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText(tr("login.password_placeholder"))
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet(self.username_input.styleSheet())
        card_layout.addWidget(self.password_input)

        self.confirm_input = QLineEdit()
        self.confirm_input.setPlaceholderText(tr("login.confirm_placeholder"))
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setStyleSheet(self.username_input.styleSheet())
        self.confirm_input.setVisible(False)
        card_layout.addWidget(self.confirm_input)

        self.remember_checkbox = QCheckBox(tr("login.remember"))
        self.remember_checkbox.setStyleSheet("color: #5a6573; font-size: 12px;")
        self.remember_checkbox.setChecked(True)
        card_layout.addWidget(self.remember_checkbox)

        self.action_btn = QPushButton(tr("login.login_btn"))
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-weight: bold;
                font-size: 15px;
                border: none;
                border-radius: 8px;
                padding: 12px;
                min-height: 44px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:pressed { background-color: #1e40af; }
        """)
        self.action_btn.clicked.connect(self._on_action)
        card_layout.addWidget(self.action_btn)

        self.switch_btn = QPushButton(tr("login.switch_to_register"))
        self.switch_btn.hide()
        self.switch_btn.setStyleSheet("""
            QPushButton {
                color: #2563eb;
                font-size: 13px;
                border: none;
                background: transparent;
                text-decoration: underline;
            }
            QPushButton:hover { color: #1d4ed8; }
        """)
        self.switch_btn.clicked.connect(self._toggle_mode)
        card_layout.addWidget(self.switch_btn)

        main_layout.addWidget(card)

        self.username_input.returnPressed.connect(self._on_action)
        self.password_input.returnPressed.connect(self._on_action)
        self.confirm_input.returnPressed.connect(self._on_action)

    def _init_animation(self):
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_anim.setDuration(self.FADE_DURATION)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

    def fade_out(self, on_finished=None):
        self._fade_anim.stop()
        self._opacity_effect.setOpacity(1.0)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()
        if on_finished:
            QTimer.singleShot(self.FADE_DURATION, on_finished)

    def fade_in(self):
        self._fade_anim.stop()
        self._opacity_effect.setOpacity(0.0)
        self.show()
        self.raise_()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def _toggle_mode(self):
        self._is_register_mode = not self._is_register_mode
        if self._is_register_mode:
            self.action_btn.setText(tr("login.register_btn"))
            self.switch_btn.setText(tr("login.switch_to_login"))
            self.confirm_input.setVisible(True)
            self.remember_checkbox.setVisible(False)
        else:
            self.action_btn.setText(tr("login.login_btn"))
            self.switch_btn.setText(tr("login.switch_to_register"))
            self.confirm_input.setVisible(False)
            self.remember_checkbox.setVisible(True)

    def _on_action(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        if not username or not password:
            from widgets.toast import toast_error
            toast_error(self, tr("login.empty_error"))
            return
        if self._is_register_mode:
            self._do_register(username, password)
        else:
            self._do_login(username, password)

    def _do_login(self, username: str, password: str):
        if self._auth_callback:
            # 通过回调认证，密码不经过 Qt 信号，仅存于局部变量
            result = self._auth_callback(username, password, is_register=False)
            if result is None:
                return  # 认证失败，回调已弹出 Toast
            # 注入 remember 标志供 MainWindow 处理
            result["remember"] = self.remember_checkbox.isChecked()
            self.login_success.emit(result)
        else:
            # 降级：无回调时直接发射（兼容旧代码）
            self.login_success.emit({
                "username": username,
                "password": password,
                "remember": self.remember_checkbox.isChecked(),
            })

    def _do_register(self, username: str, password: str):
        confirm = self.confirm_input.text().strip()
        if password != confirm:
            from widgets.toast import toast_error
            toast_error(self, tr("login.password_mismatch"))
            return
        if self._auth_callback:
            result = self._auth_callback(username, password, is_register=True)
            if result is None:
                return  # 注册失败，回调已弹出 Toast
            self.login_success.emit(result)
        else:
            self.login_success.emit({
                "username": username,
                "password": password,
                "is_register": True,
            })

    def clear_inputs(self):
        self.username_input.clear()
        self.password_input.clear()
        self.confirm_input.clear()

    def show_login(self):
        self._is_register_mode = False
        self.action_btn.setText(tr("login.login_btn"))
        self.switch_btn.setText(tr("login.switch_to_register"))
        self.confirm_input.setVisible(False)
        self.remember_checkbox.setVisible(True)
        self.clear_inputs()
        self.fade_in()

    def show_register(self):
        self._is_register_mode = True
        self.action_btn.setText(tr("login.register_btn"))
        self.switch_btn.setText(tr("login.switch_to_login"))
        self.confirm_input.setVisible(True)
        self.remember_checkbox.setVisible(False)
        self.clear_inputs()
        self.fade_in()

    def hide(self):
        self._fade_anim.stop()
        super().hide()

    def retranslate_ui(self):
        """重新应用当前语言的文本"""
        self.username_input.setPlaceholderText(tr("login.username_placeholder"))
        self.password_input.setPlaceholderText(tr("login.password_placeholder"))
        self.confirm_input.setPlaceholderText(tr("login.confirm_placeholder"))
        self.remember_checkbox.setText(tr("login.remember"))
        if self._is_register_mode:
            self.action_btn.setText(tr("login.register_btn"))
            self.switch_btn.setText(tr("login.switch_to_login"))
        else:
            self.action_btn.setText(tr("login.login_btn"))
            self.switch_btn.setText(tr("login.switch_to_register"))
