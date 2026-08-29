"""渲染布局管线 — 计算 dst_points（文字渲染的目标四角点）。"""
import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger('manga_translator')

import numpy as np
from editor import text_renderer_backend

from manga_translator.config import Config, RenderConfig
from manga_translator.rendering import _solve_unified_no_br_layout, calc_box_from_font
from manga_translator.utils import TextBlock

_EXPLICIT_BREAK_RE = re.compile(r'(\[BR\]|【BR】|<br>)', re.IGNORECASE)


def _normalize_direction(direction_value):
    if direction_value == "h":
        return "horizontal"
    if direction_value == "v":
        return "vertical"
    return direction_value


def _is_rect_like(value) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 4


def _region_bubble_size(region_data: dict, text_block: Optional[TextBlock]) -> Tuple[float, float]:
    wf = region_data.get("white_frame_rect_local")
    if bool(region_data.get("has_custom_white_frame")) and _is_rect_like(wf):
        left, top, right, bottom = (float(v) for v in wf)
        return max(1.0, right - left), max(1.0, bottom - top)

    if text_block is not None:
        try:
            width, height = text_block.unrotated_size
            if width > 0 and height > 0:
                return float(width), float(height)
        except Exception:
            pass

    lines = region_data.get("lines")
    if lines:
        try:
            pts = np.asarray(lines, dtype=np.float64).reshape(-1, 2)
            width = float(pts[:, 0].max() - pts[:, 0].min())
            height = float(pts[:, 1].max() - pts[:, 1].min())
            if width > 0 and height > 0:
                return width, height
        except Exception:
            pass

    xywh = region_data.get("xywh")
    if isinstance(xywh, (list, tuple)) and len(xywh) >= 4:
        return max(1.0, float(xywh[2])), max(1.0, float(xywh[3]))
    return 1.0, 1.0


def apply_auto_linebreak_to_region_translation(region_data: dict) -> str:
    """Pass a one-line editor translation through the shared no-BR solver once."""
    text = region_data.get("translation") or ""
    if not str(text).strip():
        return text

    normalized = re.sub(r'\r\n|\r|\n', '[BR]', text)
    if _EXPLICIT_BREAK_RE.search(normalized):
        return normalized

    try:
        from editor.text_render_pipeline import build_text_block_from_region
        from manga_translator.rendering import _resolve_region_render_horizontal

        patched = dict(region_data)
        if not patched.get("texts"):
            patched["texts"] = [patched.get("text") or ""]
        text_block = build_text_block_from_region(patched)

        if text_block is not None:
            render_horizontally = _resolve_region_render_horizontal(text_block)
        else:
            render_horizontally = region_data.get("direction", "h") in ("h", "horizontal", "hr")

        try:
            font_size = float(region_data.get("font_size") or getattr(text_block, "font_size", 0) or 16)
        except (TypeError, ValueError):
            font_size = 16.0
        font_family = region_data.get("font_family") or getattr(text_block, "font_family", "") or ""
        if font_family:
            text_renderer_backend.apply_font_for_render(font_family)

        bubble_width, bubble_height = _region_bubble_size(region_data, text_block)
        line_spacing = float(region_data.get("line_spacing") or 1.0)
        letter_spacing = float(region_data.get("letter_spacing") or 1.0)
        target_lang = region_data.get("target_lang") or getattr(text_block, "target_lang", None) or "en_US"

        try:
            from services import get_render_parameter_service

            render_parameter_service = get_render_parameter_service()
            if render_parameter_service is not None:
                _, config_obj = prepare_layout_context(render_parameter_service, None)
            else:
                config_obj = Config(render=RenderConfig())
        except Exception:
            config_obj = Config(render=RenderConfig())
        if text_block is not None:
            config_obj._current_region = text_block

        text_with_br, _, _, _, _ = _solve_unified_no_br_layout(
            text=normalized,
            render_horizontally=render_horizontally,
            target_font_size=max(1, font_size),
            bubble_width=bubble_width,
            bubble_height=bubble_height,
            layout_min_font_size=1,
            line_spacing_multiplier=line_spacing,
            letter_spacing_multiplier=letter_spacing,
            config=config_obj,
            target_lang=target_lang,
            max_font_size=max(1, font_size),
        )
        return text_with_br or normalized
    except Exception:
        logger.debug("Editor auto linebreak failed; keeping one-line translation", exc_info=True)
        return normalized


def prepare_layout_context(render_parameter_service, _text_renderer_backend) -> Tuple[dict, Config]:
    default_params_obj = render_parameter_service.get_default_parameters()
    global_params_dict = default_params_obj.to_dict()
    global_params_dict["direction"] = _normalize_direction(global_params_dict.get("direction"))

    config_obj = Config(render=RenderConfig(**global_params_dict))
    return global_params_dict, config_obj


