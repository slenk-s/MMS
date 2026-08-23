"""固定资产视图

v4.1 性能优化：
- 左侧表格使用 DataTable 组件，自带分页能力
- 渲染时禁用更新减少重绘
"""
import uuid
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDateEdit, QFileDialog, QDoubleSpinBox,
    QLabel, QSplitter,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QPixmap

from i18n import tr
from widgets.data_table import DataTable
from widgets.toast import toast_success, toast_warning
from widgets.zoomable_image_view import ZoomableImageView
from utils.dialogs import show_confirm
from utils.helpers import ImageCache


class _AssetImageLoadWorker(QThread):
    """资产图片后台加载线程"""

    finished_pixmap = Signal(str, QPixmap)

    def __init__(self, cache: ImageCache, path: str):
        super().__init__()
        self._cache = cache
        self._path = path

    def run(self):
        pixmap = self._cache.load_full_res(self._path)
        self.finished_pixmap.emit(self._path, pixmap or QPixmap())

# 固定资产列定义（数据键, 宽度, 对齐方式）
ASSET_COLUMNS = [
    ("asset_no", 140, "left"),
    ("asset_name", 180, "left"),
    ("category", 80, "center"),
    ("purchase_date", 100, "center"),
    ("status", 80, "center"),
    ("location", 120, "left"),
    ("value", 100, "right"),
    ("remark", 140, "left"),
]

_COL_KEY_MAP = {
    "asset_no": "asset.col_asset_no",
    "asset_name": "asset.col_asset_name",
    "category": "asset.col_category",
    "purchase_date": "asset.col_purchase_date",
    "status": "asset.col_status",
    "location": "asset.col_location",
    "value": "asset.col_value",
    "remark": "asset.col_remark",
}


def _build_asset_columns():
    """构建带翻译表头的列定义"""
    return [
        (tr(_COL_KEY_MAP[key]), key, width, align)
        for key, width, align in ASSET_COLUMNS
    ]


