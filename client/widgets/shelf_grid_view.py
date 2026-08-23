"""货架/货柜网格视图组件
固定网格布局，根据物料的 shelf_no（如 HJ1-2-3 / HG1-3-5）解析类型、行号、列号并高亮。

shelf_no 格式：类型前缀+编号-行号-列号
- HJ1-2-3  → 类型=HJ(货架), 前缀=HJ1, 行=2, 列=3, 网格=4×4
- HG1-3-5  → 类型=HG(货柜), 前缀=HG1, 行=3, 列=5, 网格=4×6
- 行号从下往上编号：第1层在最下面
- 列号从左往右编号
- 支持分隔符：-  *  _
"""
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
)
from PySide6.QtCore import Qt, Signal

from i18n import tr
from utils.theme import COLORS


GRID_ROWS = 4
GRID_COLS = 4

# 前缀类型 → 网格配置
_SHELF_TYPE_CONFIG = {
    "HJ": {"rows": 4, "cols": 4, "label": "货架"},
    "HG": {"rows": 6, "cols": 4, "label": "货柜"},
}

# 支持的分隔符：短横线、星号、下划线
_SHELF_SEPARATORS = r'[-*_]'


def _get_shelf_type(prefix: str) -> str:
    """从前缀中提取货架类型标识（HJ/HG），如 HJ1 → HJ"""
    if not prefix:
        return None
    if prefix.startswith("HJ"):
        return "HJ"
    if prefix.startswith("HG"):
        return "HG"
    return None


def parse_shelf_no(shelf_no: str) -> tuple:
    """解析 shelf_no 字符串，返回 (前缀, 行号, 列号) 元组（行号列号为 1-based）。
    解析失败返回 (None, None, None)。

    支持格式：
      前缀-行号-列号  （如 HJ1-2-3, HG1-3-5）
      前缀*行号*列号  （如 HJ1*2*3, HG1*3*5）
      前缀_行号_列号  （如 HJ1_2_3, HG1_3_5）
    三种分隔符也可以混合使用。
    """
    if not shelf_no:
        return None, None, None
    parts = re.split(_SHELF_SEPARATORS, str(shelf_no).strip())
    if len(parts) < 3:
        return None, None, None
    try:
        prefix = parts[0].strip()
        row = int(parts[1])
        col = int(parts[2])
        return prefix, row, col
    except (ValueError, IndexError):
        return None, None, None


