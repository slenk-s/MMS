"""库存明细视图
左侧数据表 + 右侧货架图片可视化布局
顶部工具栏：物料录入、刷新、导出、搜索

v4.1 性能优化：
- 搜索增加 QTimer 防抖（200ms），避免输入时频繁过滤

v4.3 v25: 支持 Excel "放置在单元格中" 图片导入（richData 方式）
- 同时兼容传统浮动图片导入
"""
from i18n import tr
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
    QPushButton, QLineEdit, QMessageBox, QDialog, QFormLayout,
    QSpinBox, QFileDialog, QApplication,
)
from PySide6.QtCore import Signal, Qt, QTimer, QThread
from PySide6.QtGui import QPixmap

import os
from datetime import datetime

from widgets.data_table import DataTable
from widgets.toast import toast_success, toast_warning, toast_error
from widgets.zoomable_image_view import ZoomableImageView
from widgets.shelf_grid_view import ShelfGridView
from utils.dialogs import show_confirm
from utils.excel_exporter import ExcelExporter
from utils.excel_image_extractor import extract_all_images, guess_image_ext
from utils.helpers import ImageCache, save_image_to_storage
from config import REAL_IMAGES_DIR


class _ImageLoadWorker(QThread):
    """后台图片加载线程：异步解码原图，不阻塞 UI"""

    finished_pixmap = Signal(str, QPixmap)  # (request_id, pixmap)

    def __init__(self, cache: ImageCache, path: str, request_id: str):
        super().__init__()
        self._cache = cache
        self._path = path
        self._request_id = request_id

    def run(self):
        pixmap = self._cache.load_full_res(self._path)
        self.finished_pixmap.emit(self._request_id, pixmap or QPixmap())

# 列定义基础模板（不包含翻译头 — 延迟构建）
_COLUMN_TEMPLATES = [
    ("inventory.col_location", "location", 120, "left"),
    ("inventory.col_shelf_no", "shelf_no", 80, "center"),
    ("inventory.col_material_code", "material_code", 160, "left"),
    ("inventory.col_material_name", "material_name", 220, "left"),
    ("inventory.col_stock_qty", "stock_qty", 80, "center"),
    ("inventory.col_unit", "unit", 60, "center"),
    ("inventory.col_reserved_qty", "reserved_qty", 80, "center"),
    ("inventory.col_last_update", "last_update", 160, "center"),
]


def _build_columns():
    """延迟构建带翻译表头的列定义"""
    return [
        (tr(key), data_key, width, align)
        for key, data_key, width, align in _COLUMN_TEMPLATES
    ]


