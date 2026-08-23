"""用户管理视图（仅管理员可见）
功能：查看所有用户、新增用户、删除用户、重置密码、修改密码
员工档案：管理员工信息（含指纹/NFC 硬件扫描录入）
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QDialog, QFormLayout, QLineEdit, QComboBox,
    QHeaderView, QAbstractItemView, QMessageBox,
    QTabWidget,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont

from i18n import tr
from widgets.toast import toast_success, toast_error, toast_warning
from utils.dialogs import show_wait_dialog, show_confirm
from config import TABLE_CONFIG_ITEMS, TABLE_EMPLOYEE_RECORDS
from local_db import DEFAULT_ADMIN_ID


HW_BTN_STYLE_ENABLED = """
    QPushButton { background-color: #6366f1; color: #ffffff; border: none; border-radius: 8px; padding: 10px 16px; font-size: 13px; }
    QPushButton:hover { background-color: #4f46e5; }
    QPushButton:pressed { background-color: #4338ca; }
"""
HW_BTN_STYLE_DISABLED = """
    QPushButton {
        background-color: #f1f5f9;
        color: #64748b;
        border: 1px dashed #94a3b8;
        border-radius: 8px;
        padding: 10px 16px;
        font-size: 13px;
    }
"""


class _EmployeeScanThread(QThread):
    """后台线程读取硬件（指纹/NFC），通过 result_ready 信号返回扫描结果"""
    result_ready = Signal(str)

    def __init__(self, reader, timeout: float):
        super().__init__()
        self.reader = reader
        self.timeout = timeout

    def run(self):
        try:
            sid = self.reader.read(timeout=self.timeout) or ""
        except Exception:
            sid = ""
        self.result_ready.emit(sid)


class UserDialog(QDialog):
    """新增/编辑用户弹窗"""

    def __init__(self, parent=None, user_data: dict = None):
        super().__init__(parent)
        self.setWindowTitle(tr("user.dialog_add_title") if not user_data else tr("user.dialog_edit_title"))
        self.setMinimumWidth(360)
        self._data = user_data or {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # 用户名
        self.username_input = QLineEdit()
        self.username_input.setText(self._data.get("username", ""))
        self.username_input.setPlaceholderText(tr("user.dialog_username_placeholder"))
        if self._data:
            self.username_input.setEnabled(False)
        form.addRow(tr("user.dialog_username") + ":", self.username_input)

        # 密码
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText(
            tr("user.dialog_password_placeholder") if not self._data
            else tr("user.dialog_password_edit_placeholder")
        )
        form.addRow(
            (tr("user.dialog_password") + ":") if not self._data
            else (tr("user.dialog_password") + ":"),
            self.password_input
        )

        # 确认密码
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setPlaceholderText(tr("user.dialog_confirm_password_placeholder"))
        form.addRow(tr("user.dialog_confirm_password") + ":", self.confirm_input)

        # 角色
        self.role_input = QComboBox()
        self.role_input.addItems(["admin", "user"])
        role = self._data.get("role", "user")
        idx = self.role_input.findText(role)
        self.role_input.setCurrentIndex(max(0, idx))
        form.addRow(tr("user.dialog_role") + ":", self.role_input)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ok = QPushButton(tr("common.ok"))
        self.btn_ok.setMinimumWidth(80)
        self.btn_cancel = QPushButton(tr("dialog.cancel"))
        self.btn_cancel.setObjectName("secondaryButton")
        self.btn_cancel.setMinimumWidth(80)
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)

    def _on_ok(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        confirm = self.confirm_input.text().strip()

        if not username:
            toast_warning(self, tr("toast.username_empty"))
            self.username_input.setFocus()
            return

        if not self._data and not password:
            toast_warning(self, tr("toast.password_empty"))
            self.password_input.setFocus()
            return

        if password and password != confirm:
            toast_warning(self, tr("toast.pwd_confirm_mismatch"))
            self.confirm_input.setFocus()
            return

        self.accept()

    def get_data(self) -> dict:
        data = {
            "username": self.username_input.text().strip(),
            "role": self.role_input.currentText(),
        }
        password = self.password_input.text().strip()
        if password:
            data["password"] = password
        return data


class PasswordDialog(QDialog):
    """修改密码弹窗"""

    def __init__(self, parent=None, title: str = None):
        super().__init__(parent)
        self.setWindowTitle(title or tr("user.pwd_dialog_title"))
        self.setMinimumWidth(320)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.old_input = QLineEdit()
        self.old_input.setEchoMode(QLineEdit.Password)
        self.old_input.setPlaceholderText(tr("user.pwd_dialog_old_placeholder"))
        form.addRow(tr("user.pwd_dialog_old") + ":", self.old_input)

        self.new_input = QLineEdit()
        self.new_input.setEchoMode(QLineEdit.Password)
        self.new_input.setPlaceholderText(tr("user.pwd_dialog_new_placeholder"))
        form.addRow(tr("user.pwd_dialog_new") + ":", self.new_input)

        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setPlaceholderText(tr("user.pwd_dialog_confirm_placeholder"))
        form.addRow(tr("user.pwd_dialog_confirm") + ":", self.confirm_input)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ok = QPushButton(tr("common.ok"))
        self.btn_ok.setMinimumWidth(80)
        self.btn_cancel = QPushButton(tr("dialog.cancel"))
        self.btn_cancel.setObjectName("secondaryButton")
        self.btn_cancel.setMinimumWidth(80)
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)

    def _on_ok(self):
        old = self.old_input.text().strip()
        new = self.new_input.text().strip()
        confirm = self.confirm_input.text().strip()

        if not old:
            toast_warning(self, tr("toast.old_pwd_empty"))
            return
        if not new:
            toast_warning(self, tr("toast.new_pwd_empty"))
            return
        if new != confirm:
            toast_warning(self, tr("toast.pwd_confirm_mismatch"))
            return
        self.accept()

    def get_passwords(self) -> tuple:
        return (
            self.old_input.text().strip(),
            self.new_input.text().strip(),
        )


class EmployeeDialog(QDialog):
    """新增/编辑员工弹窗"""

    # 必填项红框样式
    REQUIRED_STYLE = """
        QLineEdit {
            border: 2px solid #E53935;
        }
    """

    def __init__(self, parent=None, emp_data: dict = None, existing_employees: list = None):
        super().__init__(parent)
        self.setWindowTitle(
            tr("user_manage.emp_dialog_add_title") if not emp_data
            else tr("user_manage.emp_dialog_edit_title")
        )
        self.setMinimumWidth(360)
        self._data = emp_data or {}
        self._existing_employees = existing_employees or []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # 工号（必填、唯一）
        self.emp_no_input = QLineEdit()
        self.emp_no_input.setText(self._data.get("employee_no", ""))
        self.emp_no_input.setPlaceholderText(tr("user_manage.emp_dialog_emp_no_placeholder"))
        self.emp_no_input.setToolTip(tr("user_manage.emp_dialog_emp_no_tooltip"))
        self._set_required_style(self.emp_no_input)
        form.addRow(tr("user_manage.emp_dialog_emp_no") + ":", self.emp_no_input)

        # 姓名（必填）
        self.name_input = QLineEdit()
        self.name_input.setText(self._data.get("name", ""))
        self.name_input.setPlaceholderText(tr("user_manage.emp_dialog_name_placeholder"))
        self._set_required_style(self.name_input)
        form.addRow(tr("user_manage.emp_dialog_name") + ":", self.name_input)

        # 部门
        self.dept_input = QLineEdit()
        self.dept_input.setText(self._data.get("dept", ""))
        self.dept_input.setPlaceholderText(tr("user_manage.emp_dialog_dept_placeholder"))
        form.addRow(tr("user_manage.emp_dialog_dept") + ":", self.dept_input)

        # 联系电话
        self.phone_input = QLineEdit()
        self.phone_input.setText(self._data.get("phone", ""))
        self.phone_input.setPlaceholderText(tr("user_manage.emp_dialog_phone_placeholder"))
        form.addRow(tr("user_manage.emp_dialog_phone") + ":", self.phone_input)

        # 指纹ID
        self.fingerprint_input = QLineEdit()
        self.fingerprint_input.setText(self._data.get("fingerprint_id", ""))
        self.fingerprint_input.setPlaceholderText(tr("user_manage.emp_dialog_fingerprint_placeholder"))
        form.addRow(tr("user_manage.emp_dialog_fingerprint") + ":", self.fingerprint_input)

        # NFC卡号
        self.card_input = QLineEdit()
        self.card_input.setText(self._data.get("card_no", ""))
        self.card_input.setPlaceholderText(tr("user_manage.emp_dialog_card_placeholder"))
        form.addRow(tr("user_manage.emp_dialog_card") + ":", self.card_input)

        # 状态：启用/禁用
        self.status_input = QComboBox()
        self.status_input.addItems([tr("user.status_enabled"), tr("user.status_disabled")])
        is_active = self._data.get("is_active", 1)
        if is_active:
            self.status_input.setCurrentIndex(0)
        else:
            self.status_input.setCurrentIndex(1)
        form.addRow(tr("user_manage.emp_dialog_status") + ":", self.status_input)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ok = QPushButton(tr("common.ok"))
        self.btn_ok.setMinimumWidth(80)
        self.btn_cancel = QPushButton(tr("dialog.cancel"))
        self.btn_cancel.setObjectName("secondaryButton")
        self.btn_cancel.setMinimumWidth(80)
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)

    @staticmethod
    def _set_required_style(widget: QLineEdit):
        """为必填项输入框设置红框样式"""
        widget.setStyleSheet(EmployeeDialog.REQUIRED_STYLE)

    def _on_ok(self):
        emp_no = self.emp_no_input.text().strip()
        name = self.name_input.text().strip()

        if not emp_no:
            toast_warning(self, tr("user_manage.emp_dialog_emp_no_empty"))
            self.emp_no_input.setFocus()
            return
        if not name:
            toast_warning(self, tr("user_manage.emp_dialog_name_empty"))
            self.name_input.setFocus()
            return

        # 检查工号唯一性
        if self._existing_employees:
            self_id = self._data.get("id", "") if self._data else ""
            for emp in self._existing_employees:
                if emp.get("employee_no", "") == emp_no and emp.get("id", "") != self_id:
                    toast_warning(self, tr("user_manage.emp_dialog_emp_no_duplicate"))
                    self.emp_no_input.setFocus()
                    return

        self.accept()

    def get_data(self) -> dict:
        return {
            "employee_no": self.emp_no_input.text().strip(),
            "name": self.name_input.text().strip(),
            "dept": self.dept_input.text().strip(),
            "phone": self.phone_input.text().strip(),
            "fingerprint_id": self.fingerprint_input.text().strip(),
            "card_no": self.card_input.text().strip(),
            "is_active": 1 if self.status_input.currentIndex() == 0 else 0,
        }


class UserManageView(QWidget):
    # 用户管理信号
    add_user = Signal(object)
    update_user = Signal(str, dict)
    delete_user = Signal(str)
    toggle_user_status = Signal(str, bool)
    refresh_requested = Signal()
    # 员工档案信号
    employee_add_requested = Signal(object)
    employee_edit_requested = Signal(str, object)
    employee_delete_requested = Signal(str)
    employee_data_requested = Signal()
    # 员工硬件扫描信号
    fingerprint_scan_result = Signal(str)
    nfc_scan_result = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list = []
        self._current_user: dict = {}
        self._employee_data: list = []
        self._current_edit_dialog = None
        self._active_scan_threads = []
        self._init_ui()
        self._apply_scan_button_states()

    def _build_user_columns(self):
        """用户表列定义"""
        return [
            (tr("user.col_username"), "username", 200),
            (tr("user.col_role"), "role", 80),
            (tr("user.col_status"), "is_active", 80),
            (tr("user.col_created_at"), "created_at", 180),
        ]

    def _build_employee_columns(self):
        """员工表列定义"""
        return [
            (tr("user_manage.emp_col_emp_no"), "employee_no", 100),
            (tr("user_manage.emp_col_name"), "name", 100),
            (tr("user_manage.emp_col_dept"), "dept", 120),
            (tr("user_manage.emp_col_phone"), "phone", 130),
            (tr("user_manage.emp_col_fingerprint"), "fingerprint_id", 120),
            (tr("user_manage.emp_col_card"), "card_no", 120),
            (tr("user_manage.emp_col_status"), "is_active", 70),
            (tr("user_manage.emp_col_action"), "action", 70),
        ]

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 选项卡
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # 选项卡 1：用户管理
        self.user_widget = QWidget()
        self.tab_widget.addTab(self.user_widget, tr("user_manage.tab_users"))
        self._init_user_tab()

        # 选项卡 2：员工档案
        self.emp_widget = QWidget()
        self.tab_widget.addTab(self.emp_widget, tr("user_manage.tab_employees"))
        self._init_employee_tab()

    # ---------- 用户管理选项卡 ----------

    def _init_user_tab(self):
        user_layout = QVBoxLayout(self.user_widget)
        user_layout.setContentsMargins(0, 12, 0, 0)
        user_layout.setSpacing(12)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.btn_add = QPushButton(tr("user.btn_add"))
        self.btn_delete = QPushButton(tr("user.btn_delete"))
        self.btn_delete.setObjectName("dangerButton")
        self.btn_toggle_status = QPushButton(tr("user.btn_toggle_status"))
        self.btn_reset_pwd = QPushButton(tr("user.btn_reset_pwd"))
        self.btn_change_pwd = QPushButton(tr("user.btn_change_pwd"))
        self.btn_refresh = QPushButton(tr("user.btn_refresh"))

        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_delete)
        toolbar.addWidget(self.btn_toggle_status)
        toolbar.addWidget(self.btn_reset_pwd)
        toolbar.addWidget(self.btn_change_pwd)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addStretch()

        # 当前用户显示
        self.user_info_label = QLabel(tr("user.current_user_default"))
        self.user_info_label.setStyleSheet("color: #5a6573; font-size: 12px;")
        toolbar.addWidget(self.user_info_label)

        user_layout.addLayout(toolbar)

        # 用户表格
        self.user_table = QTableWidget()
        columns = self._build_user_columns()
        self.user_table.setColumnCount(len(columns))
        self.user_table.setHorizontalHeaderLabels([c[0] for c in columns])
        self.user_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.user_table.setFocusPolicy(Qt.NoFocus)
        self.user_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.user_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.user_table.setAlternatingRowColors(True)
        self.user_table.verticalHeader().setVisible(False)
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.user_table.horizontalHeader().setStretchLastSection(True)
        user_layout.addWidget(self.user_table)

        # 信号连接
        self.btn_add.clicked.connect(self._on_add_user)
        self.btn_delete.clicked.connect(self._on_delete_user)
        self.btn_toggle_status.clicked.connect(self._on_toggle_status)
        self.btn_reset_pwd.clicked.connect(self._on_reset_password)
        self.btn_change_pwd.clicked.connect(self._on_change_password)
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)

    # ---------- 员工档案选项卡 ----------

    def _init_employee_tab(self):
        emp_layout = QVBoxLayout(self.emp_widget)
        emp_layout.setContentsMargins(0, 12, 0, 0)
        emp_layout.setSpacing(12)

        # 员工工具栏
        emp_toolbar = QHBoxLayout()
        emp_toolbar.setSpacing(10)

        self.employee_add_btn = QPushButton(tr("user_manage.emp_btn_add"))
        self.employee_edit_btn = QPushButton(tr("user_manage.emp_btn_edit"))
        self.employee_delete_btn = QPushButton(tr("user_manage.emp_btn_delete"))
        self.employee_delete_btn.setObjectName("dangerButton")
        self.employee_refresh_btn = QPushButton(tr("user_manage.emp_btn_refresh"))

        emp_toolbar.addWidget(self.employee_add_btn)
        emp_toolbar.addWidget(self.employee_edit_btn)
        emp_toolbar.addWidget(self.employee_delete_btn)
        emp_toolbar.addWidget(self.employee_refresh_btn)
        emp_toolbar.addStretch()

        self.employee_export_btn = QPushButton(tr("user_manage.emp_btn_export"))
        self.employee_export_btn.setMinimumHeight(32)
        self.employee_export_btn.clicked.connect(self._on_export_employees)
        self.employee_import_btn = QPushButton(tr("user_manage.emp_btn_import"))
        self.employee_import_btn.setMinimumHeight(32)
        self.employee_import_btn.clicked.connect(self._on_import_employees)
        emp_toolbar.addWidget(self.employee_export_btn)
        emp_toolbar.addWidget(self.employee_import_btn)

        # 硬件扫描按钮（指纹/NFC → 填入员工编辑弹窗）
        self.btn_scan_fingerprint = QPushButton(tr("user_manage.emp_btn_scan_fingerprint"))
        self.btn_scan_fingerprint.setMinimumHeight(32)
        self.btn_scan_fingerprint.setStyleSheet(HW_BTN_STYLE_ENABLED)
        self.btn_scan_fingerprint.clicked.connect(self._on_fingerprint_scan)

        self.btn_scan_nfc = QPushButton(tr("user_manage.emp_btn_scan_nfc"))
        self.btn_scan_nfc.setMinimumHeight(32)
        self.btn_scan_nfc.setStyleSheet(HW_BTN_STYLE_ENABLED)
        self.btn_scan_nfc.clicked.connect(self._on_nfc_scan)

        emp_toolbar.addWidget(self.btn_scan_fingerprint)
        emp_toolbar.addWidget(self.btn_scan_nfc)
        emp_toolbar.addStretch()

        emp_layout.addLayout(emp_toolbar)

        # 员工表格
        self.employee_table = QTableWidget()
        emp_columns = self._build_employee_columns()
        self.employee_table.setColumnCount(len(emp_columns))
        self.employee_table.setHorizontalHeaderLabels([c[0] for c in emp_columns])
        self.employee_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.employee_table.setFocusPolicy(Qt.NoFocus)
        self.employee_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.employee_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.employee_table.setAlternatingRowColors(True)
        self.employee_table.verticalHeader().setVisible(False)
        self.employee_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.employee_table.horizontalHeader().setStretchLastSection(True)
        emp_layout.addWidget(self.employee_table)

        # 信号连接
        self.employee_add_btn.clicked.connect(self._on_add_employee)
        self.employee_edit_btn.clicked.connect(self._on_edit_employee)
        self.employee_delete_btn.clicked.connect(self._on_delete_employee)
        self.employee_refresh_btn.clicked.connect(self.employee_data_requested.emit)

    # ---------- 数据设置 ----------

    def set_current_user(self, user: dict):
        """设置当前登录用户信息"""
        self._current_user = user or {}
        username = self._current_user.get("username", "—")
        role = self._current_user.get("role", "—")
        role_text = tr("nav.role_admin") if role == "admin" else tr("nav.role_user")
        text = tr("user.current_user", name=username, role=role_text)
        self.user_info_label.setText(text)

    def set_data(self, data: list):
        """设置用户数据"""
        self._data = data
        self._refresh_user_table()

    def set_employee_data(self, data: list):
        """设置员工数据"""
        self._employee_data = data
        self._refresh_employee_table()

    # ---------- 用户表格刷新 ----------

    def _refresh_user_table(self):
        """刷新用户表格"""
        self.user_table.setRowCount(len(self._data))
        columns = self._build_user_columns()
        for row, user in enumerate(self._data):
            for col, (_, key, _) in enumerate(columns):
                value = user.get(key, "")
                if key == "is_active":
                    is_active = bool(value)
                    value = tr("user.status_enabled") if is_active else tr("user.status_disabled")
                item = QTableWidgetItem(str(value))
                if key == "is_active":
                    item.setForeground(Qt.green if user.get("is_active") else Qt.red)
                item.setTextAlignment(
                    Qt.AlignCenter if key in ("role", "is_active")
                    else Qt.AlignLeft | Qt.AlignVCenter
                )
                self.user_table.setItem(row, col, item)

    # ---------- 员工表格刷新 ----------

    def _refresh_employee_table(self):
        """刷新员工表格"""
        self.employee_table.setRowCount(len(self._employee_data))
        columns = self._build_employee_columns()
        for row, emp in enumerate(self._employee_data):
            for col, (_, key, _) in enumerate(columns):
                if key == "action":
                    item = QTableWidgetItem("—")
                elif key == "is_active":
                    value = emp.get(key, "")
                    is_active = bool(value)
                    item = QTableWidgetItem(
                        tr("user.status_enabled") if is_active
                        else tr("user.status_disabled")
                    )
                    item.setForeground(Qt.green if emp.get("is_active") else Qt.red)
                else:
                    item = QTableWidgetItem(str(emp.get(key, "")))
                if key == "is_active":
                    item.setTextAlignment(Qt.AlignCenter)
                elif key == "action":
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.employee_table.setItem(row, col, item)

    # ---------- 界面重译 ----------

    def retranslate_ui(self):
        """重新应用当前语言的文本"""
        # 选项卡标题
        self.tab_widget.setTabText(0, tr("user_manage.tab_users"))
        self.tab_widget.setTabText(1, tr("user_manage.tab_employees"))

        # 用户管理按钮
        self.btn_add.setText(tr("user.btn_add"))
        self.btn_delete.setText(tr("user.btn_delete"))
        self.btn_toggle_status.setText(tr("user.btn_toggle_status"))
        self.btn_reset_pwd.setText(tr("user.btn_reset_pwd"))
        self.btn_change_pwd.setText(tr("user.btn_change_pwd"))
        self.btn_refresh.setText(tr("user.btn_refresh"))

        # 用户表格表头
        user_columns = self._build_user_columns()
        self.user_table.setHorizontalHeaderLabels([c[0] for c in user_columns])
        self._refresh_user_table()

        if self._current_user:
            self.set_current_user(self._current_user)
        else:
            self.user_info_label.setText(tr("user.current_user_default"))

        # 员工管理按钮
        self.employee_add_btn.setText(tr("user_manage.emp_btn_add"))
        self.employee_edit_btn.setText(tr("user_manage.emp_btn_edit"))
        self.employee_delete_btn.setText(tr("user_manage.emp_btn_delete"))
        self.employee_refresh_btn.setText(tr("user_manage.emp_btn_refresh"))
        self.employee_export_btn.setText(tr("user_manage.emp_btn_export"))
        self.employee_import_btn.setText(tr("user_manage.emp_btn_import"))

        # 员工表格表头
        emp_columns = self._build_employee_columns()
        self.employee_table.setHorizontalHeaderLabels([c[0] for c in emp_columns])
        self._refresh_employee_table()

    # ---------- 用户操作 ----------

    def get_selected_user(self) -> dict:
        """获取当前选中的用户"""
        selected = self.user_table.selectedItems()
        if not selected:
            return {}
        row = selected[0].row()
        if 0 <= row < len(self._data):
            return self._data[row]
        return {}

    def _on_add_user(self):
        dialog = UserDialog(self)
        try:
            if dialog.exec() == QDialog.Accepted:
                data = dialog.get_data()
                self.add_user.emit(data)
        finally:
            dialog.deleteLater()

    def _on_delete_user(self):
        user = self.get_selected_user()
        if not user:
            toast_warning(self, tr("user.select_delete"))
            return

        user_id = user.get("id", "")
        username = user.get("username", "")

        current_username = self._current_user.get("username", "")
        if username == current_username:
            toast_error(self, tr("toast.cannot_delete_self"))
            return

        if username == "admin" and user_id == DEFAULT_ADMIN_ID:
            if not show_confirm(
                self, tr("dialog.warning"),
                tr("user.confirm_delete_default_admin"), "error"
            ):
                return
        else:
            if not show_confirm(
                self, tr("user.confirm_delete_title"),
                tr("user.confirm_delete_text", name=username), "warning"
            ):
                return

        self.delete_user.emit(user_id)

    def _on_toggle_status(self):
        user = self.get_selected_user()
        if not user:
            toast_warning(self, tr("user.select_toggle"))
            return

        user_id = user.get("id", "")
        username = user.get("username", "")
        current_active = bool(user.get("is_active", 1))

        current_username = self._current_user.get("username", "")
        if username == current_username:
            toast_error(self, tr("toast.cannot_disable_self"))
            return

        new_status = not current_active
        action = tr("user.status_enabled") if new_status else tr("user.status_disabled")

        if not show_confirm(
            self, tr("user.confirm_toggle_title"),
            tr("user.confirm_toggle_text", action=action, name=username),
            dialog_type="warning" if not new_status else "info"
        ):
            return

        self.toggle_user_status.emit(user_id, new_status)

    def _on_reset_password(self):
        user = self.get_selected_user()
        if not user:
            toast_warning(self, tr("user.select_reset"))
            return

        username = user.get("username", "")
        user_id = user.get("id", "")

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("user.reset_pwd_title"))
        dialog.setMinimumWidth(300)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        info = QLabel(tr("user.reset_pwd_info", name=username))
        info.setStyleSheet("font-size: 13px;")
        layout.addWidget(info)

        pwd_input = QLineEdit()
        pwd_input.setEchoMode(QLineEdit.Password)
        pwd_input.setPlaceholderText(tr("user.reset_pwd_placeholder"))
        pwd_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus { border: 2px solid #2563eb; }
        """)
        layout.addWidget(pwd_input)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton(tr("common.ok"))
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #2563eb; color: white; font-weight: bold;
                border: none; border-radius: 6px; padding: 8px 20px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        btn_cancel = QPushButton(tr("dialog.cancel"))
        btn_cancel.setObjectName("secondaryButton")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6; color: #4b5563;
                border: 1px solid #d1d5db; border-radius: 6px;
                padding: 8px 16px;
            }
        """)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

        btn_ok.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.Accepted:
            new_pwd = pwd_input.text().strip()
            if not new_pwd:
                toast_warning(self, tr("toast.password_empty"))
                return
            from utils.helpers import hash_password
            self.update_user.emit(user_id, {"password": hash_password(new_pwd)})
            toast_success(self, tr("toast.pwd_reset", name=username))
        dialog.deleteLater()

    def _on_change_password(self):
        dialog = PasswordDialog(self, tr("user.pwd_dialog_title"))
        try:
            if dialog.exec() == QDialog.Accepted:
                old_pwd, new_pwd = dialog.get_passwords()
                user_id = self._current_user.get("id", "")
                from utils.helpers import verify_password
                current_pwd = self._current_user.get("password", "")
                matched, _ = verify_password(old_pwd, current_pwd)
                if not matched:
                    toast_error(self, tr("toast.old_pwd_incorrect"))
                    return
                from utils.helpers import hash_password
                self.update_user.emit(user_id, {"password": hash_password(new_pwd)})
                self._current_user["password"] = hash_password(new_pwd)
                toast_success(self, tr("toast.pwd_changed_next_login"))
        finally:
            dialog.deleteLater()

    # ---------- 员工操作 ----------

    def get_selected_employee(self) -> dict:
        """获取当前选中的员工"""
        selected = self.employee_table.selectedItems()
        if not selected:
            return {}
        row = selected[0].row()
        if 0 <= row < len(self._employee_data):
            return self._employee_data[row]
        return {}

    def get_selected_employees(self) -> list:
        """获取当前选中的员工列表（多选）"""
        rows = self.employee_table.selectionModel().selectedRows()
        selected = []
        seen = set()
        for idx in rows:
            row = idx.row()
            if 0 <= row < len(self._employee_data) and row not in seen:
                seen.add(row)
                selected.append(self._employee_data[row])
        return selected

    def _on_add_employee(self):
        """新增员工"""
        dialog = EmployeeDialog(self, existing_employees=self._employee_data)
        self._current_edit_dialog = dialog
        try:
            if dialog.exec() == QDialog.Accepted:
                data = dialog.get_data()
                self.employee_add_requested.emit(data)
        finally:
            self._current_edit_dialog = None
            dialog.deleteLater()

    def _on_edit_employee(self):
        """编辑员工"""
        emp = self.get_selected_employee()
        if not emp:
            toast_warning(self, tr("user_manage.emp_select_row"))
            return
        dialog = EmployeeDialog(self, emp_data=emp, existing_employees=self._employee_data)
        self._current_edit_dialog = dialog
        try:
            if dialog.exec() == QDialog.Accepted:
                data = dialog.get_data()
                self.employee_edit_requested.emit(emp.get("id", ""), data)
        finally:
            self._current_edit_dialog = None
            dialog.deleteLater()

    def _on_delete_employee(self):
        """删除员工（支持多选）"""
        employees = self.get_selected_employees()
        if not employees:
            toast_warning(self, tr("user_manage.emp_select_row"))
            return

        if len(employees) == 1:
            emp = employees[0]
            emp_no = emp.get("employee_no", "")
            name = emp.get("name", "")
            if not show_confirm(
                self, tr("user_manage.emp_confirm_delete_title"),
                tr("user_manage.emp_confirm_delete_text", name=name, emp_no=emp_no),
                dialog_type="warning"
            ):
                return
            self.employee_delete_requested.emit(emp.get("id", ""))
        else:
            count = len(employees)
            if not show_confirm(
                self, tr("user_manage.emp_confirm_batch_delete_title"),
                tr("user_manage.emp_confirm_batch_delete_text", count=count),
                dialog_type="warning"
            ):
                return
            for emp in employees:
                self.employee_delete_requested.emit(emp.get("id", ""))
            toast_success(self, tr("user_manage.emp_batch_deleted", count=count))

    def showEvent(self, event):
        """每次视图显示时重新应用扫描按钮状态"""
        super().showEvent(event)
        self._apply_scan_button_states()

    # ---------- 员工档案 Excel 导入/导出 ----------

    def _on_export_employees(self):
        """导出员工档案为 Excel"""
        if not self._employee_data:
            toast_warning(self, tr("user_manage.emp_no_data_to_export"))
            return
        try:
            from utils.excel_exporter import ExcelExporter
            exporter = ExcelExporter()
            fp = exporter.export_employees(self._employee_data)
            toast_success(self, tr("user_manage.emp_export_success", path=fp))
        except Exception as e:
            toast_error(self, str(e))

    def _on_import_employees(self):
        """从 Excel 导入员工档案"""
        from PySide6.QtWidgets import QFileDialog
        fp, _ = QFileDialog.getOpenFileName(
            self,
            tr("user_manage.emp_import_title"),
            "",
            tr("user_manage.emp_import_filter"),
        )
        if not fp:
            return
        try:
            import openpyxl
            wb = openpyxl.load_workbook(fp, read_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            wb.close()
        except Exception as e:
            toast_error(self, str(e))
            return

        if len(rows) < 2:
            toast_warning(self, tr("user_manage.emp_import_empty"))
            return

        # 支持中英双语表头（直接复用导出的 Excel 作为模版）
        HEADER_ALIAS = {
            "工号": "employee_no", "姓名": "name",
            "部门": "dept", "联系电话": "phone",
            "指纹id": "fingerprint_id",
            "nfc卡号": "card_no",
            "状态": "is_active",
            "创建时间": "created_at", "更新时间": "updated_at",
        }
        header = [str(h or "").strip().lower() for h in rows[0]]
        header = [HEADER_ALIAS.get(h, h) for h in header]
        required = ("employee_no", "name")
        missing = [r for r in required if r not in header]
        if missing:
            toast_error(self, tr("user_manage.emp_import_fail_header", fields=", ".join(missing)))
            return

        idx = {name: i for i, name in enumerate(header)}
        fields = [
            "employee_no", "name", "dept", "phone",
            "fingerprint_id", "card_no",
        ]

        try:
            from local_db import LocalDB
            db = LocalDB()
            existing = db.query(TABLE_EMPLOYEE_RECORDS)
            existing_emp_nos = {
                str(e.get("employee_no", "")) for e in existing
            }
        except Exception:
            existing_emp_nos = set()

        success = 0
        skipped = 0
        for row in rows[1:]:
            if not any(v is not None for v in row):
                continue
            rec = {}
            for f in fields:
                if f in idx and idx[f] < len(row):
                    rec[f] = str(row[idx[f]] or "").strip()
                else:
                    rec[f] = ""
            emp_no = rec.get("employee_no", "")
            name = rec.get("name", "")
            if not emp_no or not name:
                continue
            if emp_no in existing_emp_nos:
                skipped += 1
                continue
            rec.setdefault("is_active", 1)
            import uuid
            rec["id"] = str(uuid.uuid4())
            import datetime
            now = datetime.datetime.now().isoformat()
            rec["created_at"] = now
            rec["updated_at"] = now
            try:
                db.insert(TABLE_EMPLOYEE_RECORDS, rec)
                # 加入同步队列，确保 Excel 导入的数据也会上传 MySQL
                db.add_sync_queue(TABLE_EMPLOYEE_RECORDS, "INSERT", rec["id"], rec)
                existing_emp_nos.add(emp_no)
                success += 1
            except Exception:
                skipped += 1

        if success > 0:
            self.employee_data_requested.emit()
            toast_success(
                self,
                tr(
                    "user_manage.emp_import_success",
                    count=success,
                    skipped=skipped,
                ),
            )
        else:
            toast_warning(self, tr("user_manage.emp_import_all_skipped"))

    # ---------- 硬件扫描 ----------

    def _apply_scan_button_states(self):
        """根据 config_items 启用状态设置硬件按钮外观"""
        try:
            from local_db import LocalDB
            db = LocalDB()
            fp_rows = db.query(TABLE_CONFIG_ITEMS, conditions="config_name = ?", params=("FINGERPRINT_ENABLED",))
            nfc_rows = db.query(TABLE_CONFIG_ITEMS, conditions="config_name = ?", params=("NFC_ENABLED",))
            fp_enabled = any(row.get("content") == "1" for row in fp_rows)
            nfc_enabled = any(row.get("content") == "1" for row in nfc_rows)
            if fp_enabled:
                self.btn_scan_fingerprint.setStyleSheet(HW_BTN_STYLE_ENABLED)
            else:
                self.btn_scan_fingerprint.setStyleSheet(HW_BTN_STYLE_DISABLED)
            if nfc_enabled:
                self.btn_scan_nfc.setStyleSheet(HW_BTN_STYLE_ENABLED)
            else:
                self.btn_scan_nfc.setStyleSheet(HW_BTN_STYLE_DISABLED)
        except Exception:
            pass

    def _on_fingerprint_scan(self):
        try:
            from hardware.base import ReaderType, get_reader
        except ImportError:
            toast_warning(self, "硬件模块未找到")
            return
        reader = get_reader(ReaderType.FINGERPRINT)
        if not reader.is_enabled:
            toast_warning(self, "指纹设备未启用，请在系统配置中开启")
            return
        if not reader.device:
            toast_warning(self, "指纹设备串口未配置，请先在系统配置中设置")
            return

        thread = _EmployeeScanThread(reader, 10.0)
        self._active_scan_threads.append(thread)
        thread.result_ready.connect(self._handle_fingerprint_result)
        thread.finished.connect(
            lambda: self._active_scan_threads.remove(thread) if thread in self._active_scan_threads else None
        )
        thread.start()
        ok = show_wait_dialog(self, tr("user_manage.emp_scan_fingerprint"), tr("user_manage.emp_scan_fingerprint_hint"), timeout=10)
        if not ok:
            return

    def _handle_fingerprint_result(self, scan_id: str):
        if not scan_id:
            toast_warning(self, tr("user_manage.emp_scan_timeout"))
            return
        self.fill_scanned_value(scan_id, "fingerprint_id")
        self._close_wait_dialog()

    def _on_nfc_scan(self):
        try:
            from hardware.base import ReaderType, get_reader
        except ImportError:
            toast_warning(self, "硬件模块未找到")
            return
        reader = get_reader(ReaderType.NFC)
        if not reader.is_enabled:
            toast_warning(self, "NFC设备未启用，请在系统配置中开启")
            return
        if not reader.device:
            toast_warning(self, "NFC设备串口未配置，请先在系统配置中设置")
            return

        thread = _EmployeeScanThread(reader, 10.0)
        self._active_scan_threads.append(thread)
        thread.result_ready.connect(self._handle_nfc_result)
        thread.finished.connect(
            lambda: self._active_scan_threads.remove(thread) if thread in self._active_scan_threads else None
        )
        thread.start()
        ok = show_wait_dialog(self, tr("user_manage.emp_scan_nfc"), tr("user_manage.emp_scan_nfc_hint"), timeout=10)
        if not ok:
            return

    def _handle_nfc_result(self, scan_id: str):
        if not scan_id:
            toast_warning(self, tr("user_manage.emp_scan_timeout"))
            return
        self.fill_scanned_value(scan_id, "card_no")
        self._close_wait_dialog()

    def _close_wait_dialog(self):
        """关闭当前活动的等待对话框"""
        from utils.dialogs import WaitDialog
        dlg = WaitDialog._active_dialog
        if dlg is not None:
            WaitDialog._active_dialog = None
            if hasattr(dlg, "_timer") and dlg._timer and dlg._timer.isActive():
                dlg._timer.stop()
            dlg._cancelled = False
            dlg.reject()

    def fill_scanned_value(self, scan_id: str, field: str):
        """将扫描结果填入当前员工编辑弹窗的指定字段"""
        dialog = self._current_edit_dialog
        if dialog is None:
            toast_warning(self, "请先打开员工编辑弹窗")
            return
        if not hasattr(dialog, field + "_input"):
            toast_warning(self, f"当前弹窗无 {field} 字段")
            return
        getattr(dialog, field + "_input").setText(scan_id)
        toast_success(self, tr("user_manage.emp_scan_filled", scan_id=scan_id))

    def clear_memory(self):
        """清理内存（统一生命周期管理）"""
        self._data = []
        self._employee_data = []
        try:
            self.user_table.clearContents()
            self.user_table.setRowCount(0)
            self.employee_table.clearContents()
            self.employee_table.setRowCount(0)
        except RuntimeError:
            pass

    def hideEvent(self, event):
        """视图隐藏时清理资源（统一生命周期管理）"""
        super().hideEvent(event)
        self.clear_memory()