class ShelfCell(QFrame):
    """单个货架格子组件"""

    clicked = Signal(int, int)  # (row, col) 0-based

    def __init__(self, row: int, col: int, total_rows: int = GRID_ROWS, parent=None):
        super().__init__(parent)
        self._row = row
        self._col = col
        self._total_rows = total_rows
        self._materials: list = []
        self._is_highlighted = False
        self._has_material = False

        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(60)

        self._init_ui()
        self._update_style()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # 坐标标签（右上角）—— 行号从下往上：第1层在最下面
        shelf_row_1based = self._total_rows - self._row
        self._coord_label = QLabel(f"{shelf_row_1based}-{self._col + 1}")
        self._coord_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self._coord_label.setStyleSheet("color: #94a3b8; font-size: 10px;")
        layout.addWidget(self._coord_label)

        layout.addStretch()

        self._count_label = QLabel("")
        self._count_label.setAlignment(Qt.AlignCenter)
        self._count_label.setWordWrap(True)
        layout.addWidget(self._count_label)

        self._code_label = QLabel("")
        self._code_label.setAlignment(Qt.AlignCenter)
        self._code_label.setWordWrap(True)
        self._code_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(self._code_label)

    def set_materials(self, materials: list):
        self._materials = materials
        self._has_material = len(materials) > 0

        if not materials:
            self._count_label.setText("")
            self._count_label.setStyleSheet("")
            self._code_label.setText("")
            self.setToolTip("")
        else:
            count = len(materials)
            if count == 1:
                self._count_label.setText(str(materials[0].get("stock_qty", 0)))
            else:
                self._count_label.setText(f"{count} 种")
            self._count_label.setStyleSheet("font-weight: bold; font-size: 13px;")

            codes = [m.get("material_code", "") for m in materials[:2]]
            extra = "" if count <= 2 else f"\n+{count - 2}"
            self._code_label.setText("\n".join(codes) + extra)

            tip_parts = []
            for m in materials:
                code = m.get("material_code", "")
                name = m.get("material_name", "")
                qty = m.get("stock_qty", 0)
                tip_parts.append(f"• {code} - {name} (库存:{qty})")
            self.setToolTip("\n".join(tip_parts))

        self._update_style()

    def set_highlighted(self, highlighted: bool):
        self._is_highlighted = highlighted
        self._update_style()

    def _update_style(self):
        if self._is_highlighted:
            bg = COLORS.get("danger", "#dc2626")
            border = COLORS.get("danger_hover", "#b91c1c")
            self._coord_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 10px;")
            self._count_label.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 14px;")
            self._code_label.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 10px;")
        elif self._has_material:
            bg = "#2563eb"
            border = "#1d4ed8"
            self._coord_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 10px;")
            self._count_label.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px;")
            self._code_label.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 10px;")
        else:
            bg = "#e0e4e8"
            border = "#cbd5e1"
            self._coord_label.setStyleSheet("color: #94a3b8; font-size: 10px;")

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 2px solid {border};
                border-radius: 6px;
            }}
            QFrame:hover {{
                border: 2px solid #f59e0b;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._row, self._col)
        super().mousePressEvent(event)


class ShelfGridView(QWidget):
    """货架/货柜网格视图（支持多类型切换，HJ=4x4, HG=4x6）"""

    cell_clicked = Signal(int, int)
    shelf_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_materials: list = []
        self._selected_shelf_no: str = ""
        self._shelf_prefixes: list = []
        self._current_prefix: str = ""

        self._grid_rows = GRID_ROWS
        self._grid_cols = GRID_COLS
        self._grid_label = "货架"

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        self._title_label = QLabel(tr("inventory.shelf_grid"))
        self._title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #1a1a2e;")
        title_row.addWidget(self._title_label)
        title_row.addStretch()

        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(12)

        self._legend_empty = QLabel("  空")
        self._legend_empty.setStyleSheet(
            "background-color: #e0e4e8; border: 1px solid #cbd5e1; "
            "border-radius: 3px; padding: 2px 8px; font-size: 11px; color: #5a6573;"
        )
        self._legend_filled = QLabel("  有物料")
        self._legend_filled.setStyleSheet(
            "background-color: #2563eb; border: 1px solid #1d4ed8; "
            "border-radius: 3px; padding: 2px 8px; font-size: 11px; color: #ffffff;"
        )
        self._legend_highlight = QLabel("  当前选中")
        self._legend_highlight.setStyleSheet(
            f"background-color: {COLORS.get('danger', '#dc2626')}; "
            f"border: 1px solid {COLORS.get('danger_hover', '#b91c1c')}; "
            "border-radius: 3px; padding: 2px 8px; font-size: 11px; color: #ffffff;"
        )

        legend_layout.addWidget(self._legend_empty)
        legend_layout.addWidget(self._legend_filled)
        legend_layout.addWidget(self._legend_highlight)
        title_row.addLayout(legend_layout)

        layout.addLayout(title_row)

        self._build_grid(GRID_ROWS, GRID_COLS)

    def _build_grid(self, rows: int, cols: int):
        """重建网格（移除旧容器，按新尺寸创建格子）"""
        # 移除旧 grid_container
        try:
            for i in range(self.layout().count() - 1, -1, -1):
                item = self.layout().itemAt(i)
                if item:
                    w = item.widget()
                    if w and w.objectName() == "_grid_container":
                        self.layout().removeItem(item)
                        w.deleteLater()
                        break
        except RuntimeError:
            pass

        grid_container = QFrame()
        grid_container.setObjectName("_grid_container")
        grid_container.setStyleSheet(
            "QFrame { background-color: #f8fafc; border: 1px solid #e0e4e8; border-radius: 8px; }"
        )
        grid_layout = QGridLayout(grid_container)
        grid_layout.setContentsMargins(8, 8, 8, 8)
        grid_layout.setSpacing(4)

        self._cells: list = []
        for row in range(rows):
            row_cells = []
            for col in range(cols):
                cell = ShelfCell(row, col, total_rows=rows)
                cell.clicked.connect(self._on_cell_clicked)
                grid_layout.addWidget(cell, row, col)
                row_cells.append(cell)
            self._cells.append(row_cells)

        self.layout().addWidget(grid_container, 1)
        self._grid_rows = rows
        self._grid_cols = cols

    def _update_title(self):
        """更新标题"""
        if self._current_prefix:
            self._title_label.setText(f"🗂️ {self._current_prefix} {self._grid_label}布局")
        else:
            self._title_label.setText(tr("inventory.shelf_grid"))

    def _switch_grid_type(self, prefix: str):
        """根据前缀确定网格类型，必要时重建网格"""
        stype = _get_shelf_type(prefix)
        if stype and stype in _SHELF_TYPE_CONFIG:
            cfg = _SHELF_TYPE_CONFIG[stype]
            new_rows, new_cols = cfg["rows"], cfg["cols"]
            new_label = cfg["label"]
        else:
            new_rows, new_cols, new_label = GRID_ROWS, GRID_COLS, "货架"

        if (new_rows, new_cols) != (self._grid_rows, self._grid_cols):
            self._build_grid(new_rows, new_cols)
            self._grid_label = new_label

    def set_materials(self, materials: list):
        """设置所有物料数据"""
        self._all_materials = materials

        prefix_count: dict = {}
        for m in materials:
            prefix, _, _ = parse_shelf_no(m.get("shelf_no", ""))
            if prefix:
                prefix_count[prefix] = prefix_count.get(prefix, 0) + 1

        self._shelf_prefixes = sorted(
            prefix_count.keys(),
            key=lambda p: (-prefix_count[p], p)
        )

        if self._shelf_prefixes and self._current_prefix not in self._shelf_prefixes:
            self._current_prefix = self._shelf_prefixes[0]

        self._switch_grid_type(self._current_prefix)
        self._update_title()
        self._refresh_grid()
        self._apply_highlight()

    def _refresh_grid(self):
        """根据当前货架前缀刷新网格显示"""
        rows = self._grid_rows
        cols = self._grid_cols
        cell_materials: dict = {}
        for m in self._all_materials:
            prefix, row_1based, col_1based = parse_shelf_no(m.get("shelf_no", ""))
            if prefix is None or prefix != self._current_prefix:
                continue
            if row_1based is None or col_1based is None:
                continue
            row_idx = rows - row_1based
            col_idx = col_1based - 1
            if 0 <= row_idx < rows and 0 <= col_idx < cols:
                key = (row_idx, col_idx)
                if key not in cell_materials:
                    cell_materials[key] = []
                cell_materials[key].append(m)

        for row in range(rows):
            for col in range(cols):
                self._cells[row][col].set_materials(cell_materials.get((row, col), []))

    def set_selected_shelf_no(self, shelf_no: str):
        """设置当前选中行的货架号，自动切换货架并高亮"""
        self._selected_shelf_no = shelf_no

        prefix, _, _ = parse_shelf_no(shelf_no)
        if prefix and prefix in self._shelf_prefixes and prefix != self._current_prefix:
            self._current_prefix = prefix
            self._switch_grid_type(prefix)
            self._update_title()
            self._refresh_grid()

        self._apply_highlight()

    def _apply_highlight(self):
        """根据选中的货架号应用高亮"""
        rows = self._grid_rows
        cols = self._grid_cols
        for row in range(rows):
            for col in range(cols):
                self._cells[row][col].set_highlighted(False)

        prefix, row_1based, col_1based = parse_shelf_no(self._selected_shelf_no)
        if prefix and prefix != self._current_prefix:
            return
        if row_1based is not None and col_1based is not None:
            row_idx = rows - row_1based
            col_idx = col_1based - 1
            if 0 <= row_idx < rows and 0 <= col_idx < cols:
                self._cells[row_idx][col_idx].set_highlighted(True)

    def _on_cell_clicked(self, row: int, col: int):
        shelf_row = self._grid_rows - 1 - row
        self.cell_clicked.emit(shelf_row, col)

    def clear(self):
        self._all_materials = []
        self._selected_shelf_no = ""
        self._shelf_prefixes = []
        self._current_prefix = ""
        self._grid_label = "货架"
        self._build_grid(GRID_ROWS, GRID_COLS)
        self._update_title()
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                self._cells[row][col].set_materials([])
                self._cells[row][col].set_highlighted(False)

    def retranslate_ui(self):
        self._update_title()
