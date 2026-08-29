from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QTransform
from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView
from services import get_i18n_manager, get_logger

from ui.theme import get_current_theme, get_theme_colors

from editor.editor_model import EditorModel
from editor.render_coordinator import RenderCoordinator

from .graphics_view_input import GraphicsViewInputMixin
from .graphics_view_layers import GraphicsViewLayersMixin
from .graphics_view_rendering import GraphicsViewRenderingMixin
from .mask_layer import MaskLayer
from .overlay_layer import OverlayLayerManager
from .selection_manager import SelectionManager


class GraphicsView(
    GraphicsViewLayersMixin,
    GraphicsViewRenderingMixin,
    GraphicsViewInputMixin,
    QGraphicsView,
):
    """编辑画布：主文件只保留初始化、信号接线和共享状态。"""

    region_geometry_changed = pyqtSignal(int, dict)
    _layout_result_ready = pyqtSignal(list)
    view_state_changed = pyqtSignal(object, object)

    MASK_PREVIEW_MAX_PIXELS = 2_000_000
    INPAINT_PREVIEW_MAX_PIXELS = 6_000_000
    # Middle-click pan (ScrollHandDrag) is limited by scene scroll range.
    # Always keep at least this many view-pixels of free travel past content edges
    # (and when the image is smaller than the viewport).
    PAN_EDGE_MARGIN_PX = 150

    @property
    def _text_render_cache(self):
        return self.render_coordinator.text_render_cache

    @_text_render_cache.setter
    def _text_render_cache(self, value):
        self.render_coordinator.text_render_cache = value

    @property
    def _text_blocks_cache(self):
        return self.render_coordinator.text_blocks

    @_text_blocks_cache.setter
    def _text_blocks_cache(self, value):
        self.render_coordinator.text_blocks = value

    @property
    def _dst_points_cache(self):
        return self.render_coordinator.dst_points

    @_dst_points_cache.setter
    def _dst_points_cache(self, value):
        self.render_coordinator.dst_points = value

    @property
    def _render_snapshot_cache(self):
        return self.render_coordinator.render_snapshots

    @_render_snapshot_cache.setter
    def _render_snapshot_cache(self, value):
        self.render_coordinator.render_snapshots = value

    def __init__(self, model: EditorModel, controller=None, parent=None):
        super().__init__(parent)
        self.model = model
        self.controller = controller
        self.logger = get_logger(__name__)
        self.render_coordinator = RenderCoordinator()

        self.scene = QGraphicsScene(self)
        # 编辑器频繁整批重建少量文本框；禁用 BSP 索引可避免 add/remove 时维护索引的额外开销。
        self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.setScene(self.scene)
        self._show_original_view_badge = False

        self._image_item: QGraphicsPixmapItem = None
        self._q_image_ref = None
        self._preview_item: QGraphicsPixmapItem = None
        self.mask_layer = MaskLayer(self)
        self.overlay_layers = OverlayLayerManager(self)

        self._region_items = []
        self._pending_geometry_edit_kinds: dict[int, str] = {}
        self._immediate_render_update_pending = False
        self._render_update_immediate_once = False

        self._active_tool = "select"
        self._brush_size = 30
        self._brush_color = "#ffffff"
        self._eyedropper_cursor_active = False
        self._ctrl_region_cursor_active = False
        # 스포이드 오프스크린 렌더 중: 핸들/박스 등 에디터 크롬 paint 억제
        self._eyedropper_hide_chrome = False
        # Alt/Shift+휠 브러시 크기 조절 중 원 커서 프리뷰 (스포이드 십자보다 우선)
        self._brush_size_cursor_preview = False
        self._is_drawing = False
        self._current_draw_scene_points: list[QPointF] = []
        self._current_draw_mask_points: list[tuple[int, int]] = []
        self._current_draw_mask_shape: tuple[int, int] | None = None

        self._potential_drag = False
        self._drag_start_pos = None
        self._drag_threshold = 5

        self._is_drawing_textbox = False
        self._textbox_start_pos = None
        self._textbox_preview_item = None

        self.render_debounce_timer = QTimer(self)
        self.render_debounce_timer.setSingleShot(True)
        self.render_debounce_timer.setInterval(150)
        self.render_debounce_timer.timeout.connect(self._perform_render_update)

        self._brush_size_preview_timer = QTimer(self)
        self._brush_size_preview_timer.setSingleShot(True)
        self._brush_size_preview_timer.setInterval(500)
        self._brush_size_preview_timer.timeout.connect(self._on_brush_size_preview_timeout)

        self._setup_view()
        self._connect_model_signals()
        self._layout_result_ready.connect(self._apply_layout_result)

    def set_controller(self, controller) -> None:
        self.controller = controller

    def clear_pending_geometry_edits(self) -> None:
        self._clear_pending_geometry_edits()

    def get_live_region_state_patch(self, region_index: int) -> dict | None:
        if not (0 <= region_index < len(self._region_items)):
            return None

        item = self._region_items[region_index]
        geo = getattr(item, "geo", None) if item is not None else None
        if geo is None:
            return None

        patch = geo.to_persisted_state_patch()
        patch["center"] = list(geo.center)
        if item is not None and hasattr(item, "distort_state_patch"):
            patch.update(item.distort_state_patch())
        return patch

    def get_image_scene_rect(self) -> QRectF | None:
        """返回图片 item 在场景中的包围矩形，供对齐的"画布"参照模式使用。"""
        if self._image_item is not None:
            r = self._image_item.sceneBoundingRect()
            if r.isValid() and not r.isNull():
                return QRectF(r)
        return None

    def map_global_cursor_to_image(self) -> QPointF | None:
        """Cursor in image-item local pixels. mapToScene expects viewport coords."""
        if self._image_item is None:
            return None
        viewport = self.viewport()
        if viewport is None:
            return None
        view_pos = viewport.mapFromGlobal(QCursor.pos())
        scene_pos = self.mapToScene(view_pos)
        return self._image_item.mapFromScene(scene_pos)

    def get_content_scene_rect(self) -> QRectF | None:
        rect = self.scene.itemsBoundingRect()
        if (not rect.isValid() or rect.isNull()) and self._image_item is not None:
            rect = self._image_item.sceneBoundingRect()
        if not rect.isValid() or rect.isNull():
            rect = self.scene.sceneRect()
        if rect.isValid() and not rect.isNull():
            return QRectF(rect)
        return None

    def _update_pan_scene_rect(self) -> None:
        """Expand sceneRect so middle-click pan always has ~PAN_EDGE_MARGIN_PX room.

        Qt ScrollHandDrag only moves within scrollbar range. When the image is
        smaller than the viewport (or the view is already at a content edge),
        that range is zero — expand the scene so ~PAN_EDGE_MARGIN_PX of travel
        remains in each direction under any zoom/size condition.
        """
        if self._image_item is None:
            return

        content = self._image_item.sceneBoundingRect()
        if not content.isValid() or content.isNull():
            return

        viewport = self.viewport()
        if viewport is None or viewport.width() <= 0 or viewport.height() <= 0:
            return

        # Convert view-pixel margin into scene units for the current zoom.
        transform = self.transform()
        scale_x = abs(transform.m11())
        scale_y = abs(transform.m22())
        if scale_x < 1e-9 or scale_y < 1e-9:
            return

        margin_x = self.PAN_EDGE_MARGIN_PX / scale_x
        margin_y = self.PAN_EDGE_MARGIN_PX / scale_y

        # Viewport size expressed in scene coordinates.
        view_w = viewport.width() / scale_x
        view_h = viewport.height() / scale_y

        # content + margin: extra room past edges when zoomed in.
        # viewport + 2*margin: when content is smaller than the view, still allow
        # margin_px of pan each way from the centered position.
        target_w = max(content.width() + 2.0 * margin_x, view_w + 2.0 * margin_x)
        target_h = max(content.height() + 2.0 * margin_y, view_h + 2.0 * margin_y)

        center = content.center()
        new_rect = QRectF(
            center.x() - target_w / 2.0,
            center.y() - target_h / 2.0,
            target_w,
            target_h,
        )

        old_rect = self.scene.sceneRect()
        if (
            old_rect.isValid()
            and abs(old_rect.left() - new_rect.left()) < 0.5
            and abs(old_rect.top() - new_rect.top()) < 0.5
            and abs(old_rect.width() - new_rect.width()) < 0.5
            and abs(old_rect.height() - new_rect.height()) < 0.5
        ):
            return

        # Keep the same visual center after the scrollable range changes.
        view_center = self.mapToScene(viewport.rect().center())
        self.scene.setSceneRect(new_rect)
        self.centerOn(view_center)

    def _setup_view(self):
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.apply_theme()
        self.selection_manager = SelectionManager(self.model, self.scene, lambda: self._region_items)

    def apply_theme(self, theme: str | None = None):
        colors = get_theme_colors(theme or get_current_theme())
        canvas_color = QColor(colors["bg_canvas"])
        self.scene.setBackgroundBrush(canvas_color)
        self.setBackgroundBrush(canvas_color)
        self.resetCachedContent()
        self.scene.update()
        self.viewport().update()

    def set_original_view_badge_visible(self, visible: bool):
        """원본 보기 모드일 때 캔버스 우하단 상태 배지를 켠다."""
        visible = bool(visible)
        if self._show_original_view_badge == visible:
            return
        self._show_original_view_badge = visible
        viewport = self.viewport()
        if viewport is not None:
            viewport.update()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        viewport = self.viewport()
        if viewport is None or viewport.width() <= 0 or viewport.height() <= 0:
            return

        i18n = get_i18n_manager()

        def t(key: str, fallback: str) -> str:
            return i18n.translate(key) if i18n else fallback

        painter.save()
        try:
            painter.resetTransform()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            colors = get_theme_colors(get_current_theme())

            if self._show_original_view_badge:
                self._draw_canvas_status_badge(
                    painter,
                    viewport,
                    t("Original View Mode On", "Original View Mode"),
                    QColor(colors.get("danger_bg", "#EF4444")),
                    QColor(colors.get("danger_text", "#FFFFFF")),
                    "right",
                )
                # Original view forces region mode to "none", so keep the
                # user's last selected mode for the left-hand badge.
                mode = getattr(self.controller, "_last_display_mode", "") if self.controller is not None else ""
            else:
                mode = self.model.get_region_display_mode() if self.model is not None else ""

            if mode == "compare_original_split":
                mode = "full"
            if mode == "box_only":
                text = t("Boxes Only Mode", "Boxes Only Mode")
            elif mode == "none":
                text = t("Show Nothing Mode", "Show Nothing Mode")
            else:
                return

            self._draw_canvas_status_badge(
                painter,
                viewport,
                text,
                QColor(colors.get("btn_primary_bg", "#4F46E5")),
                QColor(colors.get("btn_primary_text", "#FFFFFF")),
                "left",
            )
        finally:
            painter.restore()

    def _draw_canvas_status_badge(
        self,
        painter: QPainter,
        viewport,
        text: str,
        bg: QColor,
        text_color: QColor,
        side: str,
    ) -> None:
        """Viewport-fixed HUD badge at the bottom of the canvas."""
        if not text:
            return

        font = QFont(painter.font())
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        pad_x = 10
        pad_y = 5
        margin = 14
        radius = 6
        badge_w = metrics.horizontalAdvance(text) + pad_x * 2
        badge_h = metrics.height() + pad_y * 2
        x = margin if side == "left" else viewport.width() - margin - badge_w
        y = viewport.height() - margin - badge_h
        badge_rect = QRectF(x, y, badge_w, badge_h)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90))
        painter.drawRoundedRect(badge_rect.translated(0, 1), radius, radius)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(badge_rect, radius, radius)
        painter.setPen(text_color)
        painter.drawText(badge_rect, int(Qt.AlignmentFlag.AlignCenter), text)

    def _connect_model_signals(self):
        self.model.image_changed.connect(self.on_image_changed)
        self.model.regions_changed.connect(self.on_regions_changed)
        self.model.raw_mask_changed.connect(lambda mask: self.mask_layer.on_mask_data_changed("raw", mask))
        self.model.refined_mask_changed.connect(lambda mask: self.mask_layer.on_mask_data_changed("refined", mask))
        self.model.display_mask_type_changed.connect(self.mask_layer.on_display_mask_type_changed)
        self.model.inpainted_image_changed.connect(self.overlay_layers.on_inpainted_image_changed)
        self.model.paint_overlay_changed.connect(self.overlay_layers.on_paint_overlay_changed)
        self.model.paint_overlay_changed.connect(self.mask_layer.on_paint_overlay_changed)
        self.model.region_display_mode_changed.connect(self.on_region_display_mode_changed)
        self.model.original_image_alpha_changed.connect(self.on_original_image_alpha_changed)
        self.model.region_style_updated.connect(self.on_region_style_updated)
        self.model.active_tool_changed.connect(self._on_active_tool_changed)
        self.model.brush_size_changed.connect(self._on_brush_size_changed)
        self.model.brush_color_changed.connect(self._on_brush_color_changed)

    def get_view_state(self):
        if self._image_item is None:
            return None, None
        center_scene = self.mapToScene(self.viewport().rect().center())
        return QTransform(self.transform()), QPointF(center_scene)

    def _emit_view_state_changed(self):
        transform, center_scene = self.get_view_state()
        if transform is None or center_scene is None:
            return
        self.view_state_changed.emit(transform, center_scene)
