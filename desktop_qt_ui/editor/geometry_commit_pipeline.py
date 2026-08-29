"""几何编辑提交管线 — 构建旋转 / 白框编辑的 region_data。"""
import copy
from typing import Optional

from manga_translator.rendering.text_render import quantize_font_size
from manga_translator.rendering.text_render import strip_edge_layout_breaks

_PROBE_FONT_MAX = 64.0
_SEARCH_STEP = 0.2


def _is_rect_like(value) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 4


def strip_region_edge_breaks(region_data: dict) -> None:
    """Drop leading/trailing empty [BR] lines so a leftover newline is not a layout line."""
    if not isinstance(region_data, dict):
        return
    for key in ("translation", "translation_raw"):
        value = region_data.get(key)
        if isinstance(value, str) and value:
            cleaned = strip_edge_layout_breaks(value)
            if cleaned != value:
                region_data[key] = cleaned


def _font_fit_axis(edit_mode: Optional[str], handle_index, is_horizontal: bool) -> str:
    """상하 핸들=높이, 좌우 핸들=폭, 대각선은 글자 진행 본축."""
    if edit_mode == "white_edge":
        try:
            index = int(handle_index)
        except (TypeError, ValueError):
            index = -1
        if index in (0, 2):
            return "height"
        if index in (1, 3):
            return "width"
    return "height" if is_horizontal else "width"


def measure_text_bitmap_size(region_data: dict, font_size: float) -> Optional[tuple[float, float]]:
    """put_text로 찍은 글자 비트맵 크기 (w, h). 흰 박스는 넣지 않는다.

    에디터 실제 렌더와 같은 캔버스(스트로크 여백 포함)를 잰다.
    """
    try:
        from editor.text_renderer_backend import apply_font_for_render
        from manga_translator.rendering import text_render

        fs = quantize_font_size(font_size)
        translation = (region_data.get("translation") or "").strip()
        if fs < 1.0 or not translation:
            return None

        apply_font_for_render(region_data.get("font_family") or "")
        direction = region_data.get("direction", "h")
        is_horizontal = direction in ("h", "horizontal", "hr")
        text_for_render = text_render.prepare_text_for_direction_rendering(
            translation,
            is_horizontal=is_horizontal,
        )
        line_spacing = float(region_data.get("line_spacing") or 1.0)
        letter_spacing = float(region_data.get("letter_spacing") or 1.0)
        char_width = float(region_data.get("char_width") or 1.0)
        italic = bool(region_data.get("italic", False))
        bold = bool(region_data.get("bold", False))
        stroke_width = region_data.get("stroke_width", region_data.get("text_stroke_width"))
        try:
            stroke_val = None if stroke_width is None else float(stroke_width)
        except (TypeError, ValueError):
            stroke_val = None
        # put_text는 bg is None이면 스트로크 캔버스를 안 만든다. 화면 렌더와 맞춘다.
        bg = None if stroke_val == 0.0 else (0, 0, 0)
        if is_horizontal:
            surface = text_render.put_text_horizontal(
                fs,
                text_for_render,
                1,
                1,
                region_data.get("alignment") or "center",
                direction == "hl",
                (0, 0, 0),
                bg,
                region_data.get("target_lang") or "",
                True,
                line_spacing,
                config=None,
                stroke_width=stroke_width,
                letter_spacing=letter_spacing,
                char_width=char_width,
                italic=italic,
                bold=bold,
            )
        else:
            surface = text_render.put_text_vertical(
                fs,
                text_for_render,
                1,
                region_data.get("alignment") or "center",
                (0, 0, 0),
                bg,
                line_spacing,
                config=None,
                stroke_width=stroke_width,
                letter_spacing=letter_spacing,
                char_width=char_width,
                italic=italic,
                bold=bold,
            )
        if surface is None or getattr(surface, "size", 0) == 0:
            return None
        bitmap_h, bitmap_w = surface.shape[:2]
        if bitmap_w <= 0 or bitmap_h <= 0:
            return None
        return float(bitmap_w), float(bitmap_h)
    except Exception:
        return None