def build_region_specific_params(global_params_dict: dict, text_block: TextBlock) -> dict:
    region_params = global_params_dict.copy()
    if hasattr(text_block, "direction"):
        region_params["direction"] = _normalize_direction(getattr(text_block, "direction", None))
    if hasattr(text_block, "letter_spacing"):
        region_params["letter_spacing"] = getattr(text_block, "letter_spacing", None)
    if hasattr(text_block, "char_width"):
        region_params["char_width"] = getattr(text_block, "char_width", None)
    region_font = getattr(text_block, "font_family", "")
    if region_font:
        region_params["font_family"] = region_font
    return region_params


def _dst_points_from_size(center, box_w: float, box_h: float) -> Optional[np.ndarray]:
    """축 정렬 dst_points (world). center = 렌더 중심, box_w/h = 로컬 흰 박스 크기."""
    if box_w <= 0.0 or box_h <= 0.0:
        return None
    try:
        cx, cy = float(center[0]), float(center[1])
    except (TypeError, ValueError, IndexError):
        return None
    hw = float(box_w) / 2.0
    hh = float(box_h) / 2.0
    return np.array(
        [[[cx - hw, cy - hh], [cx + hw, cy - hh],
          [cx + hw, cy + hh], [cx - hw, cy + hh]]],
        dtype=np.float32,
    )


def _dst_points_from_white_frame_local(text_block: TextBlock, white_frame_local) -> Optional[np.ndarray]:
    """사용자 흰 박스(로컬 AABB)를 렌더 타깃으로 사용. 핸들 밖 삐져나감을 방지."""
    if white_frame_local is None or len(white_frame_local) != 4:
        return None
    try:
        left, top, right, bottom = (float(v) for v in white_frame_local)
    except (TypeError, ValueError):
        return None
    return _dst_points_from_size(
        text_block.center,
        max(0.0, right - left),
        max(0.0, bottom - top),
    )


def calculate_region_dst_points(
    text_block: TextBlock,
    region_params: dict,
    config_obj: Config,
    override_dst_points=None,
    white_frame_local=None,
    prefer_white_frame: bool = False,
) -> Optional[object]:
    """计算文字渲染的目标四角点（世界坐标轴对齐矩形）。

    dst_points 以 text_block.center 为中心。在快照流程中，center 已经被设为
    render_center（白框中心的世界坐标），因此 dst_points 自然与白框对齐。

    prefer_white_frame=True (has_custom_white_frame) 이면:
      흰 박스 크기를 단일 기준으로 사용한다. 저장된 font_size는 덮지 않는다.
    """
    if override_dst_points is not None:
        return override_dst_points

    if bool(getattr(text_block, "distortMode", False)):
        from editor.desktop_ui_geometry import distort_quad_to_dst_points

        distort_dst = distort_quad_to_dst_points(getattr(text_block, "distort_quad", None))
        if distort_dst is not None:
            return distort_dst

    if prefer_white_frame:
        custom_dst = _dst_points_from_white_frame_local(text_block, white_frame_local)
        if custom_dst is not None:
            return custom_dst

    font_size = text_block.font_size if text_block.font_size > 0 else 24
    translation = text_block.translation or ""
    if not translation.strip():
        return text_block.min_rect

    is_horizontal = text_block.horizontal
    line_spacing = region_params.get("line_spacing") or config_obj.render.line_spacing or 1.0
    letter_spacing = region_params.get("letter_spacing") or getattr(config_obj.render, "letter_spacing", None) or 1.0
    char_width = region_params.get("char_width") or getattr(config_obj.render, "char_width", None) or 1.0
    stroke_width = region_params.get("stroke_width")
    if stroke_width is None:
        stroke_width = region_params.get("text_stroke_width")
    if stroke_width is None:
        stroke_width = getattr(text_block, "default_stroke_width", None)
    target_lang = text_block.target_lang or "en_US"
    region_font = region_params.get("font_family") or getattr(text_block, "font_family", "")
    text_renderer_backend.apply_font_for_render(region_font)
    from editor.geometry_commit_pipeline import measure_text_bitmap_size

    direction = getattr(text_block, "direction", None)
    if direction == "hl":
        measure_direction = "hl"
    elif is_horizontal:
        measure_direction = "h"
    else:
        measure_direction = "v"
    bitmap = measure_text_bitmap_size(
        {
            "translation": translation,
            "font_family": region_font,
            "direction": measure_direction,
            "alignment": getattr(text_block, "alignment", None) or "center",
            "target_lang": target_lang,
            "line_spacing": line_spacing,
            "letter_spacing": letter_spacing,
            "char_width": char_width,
            "italic": bool(region_params.get("italic", getattr(text_block, "italic", False))),
            "bold": bool(region_params.get("bold", getattr(text_block, "bold", False))),
            "stroke_width": stroke_width,
        },
        font_size,
    )
    if bitmap is not None:
        box_w, box_h = bitmap
    else:
        # 编辑器尺寸计算与最终渲染保持一致，避免竖排内横排块出现白框/文字不一致
        box_w, box_h, _ = calc_box_from_font(
            font_size,
            translation,
            is_horizontal,
            line_spacing,
            config_obj,
            target_lang,
            center=None,
            angle=0,
            letter_spacing=letter_spacing,
            char_width=char_width,
            stroke_width=stroke_width,
        )
    return _dst_points_from_size(text_block.center, float(box_w), float(box_h))
