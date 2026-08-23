"""美化版对话框工具
自定义 QDialog，无标题栏、无图标，风格与 Toast 一致
"""
from i18n import tr
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QGraphicsDropShadowEffect, QLineEdit, QSpinBox,
    QFormLayout, QComboBox, QSizePolicy, QProgressBar,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor


LEVEL_STYLE = {
    "info": {
        "bg": "#eff6ff",
        "border": "#3b82f6",
        "text": "#1e40af",
        "title": "#1e40af",
    },
    "warning": {
        "bg": "#fffbeb",
        "border": "#f59e0b",
        "text": "#92400e",
        "title": "#92400e",
    },
    "error": {
        "bg": "#fef2f2",
        "border": "#ef4444",
        "text": "#991b1b",
        "title": "#991b1b",
    },
}

# ============================================================
# 公共样式常量
# ============================================================
_INPUT_STYLE_NORMAL = """
    QLineEdit, QSpinBox, QComboBox {
        border: 1px solid #d1d5db;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 13px;
        background-color: #ffffff;
        min-height: 28px;
    }
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
        border-color: #22c55e;
    }
"""

_INPUT_STYLE_REQUIRED = """
    QLineEdit {
        border: 2px solid #dc2626;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 13px;
        background-color: #ffffff;
        min-height: 28px;
    }
    QLineEdit:focus {
        border-color: #22c55e;
    }
"""

_BTN_CANCEL_STYLE = """
    QPushButton {
        background-color: #ffffff;
        color: #5a6573;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        padding: 8px 24px;
        min-width: 80px;
        min-height: 32px;
        font-size: 13px;
        font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    }
    QPushButton:hover {
        background-color: #f1f5f9;
        border-color: #94a3b8;
    }
    QPushButton:focus {
        outline: none;
    }
"""

_BTN_CONFIRM_STYLE = """
    QPushButton {
        background-color: {color};
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 8px 24px;
        min-width: 80px;
        min-height: 32px;
        font-size: 13px;
        font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    }
    QPushButton:hover {
        background-color: {hover};
    }
    QPushButton:focus {
        outline: none;
    }
"""

# ============================================================
# 通用确认对话框
# ============================================================

