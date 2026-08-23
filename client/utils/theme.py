"""
主题样式模块
定义亮色主题 QSS 样式表，统一界面视觉风格
"""

# ==================== 颜色常量（供代码中直接引用，避免魔法数字） ====================
COLORS = {
    # 绿色系（成功/在线）
    "success_light": "#f0fdf4",
    "success": "#22c55e",
    "success_hover": "#16a34a",
    "success_active": "#15803d",
    "success_deep": "#166534",
    "success_darker": "#14532d",
    "success_emerald": "#059669",

    # 黄色系（警告/待同步）
    "warning": "#d97706",

    # 红色系（错误/离线）
    "danger": "#dc2626",
    "danger_hover": "#b91c1c",
}


# 亮色主题 QSS 样式表
LIGHT_THEME_QSS = """
/* ==================== 全局基础样式 ==================== */
QWidget {
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
    font-size: 13px;
    color: #1a1a2e;
    background-color: #f5f7fa;
}

/* ==================== 主窗口 ==================== */
QMainWindow {
    background-color: #f5f7fa;
}

/* ==================== 导航栏 ==================== */
QWidget#navBar {
    background-color: #ffffff;
    border-right: 1px solid #e0e4e8;
}

QPushButton#navButton {
    background-color: transparent;
    color: #5a6573;
    border: none;
    border-radius: 6px;
    padding: 12px 16px;
    text-align: left;
    font-size: 14px;
}

QPushButton#navButton:hover {
    background-color: #eef2f7;
    color: #2563eb;
}

QPushButton#navButton:checked {
    background-color: #e0e7ff;
    color: #2563eb;
    font-weight: bold;
}

QPushButton#navButton:pressed {
    background-color: #dbe4ff;
}

/* ==================== 顶部工具栏 ==================== */
QWidget#toolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e0e4e8;
    padding: 8px 16px;
}

/* ==================== 按钮 ==================== */
QPushButton {
    background-color: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    min-height: 32px;
}

QPushButton:hover {
    background-color: #1d4ed8;
}

QPushButton:pressed {
    background-color: #1e40af;
}

QPushButton:disabled {
    background-color: #cbd5e1;
    color: #94a3b8;
}

QPushButton#secondaryButton {
    background-color: #ffffff;
    color: #2563eb;
    border: 1px solid #2563eb;
}

QPushButton#secondaryButton:hover {
    background-color: #e0e7ff;
}

QPushButton#dangerButton {
    background-color: #dc2626;
}

QPushButton#dangerButton:hover {
    background-color: #b91c1c;
}

/* ==================== 输入框 ==================== */
QLineEdit {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 8px 12px;
    color: #1a1a2e;
    font-size: 13px;
}

QLineEdit:focus {
    border: 2px solid #2563eb;
    outline: none;
}

QLineEdit:disabled {
    background-color: #f1f5f9;
    color: #94a3b8;
}

/* ==================== 下拉框 ==================== */
QComboBox {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 8px 12px;
    color: #1a1a2e;
    font-size: 13px;
    min-height: 32px;
}

QComboBox:focus {
    border: 2px solid #2563eb;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #5a6573;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    selection-background-color: #e0e7ff;
    selection-color: #2563eb;
}

/* ==================== 表格 ==================== */
QTableWidget, QTableView, QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #e0e4e8;
    border-radius: 8px;
    gridline-color: #e0e4e8;
    selection-background-color: #e0e7ff;
    selection-color: #1a1a2e;
    alternate-background-color: #f8fafc;
    outline: none;
}

QTableWidget::item, QTableView::item {
    padding: 8px 12px;
    border-bottom: 1px solid #f1f5f9;
}

QTableWidget::item:selected, QTableView::item:selected {
    background-color: #e0e7ff;
    color: #1a1a2e;
    border: none;
    outline: none;
}

QTableWidget::item:focus, QTableView::item:focus {
    border: none;
    outline: none;
}

QHeaderView::section {
    background-color: #f1f5f9;
    color: #475569;
    font-weight: bold;
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid #e0e4e8;
    border-right: 1px solid #e0e4e8;
}

QHeaderView::section:last {
    border-right: none;
}

/* ==================== 标签页 ==================== */
QTabWidget::pane {
    border: 1px solid #e0e4e8;
    border-radius: 8px;
    background-color: #ffffff;
    top: -1px;
}

QTabBar::tab {
    background-color: #f1f5f9;
    color: #5a6573;
    padding: 10px 20px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #e0e4e8;
    border-bottom: none;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    color: #2563eb;
    font-weight: bold;
    border-bottom: 2px solid #2563eb;
}

QTabBar::tab:hover:!selected {
    background-color: #e0e7ff;
    color: #2563eb;
}

/* ==================== 滚动条 ==================== */
QScrollBar:vertical {
    background-color: #f1f5f9;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background-color: #cbd5e1;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #94a3b8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #f1f5f9;
    height: 8px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background-color: #cbd5e1;
    border-radius: 4px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #94a3b8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ==================== 分组框 ==================== */
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e0e4e8;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    color: #1a1a2e;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: #2563eb;
}

/* ==================== 状态栏 ==================== */
QStatusBar {
    background-color: #ffffff;
    color: #5a6573;
    border-top: 1px solid #e0e4e8;
    padding: 4px 16px;
}

/* ==================== 对话框 ==================== */
QDialog {
    background-color: #f5f7fa;
}

QDialog QPushButton {
    min-width: 80px;
}

QMessageBox {
    background-color: #ffffff;
    border: 1px solid #e0e4e8;
    border-radius: 10px;
}

QMessageBox QLabel {
    color: #1a1a2e;
    font-size: 14px;
    padding: 8px;
}

QMessageBox QPushButton {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 8px 20px;
    min-width: 80px;
    min-height: 32px;
    font-size: 13px;
}

QMessageBox QPushButton:hover {
    background-color: #f1f5f9;
    border-color: #94a3b8;
}

QMessageBox QPushButton:focus {
    outline: none;
}

/* ==================== 菜单 ==================== */
QMenu {
    background-color: #ffffff;
    border: 1px solid #e0e4e8;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #e0e7ff;
    color: #2563eb;
}

QMenu::separator {
    height: 1px;
    background-color: #e0e4e8;
    margin: 4px 8px;
}

/* ==================== 工具提示 ==================== */
QToolTip {
    background-color: #1a1a2e;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ==================== 分页控件 ==================== */
QWidget#pageControl {
    background-color: #ffffff;
    border-top: 1px solid #e0e4e8;
    padding: 8px 16px;
}

QPushButton#pageButton {
    background-color: #ffffff;
    color: #5a6573;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 4px 12px;
    min-width: 32px;
    min-height: 28px;
}

QPushButton#pageButton:hover {
    background-color: #e0e7ff;
    color: #2563eb;
    border-color: #2563eb;
}

QPushButton#pageButton:checked {
    background-color: #2563eb;
    color: #ffffff;
    border-color: #2563eb;
}

QPushButton#pageButton:disabled {
    background-color: #f1f5f9;
    color: #cbd5e1;
    border-color: #e0e4e8;
}

/* ==================== 搜索栏 ==================== */
QWidget#searchBar {
    background-color: #ffffff;
    border: 1px solid #e0e4e8;
    border-radius: 8px;
    padding: 12px 16px;
}

/* ==================== 同步状态指示器 ==================== */
QLabel#syncStatusOnline {
    color: #059669;
    font-weight: bold;
}

QLabel#syncStatusOffline {
    color: #dc2626;
    font-weight: bold;
}

QLabel#syncStatusSyncing {
    color: #d97706;
    font-weight: bold;
}

/* ==================== 表单标签 ==================== */
QLabel#formLabel {
    color: #475569;
    font-weight: 500;
    min-width: 80px;
}

/* ==================== 数字输入框 ==================== */
QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 8px 12px;
    color: #1a1a2e;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 2px solid #2563eb;
}

/* ==================== 日期选择器 ==================== */
QDateEdit {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 8px 12px;
    color: #1a1a2e;
}

QDateEdit:focus {
    border: 2px solid #2563eb;
}

/* ==================== 日历弹窗 ==================== */
QCalendarWidget {
    background-color: #ffffff;
    border: 1px solid #e0e4e8;
    border-radius: 8px;
}

QCalendarWidget QWidget#qt_calendar_navigationbar {
    background-color: #2563eb;
    color: #ffffff;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 4px;
}

QCalendarWidget QToolButton {
    color: #ffffff;
    background-color: transparent;
    border: none;
    font-weight: bold;
    font-size: 14px;
    padding: 4px 8px;
}

QCalendarWidget QToolButton:hover {
    background-color: rgba(255, 255, 255, 0.2);
    border-radius: 4px;
}

QCalendarWidget QMenu {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #e0e4e8;
    border-radius: 6px;
    padding: 4px;
}

QCalendarWidget QMenu::item:selected {
    background-color: #e0e7ff;
    color: #2563eb;
}

QCalendarWidget QSpinBox {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 2px 6px;
}

QCalendarWidget QAbstractItemView:enabled {
    background-color: #ffffff;
    color: #1a1a2e;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    border: none;
    outline: none;
}

QCalendarWidget QAbstractItemView:disabled {
    background-color: #f1f5f9;
    color: #cbd5e1;
}

QCalendarWidget QTableView {
    background-color: #ffffff;
    alternate-background-color: #ffffff;
    border: none;
    gridline-color: transparent;
    outline: none;
}

QCalendarWidget QTableView::item {
    padding: 6px;
    border-radius: 4px;
    color: #1a1a2e;
    background-color: #ffffff;
}

QCalendarWidget QTableView::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}

QCalendarWidget QTableView::item:hover {
    background-color: #e0e7ff;
    color: #2563eb;
}

QCalendarWidget QWidget#qt_calendar_prevmonth,
QCalendarWidget QWidget#qt_calendar_nextmonth {
    background-color: transparent;
    color: #ffffff;
    border-radius: 4px;
    qproperty-icon: none;
    width: 24px;
    height: 24px;
}

QCalendarWidget QWidget#qt_calendar_prevmonth:hover,
QCalendarWidget QWidget#qt_calendar_nextmonth:hover {
    background-color: rgba(255, 255, 255, 0.2);
}

/* ==================== 文本域 ==================== */
QTextEdit {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 8px 12px;
    color: #1a1a2e;
}

QTextEdit:focus {
    border: 2px solid #2563eb;
}
"""


def apply_theme(app):
    """应用亮色主题到 QApplication"""
    app.setStyleSheet(LIGHT_THEME_QSS)