class MaterialInputDialog(QDialog):
    """物料录入/编辑弹窗"""

    def __init__(self, parent=None, material_data: dict = None):
        super().__init__(parent)
        self.setWindowTitle(tr("mat_dialog.add_title") if material_data is None else tr("mat_dialog.edit_title"))
        self.setMinimumWidth(420)
        self._data = material_data or {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        self._form = QFormLayout()
        self._form.setSpacing(10)
        self._form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # 地点
        self.location_input = QLineEdit()
        self.location_input.setText(self._data.get("location", ""))
        self.location_input.setPlaceholderText(tr("mat_dialog.location_placeholder"))
        self._form.addRow(tr("mat_dialog.location"), self.location_input)

        # 货架号
        self.shelf_no_input = QLineEdit()
        self.shelf_no_input.setText(self._data.get("shelf_no", ""))
        self.shelf_no_input.setPlaceholderText(tr("mat_dialog.shelf_no_placeholder"))
        self._form.addRow(tr("mat_dialog.shelf_no"), self.shelf_no_input)

        # 物料编码（必填）
        self.code_input = QLineEdit()
        self.code_input.setText(self._data.get("material_code", ""))
        self.code_input.setPlaceholderText(tr("mat_dialog.code_placeholder"))
        self.code_input.setStyleSheet("QLineEdit { border: 2px solid #dc2626; } QLineEdit:focus { border: 2px solid #2563eb; }")
        self._form.addRow(tr("mat_dialog.material_code"), self.code_input)

        # 物料名称（必填）
        self.name_input = QLineEdit()
        self.name_input.setText(self._data.get("material_name", ""))
        self.name_input.setPlaceholderText(tr("mat_dialog.name_placeholder"))
        self.name_input.setStyleSheet("QLineEdit { border: 2px solid #dc2626; } QLineEdit:focus { border: 2px solid #2563eb; }")
        self._form.addRow(tr("mat_dialog.material_name"), self.name_input)

        # 库存数量
        self.stock_input = QSpinBox()
        self.stock_input.setRange(-999999, 999999)
        self.stock_input.setValue(self._data.get("stock_qty", 0))
        self._form.addRow(tr("mat_dialog.stock_qty"), self.stock_input)

        # 单位
        self.unit_input = QLineEdit()
        self.unit_input.setText(self._data.get("unit", "PCS"))
        self._form.addRow(tr("mat_dialog.unit"), self.unit_input)

        # 预留量
        self.reserved_input = QSpinBox()
        self.reserved_input.setRange(0, 999999)
        self.reserved_input.setValue(self._data.get("reserved_qty", 0))
        self._form.addRow(tr("mat_dialog.reserved_qty"), self.reserved_input)

        # 图示 - 实物图
        self.real_image_input = QLineEdit()
        self.real_image_input.setText(self._data.get("real_image", ""))
        self.real_image_input.setPlaceholderText(tr("mat_dialog.real_image_placeholder"))
        self.browse_real_btn = QPushButton(tr("mat_dialog.browse"))
        self.browse_real_btn.setObjectName("secondaryButton")
        self.browse_real_btn.clicked.connect(lambda: self._browse_image(self.real_image_input, tr("mat_dialog.select_real_image")))
        real_img_layout = QHBoxLayout()
        real_img_layout.addWidget(self.real_image_input, 1)
        real_img_layout.addWidget(self.browse_real_btn)
        self._form.addRow(tr("mat_dialog.real_image"), real_img_layout)

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

    def retranslate_ui(self):
        """重新应用翻译"""
        self.setWindowTitle(tr("mat_dialog.add_title") if not self._data else tr("mat_dialog.edit_title"))
        self.location_input.setPlaceholderText(tr("mat_dialog.location_placeholder"))
        self.shelf_no_input.setPlaceholderText(tr("mat_dialog.shelf_no_placeholder"))
        self.code_input.setPlaceholderText(tr("mat_dialog.code_placeholder"))
        self.name_input.setPlaceholderText(tr("mat_dialog.name_placeholder"))
        self.real_image_input.setPlaceholderText(tr("mat_dialog.real_image_placeholder"))
        self.browse_real_btn.setText(tr("mat_dialog.browse"))
        self.btn_ok.setText(tr("common.ok"))
        self.btn_cancel.setText(tr("common.cancel"))
        # 更新表单标签
        label = self._form.labelForField(self.location_input)
        if label is not None:
            label.setText(tr("mat_dialog.location"))
        label = self._form.labelForField(self.shelf_no_input)
        if label is not None:
            label.setText(tr("mat_dialog.shelf_no"))
        label = self._form.labelForField(self.code_input)
        if label is not None:
            label.setText(tr("mat_dialog.material_code"))
        label = self._form.labelForField(self.name_input)
        if label is not None:
            label.setText(tr("mat_dialog.material_name"))
        label = self._form.labelForField(self.stock_input)
        if label is not None:
            label.setText(tr("mat_dialog.stock_qty"))
        label = self._form.labelForField(self.unit_input)
        if label is not None:
            label.setText(tr("mat_dialog.unit"))
        label = self._form.labelForField(self.reserved_input)
        if label is not None:
            label.setText(tr("mat_dialog.reserved_qty"))
        label = self._form.labelForField(self.real_image_input)
        if label is not None:
            label.setText(tr("mat_dialog.real_image"))

    def _browse_image(self, target_input, title):
        file_path, _ = QFileDialog.getOpenFileName(
            self, title, "",
            tr("dialog.image_filter")
        )
        if file_path:
            from config import REAL_IMAGES_DIR
            from utils.helpers import save_image_to_storage
            saved_path = save_image_to_storage(file_path, REAL_IMAGES_DIR, "real_")
            if saved_path:
                target_input.setText(saved_path)

    def _on_ok(self):
        code = self.code_input.text().strip()
        name = self.name_input.text().strip()
        if not code:
            toast_warning(self, tr("toast.material_code_empty"))
            self.code_input.setFocus()
            return
        if not name:
            toast_warning(self, tr("toast.material_name_empty"))
            self.name_input.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "location": self.location_input.text().strip(),
            "shelf_no": self.shelf_no_input.text().strip(),
            "material_code": self.code_input.text().strip(),
            "material_name": self.name_input.text().strip(),
            "stock_qty": self.stock_input.value(),
            "unit": self.unit_input.text().strip() or "PCS",
            "reserved_qty": self.reserved_input.value(),
            "real_image": self.real_image_input.text().strip(),
        }