def _contained_visual_bitmap_size(
    natural_w: float,
    natural_h: float,
    box_w: float,
    box_h: float,
    is_horizontal: bool,
) -> tuple[float, float]:
    """화면 렌더와 같은 정수 패딩+리사이즈 후, 글자 비트맵이 차지하는 크기."""
    w_temp = max(1, int(round(natural_w)))
    h_temp = max(1, int(round(natural_h)))
    dest_w = max(1, int(round(box_w)))
    dest_h = max(1, int(round(box_h)))
    r_temp = w_temp / h_temp
    r_orig = dest_w / dest_h
    if r_temp > r_orig:
        if is_horizontal:
            h_ext = int((w_temp / r_orig - h_temp) // 2) if r_orig > 0 else 0
        else:
            h_ext = int(w_temp / (2 * r_orig) - h_temp / 2) if r_orig > 0 else 0
        padded_w = w_temp
        padded_h = h_temp + max(h_ext, 0) * 2
    else:
        if is_horizontal:
            w_ext = int((h_temp * r_orig - w_temp) // 2)
        else:
            w_ext = int((h_temp * r_orig - w_temp) / 2)
        padded_w = w_temp + max(w_ext, 0) * 2
        padded_h = h_temp
    if padded_w <= 0 or padded_h <= 0:
        return float(w_temp), float(h_temp)
    return w_temp * dest_w / padded_w, h_temp * dest_h / padded_h


def _nearest_font_from_visual_bitmap(
    region_data: dict,
    current_fs: float,
    natural_w: float,
    natural_h: float,
    visual_w: float,
    visual_h: float,
    fit_axis: str,
) -> float:
    """화면 비트맵 픽셀 높이에 put_text 비트맵 픽셀이 맞는 font_size."""
    target = float(visual_h if fit_axis == "height" else visual_w)
    natural = float(natural_h if fit_axis == "height" else natural_w)
    if target <= 0.0 or natural <= 0.0 or current_fs < 1.0:
        return current_fs

    target_px = max(1, int(round(target)))
    seed = quantize_font_size(current_fs * (target / natural))
    if seed > _PROBE_FONT_MAX:
        return seed

    cache: dict[float, int] = {
        quantize_font_size(current_fs): max(1, int(round(natural))),
    }

    def axis_px(fs: float) -> int:
        fs = quantize_font_size(fs)
        if fs in cache:
            return cache[fs]
        measured = measure_text_bitmap_size(region_data, fs)
        value = 0
        if measured is not None:
            value = int(round(measured[1] if fit_axis == "height" else measured[0]))
        cache[fs] = value
        return value

    def _snap(fs: float) -> float:
        return quantize_font_size(round(fs / _SEARCH_STEP) * _SEARCH_STEP)

    seed = _snap(seed)
    cursor = max(1.0, min(seed, _PROBE_FONT_MAX))
    cursor_px = axis_px(cursor)
    if cursor_px < target_px:
        while True:
            nxt = _snap(cursor + _SEARCH_STEP)
            if nxt <= cursor or nxt > _PROBE_FONT_MAX:
                break
            cursor = nxt
            cursor_px = axis_px(cursor)
            if cursor_px >= target_px:
                break
    elif cursor_px > target_px:
        while True:
            nxt = _snap(cursor - _SEARCH_STEP)
            if nxt >= cursor or nxt < 1.0:
                break
            cursor = nxt
            cursor_px = axis_px(cursor)
            if cursor_px <= target_px:
                break

    match_px = cursor_px if cursor_px == target_px else None
    if match_px is None:
        prev = _snap(cursor - _SEARCH_STEP)
        nxt = _snap(cursor + _SEARCH_STEP)
        best_fs = cursor
        best_err = abs(cursor_px - target_px) if cursor_px > 0 else 10**9
        for fs in (prev, nxt):
            if fs < 1.0 or fs > _PROBE_FONT_MAX:
                continue
            value = axis_px(fs)
            if value <= 0:
                continue
            err = abs(value - target_px)
            if err < best_err or (err == best_err and fs > best_fs):
                best_fs = fs
                best_err = err
                match_px = value if err == 0 else match_px
        if match_px is None:
            return quantize_font_size(best_fs)
        cursor = best_fs

    low = high = cursor
    nxt = _snap(low - _SEARCH_STEP)
    while nxt >= 1.0 and nxt < low and axis_px(nxt) == match_px:
        low = nxt
        nxt = _snap(low - _SEARCH_STEP)
    nxt = _snap(high + _SEARCH_STEP)
    while nxt <= _PROBE_FONT_MAX and nxt > high and axis_px(nxt) == match_px:
        high = nxt
        nxt = _snap(high + _SEARCH_STEP)
    return quantize_font_size((low + high) * 0.5)


def refit_font_size_to_white_frame(region_data: dict, fit_axis: Optional[str] = None) -> None:
    """핸들을 놓은 순간 화면에 보이는 글자 비트맵 크기에 맞는 font_size를 기록한다.

    흰 박스가 아니라, put_text 비트맵이 박스 안에 비율 유지로 들어갔을 때의
    크기를 목표로 한다. 더미 레이어(calc_box_from_font)는 쓰지 않는다.
    """
    if not isinstance(region_data, dict):
        return
    try:
        wf = region_data.get("white_frame_rect_local")
        if not _is_rect_like(wf):
            return
        left, top, right, bottom = (float(v) for v in wf)
        box_w = max(0.0, right - left)
        box_h = max(0.0, bottom - top)
        translation = (region_data.get("translation") or "").strip()
        current_fs = float(region_data.get("font_size") or 0.0)
        if box_w <= 0.0 or box_h <= 0.0 or not translation or current_fs < 1.0:
            return

        font_value = region_data.get("font_family") or ""
        if font_value:
            try:
                from editor.text_renderer_backend import apply_font_for_render

                apply_font_for_render(font_value)
            except Exception:
                from manga_translator.rendering import text_render

                text_render.set_font(font_value)

        natural = measure_text_bitmap_size(region_data, current_fs)
        if natural is None:
            return
        direction = region_data.get("direction", "h")
        is_horizontal = direction in ("h", "horizontal", "hr")
        visual_w, visual_h = _contained_visual_bitmap_size(
            natural[0], natural[1], box_w, box_h, is_horizontal,
        )
        if fit_axis not in ("width", "height"):
            fit_axis = "height" if is_horizontal else "width"
        region_data["font_size"] = _nearest_font_from_visual_bitmap(
            region_data,
            current_fs,
            natural[0],
            natural[1],
            visual_w,
            visual_h,
            fit_axis,
        )
    except Exception:
        return


def repair_region_font_box_consistency(region_data: dict) -> None:
    """Normalize leftover [BR]. Stored font_size is left as-is."""
    strip_region_edge_breaks(region_data)


def build_rotate_region_data(
    region_data: dict,
    new_angle: float,
    new_center: Optional[list] = None,
    new_lines: Optional[list] = None,
) -> dict:
    """构建旋转提交数据（可选包含 center / lines 同步）。"""
    data = copy.deepcopy(region_data)
    data["angle"] = float(new_angle)
    if new_center is not None and len(new_center) >= 2:
        data["center"] = [float(new_center[0]), float(new_center[1])]
    if new_lines is not None:
        data["lines"] = copy.deepcopy(new_lines)
    return data


def build_white_frame_region_data(
    region_data: dict,
    white_patch: dict,
    white_frame_local: Optional[list],
    old_white_frame_local: Optional[list] = None,
    edit_mode: Optional[str] = None,
    handle_index=None,
) -> dict:
    """构建白框编辑提交数据（含可选字体尺寸回写）。"""
    data = copy.deepcopy(region_data)
    data.update(white_patch)
    strip_region_edge_breaks(data)

    if edit_mode == "white_move":
        return data

    if not _white_frame_size_changed(old_white_frame_local, white_frame_local):
        return data

    if _is_rect_like(white_frame_local):
        data["white_frame_rect_local"] = list(white_frame_local)
    direction = data.get("direction", "h")
    is_horizontal = direction in ("h", "horizontal", "hr")
    # 핸들을 놓은 순간에만 박스에 맞는 font_size 숫자를 기록한다. 박스 geometry는 유지.
    refit_font_size_to_white_frame(
        data,
        fit_axis=_font_fit_axis(edit_mode, handle_index, is_horizontal),
    )
    return data


def _white_frame_size_changed(
    old_wf_local: Optional[list],
    new_wf_local: Optional[list],
) -> bool:
    """白框宽高가 조금이라도 바뀌면 글자 크기를 다시 잰다."""
    old_size = _extract_white_frame_size(old_wf_local)
    new_size = _extract_white_frame_size(new_wf_local)
    if old_size is None or new_size is None:
        return True
    return abs(old_size[0] - new_size[0]) > 0.05 or abs(old_size[1] - new_size[1]) > 0.05


def _extract_white_frame_size(wf_local: Optional[list]) -> Optional[tuple[float, float]]:
    if wf_local is None or len(wf_local) != 4:
        return None
    left, top, right, bottom = wf_local
    width = float(max(0.0, right - left))
    height = float(max(0.0, bottom - top))
    if width <= 0.0 or height <= 0.0:
        return None
    return width, height
