"""可缩放图片查看组件 V2

增强特性:
- 渐进式加载: 缩略图即时显示，原图懒加载
- 鼠标滚轮缩放(以鼠标位置为锚点，支持平滑加速)
- 双击切换 1:1 原始尺寸 / 适应窗口
- 缩放级别指示器(右下角浮层显示当前缩放百分比)
- 支持拖拽平移，ScrollHandDrag 模式
- 占位文字模式(无图片时显示提示)
- 后台异步加载原图(不阻塞 UI)

用法:
    view = ZoomableImageView()
    view.set_placeholder("📷 货架图", "background-color: #e0e4e8;")
    view.set_image_thumbnail(thumb_pixmap)  # 即时显示缩略图
    view.upgrade_to_full_res(full_pixmap)   # 升级为原图(可选)
    view.clear()                             # 清空图片
"""

from typing import Optional

from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QStackedWidget, QLabel, QVBoxLayout, QWidget, QFrame,
)
from PySide6.QtCore import Qt, QRectF, QTimer, Signal
from PySide6.QtGui import QPixmap, QPainter, QWheelEvent, QMouseEvent


class _ZoomableGraphicsView(QGraphicsView):
    """内部 QGraphicsView，重写 wheelEvent 实现平滑缩放"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background: transparent;")
        self.setMouseTracking(True)
        self._zoom_level: float = 1.0

    def wheelEvent(self, event: QWheelEvent):
        """鼠标滚轮放大/缩小，以鼠标位置为锚点，带缩放级别钳制"""
        factor = 1.15
        delta = event.angleDelta().y()
        if delta > 0:
            new_level = self._zoom_level * factor
        else:
            new_level = self._zoom_level / factor

        # 钳制缩放级别: 5% ~ 500%
        new_level = max(0.05, min(5.0, new_level))
        self._zoom_level = new_level

        actual_factor = factor if delta > 0 else (1.0 / factor)
        self.scale(actual_factor, actual_factor)

        # 通知外部缩放级别变化
        self.on_zoom_level_changed(self._zoom_level)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击切换: 1:1 原始尺寸 <-> 适应窗口"""
        if event.button() == Qt.LeftButton:
            if self._zoom_level <= 1.01:
                # 当前适应窗口 → 切到 1:1
                self._set_zoom(1.0)
            else:
                # 当前放大 → 回到适应窗口
                self._fit_to_window()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _set_zoom(self, level: float):
        """设置精确缩放级别"""
        self.resetTransform()
        self.scale(level, level)
        self._zoom_level = level
        self.on_zoom_level_changed(level)

    def _fit_to_window(self):
        """适应窗口大小"""
        items = self.scene().items()
        if items:
            rect = items[0].boundingRect()
            margin = 4
            margin_rect = QRectF(rect.x() - margin, rect.y() - margin,
                                 rect.width() + margin * 2,
                                 rect.height() + margin * 2)
            self.fitInView(margin_rect, Qt.KeepAspectRatio)
            # 计算实际缩放级别
            transform = self.transform()
            self._zoom_level = (transform.m11() ** 2 + transform.m12() ** 2) ** 0.5
            self.on_zoom_level_changed(self._zoom_level)

    def on_zoom_level_changed(self, level: float):
        """缩放级别变化回调(由 ZoomableImageView 重写连接)"""
        pass


