"""物料登记视图

v4.1 性能优化：
- 领用记录表格增加分页，避免全量渲染
- 模糊匹配结果限制50条
- 人员字段模糊匹配增加防抖
- 下方展示区大表格分页渲染
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QFormLayout, QSpinBox,
    QSplitter, QFrame, QStyledItemDelegate, QStyle,
    QMenu, QAbstractItemView, QHeaderView, QDateEdit, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt, QTimer, QThread
from PySide6.QtGui import QRegularExpressionValidator, QIntValidator, QAction
from widgets.toast import toast_success, toast_warning
from utils.dialogs import show_return_confirm, show_wait_dialog
from datetime import datetime
from i18n import tr
from config import TABLE_CONFIG_ITEMS, TABLE_EMPLOYEE_RECORDS

# 列索引常量（避免硬编码魔数）
_COL_FUZZY_CODE = 0
_COL_FUZZY_NAME = 1
_COL_FUZZY_QTY = 2

_COL_FUZZY_REC_CARD = 0
_COL_FUZZY_REC_DEPT = 1
_COL_FUZZY_REC_USER = 2
_COL_FUZZY_REC_PHONE = 3

_COL_PENDING_CODE = 0
_COL_PENDING_NAME = 1
_COL_PENDING_QTY = 2

_COL_RECORD_CODE = 0
_COL_RECORD_NAME = 1
_COL_RECORD_QTY = 2
_COL_RECORD_CARD = 3
_COL_RECORD_DEPT = 4
_COL_RECORD_USER = 5
_COL_RECORD_PHONE = 6
_COL_RECORD_ACTION = 7
_COL_RECORD_TIME = 8
_COL_RECORD_OPERATOR = 9

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


class _HardwareReadThread(QThread):
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


class _ReadOnlyDelegate(QStyledItemDelegate):
    """只读委托：禁止创建编辑器，实现列级只读"""
    def createEditor(self, parent, option, index):
        return None

class _QtyDelegate(QStyledItemDelegate):
    """数量列专用委托：双击直接编辑，只能输入正整数，无缝融入单元格"""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setValidator(QIntValidator(1, 99999999))
        editor.setAlignment(Qt.AlignCenter)
        editor.setFrame(False)
        editor.setContentsMargins(0, 0, 0, 0)
        is_selected = bool(option.state & QStyle.State_Selected)
        bg = "#e0e7ff" if is_selected else "#ffffff"
        editor.setStyleSheet(f"""
            QLineEdit {{
                border: none;
                background-color: {bg};
                color: #1a1a2e;
                padding: 0px;
                margin: 0px;
                selection-background-color: #F20188;
                selection-color: #ffffff;
            }}
            QLineEdit:focus {{
                outline: none;
                border: none;
            }}
        """)
        return editor

    def setEditorData(self, editor, index):
        value = index.data(Qt.DisplayRole)
        editor.setText(str(value) if value is not None else "1")
        editor.selectAll()

    def setModelData(self, editor, model, index):
        text = editor.text().strip()
        if text and text.isdigit():
            model.setData(index, int(text), Qt.DisplayRole)
            model.setData(index, int(text), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

class _ReturnInfoLabel(QLabel):
    """归还信息标签：支持右键切换待补单/已补单状态，HTML格式彩色标签"""

    def __init__(self, text: str, record_id: str, damage_status: str = "",
                 register_view=None, parent=None):
        super().__init__(parent)
        self.record_id = record_id
        self._damage_status = damage_status
        self._register_view = register_view
        self.setText(text or "")  # 设置文本
        self.setTextFormat(Qt.RichText)  # 启用HTML渲染
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setWordWrap(False)  # 单行显示，不自动换行
        self.setStyleSheet("font-size: 9px; font-weight: bold; padding: 1px;")
        if damage_status in (tr("register.status_pending"), tr("register.status_completed")):
            self.setCursor(Qt.PointingHandCursor)
            self._update_tooltip()
        else:
            self.setToolTip("")

    def _update_tooltip(self):
        """根据当前状态更新悬停提示"""
        label = tr("register.status_completed") if self._damage_status == tr("register.status_pending") else tr("register.status_pending")
        self.setToolTip(tr("register.context_switch_tooltip", status=label))

    def contextMenuEvent(self, event):
        """右键菜单切换待补单/已补单"""
        if self._damage_status not in (tr("register.status_pending"), tr("register.status_completed")) or not self._register_view:
            return
        menu = QMenu(self)
        new_status = tr("register.status_completed") if self._damage_status != tr("register.status_completed") else tr("register.status_pending")
        action = QAction(tr("register.context_switch_to", status=new_status), self)
        action.triggered.connect(
            lambda: self._register_view._on_damage_label_right_clicked(
                self.record_id, new_status))
        menu.addAction(action)
        menu.exec(event.globalPos())

class RegisterView(QWidget):
    borrow_submitted = Signal(object)
    return_submitted = Signal(object)
    damage_status_update = Signal(str, str)
    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._materials = []
        self._records = []
        self._pending_items = []
        self._result_mode = "record"

        # 分页状态
        self._page = 1
        self._page_size = 50
        self._total = 0

        # 硬件读取线程集合（防止被 GC 回收）
        self._active_read_threads = []

        # 防抖定时器（人员字段模糊匹配）
        self._fuzzy_timer = QTimer(self)
        self._fuzzy_timer.setSingleShot(True)
        self._fuzzy_timer.timeout.connect(self._do_fuzzy_search)
        self._fuzzy_keyword = ""
        self._fuzzy_field = ""

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ========== 上部分 — 输入栏 + 待录入区 + 登记表单 ==========
        top_frame = QFrame()
        top_layout = QVBoxLayout(top_frame)
        top_layout.setContentsMargins(12, 12, 12, 12)
        top_layout.setSpacing(10)

        # 输入栏：编码 + 名称 + 数量 + 添加 + 删除（无ID）
        input_bar = QHBoxLayout()
        input_bar.setSpacing(8)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText(tr("register.code_placeholder"))
        self.code_input.setMaximumWidth(160)
        self.code_input.returnPressed.connect(lambda: self._on_code_changed(self.code_input.text()))
        self.code_input.editingFinished.connect(lambda: self._on_code_changed(self.code_input.text()))
        self.code_input.textChanged.connect(self._on_code_changed)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(tr("register.name_placeholder"))
        self.name_input.setMaximumWidth(160)
        self.name_input.returnPressed.connect(lambda: self._on_name_changed(self.name_input.text()))
        self.name_input.editingFinished.connect(lambda: self._on_name_changed(self.name_input.text()))
        self.name_input.textChanged.connect(self._on_name_changed)

        self.qty_input = QSpinBox()
        self.qty_input.setRange(1, 9999)
        self.qty_input.setValue(1)
        self.qty_input.setMaximumWidth(80)

        self.btn_add = QPushButton(tr("register.btn_add"))
        self.btn_add.clicked.connect(self._on_add_item)
        self.btn_del = QPushButton(tr("register.btn_delete"))
        self.btn_del.setObjectName("dangerButton")
        self.btn_del.clicked.connect(self._on_del_item)
        self.code_label = QLabel(tr("register.code_label"))
        self.name_label = QLabel(tr("register.name_label"))
        self.qty_label = QLabel(tr("register.qty_label"))
        input_bar.addWidget(self.code_label)
        input_bar.addWidget(self.code_input)
        input_bar.addWidget(self.name_label)
        input_bar.addWidget(self.name_input)
        input_bar.addWidget(self.qty_label)
        input_bar.addWidget(self.qty_input)
        input_bar.addWidget(self.btn_add)
        input_bar.addWidget(self.btn_del)
        input_bar.addStretch()
        top_layout.addLayout(input_bar)

        # 中间：待录入表格（左）+ 登记表单（右）
        mid_splitter = QSplitter(Qt.Horizontal)

        # 左侧：待录入区
        pending_widget = QWidget()
        pending_layout = QVBoxLayout(pending_widget)
        pending_layout.setContentsMargins(0, 0, 0, 0)

        self.pending_table = QTableWidget()
        self.pending_table.setColumnCount(3)
        self.pending_table.setHorizontalHeaderLabels([
            tr("register.pending_col_code"),
            tr("register.pending_col_name"),
            tr("register.pending_col_qty"),
        ])
        self.pending_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.pending_table.setSelectionMode(QTableWidget.SingleSelection)
        self.pending_table.setEditTriggers(QTableWidget.DoubleClicked)
        self.pending_table.setAlternatingRowColors(True)
        self.pending_table.verticalHeader().setVisible(False)
        self.pending_table.setFocusPolicy(Qt.NoFocus)
        self.pending_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.pending_table.horizontalHeader().setStretchLastSection(True)
        self.pending_table.setColumnWidth(0, 140)
        self.pending_table.setColumnWidth(1, 200)
        self.pending_table.setColumnWidth(2, 80)
        self.pending_table.horizontalHeader().sectionResized.connect(self._on_pending_col_resized)
        self._restore_table_widths(self.pending_table, "register_pending", 3)
        readonly_delegate = _ReadOnlyDelegate(self.pending_table)
        for col in [0, 1]:
            self.pending_table.setItemDelegateForColumn(col, readonly_delegate)
        qty_delegate = _QtyDelegate(self.pending_table)
        self.pending_table.setItemDelegateForColumn(2, qty_delegate)
        self.pending_table.itemChanged.connect(self._on_pending_item_changed)
        pending_layout.addWidget(self.pending_table)
        mid_splitter.addWidget(pending_widget)

        # 右侧：登记表单
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(8, 0, 0, 0)

        self._form = QFormLayout()
        self._form.setSpacing(8)
        self.card_input = QLineEdit()
        self.card_input.setPlaceholderText(tr("register.card_placeholder"))
        self.card_input.setStyleSheet("border: 2px solid #dc2626;")
        self.card_input.setValidator(QIntValidator(1, 99999999))

        self.dept_input = QLineEdit()
        self.dept_input.setPlaceholderText(tr("register.dept_placeholder"))
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText(tr("register.user_placeholder"))
        self.user_input.setStyleSheet("border: 2px solid #dc2626;")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText(tr("register.phone_placeholder"))
        self._form.addRow(tr("register.card_label"), self.card_input)
        self._form.addRow(tr("register.dept_label"), self.dept_input)
        self._form.addRow(tr("register.user_label"), self.user_input)
        self._form.addRow(tr("register.phone_label"), self.phone_input)
        form_layout.addLayout(self._form)

        btn_layout = QHBoxLayout()
        self.btn_input = QPushButton(tr("register.btn_input"))
        self.btn_input.setMinimumHeight(40)
        self.btn_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_layout.addWidget(self.btn_input)
        form_layout.addLayout(btn_layout)

        # 硬件扫描按钮（指纹 / NFC）—— 扫描成功后自动填充人员字段，不自动提交
        hw_btn_layout = QHBoxLayout()
        hw_btn_layout.setSpacing(12)

        self.btn_fingerprint = QPushButton(tr("register.fingerprint_btn"))
        self.btn_fingerprint.setMinimumHeight(36)
        self.btn_fingerprint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_fingerprint.setCursor(Qt.PointingHandCursor)
        self.btn_fingerprint.setStyleSheet(HW_BTN_STYLE_ENABLED)
        self.btn_fingerprint.clicked.connect(self._on_fingerprint_entry)

        self.btn_nfc = QPushButton(tr("register.nfc_btn"))
        self.btn_nfc.setMinimumHeight(36)
        self.btn_nfc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_nfc.setCursor(Qt.PointingHandCursor)
        self.btn_nfc.setStyleSheet(HW_BTN_STYLE_ENABLED)
        self.btn_nfc.clicked.connect(self._on_nfc_entry)

        hw_btn_layout.addWidget(self.btn_fingerprint)
        hw_btn_layout.addWidget(self.btn_nfc)
        form_layout.addLayout(hw_btn_layout)
        form_layout.addStretch()
        mid_splitter.addWidget(form_widget)

        mid_splitter.setSizes([450, 280])
        top_layout.addWidget(mid_splitter)
        layout.addWidget(top_frame, 2)

        # ========== 下部分 — 领用记录 / 模糊匹配 展示区 ==========
        bottom_frame = QFrame()
        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(12, 12, 12, 12)
        bottom_layout.setSpacing(8)

        # 标题栏 + 工具栏
        bottom_header = QHBoxLayout()
        self.bottom_title = QLabel(tr("register.bottom_title"))
        self.bottom_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #2563eb;")
        bottom_header.addWidget(self.bottom_title)
        bottom_header.addStretch()

        self.btn_filter_unreturned = QPushButton(tr("register.btn_filter_unreturned"))
        self.btn_show_all = QPushButton(tr("register.btn_show_all"))
        self.btn_refresh_list = QPushButton(tr("register.btn_refresh_list"))
        self.btn_export = QPushButton(tr("register.btn_export"))
        self.btn_export.clicked.connect(self._on_export)
        bottom_header.addWidget(self.btn_filter_unreturned)
        bottom_header.addWidget(self.btn_show_all)
        bottom_header.addWidget(self.btn_refresh_list)
        bottom_header.addWidget(self.btn_export)
        bottom_layout.addLayout(bottom_header)

        # 展示区大表格（只读）
        self.result_table = QTableWidget()
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.setFocusPolicy(Qt.NoFocus)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table.setSelectionMode(QTableWidget.SingleSelection)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.result_table.verticalHeader().setDefaultSectionSize(36)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.horizontalHeader().sectionResized.connect(self._on_result_col_resized)
        self.result_table.itemClicked.connect(self._on_result_clicked)
        self.result_table.itemDoubleClicked.connect(self._on_result_double_clicked)
        bottom_layout.addWidget(self.result_table)

        # 分页控件
        page_layout = QHBoxLayout()
        page_layout.setSpacing(8)

        self.page_info = QLabel(tr("common.total", count=0))
        page_layout.addWidget(self.page_info)
        page_layout.addStretch()

        self.btn_first = QPushButton(tr("register.btn_first"))
        self.btn_first.setObjectName("pageButton")
        self.btn_first.clicked.connect(lambda: self._goto_page(1))
        page_layout.addWidget(self.btn_first)

        self.btn_prev = QPushButton(tr("register.btn_prev"))
        self.btn_prev.setObjectName("pageButton")
        self.btn_prev.clicked.connect(lambda: self._goto_page(self._page - 1))
        page_layout.addWidget(self.btn_prev)

        self.page_input = QLineEdit()
        self.page_input.setMaximumWidth(60)
        self.page_input.setAlignment(Qt.AlignCenter)
        self.page_input.returnPressed.connect(self._on_page_input)
        page_layout.addWidget(self.page_input)

        self.page_total = QLabel(tr("common.page_total", total=1))
        page_layout.addWidget(self.page_total)

        self.btn_next = QPushButton(tr("register.btn_next"))
        self.btn_next.setObjectName("pageButton")
        self.btn_next.clicked.connect(lambda: self._goto_page(self._page + 1))
        page_layout.addWidget(self.btn_next)

        self.btn_last = QPushButton(tr("register.btn_last"))
        self.btn_last.setObjectName("pageButton")
        self.btn_last.clicked.connect(self._goto_last)
        page_layout.addWidget(self.btn_last)

        self.page_size_combo = QPushButton(tr("common.items_per_page", size=50))
        self.page_size_combo.setObjectName("pageButton")
        self.page_size_combo.setMenu(self._create_page_size_menu())
        page_layout.addWidget(self.page_size_combo)

        bottom_layout.addLayout(page_layout)
        layout.addWidget(bottom_frame, 3)

        # 信号连接
        self.btn_input.clicked.connect(self._on_input)
        self.btn_filter_unreturned.clicked.connect(self._on_filter_unreturned)
        self.btn_show_all.clicked.connect(self._on_show_all)
        self.btn_refresh_list.clicked.connect(self._on_refresh_list)

        # 人员字段模糊匹配（带防抖，仅展示结果不自动填充）
        self.card_input.textChanged.connect(lambda t: self._on_person_field_changed(t, "card_no"))
        self.dept_input.textChanged.connect(lambda t: self._on_person_field_changed(t, "dept"))
        self.user_input.textChanged.connect(lambda t: self._on_person_field_changed(t, "user_name"))
        # 回车/失焦触发人员模糊匹配（中文输入法兼容）
        self.card_input.returnPressed.connect(lambda: self._on_person_enter("card_no"))
        self.card_input.editingFinished.connect(lambda: self._on_person_enter("card_no"))
        self.dept_input.returnPressed.connect(lambda: self._on_person_enter("dept"))
        self.dept_input.editingFinished.connect(lambda: self._on_person_enter("dept"))
        self.user_input.returnPressed.connect(lambda: self._on_person_enter("user_name"))
        self.user_input.editingFinished.connect(lambda: self._on_person_enter("user_name"))

        # 初始化为领用记录模式
        self._switch_result_columns("record")

    # ---------- i18n retranslate ----------

    def retranslate_ui(self):
        """重新翻译所有UI字符串"""
        self.code_input.setPlaceholderText(tr("register.code_placeholder"))
        self.name_input.setPlaceholderText(tr("register.name_placeholder"))
        self.card_input.setPlaceholderText(tr("register.card_placeholder"))

        self.btn_add.setText(tr("register.btn_add"))
        self.btn_del.setText(tr("register.btn_delete"))
        self.btn_input.setText(tr("register.btn_input"))
        self.btn_fingerprint.setText(tr("register.fingerprint_btn"))
        self.btn_nfc.setText(tr("register.nfc_btn"))
        self.btn_filter_unreturned.setText(tr("register.btn_filter_unreturned"))
        self.btn_show_all.setText(tr("register.btn_show_all"))
        self.btn_refresh_list.setText(tr("register.btn_refresh_list"))
        self.btn_export.setText(tr("register.btn_export"))
        self.btn_first.setText(tr("register.btn_first"))
        self.btn_prev.setText(tr("common.prev"))
        self.btn_next.setText(tr("common.next"))
        self.btn_last.setText(tr("register.btn_last"))

        self.page_size_combo.setText(tr("common.items_per_page", size=self._page_size))
        self.page_size_combo.setMenu(self._create_page_size_menu())

        self.page_info.setText(tr("common.total", count=self._total))
        total_pages = max(1, (self._total + self._page_size - 1) // self._page_size)
        self.page_total.setText(tr("common.page_total", total=total_pages))

        self.bottom_title.setText(tr("register.bottom_title"))

        self.pending_table.setHorizontalHeaderLabels([
            tr("register.pending_col_code"),
            tr("register.pending_col_name"),
            tr("register.pending_col_qty"),
        ])
        self._restore_table_widths(self.pending_table, "register_pending", 3)

        # 更新输入栏标签
        self.code_label.setText(tr("register.code_label"))
        self.name_label.setText(tr("register.name_label"))
        self.qty_label.setText(tr("register.qty_label"))

        # 更新登记表单标签
        label = self._form.labelForField(self.card_input)
        if label is not None:
            label.setText(tr("register.card_label"))
        label = self._form.labelForField(self.dept_input)
        if label is not None:
            label.setText(tr("register.dept_label"))
        label = self._form.labelForField(self.user_input)
        if label is not None:
            label.setText(tr("register.user_label"))
        label = self._form.labelForField(self.phone_input)
        if label is not None:
            label.setText(tr("register.phone_label"))

        self._switch_result_columns(self._result_mode)

    # ---------- 列模式切换 ----------

    def _switch_result_columns(self, mode: str):
        """切换下方表格列结构：record / fuzzy / fuzzy_record"""
        self._result_mode = mode
        self.result_table.clear()
        if mode == "fuzzy":
            self.result_table.setColumnCount(3)
            self.result_table.setHorizontalHeaderLabels([
                tr("register.fuzzy_col_code"),
                tr("register.fuzzy_col_name"),
                tr("register.fuzzy_col_qty"),
            ])
            self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            self.result_table.horizontalHeader().setStretchLastSection(True)
            self._restore_table_widths(self.result_table, "register_result_fuzzy", 3)
        elif mode == "fuzzy_record":
            self.result_table.setColumnCount(4)
            self.result_table.setHorizontalHeaderLabels([
                tr("register.person_col_card"),
                tr("register.person_col_dept"),
                tr("register.person_col_user"),
                tr("register.person_col_phone"),
            ])
            self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            self.result_table.horizontalHeader().setStretchLastSection(True)
            self._restore_table_widths(self.result_table, "register_result_fuzzy_record", 4)
        else:
            # v25: 增加物料编码列，共11列（不含ID）
            self.result_table.setColumnCount(11)
            self.result_table.setHorizontalHeaderLabels([
                tr("register.record_col_code"),
                tr("register.record_col_name"),
                tr("register.record_col_qty"),
                tr("register.record_col_card"),
                tr("register.record_col_dept"),
                tr("register.record_col_user"),
                tr("register.record_col_phone"),
                tr("register.record_col_action_type"),
                tr("register.record_col_out_time"),
                tr("register.record_col_operator"),
                tr("register.record_col_action"),
            ])
            self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            self.result_table.horizontalHeader().setStretchLastSection(True)
            self._restore_table_widths(self.result_table, "register_result_record", 11)

    # ---------- 物料模糊匹配 ----------

    def _fuzzy_match(self, text: str) -> list:
        """通过编码/名称两路模糊匹配（限制最多50条）"""
        if not text:
            return []
        t = text.lower()
        results = []
        for m in self._materials:
            if t in str(m.get("material_code", "")).lower() or t in str(m.get("material_name", "")).lower():
                results.append(m)
                if len(results) >= 50:
                    break
        return results

    def _fill_input(self, material: dict):
        """将匹配到的物料填充到输入框"""
        self.code_input.setText(material.get("material_code", ""))
        self.name_input.setText(material.get("material_name", ""))

    def _on_code_changed(self, text: str):
        """编码变化：仅展示模糊匹配结果，不自动填充"""
        if not text.strip():
            return
        matches = self._fuzzy_match(text)
        self._refresh_fuzzy_table(matches)

    def _on_name_changed(self, text: str):
        """名称变化：仅展示模糊匹配结果，不自动填充"""
        if not text.strip():
            return
        matches = self._fuzzy_match(text)
        self._refresh_fuzzy_table(matches)

    # ---------- 人员模糊匹配（带防抖）----------

    def _on_person_field_changed(self, text: str, field: str):
        """人员字段变化：触发防抖搜索（仅展示结果，不自动填充）"""
        if not text.strip():
            return
        self._fuzzy_keyword = text.strip()
        self._fuzzy_field = field
        self._fuzzy_timer.stop()
        self._fuzzy_timer.start(200)

    def _on_person_enter(self, field: str):
        """回车触发人员模糊匹配"""
        self._fuzzy_timer.stop()
        field_map = {
            "card_no": self.card_input,
            "dept": self.dept_input,
            "user_name": self.user_input,
        }
        text = field_map.get(field, QLineEdit()).text().strip()
        if not text:
            return
        matches = self._fuzzy_match_records(text, field)
        self._refresh_fuzzy_record_table(matches)

    def _do_fuzzy_search(self):
        """执行人员模糊匹配（仅展示结果，不自动填充）"""
        text = self._fuzzy_keyword
        field = self._fuzzy_field
        if not text:
            return
        matches = self._fuzzy_match_records(text, field)
        self._refresh_fuzzy_record_table(matches)

    def _fuzzy_match_records(self, text: str, field: str) -> list:
        """从员工档案中模糊匹配指定字段（卡号/部门/使用人），按 (卡号,部门,姓名) 去重（限制最多50条）"""
        if not text:
            return []
        t = text.lower()
        if field not in ("card_no", "dept", "user_name"):
            return []
        try:
            from local_db import LocalDB
            db = LocalDB()
            employees = db.query(TABLE_EMPLOYEE_RECORDS)
        except Exception:
            return []
        results = []
        seen = set()
        for r in employees:
            if field == "user_name":
                val = str(r.get("name", "")).lower()
            else:
                val = str(r.get(field, "")).lower()
            if t in val:
                key = (r.get("card_no", ""), r.get("dept", ""), r.get("name", ""))
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "card_no": r.get("card_no", ""),
                        "dept": r.get("dept", ""),
                        "user_name": r.get("name", ""),
                        "phone": r.get("phone", ""),
                    })
                    if len(results) >= 50:
                        break
        return results

    def _fill_person_info(self, record: dict):
        """将匹配到的人员信息填充到表单"""
        self.card_input.setText(str(record.get("card_no", "")))
        self.dept_input.setText(str(record.get("dept", "")))
        self.user_input.setText(str(record.get("user_name", "")))
        self.phone_input.setText(str(record.get("phone", "")))

    # ---------- 下方展示区交互 ----------

    def _refresh_fuzzy_table(self, matches: list):
        """刷新模糊匹配结果到下方展示区（物料4列）"""
        if self._result_mode != "fuzzy":
            self._switch_result_columns("fuzzy")
        self.bottom_title.setText(tr("register.bottom_title_fuzzy"))
        # 模糊匹配结果通常较少，直接渲染不分页
        self.result_table.setRowCount(len(matches))
        for row, m in enumerate(matches):
            self.result_table.setItem(row, _COL_FUZZY_CODE, QTableWidgetItem(str(m.get("material_code", ""))))
            self.result_table.setItem(row, _COL_FUZZY_NAME, QTableWidgetItem(str(m.get("material_name", ""))))
            self.result_table.setItem(row, _COL_FUZZY_QTY, QTableWidgetItem(str(m.get("stock_qty", ""))))
        self._hide_pagination()

    def _refresh_fuzzy_record_table(self, matches: list):
        """刷新人员模糊匹配结果到下方展示区（人员4列）"""
        if self._result_mode != "fuzzy_record":
            self._switch_result_columns("fuzzy_record")
        self.bottom_title.setText(tr("register.bottom_title_person"))
        self.result_table.setRowCount(len(matches))
        for row, r in enumerate(matches):
            self.result_table.setItem(row, _COL_FUZZY_REC_CARD, QTableWidgetItem(str(r.get("card_no", ""))))
            self.result_table.setItem(row, _COL_FUZZY_REC_DEPT, QTableWidgetItem(str(r.get("dept", ""))))
            self.result_table.setItem(row, _COL_FUZZY_REC_USER, QTableWidgetItem(str(r.get("user_name", ""))))
            self.result_table.setItem(row, _COL_FUZZY_REC_PHONE, QTableWidgetItem(str(r.get("phone", ""))))
        self._hide_pagination()

    def _on_result_clicked(self, item):
        """单击选中行"""
        pass

    def _on_result_double_clicked(self, item):
        """双击：物料模糊结果直接加入待录入清单；人员模糊结果填充到表单"""
        row = item.row()
        if self._result_mode == "fuzzy":
            code_item = self.result_table.item(row, 0)
            name_item = self.result_table.item(row, 1)
            code_text = code_item.text() if code_item else ""
            name_text = name_item.text() if name_item else ""
            if code_text:
                self.code_input.setText(code_text)
            if name_text:
                self.name_input.setText(name_text)
            self._on_add_item()
        elif self._result_mode == "fuzzy_record":
            card_item = self.result_table.item(row, 0)
            dept_item = self.result_table.item(row, 1)
            user_item = self.result_table.item(row, 2)
            phone_item = self.result_table.item(row, 3)
            if card_item:
                self.card_input.setText(card_item.text())
            if dept_item:
                self.dept_input.setText(dept_item.text())
            if user_item:
                self.user_input.setText(user_item.text())
            if phone_item:
                self.phone_input.setText(phone_item.text())
            self._refresh_record_table(self._records, tr("register.record_title"))

    # ---------- 分页控制 ----------

    def _hide_pagination(self):
        """隐藏分页控件（用于模糊匹配模式）"""
        self.page_info.setText("")
        self.btn_first.setVisible(False)
        self.btn_prev.setVisible(False)
        self.page_input.setVisible(False)
        self.page_total.setVisible(False)
        self.btn_next.setVisible(False)
        self.btn_last.setVisible(False)
        self.page_size_combo.setVisible(False)

    def _show_pagination(self):
        """显示分页控件"""
        self.btn_first.setVisible(True)
        self.btn_prev.setVisible(True)
        self.page_input.setVisible(True)
        self.page_total.setVisible(True)
        self.btn_next.setVisible(True)
        self.btn_last.setVisible(True)
        self.page_size_combo.setVisible(True)

    def _create_page_size_menu(self):
        menu = QMenu(self)
        for size in [20, 50, 100, 200]:
            action = QAction(tr("common.items_per_page", size=size), self)
            action.triggered.connect(lambda checked, s=size: self._set_page_size(s))
            menu.addAction(action)
        return menu

    def _set_page_size(self, size: int):
        self._page_size = size
        self.page_size_combo.setText(tr("common.items_per_page", size=size))
        self._page = 1
        self._refresh_current_page()

    def _goto_page(self, page: int):
        total_pages = max(1, (self._total + self._page_size - 1) // self._page_size)
        if 1 <= page <= total_pages:
            self._page = page
            self._refresh_current_page()

    def _on_page_input(self):
        try:
            page = int(self.page_input.text())
            self._goto_page(page)
        except ValueError:
            pass

    def _goto_last(self):
        total_pages = max(1, (self._total + self._page_size - 1) // self._page_size)
        self._goto_page(total_pages)

    def _update_pagination_ui(self):
        total_pages = max(1, (self._total + self._page_size - 1) // self._page_size)
        self.page_info.setText(tr("common.total", count=self._total))
        self.page_input.setText(str(self._page))
        self.page_total.setText(tr("common.page_total", total=total_pages))
        self.btn_first.setEnabled(self._page > 1)
        self.btn_prev.setEnabled(self._page > 1)
        self.btn_next.setEnabled(self._page < total_pages)
        self.btn_last.setEnabled(self._page < total_pages)

    # ---------- 待录入区操作 ----------

    def _refresh_pending_table(self):
        """刷新待录入区表格（屏蔽信号防止 itemChanged 干扰）"""
        self.pending_table.blockSignals(True)
        self.pending_table.setRowCount(len(self._pending_items))
        for row, item in enumerate(self._pending_items):
            self.pending_table.setItem(row, _COL_PENDING_CODE, QTableWidgetItem(str(item.get("material_code", ""))))
            self.pending_table.setItem(row, _COL_PENDING_NAME, QTableWidgetItem(str(item.get("material_name", ""))))
            self.pending_table.setItem(row, _COL_PENDING_QTY, QTableWidgetItem(str(item.get("qty", 1))))
        self.pending_table.blockSignals(False)

    def _on_pending_item_changed(self, item):
        """待录入表格数量修改后同步到 _pending_items"""
        row = item.row()
        col = item.column()
        if col == _COL_PENDING_QTY and 0 <= row < len(self._pending_items):
            try:
                new_qty = int(item.text())
                if new_qty > 0:
                    self._pending_items[row]["qty"] = new_qty
            except ValueError:
                # 输入非数字，恢复原始值
                original = self._pending_items[row].get("qty", 1)
                item.setText(str(original))

    def _on_add_item(self):
        """添加按钮：将当前输入的物料加入待录入清单"""
        code = self.code_input.text().strip()
        name = self.name_input.text().strip()
        qty = self.qty_input.value()

        if not code and not name:
            toast_warning(self, tr("toast.input_code_or_name"))
            return

        material = None
        # 精确匹配优先：编码精确匹配
        if code:
            for m in self._materials:
                if m.get("material_code") == code:
                    material = m
                    break
        if not material and name:
            for m in self._materials:
                if m.get("material_name") == name:
                    material = m
                    break
        if not material:
            # 精确匹配失败，使用模糊匹配（双字段交叉搜索）
            matches = self._fuzzy_match(code or name)
            if matches:
                material = matches[0]

        if not material:
            toast_warning(self, tr("toast.no_match", text=code or name))
            return

        mat_id = str(material.get("id", ""))
        for item in self._pending_items:
            if str(item.get("id", "")) == mat_id:
                item["qty"] = item.get("qty", 0) + qty
                self._refresh_pending_table()
                toast_success(
                    self,
                    tr("toast.accumulated",
                       code=material.get("material_code", ""),
                       name=material.get("material_name", ""),
                       add=qty,
                       total=item["qty"])
                )
                self.code_input.clear()
                self.name_input.clear()
                self.qty_input.setValue(1)
                return

        self._pending_items.append({
            "id": mat_id,
            "material_code": material.get("material_code", ""),
            "material_name": material.get("material_name", ""),
            "qty": qty,
        })
        self._refresh_pending_table()
        self.code_input.clear()
        self.name_input.clear()
        self.qty_input.setValue(1)

    def _on_del_item(self):
        """删除按钮：删除待录入区选中行"""
        row = self.pending_table.currentRow()
        if row < 0:
            toast_warning(self, tr("toast.select_row", action=tr("common.delete")))
            return
        if 0 <= row < len(self._pending_items):
            del self._pending_items[row]
            self._refresh_pending_table()

    # ---------- 硬件按钮状态 / 扫描 ----------

    def _apply_button_states(self):
        """根据 config_items 启用状态设置硬件按钮外观（不触碰串口）"""
        try:
            from local_db import LocalDB
            db = LocalDB()
            fp_rows = db.query(TABLE_CONFIG_ITEMS, conditions="config_name = ?", params=("FINGERPRINT_ENABLED",))
            nfc_rows = db.query(TABLE_CONFIG_ITEMS, conditions="config_name = ?", params=("NFC_ENABLED",))
            fp_enabled = any(row.get("content") == "1" for row in fp_rows)
            nfc_enabled = any(row.get("content") == "1" for row in nfc_rows)
            if fp_enabled:
                self.btn_fingerprint.setStyleSheet(HW_BTN_STYLE_ENABLED)
            else:
                self.btn_fingerprint.setStyleSheet(HW_BTN_STYLE_DISABLED)
            if nfc_enabled:
                self.btn_nfc.setStyleSheet(HW_BTN_STYLE_ENABLED)
            else:
                self.btn_nfc.setStyleSheet(HW_BTN_STYLE_DISABLED)
        except Exception:
            pass

    def showEvent(self, event):
        """每次视图显示时重新应用硬件按钮状态（用户配置变更后生效）"""
        super().showEvent(event)
        self._apply_button_states()

    # ---------- 快速录入（指纹 / NFC 扫描并填充人员字段）----------

    def _on_fingerprint_entry(self):
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

        thread = _HardwareReadThread(reader, 10.0)
        self._active_read_threads.append(thread)
        thread.result_ready.connect(self._handle_fingerprint_result)
        thread.finished.connect(
            lambda: self._active_read_threads.remove(thread) if thread in self._active_read_threads else None
        )
        thread.start()
        ok = show_wait_dialog(self, tr("dialog.wait_fingerprint"), tr("dialog.wait_fingerprint_hint"), timeout=10)
        if not ok:
            thread.quit()
            thread.wait(500)
            return

    def _handle_fingerprint_result(self, scan_id: str):
        self._fill_employee_from_scan(scan_id, "fingerprint_id")

    def _on_nfc_entry(self):
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

        thread = _HardwareReadThread(reader, 10.0)
        self._active_read_threads.append(thread)
        thread.result_ready.connect(self._handle_nfc_result)
        thread.finished.connect(
            lambda: self._active_read_threads.remove(thread) if thread in self._active_read_threads else None
        )
        thread.start()
        ok = show_wait_dialog(self, tr("dialog.wait_nfc"), tr("dialog.wait_nfc_hint"), timeout=10)
        if not ok:
            thread.quit()
            thread.wait(500)
            return

    def _handle_nfc_result(self, scan_id: str):
        self._fill_employee_from_scan(scan_id, "card_no")

    def _fill_employee_from_scan(self, scan_id: str, match_field: str):
        """扫描成功后按 scan_id 匹配员工档案，把姓名/部门/电话填入表单（不自动提交）"""
        if not scan_id:
            toast_warning(self, tr("register.toast_read_timeout"))
            return
        try:
            from local_db import LocalDB
            db = LocalDB()
            if match_field == "fingerprint_id":
                emp = db.get_employee_by_fingerprint_id(scan_id)
            else:
                emp = db.get_employee_by_card_no(scan_id)
            if not emp:
                type_label = "指纹" if match_field == "fingerprint_id" else "NFC卡"
                toast_warning(self, tr("register.toast_no_employee", type=type_label))
                return
            self.card_input.setText(str(emp.get("card_no", "")))
            self.dept_input.setText(str(emp.get("dept", "")))
            self.user_input.setText(str(emp.get("name", "")))
            self.phone_input.setText(str(emp.get("phone", "")))
            toast_success(self, tr("register.toast_scan_filled",
                name=emp.get("name", ""), dept=emp.get("dept", "")))
            # 成功填入数据后关闭等待窗口
            self._close_wait_dialog()
        except Exception as e:
            toast_warning(self, str(e))

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


    # ---------- 录入操作 ----------
    def _on_input(self):
        """录入按钮：提交所有待录入物料（必须包含物料）"""
        card_no = self.card_input.text().strip()
        if not card_no:
            toast_warning(self, tr("toast.card_required"))
            return
        user = self.user_input.text().strip()
        if not user:
            toast_warning(self, tr("toast.user_required"))
            return
        if not self._pending_items:
            toast_warning(self, tr("toast.add_material_first"))
            return

        dept = self.dept_input.text().strip()
        phone = self.phone_input.text().strip()

        for item in self._pending_items:
            data = {
                "material_id": item.get("id", ""),
                "material_code": item.get("material_code", ""),
                "material_name": item.get("material_name", ""),
                "qty": item.get("qty", 1),
                "card_no": card_no,
                "dept": dept,
                "user_name": user,
                "phone": phone,
                "action_type": "领用",
                "out_time": datetime.now().isoformat(),
                "is_returned": False,
            }
            self.borrow_submitted.emit(data)

        toast_success(self, tr("toast.entered", count=len(self._pending_items)))

        self._pending_items.clear()
        self._refresh_pending_table()
        self.card_input.clear()
        self.dept_input.clear()
        self.user_input.clear()
        self.phone_input.clear()
        self.qty_input.setValue(1)

        self.refresh_requested.emit()


    # ---------- 下方展示区（领用记录模式）分页渲染 ----------

    def _refresh_record_table(self, records: list, title: str = "领用记录"):
        """刷新领用记录到下方展示区（11列）- 分页渲染"""
        # 确保表头始终正确（即使 _result_mode 已是 record，也强制校验表头）
        if self._result_mode != "record" or self.result_table.columnCount() != 11:
            self._switch_result_columns("record")
        self.bottom_title.setText(title)
        self._show_pagination()

        self._records_for_display = records  # 保存当前要显示的数据集
        self._total = len(records)
        # 保持当前页码，不重置到 1
        self._page = self._page

        self._refresh_current_page()

    def _refresh_current_page(self):
        """渲染当前页数据（稳定优先：每次刷新直接创建新 widget，避免 Qt C++ 对象生命周期问题）"""
        records = getattr(self, '_records_for_display', self._records)
        total = len(records)
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        self._page = min(self._page, total_pages)

        start = (self._page - 1) * self._page_size
        end = min(start + self._page_size, total)
        page_data = records[start:end]

        # 保存滚动条位置
        v_scroll = self.result_table.verticalScrollBar()
        saved_scroll_pos = v_scroll.value()
        saved_selection = self.result_table.currentRow()

        # 性能优化：刷新前禁用更新和重绘
        self.result_table.blockSignals(True)
        self.result_table.setUpdatesEnabled(False)

        # 先清除旧的 cell widget，释放 C++ 对象（避免复用池引发的已删除对象访问）
        self.result_table.clearContents()
        self.result_table.setRowCount(len(page_data))

        for row, item in enumerate(page_data):
            # 共11列：物料编码、物料名称、数量、卡号、部门、使用人、电话、领/借、出库时间、经办人、操作
            self.result_table.setItem(row, _COL_RECORD_CODE, QTableWidgetItem(str(item.get("material_code", ""))))
            self.result_table.setItem(row, _COL_RECORD_NAME, QTableWidgetItem(str(item.get("material_name", ""))))
            self.result_table.setItem(row, _COL_RECORD_QTY, QTableWidgetItem(str(item.get("qty", ""))))
            self.result_table.setItem(row, _COL_RECORD_CARD, QTableWidgetItem(str(item.get("card_no", ""))))
            self.result_table.setItem(row, _COL_RECORD_DEPT, QTableWidgetItem(str(item.get("dept", ""))))
            self.result_table.setItem(row, _COL_RECORD_USER, QTableWidgetItem(str(item.get("user_name", ""))))
            self.result_table.setItem(row, _COL_RECORD_PHONE, QTableWidgetItem(str(item.get("phone", ""))))
            self.result_table.setItem(row, _COL_RECORD_ACTION, QTableWidgetItem(str(item.get("action_type", ""))))
            self.result_table.setItem(row, _COL_RECORD_TIME, QTableWidgetItem(str(item.get("out_time", ""))))
            self.result_table.setItem(row, _COL_RECORD_OPERATOR, QTableWidgetItem(str(item.get("operator", ""))))

            self._render_row_action(row, item)

        self.result_table.setUpdatesEnabled(True)
        self.result_table.blockSignals(False)

        # 恢复滚动位置
        v_scroll.setValue(saved_scroll_pos)

        self._total = total
        self._update_pagination_ui()

    def _render_row_action(self, row: int, item: dict):
        action_type = str(item.get("action_type", "") or "")
        is_person_registration = action_type == "人员登记"
        is_returned = item.get("is_returned")
        if is_person_registration:
            self.result_table.setCellWidget(row, 10, QLabel(tr("register.no_return_needed")))
        elif is_returned:
            self._render_returned_label(row, item)
        else:
            self._render_return_button(row, item)

    def _render_returned_label(self, row: int, item: dict):
        return_person = str(item.get("return_person", "") or item.get("user_name", "") or "")
        receiver = str(item.get("confirm_person", "") or "")
        return_qty = int(item.get("return_qty", 0) or 0)
        good_qty = int(item.get("good_qty", 0) or 0)
        damage_qty = int(item.get("damage_qty", 0) or 0)
        damage_status = str(item.get("damage_status", "") or "")
        mixed_qty = int(item.get("mixed_qty", 0) or 0)
        mixed_remark = str(item.get("mixed_remark", "") or "")

        status_text = ""
        if damage_status == tr("register.status_pending"):
            status_text = f'<span style="color:#ea580c;">{tr("register.status_pending")}</span>'
        elif damage_status == tr("register.status_completed"):
            status_text = f'<span style="color:#16a34a;">{tr("register.status_completed")}</span>'

        rp = (return_person[:4] + "\u2026") if len(return_person) > 5 else return_person
        rv = (receiver[:4] + "\u2026") if len(receiver) > 5 else receiver

        parts = [tr("register.returned")]
        if rp:
            parts.append(f"归:{rp}")
        if rv:
            parts.append(f"收:{rv}")
        if return_qty > 0:
            parts.append(f"还{return_qty}")
        if good_qty > 0:
            parts.append(f"好{good_qty}")
        if damage_qty > 0:
            parts.append(f"坏{damage_qty}")
        if mixed_qty > 0:
            parts.append(f"混{mixed_qty}")
        if status_text:
            parts.append(status_text)

        info_text = "-".join(parts)

        tooltip_parts = [tr("register.returned")]
        if return_person:
            tooltip_parts.append(f"归还人:{return_person}")
        if receiver:
            tooltip_parts.append(f"接收人:{receiver}")
        if return_qty > 0:
            tooltip_parts.append(f"还{return_qty}")
        if good_qty > 0:
            tooltip_parts.append(f"好板:{good_qty}")
        if damage_qty > 0:
            tooltip_parts.append(f"坏板:{damage_qty}")
        if mixed_qty > 0:
            tooltip_parts.append(f"混板:{mixed_qty}")
        if damage_status:
            tooltip_parts.append(f"状态:{damage_status}")
        tooltip_text = " | ".join(tooltip_parts)

        label = _ReturnInfoLabel(info_text, str(item.get("id", "")), damage_status, register_view=self)
        label.setToolTip(tooltip_text)
        self.result_table.setCellWidget(row, 10, label)

    def _render_return_button(self, row: int, item: dict):
        btn = QPushButton(tr("register.btn_return_confirm"))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #22c55e;
                color: #ffffff;
                border: none;
                outline: none;
                margin: 0px;
                border-radius: 4px;
                padding: 0px 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #16a34a;
                border: none;
                outline: none;
                margin: 0px;
            }
            QPushButton:pressed {
                background-color: #15803d;
                border: none;
                outline: none;
                margin: 0px;
            }
            QPushButton:focus {
                border: none;
                outline: none;
                margin: 0px;
            }
        """)
        record_id = str(item.get("id") or "")
        material_code = str(item.get("material_code") or "")
        material_name = str(item.get("material_name") or "")
        qty = int(item.get("qty") or 0)
        material_id = str(item.get("material_id") or "")
        current_stock = 0
        for m in self._materials:
            if str(m.get("id", "")) == material_id:
                current_stock = int(m.get("stock_qty", 0) or 0)
                break
        btn.clicked.connect(
            lambda checked=False, rid=record_id, mn=material_name, q=qty, cs=current_stock, mc=material_code:
            self._on_return_btn_clicked(rid, mn, q, cs, mc)
        )
        self.result_table.setCellWidget(row, 10, btn)

    def _on_return_btn_clicked(self, record_id: str, material_name: str, qty: int, current_stock: int = 0, material_code: str = ""):
        """归还确认按钮点击：弹出 v19 完整归还对话框"""
        confirmed, data = show_return_confirm(self, material_name, qty, current_stock, material_code)
        if confirmed and record_id:
            data["record_id"] = record_id
            self.return_submitted.emit(data)

    def _on_damage_label_right_clicked(self, record_id: str, new_status: str):
        """右键菜单切换待补单/已补单"""
        if record_id:
            self.damage_status_update.emit(record_id, new_status)

    def _on_filter_unreturned(self):
        unreturned = [r for r in self._records if not r.get("is_returned")]
        self._refresh_record_table(unreturned, tr("register.unreturned_title"))

    def _on_show_all(self):
        self._refresh_record_table(self._records, tr("register.record_title"))

    def _on_refresh_list(self):
        self._refresh_record_table(self._records, tr("register.record_title"))
        self.refresh_requested.emit()

    def refresh_return_row(self, record_id: str, updates: dict):
        if not record_id:
            return
        target = None
        for rec in self._records:
            if str(rec.get("id", "")) == record_id:
                target = rec
                break
        if target is None:
            return
        target.update(updates)
        if self.bottom_title.text() == tr("register.unreturned_title"):
            if target.get("is_returned"):
                self._records_for_display = [r for r in self._records_for_display if str(r.get("id", "")) != record_id]
                self._total = len(self._records_for_display)
                self._refresh_current_page()
            return
        page_size = self._page_size
        start = (self._page - 1) * page_size
        end = min(start + page_size, len(self._records_for_display))
        row_idx = None
        for i in range(start, end):
            if str(self._records_for_display[i].get("id", "")) == record_id:
                row_idx = i - start
                break
        if row_idx is None:
            return
        self._render_row_action(row_idx, self._records_for_display[row_idx])

    def _on_export(self):
        """导出领用记录到 Excel（支持日期范围选择）"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDateEdit, QPushButton
        from PySide6.QtCore import QDate
        from utils.excel_exporter import ExcelExporter
        from widgets.toast import toast_success, toast_error, toast_warning

        if not self._records:
            toast_warning(self, tr("toast.no_data_export"))
            return

        # 日期选择对话框（统一风格美化）
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("register.export_title"))
        dialog.setMinimumWidth(360)
        dialog.setStyleSheet("""
            QDialog { background-color: #ffffff; }
            QLabel { color: #374151; font-size: 13px; }
            QPushButton {
                background-color: #2563eb; color: white; font-weight: bold;
                border: none; border-radius: 6px; padding: 8px 20px;
                font-size: 13px; min-height: 32px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton#secondaryButton {
                background-color: #f3f4f6; color: #4b5563;
                border: 1px solid #d1d5db;
            }
            QPushButton#secondaryButton:hover { background-color: #e5e7eb; }
        """)
        dlayout = QVBoxLayout(dialog)
        dlayout.setSpacing(16)
        dlayout.setContentsMargins(20, 20, 20, 20)

        date_layout = QHBoxLayout()
        date_layout.setSpacing(8)

        date_start = QDateEdit()
        date_start.setDate(QDate.currentDate().addDays(-30))
        date_start.setStyleSheet("""
            QDateEdit {
                border: 1px solid #d1d5db; border-radius: 6px;
                padding: 6px 10px; background-color: #ffffff;
                min-height: 28px; font-size: 13px;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding; subcontrol-position: top right;
                width: 24px; border-left: 1px solid #d1d5db;
            }
        """)

        date_end = QDateEdit()
        date_end.setDate(QDate.currentDate())
        date_end.setStyleSheet("""
            QDateEdit {
                border: 1px solid #d1d5db; border-radius: 6px;
                padding: 6px 10px; background-color: #ffffff;
                min-height: 28px; font-size: 13px;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding; subcontrol-position: top right;
                width: 24px; border-left: 1px solid #d1d5db;
            }
        """)

        date_layout.addWidget(QLabel(tr("register.export_date_start")))
        date_layout.addWidget(date_start, 1)
        date_layout.addWidget(QLabel(tr("register.export_date_end")))
        date_layout.addWidget(date_end, 1)
        dlayout.addLayout(date_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton(tr("register.export_date_confirm"))
        cancel_btn = QPushButton(tr("register.export_date_cancel"))
        cancel_btn.setObjectName("secondaryButton")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        dlayout.addLayout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        start_str = date_start.date().toString("yyyy-MM-dd")
        end_str = date_end.date().toString("yyyy-MM-dd")

        # 按出库时间过滤
        filtered = []
        for r in self._records:
            out_time = r.get("out_time", "")
            if out_time and start_str <= out_time[:10] <= end_str:
                filtered.append(r)

        if not filtered:
            toast_warning(self, tr("register.export_date_range_empty"))
            return

        try:
            exporter = ExcelExporter()
            filepath = exporter.export_inventory_records(filtered)
            toast_success(self, tr("toast.export_success", path=filepath))
        except ImportError:
            toast_error(self, tr("toast.install_openpyxl"))
        except (OSError, IOError, ValueError, RuntimeError) as e:
            toast_error(self, tr("toast.export_failed", error=str(e)))
        except Exception as e:
            toast_error(self, tr("toast.export_failed", error=str(e)))

    # ---------- 公共接口 ----------

    def set_materials(self, materials: list):
        self._materials = materials

    def set_records(self, records: list):
        self._records = records
        self._refresh_record_table(records, tr("register.record_title"))

    def clear_memory(self, keep_pending=False):
        """清理内存缓存（窗口关闭时调用）

        Args:
            keep_pending: 为 True 时保留待录入区数据（标签页切换场景）
        """
        # 统一生命周期管理：先停定时器，再清数据，最后清UI
        try:
            self._fuzzy_timer.stop()
        except RuntimeError:
            pass
        self._materials = []
        self._records = []
        self._records_for_display = []
        if not keep_pending:
            self._pending_items.clear()
        try:
            self.result_table.blockSignals(True)
            # 注意：使用 clearContents() 而不是 clear()，避免清除表头标签
            self.result_table.clearContents()
            self.result_table.setRowCount(0)
        except RuntimeError:
            pass
        finally:
            try:
                self.result_table.blockSignals(False)
            except RuntimeError:
                pass
        if not keep_pending:
            try:
                self.pending_table.blockSignals(True)
                self.pending_table.clearContents()
                self.pending_table.setRowCount(0)
                self.pending_table.blockSignals(False)
            except RuntimeError:
                pass

    def _save_table_widths(self, table: QTableWidget, key: str):
        """保存表格所有列宽到 config_backups"""
        widths = [table.columnWidth(i) for i in range(table.columnCount())]
        from utils.ui_settings import save_column_widths
        save_column_widths(key, widths)

    def _restore_table_widths(self, table: QTableWidget, key: str, expected_count: int):
        """从 config_backups 恢复列宽"""
        from utils.ui_settings import restore_column_widths
        widths = restore_column_widths(key)
        if widths and len(widths) == expected_count:
            table.horizontalHeader().blockSignals(True)
            for i, w in enumerate(widths):
                if w > 0:
                    table.setColumnWidth(i, w)
            table.horizontalHeader().blockSignals(False)

    def _on_pending_col_resized(self, logical_index: int, old_size: int, new_size: int):
        self._save_table_widths(self.pending_table, "register_pending")

    def _on_result_col_resized(self, logical_index: int, old_size: int, new_size: int):
        key = f"register_result_{self._result_mode}"
        self._save_table_widths(self.result_table, key)

    def hideEvent(self, event):
        """视图隐藏时清理资源（统一生命周期管理）

        注意：窗口最小化也会触发 hideEvent，此时不应清理数据，
        否则恢复窗口后展示区变空白需手动刷新。
        标签页切换时保留待录入数据，避免用户未提交数据丢失。
        """
        super().hideEvent(event)
        # 窗口最小化/最大化切换时，跳过清理
        window = self.window()
        if window and bool(window.windowState() & Qt.WindowMinimized):
            return
        self.clear_memory(keep_pending=True)

