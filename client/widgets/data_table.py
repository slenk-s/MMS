"""
数据表格组件
封装 QTableWidget，支持分页、排序、行选择、右键菜单

v4.1 性能优化：
- 刷新表格时禁用更新减少重绘
- 过滤数据时批量处理
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QLineEdit, QMenu, QAbstractItemView
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction

from i18n import tr


class DataTable(QWidget):
    """数据表格组件"""

    # 信号定义
    row_selected = Signal(object)          # 行选中信号，携带该行数据
    row_double_clicked = Signal(object)   # 行双击信号
    page_changed = Signal(int)          # 页码变更信号
    page_size_changed = Signal(int)     # 每页条数变更信号

    def __init__(self, columns: list, parent=None, search_keys: list = None, table_id: str = None):
        """
        参数:
            columns: [(显示名, 数据键, 宽度, 对齐方式), ...]
            search_keys: 搜索时只匹配这些数据键（None=搜索全部字段）
            table_id: 表格唯一标识，用于列宽持久化（None=不持久化）
        """
        super().__init__(parent)
        self.columns = columns
        self._search_keys = search_keys
        self._table_id = table_id
        self._data: list = []
        self._filtered_data: list = []
        self._current_page = 1
        self._page_size = 20
        self._saved_widths: list = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.columns])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        last_idx = len(self.columns) - 1
        self.table.horizontalHeader().setSectionResizeMode(last_idx, QHeaderView.Stretch)
        self.table.horizontalHeader().sectionResized.connect(self._on_column_resized)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        # 分页控件
        page_layout = QHBoxLayout()
        page_layout.setSpacing(8)

        self.page_info = QLabel(tr("common.total", count=0))
        page_layout.addWidget(self.page_info)

        page_layout.addStretch()

        self.btn_first = QPushButton(tr("register.btn_first"))
        self.btn_first.setObjectName("pageButton")
        self.btn_first.clicked.connect(lambda: self.goto_page(1))
        page_layout.addWidget(self.btn_first)

        self.btn_prev = QPushButton(tr("common.prev"))
        self.btn_prev.setObjectName("pageButton")
        self.btn_prev.clicked.connect(lambda: self.goto_page(self._current_page - 1))
        page_layout.addWidget(self.btn_prev)

        self.page_input = QLineEdit()
        self.page_input.setMaximumWidth(60)
        self.page_input.setAlignment(Qt.AlignCenter)
        self.page_input.returnPressed.connect(self._on_page_input)
        page_layout.addWidget(self.page_input)

        self.page_total = QLabel(tr("common.page_total", total=1))
        page_layout.addWidget(self.page_total)

        self.btn_next = QPushButton(tr("common.next"))
        self.btn_next.setObjectName("pageButton")
        self.btn_next.clicked.connect(lambda: self.goto_page(self._current_page + 1))
        page_layout.addWidget(self.btn_next)

        self.btn_last = QPushButton(tr("register.btn_last"))
        self.btn_last.setObjectName("pageButton")
        self.btn_last.clicked.connect(self._goto_last)
        page_layout.addWidget(self.btn_last)

        self.page_size_combo = QPushButton(tr("common.items_per_page", size=20))
        self.page_size_combo.setObjectName("pageButton")
        self.page_size_combo.setMenu(self._create_page_size_menu())
        page_layout.addWidget(self.page_size_combo)

        layout.addLayout(page_layout)

    def _create_page_size_menu(self):
        """创建每页条数菜单"""
        menu = QMenu(self)
        for size in [10, 20, 50, 100]:
            action = QAction(tr("common.items_per_page", size=size), self)
            action.triggered.connect(lambda checked, s=size: self.set_page_size(s))
            menu.addAction(action)
        return menu

    def set_data(self, data: list):
        """设置表格数据（含列数一致性防御检查）"""
        # A01: 防御性检查 — 首次加载时验证数据键与列定义匹配
        if data and len(self._data) == 0:
            first = data[0]
            col_keys = {key for _, key, _, _ in self.columns}
            data_keys = set(first.keys())
            missing = col_keys - data_keys
            if missing:
                import warnings
                warnings.warn(
                    f"DataTable 列定义中有 {len(missing)} 个键在数据中不存在: {missing}",
                    RuntimeWarning, stacklevel=2
                )
        self._data = data
        self._filtered_data = data
        self._current_page = 1
        self._refresh_table()

    def filter_data(self, keyword: str):
        """按关键词过滤数据"""
        if not keyword:
            self._filtered_data = self._data
        else:
            keyword = keyword.lower()
            if self._search_keys:
                # 只匹配指定的字段
                self._filtered_data = [
                    row for row in self._data
                    if any(keyword in str(row.get(k, "")).lower() for k in self._search_keys)
                ]
            else:
                # 匹配全部字段（默认行为）
                self._filtered_data = [
                    row for row in self._data
                    if any(str(v).lower().find(keyword) >= 0 for v in row.values())
                ]
        self._current_page = 1
        self._refresh_table()

    def restore_column_widths(self, widths: list):
        """从持久化设置恢复列宽，并直接应用到表格"""
        if widths and len(widths) == len(self.columns):
            self._saved_widths = widths
            self.table.blockSignals(True)
            for i, w in enumerate(widths):
                if w:
                    self.table.setColumnWidth(i, w)
            self.table.blockSignals(False)
        else:
            self._saved_widths = []

    def _on_column_resized(self, logical_index: int, old_size: int, new_size: int):
        """列宽拖动完成后保存（sectionResized 信号为 3 参数）"""
        if not self._table_id:
            return
        widths = [self.table.columnWidth(i) for i in range(len(self.columns))]
        self._saved_widths = widths
        from utils.ui_settings import save_column_widths
        save_column_widths(self._table_id, widths)

    def _refresh_table(self):
        """刷新表格显示（性能优化：禁用更新减少重绘）"""
        total = len(self._filtered_data)
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        self._current_page = min(self._current_page, total_pages)

        start = (self._current_page - 1) * self._page_size
        end = min(start + self._page_size, total)
        page_data = self._filtered_data[start:end]

        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)

        self.table.setRowCount(len(page_data))

        for col_idx, (_, _, width, _) in enumerate(self.columns):
            if self._saved_widths and col_idx < len(self._saved_widths):
                w = self._saved_widths[col_idx]
            else:
                w = width
            if w:
                self.table.setColumnWidth(col_idx, w)

        for row_idx, row_data in enumerate(page_data):
            for col_idx, (_, key, _, align) in enumerate(self.columns):
                value = row_data.get(key, "")
                item = QTableWidgetItem(str(value))
                # 只在第一列存储完整数据，其余列不必重复
                if col_idx == 0:
                    item.setData(Qt.UserRole, row_data)
                if align == "center":
                    item.setTextAlignment(Qt.AlignCenter)
                elif align == "right":
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, col_idx, item)

        # 恢复更新
        self.table.setUpdatesEnabled(True)
        self.table.blockSignals(False)

        self.page_info.setText(tr("common.total", count=total))
        self.page_input.setText(str(self._current_page))
        self.page_total.setText(tr("common.page_total", total=total_pages))
        self.btn_first.setEnabled(self._current_page > 1)
        self.btn_prev.setEnabled(self._current_page > 1)
        self.btn_next.setEnabled(self._current_page < total_pages)
        self.btn_last.setEnabled(self._current_page < total_pages)

    def goto_page(self, page: int):
        """跳转到指定页"""
        total = len(self._filtered_data)
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        if 1 <= page <= total_pages:
            self._current_page = page
            self._refresh_table()
            self.page_changed.emit(page)

    def _on_page_input(self):
        """页码输入框回车事件"""
        try:
            page = int(self.page_input.text())
            self.goto_page(page)
        except ValueError:
            pass

    def _goto_last(self):
        """跳转到最后一页"""
        total = len(self._filtered_data)
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        self.goto_page(total_pages)

    def set_page_size(self, size: int):
        """设置每页条数"""
        self._page_size = size
        self.page_size_combo.setText(f"{size}条/页")
        self._current_page = 1
        self._refresh_table()
        self.page_size_changed.emit(size)

    def _on_selection_changed(self):
        """选择变更事件"""
        selected = self.table.selectedItems()
        if selected:
            row_data = selected[0].data(Qt.UserRole)
            if row_data:
                self.row_selected.emit(row_data)

    def _on_double_click(self, item):
        """双击事件"""
        row_data = item.data(Qt.UserRole)
        if row_data:
            self.row_double_clicked.emit(row_data)

    def _show_context_menu(self, position):
        """右键菜单"""
        menu = QMenu(self)
        view_action = QAction(tr("common.view_detail"), self)
        view_action.triggered.connect(self._on_selection_changed)
        menu.addAction(view_action)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def retranslate_ui(self):
        """重新应用当前语言的文本"""
        self.table.setHorizontalHeaderLabels([c[0] for c in self.columns])
        self.page_info.setText(tr("common.total", count=len(self._filtered_data)))
        self.btn_first.setText(tr("register.btn_first"))
        self.btn_prev.setText(tr("common.prev"))
        self.page_total.setText(tr("common.page_total", total=max(1, (len(self._filtered_data) + self._page_size - 1) // self._page_size)))
        self.btn_next.setText(tr("common.next"))
        self.btn_last.setText(tr("register.btn_last"))
        self.page_size_combo.setText(tr("common.items_per_page", size=self._page_size))
        self.page_size_combo.setMenu(self._create_page_size_menu())
        # 刷新表格以更新表头
        self._refresh_table()

    def get_selected_row(self) -> dict:
        """获取当前选中行数据"""
        selected = self.table.selectedItems()
        if selected:
            return selected[0].data(Qt.UserRole) or {}
        return {}

    def clear_selection(self):
        """清除选择"""
        self.table.clearSelection()
