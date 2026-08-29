from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional, Tuple

import cv2
import numpy as np
import torch
from editor.commands import MaskEditCommand, PaintOverlayEditCommand
from services import get_config_service

from .image_utils import image_like_to_rgb_array

if TYPE_CHECKING:
    from .editor_controller import EditorController


class EditorControllerInpaintService:
    """蒙版与 inpaint 流程。"""

    def __init__(self, controller: "EditorController"):
        self.controller = controller

    @property
    def logger(self):
        return self.controller.logger

    @property
    def model(self):
        return self.controller.model

    @property
    def async_service(self):
        return self.controller.async_service

    @property
    def resource_manager(self):
        return self.controller.resource_manager

    @staticmethod
    def normalize_binary_mask(mask: Optional[np.ndarray]) -> Optional[np.ndarray]:
        if mask is None:
            return None
        mask_np = np.array(mask)
        if mask_np.ndim == 3:
            mask_np = mask_np[:, :, 0]
        return np.where(mask_np > 0, 255, 0).astype(np.uint8)

    def get_cached_mask_snapshot(self) -> Optional[np.ndarray]:
        cached_mask = self.resource_manager.get_cache(self.controller.CACHE_LAST_MASK)
        normalized = self.normalize_binary_mask(cached_mask)
        return None if normalized is None else normalized.copy()

    def get_cached_inpainted_snapshot(self) -> Optional[np.ndarray]:
        cached_image = self.resource_manager.get_cache(self.controller.CACHE_LAST_INPAINTED)
        return image_like_to_rgb_array(cached_image, copy=True)

    def get_live_inpainted_snapshot(self) -> Optional[np.ndarray]:
        return image_like_to_rgb_array(self.model.get_inpainted_image(), copy=True)

    def resolve_incremental_inpaint_base(self, expected_shape: Tuple[int, int, int]) -> Optional[np.ndarray]:
        """Prefer the incremental cache, then the live inpainted document.

        Never fall back to the original here: a missing cache plus original
        as the base would keep the mask overlay while wiping previous inpaint
        pixels, which is exactly the save-then-brush failure mode.
        """
        cached = self.get_cached_inpainted_snapshot()
        if cached is not None and cached.shape == expected_shape:
            return cached
        live = self.get_live_inpainted_snapshot()
        if live is not None and live.shape == expected_shape:
            return live
        return None

    def get_base_image_rgb_array(self) -> Optional[np.ndarray]:
        image = self.controller._get_current_image()
        if image is None:
            return None

        expected_shape = (int(image.height), int(image.width), 3)
        cached_array = self.resource_manager.get_weak_cache(self.controller.WEAK_CACHE_BASE_IMAGE_RGB)
        if isinstance(cached_array, np.ndarray) and cached_array.shape == expected_shape and cached_array.dtype == np.uint8:
            return cached_array

        image_array = image_like_to_rgb_array(image, copy=False)
        if image_array is None:
            return None
        self.resource_manager.set_weak_cache(self.controller.WEAK_CACHE_BASE_IMAGE_RGB, image_array)
        return image_array

    def cancel_active_inpaint_task(self) -> None:
        future = self.controller._active_inpaint_future
        self.controller._active_inpaint_future = None
        if future is not None and not future.done():
            future.cancel()

    def invalidate_inpaint_requests(self) -> None:
        self.cancel_active_inpaint_task()
        self.controller._inpaint_request_generation += 1

    def begin_inpaint_request(self) -> int:
        self.invalidate_inpaint_requests()
        return self.controller._inpaint_request_generation

    def is_inpaint_request_current(self, generation: int) -> bool:
        return generation == self.controller._inpaint_request_generation

    def sync_last_cache_from_model(self) -> None:
        """Keep incremental-inpaint caches aligned with the live model.

        Undo restores mask + inpainted image on the model; without this the
        next stroke still diffs against the pre-undo cache.
        """
        inpainted = image_like_to_rgb_array(self.model.get_inpainted_image(), copy=True)
        mask = self.normalize_binary_mask(self.model.get_refined_mask())
        if inpainted is None:
            self.resource_manager.clear_cache(self.controller.CACHE_LAST_INPAINTED)
        else:
            self.resource_manager.set_cache(self.controller.CACHE_LAST_INPAINTED, inpainted)
        if mask is None:
            self.resource_manager.clear_cache(self.controller.CACHE_LAST_MASK)
        else:
            self.resource_manager.set_cache(self.controller.CACHE_LAST_MASK, mask.copy())

    def on_refined_mask_changed(self, mask) -> None:
        if self.controller._suppress_refined_mask_autoinpaint:
            return

        image = self.controller._get_current_image()
        if image is None or mask is None:
            self.invalidate_inpaint_requests()
            return

        cached_mask = self.get_cached_mask_snapshot()
        generation = self.begin_inpaint_request()
        if cached_mask is not None:
            future = self.async_service.submit_task(self.async_incremental_inpaint(mask, generation))
        else:
            future = self.async_service.submit_task(self.async_full_inpaint_with_cache(mask, generation))
        self.controller._active_inpaint_future = future

    async def async_refine_and_inpaint(self):
        try:
            raw_mask = self.model.get_raw_mask()
            regions = self.controller._get_regions()

            if raw_mask is None or not regions:
                self.logger.warning("Refinement/Inpainting skipped: image, mask, or regions not available.")
                return

            refined_mask = self.normalize_binary_mask(raw_mask)
            if refined_mask is None:
                self.logger.error("Mask refinement failed.")
                return
            if not isinstance(refined_mask, np.ndarray):
                self.logger.error(f"Refined mask is not a numpy array: {type(refined_mask)}")
                return
            if refined_mask.size == 0:
                self.logger.error("Refined mask is empty")
                return

            current_inpainted_image = self.model.get_inpainted_image()
            if current_inpainted_image is not None:
                inpainted_image_np = image_like_to_rgb_array(current_inpainted_image, copy=False)
                if inpainted_image_np is None:
                    self.logger.warning("Current inpainted image could not be normalized to RGB array.")
                    return
                self.resource_manager.set_cache(self.controller.CACHE_LAST_INPAINTED, inpainted_image_np)
                self.resource_manager.set_cache(self.controller.CACHE_LAST_MASK, refined_mask.copy())
                if not self.controller._user_adjusted_alpha:
                    self.model.set_original_image_alpha(0.0)
            else:
                self.resource_manager.clear_cache(self.controller.CACHE_LAST_INPAINTED)
                self.resource_manager.clear_cache(self.controller.CACHE_LAST_MASK)

            self.controller._suppress_refined_mask_autoinpaint = True
            try:
                self.model.set_refined_mask(refined_mask)
            finally:
                self.controller._suppress_refined_mask_autoinpaint = False
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.error(f"Error during async refine and inpaint: {e}")

    def force_inpaint_stroke(self, stroke_mask: np.ndarray) -> None:
        if self.controller._suppress_refined_mask_autoinpaint:
            return

        current_mask = self.model.get_refined_mask()
        if current_mask is None:
            return

        generation = self.begin_inpaint_request()
        future = self.async_service.submit_task(self.async_incremental_inpaint(current_mask, generation, stroke_mask=stroke_mask))
        self.controller._active_inpaint_future = future

    async def async_incremental_inpaint(self, current_mask, generation: int, stroke_mask: Optional[np.ndarray] = None):
        try:
            if not self.is_inpaint_request_current(generation):
                return

            image = self.controller._get_current_image()
            if image is None or current_mask is None:
                self.logger.warning("Incremental inpainting skipped: missing data.")
                return

            current_mask_2d = self.normalize_binary_mask(current_mask)
            if current_mask_2d is None:
                return

            if stroke_mask is not None:
                stroke_mask_2d = self.normalize_binary_mask(stroke_mask)
                if stroke_mask_2d is None:
                    return
                added_areas = stroke_mask_2d
                removed_areas = np.zeros_like(stroke_mask_2d)
            else:
                last_processed_mask = self.get_cached_mask_snapshot()
                if last_processed_mask is None:
                    await self.async_full_inpaint_with_cache(current_mask, generation)
                    return
    
                if current_mask_2d.shape != last_processed_mask.shape:
                    self.logger.warning(
                        "Incremental inpainting fell back to full: mask shape changed from %s to %s",
                        last_processed_mask.shape,
                        current_mask_2d.shape,
                    )
                    await self.async_full_inpaint_with_cache(current_mask_2d, generation)
                    return
    
                added_areas = cv2.bitwise_and(current_mask_2d, cv2.bitwise_not(last_processed_mask))
                removed_areas = cv2.bitwise_and(last_processed_mask, cv2.bitwise_not(current_mask_2d))

            if not np.any(added_areas) and not np.any(removed_areas):
                return

            expected_shape = (int(image.height), int(image.width), 3)
            full_result = self.resolve_incremental_inpaint_base(expected_shape)
            if full_result is None:
                self.logger.warning(
                    "Incremental inpainting fell back to full: no live inpainted base"
                )
                await self.async_full_inpaint_with_cache(current_mask_2d, generation)
                return

            base_image_np = None

            if np.any(removed_areas):
                if base_image_np is None:
                    base_image_np = self.get_base_image_rgb_array()
                    if base_image_np is None:
                        self.logger.warning("Incremental inpainting restore skipped: failed to normalize base image.")
                        return
                removed_pixels = removed_areas > 0
                full_result[removed_pixels] = base_image_np[removed_pixels]

            if np.any(added_areas):
                coords = np.where(added_areas > 0)
                if len(coords[0]) == 0:
                    return

                y_min, y_max = np.min(coords[0]), np.max(coords[0])
                x_min, x_max = np.min(coords[1]), np.max(coords[1])

                padding = 50
                h, w = current_mask_2d.shape
                y_min = max(0, y_min - padding)
                y_max = min(h, y_max + padding + 1)
                x_min = max(0, x_min - padding)
                x_max = min(w, x_max + padding + 1)

                bbox_image = full_result[y_min:y_max, x_min:x_max].copy()
                bbox_mask = added_areas[y_min:y_max, x_min:x_max].copy()

                config = get_config_service().get_config()
                inpainter_config_model = config.inpainter
                try:
                    from manga_translator.config import Inpainter, InpainterConfig, InpaintPrecision
                    from manga_translator.inpainting import dispatch as inpaint_dispatch
                except ImportError as e:
                    self.logger.error(f"Failed to import backend modules: {e}")
                    return

                inpainter_config = InpainterConfig()
                inpainter_config.inpainting_precision = InpaintPrecision(inpainter_config_model.inpainting_precision)
                inpainter_config.force_use_torch_inpainting = inpainter_config_model.force_use_torch_inpainting

                try:
                    inpainter_key = Inpainter(inpainter_config_model.inpainter)
                except ValueError:
                    inpainter_key = Inpainter.lama_large

                device = "cuda" if config.cli.use_gpu and torch.cuda.is_available() else "cpu"
                bbox_result = await inpaint_dispatch(
                    inpainter_key=inpainter_key,
                    image=bbox_image,
                    mask=bbox_mask,
                    config=inpainter_config,
                    inpainting_size=inpainter_config_model.inpainting_size,
                    device=device,
                )
                if bbox_result is None:
                    self.logger.error("Incremental inpainting failed, returned None.")
                    return
                if not self.is_inpaint_request_current(generation):
                    return
                full_result[y_min:y_max, x_min:x_max] = bbox_result

            if not self.is_inpaint_request_current(generation):
                return
            self.resource_manager.set_cache(self.controller.CACHE_LAST_INPAINTED, full_result)
            self.resource_manager.set_cache(self.controller.CACHE_LAST_MASK, current_mask_2d)
            self.controller.apply_inpaint_result(full_result, generation)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.error(f"Error during bounding box inpainting: {e}", exc_info=True)

    async def async_full_inpaint_with_cache(self, mask, generation: int):
        try:
            if not self.is_inpaint_request_current(generation):
                return

            image_np = self.get_base_image_rgb_array()
            if image_np is None or mask is None:
                self.logger.warning("Full inpainting skipped: failed to normalize base image.")
                return

            try:
                from manga_translator.config import Inpainter, InpainterConfig, InpaintPrecision
                from manga_translator.inpainting import dispatch as inpaint_dispatch
            except ImportError as e:
                self.logger.error(f"Failed to import backend modules: {e}")
                return

            mask_2d = self.normalize_binary_mask(mask)
            if mask_2d is None:
                return

            config = get_config_service().get_config()
            inpainter_config_model = config.inpainter

            inpainter_config = InpainterConfig()
            inpainter_config.inpainting_precision = InpaintPrecision(inpainter_config_model.inpainting_precision)
            inpainter_config.force_use_torch_inpainting = inpainter_config_model.force_use_torch_inpainting

            try:
                inpainter_key = Inpainter(inpainter_config_model.inpainter)
            except ValueError:
                self.logger.warning(f"Unknown inpainter model: {inpainter_config_model.inpainter}, defaulting to lama_large")
                inpainter_key = Inpainter.lama_large

            device = "cuda" if config.cli.use_gpu and torch.cuda.is_available() else "cpu"
            inpainted_image_np = await inpaint_dispatch(
                inpainter_key=inpainter_key,
                image=image_np,
                mask=mask_2d,
                config=inpainter_config,
                inpainting_size=inpainter_config_model.inpainting_size,
                device=device,
            )

            if inpainted_image_np is not None and self.is_inpaint_request_current(generation):
                self.resource_manager.set_cache(self.controller.CACHE_LAST_INPAINTED, inpainted_image_np)
                self.resource_manager.set_cache(self.controller.CACHE_LAST_MASK, mask_2d)
                self.controller.apply_inpaint_result(inpainted_image_np, generation)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.error(f"Error during full inpainting with cache: {e}", exc_info=True)

    def set_display_mask_type(self, mask_type: str, visible: bool) -> None:
        self.model.set_display_mask_type(mask_type if visible else "none")

    def set_active_tool(self, tool: str) -> None:
        self.model.set_active_tool(tool)

    def set_brush_size(self, size: int) -> None:
        self.model.set_brush_size(size)

    def set_brush_color(self, color: str) -> None:
        self.model.set_brush_color(color)

    def handle_ctrl_click_region_edit(
        self,
        image_x: int,
        image_y: int,
        image_shape: Tuple[int, int],
    ) -> bool:
        """Ctrl+클릭으로 연결 영역을 변환/삭제. 해당 영역이 아니면 False."""
        try:
            image_h, image_w = int(image_shape[0]), int(image_shape[1])
            if image_h <= 0 or image_w <= 0:
                return False
            if not (0 <= image_x < image_w and 0 <= image_y < image_h):
                return False

            tool = self.model.get_active_tool()
            if tool == "paint":
                return self.convert_inpaint_blob_to_overlay(image_x, image_y, image_h, image_w)
            if tool == "paint_erase":
                return self.erase_overlay_blob(image_x, image_y, image_h, image_w)
            if tool == "eraser":
                return self.erase_inpaint_blob(image_x, image_y, image_h, image_w)
            return False
        except Exception as e:
            self.logger.error("Ctrl-click region edit failed: %s", e, exc_info=True)
            return False

    def convert_inpaint_blob_to_overlay(
        self,
        image_x: int,
        image_y: int,
        image_h: int,
        image_w: int,
    ) -> bool:
        mask = self.normalize_binary_mask(self.model.get_refined_mask())
        if mask is None or not np.any(mask):
            return False

        mx, my = self._map_pixel(image_x, image_y, image_h, image_w, mask.shape[0], mask.shape[1])
        if mask[my, mx] == 0:
            return False

        blob = self._blob_at(mask, mx, my)
        if blob is None:
            return False

        from manga_translator.mask_refinement import morph_binary_by_offset

        full_overlay_blob = self._resize_binary(blob, image_h, image_w)
        overlay_blob = morph_binary_by_offset(
            full_overlay_blob,
            self._inpaint_to_overlay_dilation_offset(),
        )
        old_overlay = self._overlay_rgba_at_size(image_h, image_w)
        if old_overlay is None:
            new_overlay = np.zeros((image_h, image_w, 4), dtype=np.uint8)
        else:
            new_overlay = old_overlay.copy()

        pixels = overlay_blob > 0
        if np.any(pixels):
            red, green, blue = self._brush_rgb()
            new_overlay[pixels, 0] = red
            new_overlay[pixels, 1] = green
            new_overlay[pixels, 2] = blue
            new_overlay[pixels, 3] = 255

        new_mask = mask.copy()
        new_mask[blob > 0] = 0

        overlay_changed = (
            bool(np.any(pixels))
            if old_overlay is None
            else not np.array_equal(old_overlay, new_overlay)
        )
        mask_changed = not np.array_equal(mask, new_mask)
        if not overlay_changed and not mask_changed:
            return False

        # 마스크를 먼저 지운 뒤 인페인트 자리 전체를 원본으로 되돌리고, 그 위에 덧칠한다.
        restored_inpainted = self._original_under_blob(full_overlay_blob) if mask_changed else None

        self.invalidate_inpaint_requests()
        if mask_changed:
            self.controller._suppress_refined_mask_autoinpaint = True
        try:
            with self.controller.history_service.macro("Convert Inpaint to Overlay"):
                if mask_changed:
                    self.controller.execute_command(
                        MaskEditCommand(
                            model=self.model,
                            old_mask=mask,
                            new_mask=new_mask,
                            new_inpainted=restored_inpainted,
                        ),
                        update_ui=False,
                    )
                if overlay_changed:
                    self.controller.execute_command(
                        PaintOverlayEditCommand(
                            model=self.model,
                            old_overlay=old_overlay,
                            new_overlay=new_overlay,
                        ),
                        update_ui=False,
                    )
        finally:
            if mask_changed:
                self.controller._suppress_refined_mask_autoinpaint = False
        self.sync_last_cache_from_model()
        self.controller._update_undo_redo_buttons()
        return True

    def _original_under_blob(self, blob_at_image: np.ndarray) -> Optional[np.ndarray]:
        """인페인트 밑그림에서 blob 자리를 원본 픽셀로 되돌린 복사본."""
        base = self.get_base_image_rgb_array()
        if base is None or blob_at_image is None:
            return None
        current = image_like_to_rgb_array(self.model.get_inpainted_image(), copy=True)
        if current is None:
            current = base.copy()
        if current.shape[:2] != base.shape[:2]:
            return None
        blob = blob_at_image
        if blob.shape[:2] != current.shape[:2]:
            blob = self._resize_binary(blob, current.shape[0], current.shape[1])
        pixels = blob > 0
        if not np.any(pixels):
            return None
        restored = current.copy()
        restored[pixels] = base[pixels]
        return restored

    def erase_overlay_blob(
        self,
        image_x: int,
        image_y: int,
        image_h: int,
        image_w: int,
    ) -> bool:
        overlay = self._overlay_rgba_at_size(image_h, image_w)
        if overlay is None or overlay[image_y, image_x, 3] == 0:
            return False

        blob = self._blob_at(np.where(overlay[:, :, 3] > 0, 255, 0).astype(np.uint8), image_x, image_y)
        if blob is None:
            return False

        new_overlay = overlay.copy()
        new_overlay[blob > 0] = 0
        if np.array_equal(overlay, new_overlay):
            return False

        self.controller.execute_command(
            PaintOverlayEditCommand(
                model=self.model,
                old_overlay=overlay,
                new_overlay=new_overlay,
            )
        )
        return True

    def erase_inpaint_blob(
        self,
        image_x: int,
        image_y: int,
        image_h: int,
        image_w: int,
    ) -> bool:
        mask = self.normalize_binary_mask(self.model.get_refined_mask())
        if mask is None or not np.any(mask):
            return False

        mx, my = self._map_pixel(image_x, image_y, image_h, image_w, mask.shape[0], mask.shape[1])
        if mask[my, mx] == 0:
            return False

        blob = self._blob_at(mask, mx, my)
        if blob is None:
            return False

        new_mask = mask.copy()
        new_mask[blob > 0] = 0
        if np.array_equal(mask, new_mask):
            return False

        self.controller.execute_command(
            MaskEditCommand(model=self.model, old_mask=mask, new_mask=new_mask)
        )
        return True

    @staticmethod
    def _blob_at(binary_mask: np.ndarray, x: int, y: int) -> Optional[np.ndarray]:
        if binary_mask[y, x] == 0:
            return None
        _num_labels, labels = cv2.connectedComponents(
            (binary_mask > 0).astype(np.uint8),
            connectivity=8,
        )
        label = int(labels[y, x])
        if label == 0:
            return None
        return np.where(labels == label, 255, 0).astype(np.uint8)

    @staticmethod
    def _map_pixel(
        x: int,
        y: int,
        src_h: int,
        src_w: int,
        dst_h: int,
        dst_w: int,
    ) -> Tuple[int, int]:
        if src_h <= 0 or src_w <= 0 or dst_h <= 0 or dst_w <= 0:
            return 0, 0
        x_ratio = float(x) / float(max(src_w - 1, 1))
        y_ratio = float(y) / float(max(src_h - 1, 1))
        mx = int(round(x_ratio * float(max(dst_w - 1, 0))))
        my = int(round(y_ratio * float(max(dst_h - 1, 0))))
        return min(max(mx, 0), dst_w - 1), min(max(my, 0), dst_h - 1)

    @staticmethod
    def _resize_binary(mask: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
        if mask.shape[0] == target_h and mask.shape[1] == target_w:
            return mask
        resized = cv2.resize(mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
        return np.where(resized > 0, 255, 0).astype(np.uint8)

    @staticmethod
    def _inpaint_to_overlay_dilation_offset() -> int:
        try:
            return int(getattr(get_config_service().get_config(), "inpaint_to_overlay_dilation_offset", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _overlay_rgba_at_size(self, height: int, width: int) -> Optional[np.ndarray]:
        overlay = PaintOverlayEditCommand._normalize_overlay(self.model.get_paint_overlay_image())
        if overlay is None:
            return None
        if overlay.shape[0] != height or overlay.shape[1] != width:
            return None
        return np.array(overlay, copy=True, dtype=np.uint8)

    def _brush_rgb(self) -> Tuple[int, int, int]:
        color = (self.model.get_brush_color() or "#ffffff").strip()
        if color.startswith("#") and len(color) >= 7:
            try:
                return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            except ValueError:
                pass
        return 255, 255, 255

    def clear_paint_overlay(self) -> None:
        try:
            from editor.commands import PaintOverlayEditCommand

            old = self.model.get_paint_overlay_image()
            if old is None:
                return
            import numpy as np

            old_arr = np.asarray(old)
            if old_arr.size == 0:
                self.model.set_paint_overlay_image(None)
                return
            if old_arr.ndim == 3 and old_arr.shape[2] == 4:
                has_content = bool(np.any(old_arr[..., 3]))
            else:
                has_content = bool(np.any(old_arr))
            if not has_content:
                self.model.set_paint_overlay_image(None)
                return
            command = PaintOverlayEditCommand(
                model=self.model,
                old_overlay=old_arr.copy(),
                new_overlay=None,
            )
            self.controller.execute_command(command)
        except Exception as e:
            self.logger.error(f"Clear paint overlay failed: {e}", exc_info=True)

    def clear_all_masks(self) -> None:
        try:
            source_mask = self.model.get_refined_mask()
            if source_mask is None:
                source_mask = self.model.get_raw_mask()

            old_mask = None
            if source_mask is not None:
                old_mask = np.array(source_mask)
                if old_mask.ndim == 3:
                    old_mask = old_mask[:, :, 0]
                old_mask = np.where(old_mask > 0, 255, 0).astype(np.uint8)

            if old_mask is None:
                image = self.controller._get_current_image()
                if image is None:
                    self.logger.warning("Clear all masks skipped: no active image.")
                    return
                old_mask = np.zeros((int(image.height), int(image.width)), dtype=np.uint8)

            if not np.any(old_mask):
                return

            new_mask = np.zeros_like(old_mask)
            command = MaskEditCommand(model=self.model, old_mask=old_mask, new_mask=new_mask)
            self.controller.execute_command(command)
        except Exception as e:
            self.logger.error(f"Clear all masks failed: {e}", exc_info=True)