class AssetDialog(QDialog):
    """固定资产新增/编辑弹窗（风格与库存明细页物料弹窗一致）"""

    def __init__(self, parent=None, asset_data: dict = None):
        super().__init__(parent)
        self.setWindowTitle(tr("asset.dialog_add_title") if not asset_data else tr("asset.dialog_edit_title"))
        self.setMinimumWidth(420)
        self._data = asset_data or {}
        self._image_path = self._data.get("location_image", "")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        self._form = QFormLayout()
        self._form.setSpacing(10)
        self._form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.asset_no_input = QLineEdit()
        self.asset_no_input.setPlaceholderText(tr("asset.dialog_asset_no_placeholder"))
        self.asset_no_input.setStyleSheet("QLineEdit { border: 2px solid #dc2626; } QLineEdit:focus { border: 2px solid #2563eb; }")
        self._form.addRow(tr("asset.dialog_asset_no"), self.asset_no_input)

        self.asset_name_input = QLineEdit()
        self.asset_name_input.setPlaceholderText(tr("asset.dialog_asset_name_placeholder"))
        self.asset_name_input.setStyleSheet("QLineEdit { border: 2px solid #dc2626; } QLineEdit:focus { border: 2px solid #2563eb; }")
        self._form.addRow(tr("asset.dialog_asset_name"), self.asset_name_input)

        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.addItems([tr("asset.category_device"), tr("asset.category_tool"), tr("asset.category_instrument"), tr("asset.category_other")])
        self._form.addRow(tr("asset.dialog_category"), self.category_input)

        self.purchase_date_input = QDateEdit()
        self.purchase_date_input.setCalendarPopup(True)
        self.purchase_date_input.setDisplayFormat("yyyy-MM-dd")
        self.purchase_date_input.setDate(datetime.now())
        self._form.addRow(tr("asset.dialog_purchase_date"), self.purchase_date_input)

        self.status_input = QComboBox()
        self.status_input.addItems([tr("asset.status_in_use"), tr("asset.status_idle"), tr("asset.status_repairing"), tr("asset.status_scrapped")])
        self._form.addRow(tr("asset.dialog_status"), self.status_input)

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText(tr("asset.dialog_location_placeholder"))
        self._form.addRow(tr("asset.dialog_location"), self.location_input)

        # 位置图片
        self.image_preview = QLineEdit()
        self.image_preview.setPlaceholderText(tr("asset.dialog_image_placeholder"))
        self.image_preview.setReadOnly(True)
        self.browse_btn = QPushButton(tr("common.browse"))
        self.browse_btn.setObjectName("secondaryButton")
        self.browse_btn.clicked.connect(self._choose_image)
        img_layout = QHBoxLayout()
        img_layout.addWidget(self.image_preview, 1)
        img_layout.addWidget(self.browse_btn)
        self._form.addRow(tr("asset.dialog_image"), img_layout)

        self.value_input = QDoubleSpinBox()
        self.value_input.setRange(0, 99999999)
        self.value_input.setDecimals(2)
        self.value_input.setValue(0)
        self._form.addRow(tr("asset.dialog_value"), self.value_input)

        self.remark_input = QLineEdit()
        self.remark_input.setPlaceholderText(tr("asset.dialog_remark_placeholder"))
        self._form.addRow(tr("asset.dialog_remark"), self.remark_input)

        layout.addLayout(self._form)

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ok = QPushButton(tr("common.ok"))
        self.btn_ok.setMinimumWidth(80)
        self.btn_cancel = QPushButton(tr("common.cancel"))
        self.btn_cancel.setObjectName("secondaryButton")
        self.btn_cancel.setMinimumWidth(80)
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)

        self._fill_data()

    def retranslate_ui(self):
        """重新应用翻译"""
        self.setWindowTitle(tr("asset.dialog_add_title") if not self._data else tr("asset.dialog_edit_title"))
        self.asset_no_input.setPlaceholderText(tr("asset.dialog_asset_no_placeholder"))
        self.asset_name_input.setPlaceholderText(tr("asset.dialog_asset_name_placeholder"))
        self.location_input.setPlaceholderText(tr("asset.dialog_location_placeholder"))
        self.image_preview.setPlaceholderText(tr("asset.dialog_image_placeholder"))
        self.remark_input.setPlaceholderText(tr("asset.dialog_remark_placeholder"))
        self.browse_btn.setText(tr("common.browse"))
        self.btn_ok.setText(tr("common.ok"))
        self.btn_cancel.setText(tr("common.cancel"))
        # 更新表单标签
        label = self._form.labelForField(self.asset_no_input)
        if label is not None:
            label.setText(tr("asset.dialog_asset_no"))
        label = self._form.labelForField(self.asset_name_input)
        if label is not None:
            label.setText(tr("asset.dialog_asset_name"))
        label = self._form.labelForField(self.category_input)
        if label is not None:
            label.setText(tr("asset.dialog_category"))
        label = self._form.labelForField(self.purchase_date_input)
        if label is not None:
            label.setText(tr("asset.dialog_purchase_date"))
        label = self._form.labelForField(self.status_input)
        if label is not None:
            label.setText(tr("asset.dialog_status"))
        label = self._form.labelForField(self.location_input)
        if label is not None:
            label.setText(tr("asset.dialog_location"))
        label = self._form.labelForField(self.image_preview)
        if label is not None:
            label.setText(tr("asset.dialog_image"))
        label = self._form.labelForField(self.value_input)
        if label is not None:
            label.setText(tr("asset.dialog_value"))
        label = self._form.labelForField(self.remark_input)
        if label is not None:
            label.setText(tr("asset.dialog_remark"))
        # 更新下拉选项
        cur_cat = self.category_input.currentText()
        self.category_input.clear()
        self.category_input.addItems([tr("asset.category_device"), tr("asset.category_tool"), tr("asset.category_instrument"), tr("asset.category_other")])
        idx = self.category_input.findText(cur_cat)
        if idx >= 0:
            self.category_input.setCurrentIndex(idx)
        cur_status = self.status_input.currentText()
        self.status_input.clear()
        self.status_input.addItems([tr("asset.status_in_use"), tr("asset.status_idle"), tr("asset.status_repairing"), tr("asset.status_scrapped")])
        idx = self.status_input.findText(cur_status)
        if idx >= 0:
            self.status_input.setCurrentIndex(idx)

    def _fill_data(self):
        if not self._data:
            return
        self.asset_no_input.setText(str(self._data.get("asset_no", "")))
        self.asset_name_input.setText(str(self._data.get("asset_name", "")))
        category = self._data.get("category", "")
        if category:
            self.category_input.setCurrentText(category)
        date_str = self._data.get("purchase_date", "")
        if date_str:
            try:
                from PySide6.QtCore import QDate
                d = datetime.strptime(date_str, "%Y-%m-%d")
                self.purchase_date_input.setDate(QDate(d.year, d.month, d.day))
            except (ValueError, AttributeError):
                pass
        status = self._data.get("status", "")
        if status:
            self.status_input.setCurrentText(status)
        self.location_input.setText(str(self._data.get("location", "")))
        self.value_input.setValue(float(self._data.get("value", 0) or 0))
        self.remark_input.setText(str(self._data.get("remark", "")))
        img_path = self._data.get("location_image", "")
        if img_path:
            self._image_path = img_path
            self.image_preview.setText(img_path)

    def _choose_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("asset.dialog_select_image"), "",
            tr("dialog.image_filter")
        )
        if file_path:
            from config import LOCATION_IMAGES_DIR
            from utils.helpers import save_image_to_storage
            saved_path = save_image_to_storage(file_path, LOCATION_IMAGES_DIR, "location_")
            if saved_path:
                self._image_path = saved_path
                self.image_preview.setText(saved_path)

    def _on_ok(self):
        asset_no = self.asset_no_input.text().strip()
        asset_name = self.asset_name_input.text().strip()
        if not asset_no:
            toast_warning(self, tr("asset.dialog_asset_no_required"))
            self.asset_no_input.setFocus()
            return
        if not asset_name:
            toast_warning(self, tr("asset.dialog_asset_name_required"))
            self.asset_name_input.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        data = {
            "asset_no": self.asset_no_input.text().strip(),
            "asset_name": self.asset_name_input.text().strip(),
            "category": self.category_input.currentText(),
            "purchase_date": self.purchase_date_input.date().toString("yyyy-MM-dd"),
            "status": self.status_input.currentText(),
            "location": self.location_input.text().strip(),
            "value": self.value_input.value(),
            "remark": self.remark_input.text().strip(),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if self._image_path:
            data["location_image"] = self._image_path
        if self._data and "id" in self._data:
            data["id"] = self._data["id"]
        else:
            data["id"] = str(uuid.uuid4())
            data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return data


class AssetView(QWidget):
    add_asset = Signal(object)
    update_asset = Signal(str, dict)
    delete_asset = Signal(str)
    refresh_requested = Signal()

    # 图片缓存上限
    _MAX_PIXMAP_CACHE = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._image_cache = ImageCache(max_size=self._MAX_PIXMAP_CACHE)
        # 异步加载支持
        self._load_counter = 0
        self._current_load_id = 0
        self._upgrade_timer = QTimer(self)
        self._upgrade_timer.setSingleShot(True)
        self._upgrade_timer.setInterval(300)
        self._upgrade_timer.timeout.connect(self._do_upgrade_full_res)
        self._pending_upgrades: list = []
        # 活跃的后台加载线程（用于安全清理）
        self._active_workers: list = []
        self._cleaned_up: bool = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 工具栏
        toolbar = QHBoxLayout()
        self.btn_add = QPushButton(tr("asset.btn_add"))
        self.btn_edit = QPushButton(tr("asset.btn_edit"))
        self.btn_delete = QPushButton(tr("asset.btn_delete"))
        self.btn_refresh = QPushButton(tr("asset.btn_refresh"))
        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_edit)
        toolbar.addWidget(self.btn_delete)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 左右分栏
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：DataTable 组件（自带分页）
        from utils.ui_settings import restore_column_widths
        self.data_table = DataTable(_build_asset_columns(), parent=self, table_id="assets")
        saved_widths = restore_column_widths("assets")
        self.data_table.restore_column_widths(saved_widths)
        self.data_table.row_selected.connect(self._on_row_selected)
        self.data_table.row_double_clicked.connect(self._on_edit)
        splitter.addWidget(self.data_table)

        # 右侧：图示区域（位置图片 + 资产信息，垂直可调）
        self.img_widget = QWidget()
        right_layout = QVBoxLayout(self.img_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(0)

        # 垂直分割器：图片区（上）+ 信息区（下）
        right_splitter = QSplitter(Qt.Vertical)

        # === 上半：位置图片区 ===
        img_area = QWidget()
        img_area_layout = QVBoxLayout(img_area)
        img_area_layout.setContentsMargins(0, 0, 0, 0)
        img_area_layout.setSpacing(4)

        self.img_title = QLabel(tr("asset.image_title"))
        self.img_title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #1e40af; padding: 4px 0;"
        )
        img_area_layout.addWidget(self.img_title)

        _placeholder_style = (
            "background-color: #e8edf2; border-radius: 8px; color: #dc2626; font-size: 16px;"
        )
        self.location_view = ZoomableImageView(placeholder_style=_placeholder_style)
        self.location_view.set_minimum_height(120)
        self.location_view.set_placeholder(tr("asset.image_placeholder"))
        img_area_layout.addWidget(self.location_view, 1)
        right_splitter.addWidget(img_area)

        # === 下半：资产信息区 ===
        info_area = QWidget()
        info_area_layout = QVBoxLayout(info_area)
        info_area_layout.setContentsMargins(0, 0, 0, 0)
        info_area_layout.setSpacing(4)

        self.info_title = QLabel(tr("asset.info_title"))
        self.info_title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #1e40af; padding: 4px 0;"
        )
        info_area_layout.addWidget(self.info_title)

        self.info_label = QLabel(tr("asset.info_placeholder"))
        self.info_label.setStyleSheet(
            "background-color: #f1f5f9; border-radius: 8px; color: #374151; font-size: 13px; padding: 12px;"
        )
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.info_label.setMinimumHeight(80)
        info_area_layout.addWidget(self.info_label, 1)
        right_splitter.addWidget(info_area)

        right_splitter.setSizes([400, 120])
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 0)
        right_layout.addWidget(right_splitter)

        splitter.addWidget(self.img_widget)
        splitter.setSizes([720, 300])
        layout.addWidget(splitter)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit_selected)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)

    def retranslate_ui(self):
        """重新应用翻译"""
        from utils.ui_settings import restore_column_widths
        new_columns = _build_asset_columns()
        self.data_table.columns = new_columns
        self.data_table.table.setHorizontalHeaderLabels([c[0] for c in new_columns])
        saved_widths = restore_column_widths("assets")
        self.data_table.restore_column_widths(saved_widths)
        # 更新按钮
        self.btn_add.setText(tr("asset.btn_add"))
        self.btn_edit.setText(tr("asset.btn_edit"))
        self.btn_delete.setText(tr("asset.btn_delete"))
        self.btn_refresh.setText(tr("asset.btn_refresh"))
        # 更新右侧区域标题
        self.img_title.setText(tr("asset.image_title"))
        self.info_title.setText(tr("asset.info_title"))
        self.location_view.set_placeholder(tr("asset.image_placeholder"))
        self.info_label.setText(tr("asset.info_placeholder"))

    def set_data(self, data: list):
        self._data = data
        # 构建 O(1) 查重字典
        self._data_by_asset_no = {}
        for a in data:
            no = a.get("asset_no", "").strip()
            if no:
                self._data_by_asset_no[no] = a
        self.data_table.set_data(data)

    def _load_image(self, image_path: str, load_id: int):
        """渐进式加载：缩略图即时显示 → 300ms 后后台升级原图"""
        if not image_path:
            self.location_view.set_placeholder(tr("asset.image_placeholder"))
            return

        # 步骤 1: 快速加载缩略图
        thumb = self._image_cache.load_thumbnail(
            image_path, max(self.location_view.width() - 20, 200),
            max(self.location_view.height() - 20, 200)
        )
        if thumb is not None:
            self.location_view.set_image_thumbnail(thumb, source_path=image_path)
        else:
            self.location_view.set_placeholder(tr("asset.image_placeholder"))
            return

        # 步骤 2: 安排后台升级原图
        if not any(item[1] == load_id and item[0] == image_path
                   for item in self._pending_upgrades):
            self._pending_upgrades.append((image_path, load_id))

        self._upgrade_timer.start()

    def _do_upgrade_full_res(self):
        """定时器触发：在后台线程中加载原图"""
        if self._cleaned_up or not self._pending_upgrades:
            return
        current_id = self._current_load_id
        to_load = [path for path, lid in self._pending_upgrades
                   if lid == current_id and self.location_view.has_image()]
        self._pending_upgrades.clear()

        for path in to_load:
            worker = _AssetImageLoadWorker(self._image_cache, path)
            self._active_workers.append(worker)
            worker.finished_pixmap.connect(
                lambda request_id, pixmap, p=path:
                    self._on_full_res_loaded(request_id, pixmap, current_id)
            )
            worker.finished.connect(lambda w=worker: self._on_worker_done(w))
            worker.finished.connect(worker.deleteLater)
            worker.start()

    def _on_worker_done(self, worker: QThread):
        """线程完成后从活跃列表移除"""
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def _cleanup_workers(self):
        """安全清理所有活跃的后台线程"""
        self._cleaned_up = True
        try:
            self._upgrade_timer.stop()
        except RuntimeError:
            pass
        self._pending_upgrades.clear()
        for worker in list(self._active_workers):
            try:
                if worker.isRunning():
                    worker.quit()
                    worker.wait(2000)
            except RuntimeError:
                pass
        self._active_workers.clear()

    def _on_full_res_loaded(self, request_id: str, pixmap: QPixmap, load_id: int):
        """原图加载完成：升级显示"""
        if self._cleaned_up:
            return
        if load_id != self._current_load_id:
            return
        if self.location_view.has_image() and not pixmap.isNull():
            self.location_view.upgrade_to_full_res(pixmap)

    def _on_row_selected(self, row_data: dict):
        """行选中时更新图示区域（缩略图即时显示 + 后台升级原图）"""
        self._load_counter += 1
        self._current_load_id = self._load_counter
        current_id = self._current_load_id

        if not row_data:
            self.location_view.set_placeholder(tr("asset.image_placeholder"))
            self.info_label.setText(tr("asset.info_placeholder"))
            return

        self._load_image(row_data.get("location_image", ""), current_id)

        # 更新资产信息
        info = (
            f"<b>{tr('asset.col_asset_no')}:</b> {row_data.get('asset_no', '')}<br>"
            f"<b>{tr('asset.col_asset_name')}:</b> {row_data.get('asset_name', '')}<br>"
            f"<b>{tr('asset.col_location')}:</b> {row_data.get('location', '')}<br>"
            f"<b>{tr('asset.col_status')}:</b> {row_data.get('status', '')}"
        )
        self.info_label.setText(info)

    def clear_memory(self):
        """清理内存缓存（窗口关闭时调用）"""
        self._cleanup_workers()
        self._image_cache.clear()
        self.location_view.clear()
        self._data = []

    def hideEvent(self, event):
        """视图隐藏时清理图片缓存，释放内存"""
        super().hideEvent(event)
        # 窗口最小化时跳过清理，避免恢复后图片无法加载
        window = self.window()
        if window and bool(window.windowState() & Qt.WindowMinimized):
            return
        self._cleanup_workers()
        self._image_cache.clear()
        self.location_view.clear()

    def showEvent(self, event):
        """视图重新显示时重置清理标志，恢复图片加载能力"""
        super().showEvent(event)
        self._cleaned_up = False

    def _on_add(self):
        dlg = AssetDialog(self)
        try:
            if dlg.exec() == QDialog.Accepted:
                data = dlg.get_data()
                # 本地检查资产编号是否已存在（O(1) 查重）
                asset_no = data.get("asset_no", "").strip()
                if asset_no and asset_no in self._data_by_asset_no:
                    toast_warning(self, tr("asset.asset_no_duplicate", asset_no=asset_no))
                    return
                self.add_asset.emit(data)
        finally:
            dlg.deleteLater()

    def _on_edit_selected(self):
        row_data = self.data_table.get_selected_row()
        if not row_data:
            toast_warning(self, tr("asset.select_edit"))
            return
        self._on_edit(row_data)

    def _on_edit(self, row_data: dict):
        dlg = AssetDialog(self, row_data)
        try:
            if dlg.exec() == QDialog.Accepted:
                data = dlg.get_data()
                asset_id = str(row_data.get("id", ""))
                asset_no = data.get("asset_no", "").strip()
                # 本地检查资产编号是否与其他记录冲突（排除自身，O(1) 查重）
                if asset_no and asset_no in self._data_by_asset_no:
                    existing = self._data_by_asset_no[asset_no]
                    if str(existing.get("id", "")) != asset_id:
                        toast_warning(self, tr("asset.asset_no_occupied", asset_no=asset_no))
                        return
                self.update_asset.emit(asset_id, data)
        finally:
            dlg.deleteLater()

    def _on_delete(self):
        row_data = self.data_table.get_selected_row()
        if not row_data:
            toast_warning(self, tr("asset.select_delete"))
            return
        asset_id = str(row_data.get("id", ""))
        asset_name = row_data.get("asset_name", "")
        if show_confirm(self, tr("asset.confirm_delete_title"), tr("asset.confirm_delete_text", name=asset_name), "warning"):
            self.delete_asset.emit(asset_id)