class StyledConfirmDialog(QDialog):
    """美化确认对话框：无标题栏、无图标"""

    def __init__(self, parent, title: str, text: str, dialog_type: str = "warning"):
        super().__init__(parent)
        self._style = LEVEL_STYLE.get(dialog_type, LEVEL_STYLE["warning"])
        self._confirmed = False
        self._init_ui(title, text)

    def _init_ui(self, title: str, text: str):
        s = self._style
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setMaximumWidth(460)

        container = QWidget(self)
        container.setStyleSheet(f"""
            QWidget {{
                background-color: {s['bg']};
                border: 1px solid {s['border']};
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Microsoft YaHei", 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {s['title']}; background: transparent; border: none;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        text_lbl = QLabel(text)
        text_lbl.setWordWrap(True)
        text_lbl.setFont(QFont("Microsoft YaHei", 13))
        text_lbl.setStyleSheet(f"color: {s['text']}; background: transparent; border: none;")
        text_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(text_lbl)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        cancel_btn = QPushButton(tr("dialog.cancel"))
        cancel_btn.setStyleSheet(_BTN_CANCEL_STYLE)
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QPushButton(tr("dialog.confirm"))
        confirm_btn.setStyleSheet(
        _BTN_CONFIRM_STYLE.replace("{color}", s["border"]).replace("{hover}", s["text"])
    )
        confirm_btn.clicked.connect(self._on_confirm)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.addWidget(container)

    def _on_confirm(self):
        self._confirmed = True
        self.accept()

    def is_confirmed(self) -> bool:
        return self._confirmed


def show_confirm(parent, title: str, text: str, dialog_type: str = "warning") -> bool:
    """显示美化版确认对话框（无标题栏、无图标）

    Args:
        dialog_type: "info" | "warning" | "error"
    Returns:
        True 表示用户点了确认，False 表示点了取消或关闭
    """
    dlg = StyledConfirmDialog(parent, title, text, dialog_type)
    try:
        dlg.exec()
        result = dlg.is_confirmed()
    finally:
        dlg.deleteLater()
    return result


# ============================================================
# 等待对话框（等待硬件读取）
# ============================================================

class WaitDialog(QDialog):
    """等待对话框：无标题栏、半透明背景、圆角、阴影，靛蓝主题。
    显示进度条、提示语、倒计时，用户可点取消，超时自动关闭。
    _active_dialog: 当前活动的等待对话框，供扫描回调主动关闭。
    """
    _active_dialog = None

    def __init__(self, parent, title: str, hint: str = "", timeout: float = 0):
        super().__init__(parent)
        self._cancelled = False
        self._timeout = timeout
        self._countdown = 0
        self._timer = None
        WaitDialog._active_dialog = self
        self._init_ui(title, hint)

    def _init_ui(self, title: str, hint: str):
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(380)

        container = QWidget(self)
        container.setStyleSheet("""
            QWidget { background-color: #f5f3ff; border: 1px solid #6366f1; border-radius: 10px; }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Microsoft YaHei", 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #4338ca; background: transparent; border: none;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setStyleSheet("""
            QProgressBar { background: #e0e7ff; border: 1px solid #a5b4fc; border-radius: 4px; height: 8px; }
            QProgressBar::chunk { background: #6366f1; }
        """)
        layout.addWidget(self.progress)

        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setFont(QFont("Microsoft YaHei", 12))
            hint_lbl.setStyleSheet("color: #6366f1; background: transparent; border: none;")
            hint_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(hint_lbl)

        self.countdown_lbl = QLabel()
        self.countdown_lbl.setFont(QFont("Microsoft YaHei", 24, QFont.Weight.Bold))
        self.countdown_lbl.setStyleSheet("color: #dc2626; background: transparent; border: none;")
        self.countdown_lbl.setAlignment(Qt.AlignCenter)
        if self._timeout > 0:
            self._countdown = int(self._timeout)
            self.countdown_lbl.setText(str(self._countdown))
        layout.addWidget(self.countdown_lbl)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton(tr("dialog.cancel"))
        cancel_btn.setStyleSheet(_BTN_CANCEL_STYLE)
        cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.addWidget(container)

        if self._timeout > 0:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._on_tick)
            self._timer.start(1000)

    def _on_tick(self):
        self._countdown -= 1
        if self._countdown <= 0:
            self.countdown_lbl.hide()
            self._timer.stop()
            self._cancelled = False
            self.reject()
        else:
            self.countdown_lbl.setText(str(self._countdown))

    def _on_cancel(self):
        if self._timer:
            self._timer.stop()
        self._cancelled = True
        self.reject()

    def is_cancelled(self) -> bool:
        return self._cancelled


def show_wait_dialog(parent, title: str, hint: str = "", timeout: float = 0) -> bool:
    """显示等待对话框。

    Args:
        timeout: 倒计时秒数，0 表示无倒计时。
    Returns:
        True = 正常关闭（回调关闭），False = 用户取消 或 超时
    """
    dlg = WaitDialog(parent, title, hint, timeout=timeout)
    try:
        dlg.exec()
        return not dlg.is_cancelled()
    finally:
        dlg.deleteLater()
    return False


# ============================================================
# 归还确认对话框（完整版）
# ============================================================

class ReturnConfirmDialog(QDialog):
    """归还确认对话框：
    - 无标题栏、半透明背景、圆角
    - 字段：归还人、接收人、归还数量、好板数、坏板数(待补单/已补单)、混板数量、混板备注
    - 实时校验：好 + 坏 + 混 = 归还数量
    """

    def __init__(self, parent, material_name: str = "", original_qty: int = 0, current_stock: int = 0, material_code: str = ""):
        super().__init__(parent)
        # 防御性处理：确保数量为有效整数
        self._original_qty = max(0, int(original_qty or 0))
        self._current_stock = max(0, int(current_stock or 0))
        self._material_code = material_code or ""
        self._confirmed = False
        self._init_ui(material_code, material_name, self._original_qty)

    def _init_ui(self, material_code: str, material_name: str, original_qty: int):
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)

        container = QWidget(self)
        container.setStyleSheet("""
            QWidget {
                background-color: #f0fdf4;
                border: 1px solid #22c55e;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 标题
        title_lbl = QLabel(tr("dialog.return_confirm_title"))
        title_lbl.setFont(QFont("Microsoft YaHei", 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #15803d; background: transparent; border: none;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 物料信息（显示物料编码 + 名称 + 数量）
        if material_code:
            info_text = tr("dialog.return_material_info", code=material_code, name=material_name or '未知', qty=original_qty)
        else:
            info_text = tr("dialog.return_material_info", name=material_name or '未知', qty=original_qty)
        info_lbl = QLabel(info_text)
        info_lbl.setWordWrap(True)
        info_lbl.setFont(QFont("Microsoft YaHei", 12))
        info_lbl.setStyleSheet("color: #166534; background: transparent; border: none;")
        info_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_lbl)

        # 库存计算过程展示（动态更新）
        self.calc_label = QLabel()
        self.calc_label.setAlignment(Qt.AlignCenter)
        self.calc_label.setStyleSheet("color: #166534; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        layout.addWidget(self.calc_label)

        # 表单区
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # 归还人（必填）
        self.return_person_input = QLineEdit()
        self.return_person_input.setPlaceholderText(tr("dialog.return_person_placeholder"))
        self.return_person_input.setStyleSheet(_INPUT_STYLE_REQUIRED)
        form_layout.addRow(tr("dialog.return_person"), self.return_person_input)

        # 接收人（必填，原确认人）
        self.receiver_input = QLineEdit()
        self.receiver_input.setPlaceholderText(tr("dialog.return_person_placeholder"))
        self.receiver_input.setStyleSheet(_INPUT_STYLE_REQUIRED)
        form_layout.addRow(tr("dialog.receiver"), self.receiver_input)

        # 归还数量
        self.return_qty_input = QSpinBox()
        self.return_qty_input.setRange(0, original_qty)
        self.return_qty_input.setValue(original_qty)
        self.return_qty_input.setStyleSheet(_INPUT_STYLE_NORMAL)
        self.return_qty_input.valueChanged.connect(self._on_qty_changed)
        form_layout.addRow(tr("dialog.return_qty"), self.return_qty_input)

        # 好板数
        self.good_qty_input = QSpinBox()
        self.good_qty_input.setRange(0, original_qty)
        self.good_qty_input.setValue(original_qty)
        self.good_qty_input.setStyleSheet(_INPUT_STYLE_NORMAL)
        self.good_qty_input.valueChanged.connect(self._on_qty_changed)
        form_layout.addRow(tr("dialog.good_qty"), self.good_qty_input)

        # 坏板数
        self.damage_qty_input = QSpinBox()
        self.damage_qty_input.setRange(0, original_qty)
        self.damage_qty_input.setValue(0)
        self.damage_qty_input.setStyleSheet(_INPUT_STYLE_NORMAL)
        self.damage_qty_input.valueChanged.connect(self._on_qty_changed)
        form_layout.addRow(tr("dialog.damage_qty"), self.damage_qty_input)

        # 补单状态（坏板>0时显示/必填）
        self.damage_status_combo = QComboBox()
        self.damage_status_combo.addItems([tr("register.status_pending"), tr("register.status_completed")])
        self.damage_status_combo.setStyleSheet(_INPUT_STYLE_NORMAL)
        self.damage_status_combo.setVisible(False)
        self._damage_status_label = QLabel(tr("dialog.damage_status"))
        self._damage_status_label.setVisible(False)
        form_layout.addRow(self._damage_status_label, self.damage_status_combo)

        # 混板数量
        self.mixed_qty_input = QSpinBox()
        self.mixed_qty_input.setRange(0, original_qty)
        self.mixed_qty_input.setValue(0)
        self.mixed_qty_input.setStyleSheet(_INPUT_STYLE_NORMAL)
        self.mixed_qty_input.valueChanged.connect(self._on_qty_changed)
        form_layout.addRow(tr("dialog.mixed_qty"), self.mixed_qty_input)

        # 混板备注
        self.mixed_remark_input = QLineEdit()
        self.mixed_remark_input.setPlaceholderText(tr("dialog.mixed_remark_placeholder"))
        self.mixed_remark_input.setMaxLength(20)
        self.mixed_remark_input.setStyleSheet(_INPUT_STYLE_NORMAL)
        self.mixed_remark_input.textChanged.connect(self._on_mixed_remark_changed)
        form_layout.addRow(tr("dialog.mixed_remark"), self.mixed_remark_input)

        layout.addLayout(form_layout)

        # 实时校验提示
        self.tip_label = QLabel(tr("dialog.validate_pass"))
        self.tip_label.setAlignment(Qt.AlignCenter)
        self.tip_label.setStyleSheet("color: #16a34a; font-size: 12px; font-weight: bold;")
        layout.addWidget(self.tip_label)

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        cancel_btn = QPushButton(tr("dialog.cancel"))
        cancel_btn.setStyleSheet(_BTN_CANCEL_STYLE)
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QPushButton(tr("dialog.confirm_return"))
        confirm_btn.setStyleSheet(
            _BTN_CONFIRM_STYLE.replace("{color}", "#22c55e").replace("{hover}", "#16a34a")
        )
        confirm_btn.clicked.connect(self._on_confirm)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

        # 阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.addWidget(container)

        self._update_calc_label()
        self._validate()

    def _on_qty_changed(self):
        """数量变化时触发动态显示/隐藏补单状态和库存计算"""
        damage = self.damage_qty_input.value()
        # 坏板数>0时显示补单状态
        show_status = damage > 0
        self.damage_status_combo.setVisible(show_status)
        self._damage_status_label.setVisible(show_status)
        self._update_calc_label()
        self._validate()

    def _update_calc_label(self):
        """动态更新库存计算过程展示"""
        good = self.good_qty_input.value()
        new_stock = self._current_stock + good
        self.calc_label.setText(
            tr("dialog.return_stock_calc",
               current=self._current_stock,
               add=good,
               new=new_stock)
        )

    def _on_mixed_remark_changed(self, text: str):
        """混板备注变化时校验"""
        self._validate()

    def _validate(self) -> bool:
        """实时校验，返回是否通过"""
        return_qty = self.return_qty_input.value()
        good = self.good_qty_input.value()
        damage = self.damage_qty_input.value()
        mixed = self.mixed_qty_input.value()
        remark = self.mixed_remark_input.text().strip()

        # 校验规则
        errors = []
        if return_qty <= 0:
            errors.append(tr("dialog.validate_qty_positive"))
        if return_qty > self._original_qty:
            errors.append(tr("dialog.validate_qty_exceed", max=self._original_qty))
        if good + damage + mixed != return_qty:
            errors.append(tr("dialog.validate_sum_mismatch", good=good, damage=damage, mixed=mixed, return_qty=return_qty))
        if mixed > 0 and not remark:
            errors.append(tr("dialog.validate_mixed_remark_required"))
        if remark and len(remark) > 20:
            errors.append(tr("dialog.validate_remark_max_length"))

        if errors:
            self.tip_label.setText(tr("dialog.validate_fail", errors="；".join(errors)))
            self.tip_label.setStyleSheet("color: #dc2626; font-size: 12px; font-weight: bold;")
            return False
        else:
            self.tip_label.setText(tr("dialog.validate_pass"))
            self.tip_label.setStyleSheet("color: #16a34a; font-size: 12px; font-weight: bold;")
            return True

    def _on_confirm(self):
        if not self.return_person_input.text().strip():
            self.return_person_input.setFocus()
            self._validate()
            return
        if not self.receiver_input.text().strip():
            self.receiver_input.setFocus()
            self._validate()
            return
        if not self._validate():
            return
        self._confirmed = True
        self.accept()

    def is_confirmed(self) -> bool:
        return self._confirmed

    def get_data(self) -> dict:
        """返回归还弹窗的完整数据"""
        return {
            "return_person": self.return_person_input.text().strip(),
            "confirm_person": self.receiver_input.text().strip(),
            "return_qty": self.return_qty_input.value(),
            "good_qty": self.good_qty_input.value(),
            "damage_qty": self.damage_qty_input.value(),
            "damage_status": self.damage_status_combo.currentText() if self.damage_qty_input.value() > 0 else "",
            "mixed_qty": self.mixed_qty_input.value(),
            "mixed_remark": self.mixed_remark_input.text().strip(),
        }


def show_return_confirm(parent, material_name: str = "", original_qty: int = 0, current_stock: int = 0, material_code: str = "") -> tuple:
    """显示归还确认对话框

    Args:
        material_code: 物料编码，显示在弹窗标题区
        current_stock: 当前库存数量，用于展示计算过程

    Returns:
        (confirmed: bool, data: dict)
        data 为空 dict 时 confirmed 为 False
    """
    # 防御性处理：确保传入的数量为有效整数
    safe_qty = max(0, int(original_qty or 0))
    safe_stock = max(0, int(current_stock or 0))
    dlg = ReturnConfirmDialog(parent, material_name, safe_qty, safe_stock, material_code)
    try:
        dlg.exec()
        if dlg.is_confirmed():
            return True, dlg.get_data()
        return False, {}
    finally:
        dlg.deleteLater()
