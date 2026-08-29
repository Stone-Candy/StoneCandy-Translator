from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from PyQt6.QtGui import QPixmap
from editor.image_utils import build_mask_display_frame

from .graphics_items import TransparentPixmapItem

if TYPE_CHECKING:
    from .graphics_view import GraphicsView


class MaskLayer:
    """管理 raw/refined mask 覆盖层，隐藏时只标脏，显示时再生成 pixmap。"""

    MASK_TYPES = {"raw", "refined", "paint"}
    Z_VALUES = {"raw": 10, "refined": 11, "paint": 12}
    MASK_COLORS = {
        "raw": (255, 0, 38),
        "refined": (255, 0, 38),
        "paint": (0, 200, 255),
    }

    def __init__(self, view: "GraphicsView"):
        self.view = view
        self.items: dict[str, TransparentPixmapItem | None] = {"raw": None, "refined": None, "paint": None}
        self.dirty = {"raw": False, "refined": False, "paint": False}
        self._forced_visible_mask_type: str | None = None

    def clear(self) -> None:
        for mask_type, item in list(self.items.items()):
            if item and item.scene():
                self.view.scene.removeItem(item)
            self.items[mask_type] = None
        self.dirty = {"raw": False, "refined": False, "paint": False}
        self._forced_visible_mask_type = None

    def set_forced_visible_mask_type(self, mask_type: str | None) -> None:
        """Temporarily show one mask regardless of the model display toggle.

        `mask_type`이 None이면 강제 표시를 "해제"하는 것뿐, "모두 숨김"이
        아니다. 해제 후에는 토글(`model.get_display_mask_type()`)이 가리키는
        마스크가 있다면 그게 다시 보여야 한다 — 무조건 숨기면 토글이 켜진
        상태에서 Ctrl을 뗐을 때 레이어가 사라져 버리는 버그가 생긴다.
        """
        if mask_type is not None and mask_type not in self.MASK_TYPES:
            mask_type = None
        self._forced_visible_mask_type = mask_type
        if mask_type is not None:
            self._build_visible_mask_if_needed(mask_type)
        else:
            toggled_type = self.view.model.get_display_mask_type()
            if toggled_type in self.MASK_TYPES:
                self._build_visible_mask_if_needed(toggled_type)
        for item_type, item in self.items.items():
            if item:
                item.setVisible(self._is_mask_visible(item_type))
        self.view.viewport().update()

    def _is_mask_visible(self, mask_type: str) -> bool:
        return (
            self._forced_visible_mask_type == mask_type
            or (self._forced_visible_mask_type is None
                and self.view.model.get_display_mask_type() == mask_type)
        )

    @staticmethod
    def _overlay_alpha_mask(overlay: Any) -> Any:
        if overlay is None:
            return None
        array = np.asarray(overlay)
        if getattr(array, "size", 0) == 0:
            return None
        if array.ndim == 3 and array.shape[2] >= 4:
            return np.where(array[..., 3] > 0, 255, 0).astype(np.uint8)
        if array.ndim == 2:
            return np.where(array > 0, 255, 0).astype(np.uint8)
        if array.ndim == 3 and array.shape[2] == 3:
            return np.where(np.any(array > 0, axis=2), 255, 0).astype(np.uint8)
        return None

    def on_paint_overlay_changed(self, overlay: Any) -> None:
        self.on_mask_data_changed("paint", self._overlay_alpha_mask(overlay))

    def on_mask_data_changed(self, mask_type: str, mask_array: Any) -> None:
        if mask_type not in self.MASK_TYPES:
            return

        item = self.items[mask_type]
        if mask_array is None or getattr(mask_array, "size", 0) == 0:
            self.dirty[mask_type] = False
            self._hide_item(item, clear_pixmap=True)
            return

        self.dirty[mask_type] = True
        current_display_type = self.view.model.get_display_mask_type()
        if current_display_type != mask_type and self._forced_visible_mask_type != mask_type:
            self._hide_item(item)
            return

        display_frame = build_mask_display_frame(
            mask_array,
            max_pixels=self.view.MASK_PREVIEW_MAX_PIXELS,
            color=self.MASK_COLORS.get(mask_type, (255, 0, 38)),
        )
        if display_frame is None:
            return

        item = self._set_mask_pixmap(mask_type, QPixmap.fromImage(display_frame.qimage))

        self.view.viewport().update()

        if item:
            item.setVisible(True)
            self.dirty[mask_type] = False

    def on_display_mask_type_changed(self, mask_type: str) -> None:
        self._build_visible_mask_if_needed(mask_type)
        for item_type, item in self.items.items():
            if item:
                item.setVisible(mask_type == item_type)
        self.view.viewport().update()

    def _build_visible_mask_if_needed(self, mask_type: str) -> None:
        if mask_type == "raw":
            self._build_if_needed("raw", self.view.model.get_raw_mask())
        elif mask_type == "refined":
            self._build_if_needed("refined", self.view.model.get_refined_mask())
        elif mask_type == "paint":
            self._build_if_needed("paint", self._overlay_alpha_mask(self.view.model.get_paint_overlay_image()))

    def _build_if_needed(self, mask_type: str, mask_array: Any) -> None:
        if mask_array is None:
            return
        if self.items[mask_type] is None or self.dirty.get(mask_type, False):
            self.on_mask_data_changed(mask_type, mask_array)

    def _set_mask_pixmap(self, mask_type: str, pixmap: QPixmap):
        item = self._ensure_item(mask_type)
        item.setPixmap(pixmap)
        self.view._scale_mask_item(item)
        item.setVisible(self._is_mask_visible(mask_type))
        return item

    def _ensure_item(self, mask_type: str):
        item = self.items[mask_type]
        if item is not None and item.scene() is not None:
            return item

        item = TransparentPixmapItem()
        item.setZValue(self.Z_VALUES[mask_type])
        self.view.scene.addItem(item)
        self.items[mask_type] = item
        return item

    @staticmethod
    def _hide_item(item, *, clear_pixmap: bool = False) -> None:
        if item is None:
            return
        item.setVisible(False)
        if clear_pixmap:
            item.setPixmap(QPixmap())