class InventoryDetailView(QWidget):
    """库存明细主视图"""

    # 信号定义
    add_material = Signal(object)           # 新增物料
    update_material = Signal(str, dict)   # 更新物料 (id, data)
    delete_material = Signal(str)         # 删除物料 (id)
    import_materials = Signal(object)       # 批量导入物料 (list of dict)
    refresh_requested = Signal()          # 请求刷新

    # 图片缓存上限
    _MAX_PIXMAP_CACHE = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list = []
        self._data_by_code: dict = {}  # material_code -> material (O(1) 查重)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._do_search)
        self._search_keyword = ""
        # 图片缓存：path -> QPixmap，限制大小避免内存无限增长
        self._image_cache = ImageCache(max_size=self._MAX_PIXMAP_CACHE)
        # 异步加载请求 ID（防止过期请求覆盖新选择）
        self._load_counter = 0
        self._current_load_id = 0
        # 异步加载定时器（缩略图显示 300ms 后加载原图）
        self._upgrade_timer = QTimer(self)
        self._upgrade_timer.setSingleShot(True)
        self._upgrade_timer.setInterval(300)
        self._upgrade_timer.timeout.connect(self._do_upgrade_full_res)
        # 待升级的图片信息
        self._pending_upgrades: list = []
        # 活跃的后台加载线程（用于安全清理）
        self._active_workers: list = []
        self._cleaned_up: bool = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ---------- 工具栏 ----------
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.btn_add = QPushButton(tr("inventory.btn_add"))
        self.btn_import = QPushButton(tr("inventory.btn_import"))
        self.btn_refresh = QPushButton(tr("inventory.btn_refresh"))
        self.btn_export = QPushButton(tr("inventory.btn_export"))
        self.btn_edit = QPushButton(tr("inventory.btn_edit"))
        self.btn_delete = QPushButton(tr("inventory.btn_delete"))
        self.btn_delete.setObjectName("dangerButton")

        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_import)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addWidget(self.btn_export)
        toolbar.addWidget(self.btn_edit)
        toolbar.addWidget(self.btn_delete)
        toolbar.addStretch()

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("inventory.search_placeholder"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMaximumWidth(320)
        self.search_input.returnPressed.connect(self._on_search)
        self.search_input.editingFinished.connect(self._on_search)
        self.search_input.textChanged.connect(self._on_search_delayed)
        toolbar.addWidget(self.search_input)

        layout.addLayout(toolbar)

        # ---------- 内容区域 ----------
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：数据表格（带分页）
        from utils.ui_settings import restore_column_widths
        self.data_table = DataTable(
            _build_columns(), parent=self,
            search_keys=["material_code", "material_name"],
            table_id="inventory_materials"
        )
        saved_widths = restore_column_widths("inventory_materials")
        self.data_table.restore_column_widths(saved_widths)
        self.data_table.row_selected.connect(self._on_row_selected)
        self.data_table.row_double_clicked.connect(self._on_edit_material)
        splitter.addWidget(self.data_table)

        # 右侧：货架布局网格 + 实物图
        self.shelf_widget = QWidget()
        shelf_layout = QVBoxLayout(self.shelf_widget)
        shelf_layout.setContentsMargins(0, 0, 0, 0)
        shelf_layout.setSpacing(8)

        # 占位图样式（实物图仍使用）
        _placeholder_style = (
            "background-color: #e0e4e8; border-radius: 8px; color: #5a6573; font-size: 13px;"
        )

        # 货架网格视图（替代原货架图）
        self.shelf_view = ShelfGridView()
        shelf_layout.addWidget(self.shelf_view, 3)  # 占 3 份空间

        # 实物图
        self.real_view = ZoomableImageView(placeholder_style=_placeholder_style)
        self.real_view.set_minimum_height(160)
        self.real_view.set_placeholder(tr("inventory.real_image"))
        shelf_layout.addWidget(self.real_view, 2)  # 占 2 份空间

        splitter.addWidget(self.shelf_widget)

        splitter.setSizes([720, 340])
        layout.addWidget(splitter)

        # ---------- 信号连接 ----------
        self.btn_add.clicked.connect(self._on_add_material)
        self.btn_import.clicked.connect(self._on_import_material)
        self.btn_refresh.clicked.connect(self._on_refresh)
        self.btn_export.clicked.connect(self._on_export)
        self.btn_edit.clicked.connect(self._on_edit_selected)
        self.btn_delete.clicked.connect(self._on_delete_selected)

    def retranslate_ui(self):
        """重新应用翻译"""
        self.btn_add.setText(tr("inventory.btn_add"))
        self.btn_import.setText(tr("inventory.btn_import"))
        self.btn_refresh.setText(tr("inventory.btn_refresh"))
        self.btn_export.setText(tr("inventory.btn_export"))
        self.btn_edit.setText(tr("inventory.btn_edit"))
        self.btn_delete.setText(tr("inventory.btn_delete"))
        self.search_input.setPlaceholderText(tr("inventory.search_placeholder"))
        self.real_view.set_placeholder(tr("inventory.real_image"))
        from utils.ui_settings import restore_column_widths
        new_columns = _build_columns()
        self.data_table.columns = new_columns
        self.data_table.table.setHorizontalHeaderLabels([c[0] for c in new_columns])
        saved_widths = restore_column_widths("inventory_materials")
        self.data_table.restore_column_widths(saved_widths)
        self.data_table.retranslate_ui()
        self.shelf_view.retranslate_ui()

    # ---------- 槽函数 ----------

    def _on_add_material(self):
        """新增物料——编码相同则累计数量（O(1) 查重）"""
        dialog = MaterialInputDialog(self)
        try:
            if dialog.exec() == QDialog.Accepted:
                data = dialog.get_data()
                code = data.get("material_code", "")

                # 通过字典 O(1) 查重
                existing = self._data_by_code.get(code)

                if existing:
                    old_qty = existing.get("stock_qty", 0)
                    add_qty = data.get("stock_qty", 0)
                    new_qty = old_qty + add_qty

                    toast_success(
                        self,
                        tr("toast.accumulated", code=code, name=data.get("material_name", ""), add=add_qty, total=new_qty)
                    )

                    update_data = dict(existing)
                    update_data["stock_qty"] = new_qty
                    self.update_material.emit(str(existing.get("id", "")), update_data)
                else:
                    self.add_material.emit(data)
        finally:
            dialog.deleteLater()

    def _on_edit_material(self, row_data: dict):
        """双击行编辑物料"""
        dialog = MaterialInputDialog(self, row_data)
        try:
            if dialog.exec() == QDialog.Accepted:
                data = dialog.get_data()
                material_id = str(row_data.get("id", ""))
                if material_id:
                    self.update_material.emit(material_id, data)
        finally:
            dialog.deleteLater()

    def _on_edit_selected(self):
        """编辑当前选中行"""
        row_data = self.data_table.get_selected_row()
        if not row_data:
            toast_warning(self, tr("inventory.select_edit"))
            return
        self._on_edit_material(row_data)

    def _on_delete_selected(self):
        """删除当前选中行"""
        row_data = self.data_table.get_selected_row()
        if not row_data:
            toast_warning(self, tr("inventory.select_delete"))
            return
        material_id = str(row_data.get("id", ""))
        material_name = row_data.get("material_name", "")
        if show_confirm(
            self, tr("inventory.confirm_delete_title"),
            tr("inventory.confirm_delete_text", name=material_name),
            dialog_type="warning"
        ) and material_id:
            self.delete_material.emit(material_id)

    def _on_refresh(self):
        """刷新数据"""
        self.refresh_requested.emit()

    def _on_export(self):
        """导出数据到 Excel"""
        if not self._data:
            toast_warning(self, tr("toast.no_data_export"))
            return
        try:
            exporter = ExcelExporter()
            filepath = exporter.export_inventory(self._data)
            toast_success(self, tr("toast.export_success", path=filepath))
        except ImportError:
            toast_error(
                self,
                tr("toast.install_openpyxl")
            )
        except (OSError, IOError, ValueError, RuntimeError) as e:
            toast_error(self, tr("toast.export_failed", error=str(e)))
        except Exception as e:
            toast_error(self, tr("toast.export_failed", error=str(e)))

    # ---------- 图片导入辅助方法（已抽取到 utils/excel_image_extractor）----------

    @staticmethod
    def _save_image_bytes(image_data: bytes, target_dir: str, prefix: str = "") -> str:
        """将图片二进制数据保存到指定目录，返回绝对路径"""
        if not image_data:
            return ""
        ext = guess_image_ext(image_data)
        from hashlib import md5
        hash_str = md5(image_data).hexdigest()[:8]
        new_name = f"{prefix}{hash_str}{ext}"
        dest_path = os.path.join(target_dir, new_name)
        if os.path.exists(dest_path):
            return os.path.abspath(dest_path)
        os.makedirs(target_dir, exist_ok=True)
        with open(dest_path, 'wb') as f:
            f.write(image_data)
        return os.path.abspath(dest_path)


    def _on_import_material(self):
        """从Excel导入物料（支持传统浮动图片 + 单元格内嵌图片）"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("mat_dialog.import_title"), "", tr("dialog.excel_filter")
        )
        if not file_path:
            return
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows or len(rows) < 2:
                toast_warning(self, tr("toast.file_empty"))
                return

            # 解析表头（支持中英文多语言表头）
            headers = [str(h).strip().lower() if h else "" for h in rows[0]]
            header_map = {}
            for idx, h in enumerate(headers):
                # 物料编码 / material code / código mat.
                if any(k in h for k in ("物料编码", "material_code", "código mat", "codigo mat", "编码")):
                    header_map["material_code"] = idx
                # 物料名称 / material name / nombre mat.
                elif any(k in h for k in ("物料名称", "material_name", "nombre mat", "名称")):
                    header_map["material_name"] = idx
                # 备注 / remark / nota
                elif any(k in h for k in ("备注", "remark", "nota")):
                    header_map["remark"] = idx
                # 分类 / category / categoría
                elif any(k in h for k in ("分类", "category", "categoría", "categoria")):
                    header_map["category"] = idx
                # 库存数量 / stock qty / cantidad
                elif any(k in h for k in ("库存数量", "stock_qty", "stock qty", "cantidad", "数量")):
                    header_map["stock_qty"] = idx
                # 存放位置 / location / ubicación
                elif any(k in h for k in ("存放位置", "location", "ubicación", "ubicacion", "位置")):
                    header_map["location"] = idx
                # 货架号 / shelf no / estante
                elif any(k in h for k in ("货架号", "shelf_no", "shelf no", "estante")):
                    header_map["shelf_no"] = idx

            if "material_code" not in header_map or "material_name" not in header_map:
                toast_error(self, tr("toast.invalid_headers"))
                return

            # ── 新增：识别图片列 ──
            for idx, h in enumerate(headers):
                if any(k in h for k in ("实物图", "real_image")):
                    header_map["real_image"] = idx

            # ── 提取图片（两种方式，richData 优先覆盖）──
            all_images = extract_all_images(file_path, ws)

            imported = []
            for row_idx, row in enumerate(rows[1:], start=2):
                if not row or not row[header_map["material_code"]]:
                    continue

                material_code = str(row[header_map["material_code"]]).strip()
                material_name = str(row[header_map["material_name"]]).strip() if "material_name" in header_map else ""
                if not material_name:
                    material_name = material_code

                # 获取各字段
                location = str(row[header_map["location"]]).strip() if "location" in header_map and row[header_map["location"]] else ""
                shelf_no = str(row[header_map["shelf_no"]]).strip() if "shelf_no" in header_map and row[header_map["shelf_no"]] else ""

                stock_qty = 0
                if "stock_qty" in header_map:
                    try:
                        stock_qty = int(row[header_map["stock_qty"]])
                    except (ValueError, TypeError):
                        stock_qty = 0

                # ── 提取该行的图片 ──
                real_image_path = ""
                if "real_image" in header_map:
                    col_num = header_map["real_image"] + 1
                    img_data = all_images.get((row_idx, col_num))
                    if img_data:
                        real_image_path = self._save_image_bytes(
                            img_data, REAL_IMAGES_DIR, f"{material_code}_real_"
                        )

                imported.append({
                    "material_code": material_code,
                    "material_name": material_name,
                    "location": location,
                    "shelf_no": shelf_no,
                    "stock_qty": stock_qty,
                    "unit": "PCS",
                    "real_image": real_image_path,
                })

            if not imported:
                toast_warning(self, tr("toast.no_valid_data"))
                return

            self.import_materials.emit(imported)
            toast_success(self, tr("toast.import_success", count=len(imported)))
        except ImportError:
            toast_error(self, tr("toast.install_openpyxl"))
        except (OSError, IOError, ValueError, RuntimeError, KeyError) as e:
            toast_error(self, tr("toast.import_failed", error=str(e)))
        except Exception as e:
            toast_error(self, tr("toast.import_failed", error=str(e)))

    def _on_search(self):
        """搜索过滤（回车或失焦时执行）"""
        self._search_timer.stop()
        self._search_keyword = self.search_input.text().strip()
        self._do_search()

    def _on_search_delayed(self, text: str):
        """输入时实时过滤（防抖 200ms）"""
        keyword = text.strip()
        if keyword == self._search_keyword:
            return
        self._search_keyword = keyword
        self._search_timer.stop()
        self._search_timer.start(200)

    def _do_search(self):
        """执行搜索过滤"""
        self.data_table.filter_data(self._search_keyword)

    def _on_row_selected(self, row_data: dict):
        """行选中时：货架网格高亮对应位置 + 实物图加载"""
        # 货架网格：高亮选中行的 shelf_no 对应位置
        self.shelf_view.set_selected_shelf_no(row_data.get("shelf_no", ""))

        # 实物图：保留原加载逻辑（缩略图 + 后台升级原图）
        self._load_counter += 1
        self._current_load_id = self._load_counter
        current_id = self._current_load_id

        self._load_image(row_data.get("real_image", ""), self.real_view,
                         tr("inventory.real_image_name"), current_id)

    def _load_image(self, image_path: str, view: ZoomableImageView,
                    label_name: str, load_id: int):
        """渐进式加载：缩略图即时显示 → 300ms 后后台升级原图"""
        if not image_path:
            view.set_placeholder(tr("inventory.no_image", type=label_name))
            return

        # 步骤 1: 快速加载缩略图(适配视图大小)
        thumb = self._image_cache.load_thumbnail(
            image_path, max(view.width() - 20, 200), max(view.height() - 20, 200)
        )
        if thumb is not None:
            view.set_image_thumbnail(thumb, source_path=image_path)
        else:
            view.set_placeholder(tr("inventory.no_image", type=label_name))
            return

        # 步骤 2: 安排后台升级原图(去重)
        if not any(item[2] == load_id and item[0] == image_path
                   for item in self._pending_upgrades):
            self._pending_upgrades.append((image_path, view, load_id))

        # 重启定时器(合并多次请求)
        self._upgrade_timer.start()

    def _do_upgrade_full_res(self):
        """定时器触发：在后台线程中加载原图"""
        if self._cleaned_up or not self._pending_upgrades:
            return

        current_id = self._current_load_id
        to_load = [(path, view) for path, view, lid in self._pending_upgrades
                   if lid == current_id and view.has_image()]
        self._pending_upgrades.clear()

        for path, view in to_load:
            worker = _ImageLoadWorker(self._image_cache, path, path)
            self._active_workers.append(worker)
            worker.finished_pixmap.connect(
                lambda request_id, pixmap, v=view, req_path=path:
                    self._on_full_res_loaded(request_id, pixmap, v, req_path, current_id)
            )
            worker.finished.connect(lambda w=worker: self._on_worker_done(w))
            worker.finished.connect(worker.deleteLater)
            worker.start()

    def _on_worker_done(self, worker: QThread):
        """线程完成后从活跃列表移除"""
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def _cleanup_workers(self):
        """安全清理所有活跃的后台线程（在视图销毁前调用）"""
        self._cleaned_up = True
        try:
            self._upgrade_timer.stop()
        except RuntimeError:
            pass
        self._pending_upgrades.clear()
        # 等待所有活跃线程完成（最多 2 秒）
        for worker in list(self._active_workers):
            try:
                if worker.isRunning():
                    worker.quit()
                    worker.wait(2000)
            except RuntimeError:
                pass
        self._active_workers.clear()

    def _on_full_res_loaded(self, request_id: str, pixmap: QPixmap,
                            view: ZoomableImageView, path: str, load_id: int):
        """原图加载完成：升级显示"""
        if self._cleaned_up:
            return
        if load_id != self._current_load_id:
            return  # 已切换到其他行，丢弃过期结果
        if view.has_image() and not pixmap.isNull():
            view.upgrade_to_full_res(pixmap)

    def clear_memory(self):
        """清理内存缓存（窗口关闭时调用）"""
        self._cleanup_workers()
        self._image_cache.clear()
        # 清空图片视图，释放 pixmap
        self.shelf_view.clear()
        self.real_view.clear()
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
        self.real_view.clear()

    def showEvent(self, event):
        """视图重新显示时重置清理标志，恢复图片加载能力"""
        super().showEvent(event)
        self._cleaned_up = False

    # ---------- 公共接口 ----------

    def set_data(self, data: list):
        """设置表格数据"""
        self._data = data
        # 构建 O(1) 查重字典
        self._data_by_code = {}
        for m in data:
            code = m.get("material_code", "")
            if code:
                self._data_by_code[code] = m
        self.data_table.set_data(data)
        # 更新货架网格（所有物料按 shelf_no 分布）
        self.shelf_view.set_materials(data)