class ZoomableImageView(QWidget):
    """可缩放图片查看组件 V2

    特性:
    - 渐进式加载: set_image_thumbnail() 即时显示 → upgrade_to_full_res() 升级原图
    - 滚轮缩放: 以鼠标位置为锚点，缩放范围 5%-500%
    - 双击切换: 适应窗口 ↔ 1:1 原始尺寸
    - 缩放指示: 右下角浮层显示当前缩放百分比
    - 支持拖拽平移(ScrollHandDrag)
    """

    # 信号: 缩放级别变化
    zoom_level_changed = Signal(float)

    def __init__(self, parent=None, placeholder_style: str = ""):
        super().__init__(parent)
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._original_pixmap: Optional[QPixmap] = None
        self._is_full_res: bool = False  # 当前是否为原图
        self._display_path: str = ""     # 当前显示的图片路径(用于升级)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # ---- 页面 0：占位文字 ----
        self._placeholder_label = QLabel()
        self._placeholder_label.setAlignment(Qt.AlignCenter)
        self._placeholder_label.setWordWrap(True)
        if placeholder_style:
            self._placeholder_label.setStyleSheet(placeholder_style)
        self._stack.addWidget(self._placeholder_label)  # index 0

        # ---- 页面 1：可缩放图片视图 ----
        self._scene = QGraphicsScene(self)
        self._view = _ZoomableGraphicsView()
        self._view.setScene(self._scene)
        # 连接缩放回调
        self._view.on_zoom_level_changed = self._on_zoom_changed
        self._stack.addWidget(self._view)  # index 1

        # ---- 缩放级别指示器 ----
        self._zoom_indicator = QLabel("", self)
        self._zoom_indicator.setAlignment(Qt.AlignCenter)
        self._zoom_indicator.setFixedHeight(22)
        self._zoom_indicator.setStyleSheet(
            "background-color: rgba(15, 23, 42, 0.75);"
            "color: white;"
            "border-radius: 11px;"
            "padding: 0 10px;"
            "font-size: 11px;"
            "font-weight: bold;"
        )
        self._zoom_indicator.hide()
        self._zoom_indicator.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # 缩放指示自动隐藏定时器
        self._indicator_timer = QTimer(self)
        self._indicator_timer.setSingleShot(True)
        self._indicator_timer.setInterval(1500)
        self._indicator_timer.timeout.connect(lambda: self._zoom_indicator.hide())

        self._stack.setCurrentIndex(0)

    # ---- 公共 API ----

    def set_image(self, pixmap: QPixmap):
        """显示图片(原图或缩略图均可)，自动适应大小

        如果后续调用 upgrade_to_full_res()，会以原图替换当前显示。
        """
        if pixmap is None or pixmap.isNull():
            return
        self._original_pixmap = pixmap
        self._is_full_res = False
        self._display_path = ""
        self._show_pixmap(pixmap)

    def set_image_thumbnail(self, pixmap: QPixmap, source_path: str = ""):
        """设置缩略图用于即时显示

        Args:
            pixmap: 缩略图 QPixmap
            source_path: 原图路径(用于后续 upgrade_to_full_res)
        """
        if pixmap is None or pixmap.isNull():
            return
        self._original_pixmap = pixmap
        self._is_full_res = False
        self._display_path = source_path
        self._show_pixmap(pixmap)

    def upgrade_to_full_res(self, full_pixmap: QPixmap):
        """升级显示为原图(更高分辨率)

        Args:
            full_pixmap: 原图 QPixmap
        """
        if full_pixmap is None or full_pixmap.isNull():
            return
        self._original_pixmap = full_pixmap
        self._is_full_res = True
        self._display_path = ""

        # 保留当前缩放和位置，只替换 pixmap 内容
        if self._pixmap_item is not None:
            self._pixmap_item.setPixmap(full_pixmap)
            self._pixmap_item.setTransformationMode(Qt.SmoothTransformation)
        else:
            self._show_pixmap(full_pixmap)

    def set_placeholder(self, text: str, style: str = ""):
        """显示占位文字(清空图片)"""
        self._original_pixmap = None
        self._pixmap_item = None
        self._is_full_res = False
        self._display_path = ""
        self._scene.clear()
        self._placeholder_label.setText(text)
        if style:
            self._placeholder_label.setStyleSheet(style)
        self._stack.setCurrentIndex(0)
        self._zoom_indicator.hide()

    def set_placeholder_style(self, style: str):
        """更新占位文字的样式"""
        self._placeholder_label.setStyleSheet(style)

    def clear(self):
        """清空图片，回到占位模式(保留当前占位文字)"""
        self._original_pixmap = None
        self._pixmap_item = None
        self._is_full_res = False
        self._display_path = ""
        self._scene.clear()
        self._stack.setCurrentIndex(0)
        self._zoom_indicator.hide()

    def reset_zoom(self):
        """重置缩放到适应大小"""
        if self._pixmap_item is not None:
            self._view._fit_to_window()

    def zoom_to_100(self):
        """切换到 1:1 原始尺寸"""
        if self._pixmap_item is not None:
            self._view._set_zoom(1.0)

    def has_image(self) -> bool:
        """当前是否显示图片"""
        return self._pixmap_item is not None

    def is_full_res(self) -> bool:
        """当前是否为原图"""
        return self._is_full_res

    def get_current_zoom(self) -> float:
        """获取当前缩放级别"""
        return self._view._zoom_level

    def set_minimum_height(self, height: int):
        self.setMinimumHeight(height)

    def set_minimum_width(self, width: int):
        self.setMinimumWidth(width)

    # ---- 内部方法 ----

    def _show_pixmap(self, pixmap: QPixmap):
        """在 scene 中显示 pixmap 并适应窗口"""
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._pixmap_item.setTransformationMode(Qt.SmoothTransformation)

        self._view.resetTransform()
        self._fit_in_view()

        self._stack.setCurrentIndex(1)

    def _fit_in_view(self):
        """将图片适应到视图大小"""
        if self._pixmap_item is not None:
            rect = self._pixmap_item.boundingRect()
            margin = 4
            margin_rect = QRectF(rect.x() - margin, rect.y() - margin,
                                 rect.width() + margin * 2,
                                 rect.height() + margin * 2)
            self._view.fitInView(margin_rect, Qt.KeepAspectRatio)
            transform = self._view.transform()
            self._view._zoom_level = (transform.m11() ** 2 + transform.m12() ** 2) ** 0.5

    def _on_zoom_changed(self, level: float):
        """缩放级别变化: 更新指示器显示"""
        if level < 0.98 or level > 1.02:
            pct = int(level * 100)
            self._zoom_indicator.setText(f"🔍 {pct}%")
            self._position_indicator()
            self._zoom_indicator.show()
            self._indicator_timer.start()
            self.zoom_level_changed.emit(level)
        else:
            self._zoom_indicator.hide()

    def _position_indicator(self):
        """将指示器定位到右下角"""
        x = self.width() - self._zoom_indicator.width() - 12
        y = self.height() - self._zoom_indicator.height() - 8
        self._zoom_indicator.move(max(8, x), max(8, y))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 指示器跟随右下角
        if self._zoom_indicator.isVisible():
            self._position_indicator()
        # 组件大小变化时重新适应图片(仅适应模式)
        if self._pixmap_item is not None:
            self._fit_in_view()
