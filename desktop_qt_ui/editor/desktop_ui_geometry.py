"""
完全基于 desktop-ui 的几何系统
替换 Qt 的坐标系统，使用 desktop-ui 的数据结构和算法
"""
import math
from typing import List, Optional, Tuple

# === desktop-ui 的核心几何函数 ===

def rotate_point(x, y, angle_deg, cx, cy):
    """围绕中心点旋转一个点"""
    angle_rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    x_new = cx + (x - cx) * cos_a - (y - cy) * sin_a
    y_new = cy + (x - cx) * sin_a + (y - cy) * cos_a
    return x_new, y_new

def get_polygon_center(vertices: List[Tuple[float, float]]) -> Tuple[float, float]:
    """
    计算多边形的中心点（边界框中心）

    注意：lines存储的是未旋转的世界坐标，所以这里计算的是
    这些未旋转坐标的简单边界框中心，不使用cv2.minAreaRect
    """
    if not vertices:
        return 0, 0

    # 直接计算边界框中心（对于未旋转的坐标）
    x_coords = [v[0] for v in vertices]
    y_coords = [v[1] for v in vertices]

    if not x_coords or not y_coords:
        return 0, 0

    center_x = (min(x_coords) + max(x_coords)) / 2
    center_y = (min(y_coords) + max(y_coords)) / 2

    return center_x, center_y

def calculate_new_vertices_on_drag(
    original_vertices: List[Tuple[float, float]],
    dragged_vertex_index: int,
    new_mouse_position: Tuple[float, float],
    angle: float = 0,
    center: Optional[Tuple[float, float]] = None
) -> List[Tuple[float, float]]:
    """当单个顶点被拖拽时，计算所有顶点的新位置。

    中心点(center)固定：不再以对角顶点为锚点，而是把鼠标位置换算到
    model space 后，以 center 为对称中心重新生成四个顶点。
    """

    rotation_center = center if center else get_polygon_center(original_vertices)
    cx, cy = rotation_center

    # For non-quadrilaterals, use simple logic (与中心锚点无关，保持原样)
    if len(original_vertices) != 4:
        if angle != 0:
             new_mouse_position = rotate_point(new_mouse_position[0], new_mouse_position[1], -angle, cx, cy)
        new_vertices_fallback = list(original_vertices)
        new_vertices_fallback[dragged_vertex_index] = new_mouse_position
        return new_vertices_fallback

    # 1. 把鼠标位置从 world space 转回 model space（与 original_vertices 同一坐标系）
    #    회전 축은 넘겨받은(혹은 계산된) rotation_center(cx, cy)를 그대로 사용
    if angle != 0:
        mouse_model = rotate_point(new_mouse_position[0], new_mouse_position[1], -angle, cx, cy)
    else:
        mouse_model = new_mouse_position

    # 2. 리사이즈 대칭 기준점은 넘겨받은 center가 아니라
    #    '지금 이 박스 자신의 실제 중심'에서 매번 다시 구한다
    box_cx, box_cy = get_polygon_center(original_vertices)

    # 3. model space 中，鼠标到 box 中心的距离即为新的半宽/半高
    new_hw = abs(mouse_model[0] - box_cx)
    new_hh = abs(mouse_model[1] - box_cy)

    # 4. 以 box 中心为对称中心重新生成四个顶点，符号取自各顶点原本相对 box 中心的方位，
    #    这样不需要假设固定的顶点顺序（左上/右上/右下/左下）
    new_vertices = []
    for vx, vy in original_vertices:
        sx = 1.0 if vx >= box_cx else -1.0
        sy = 1.0 if vy >= box_cy else -1.0
        new_vertices.append((box_cx + sx * new_hw, box_cy + sy * new_hh))

    return new_vertices

def calculate_new_edge_on_drag(
    original_vertices: List[Tuple[float, float]],
    dragged_edge_index: int,
    new_mouse_position: Tuple[float, float],
    angle: float = 0,
    center: Optional[Tuple[float, float]] = None
) -> List[Tuple[float, float]]:
    """当边缘被拖拽时，计算新的顶点位置 (沿法线移动)

    只调整被拖拽轴向的半宽/半高，对边一起对称移动。
    对称中心是当前白框中心，不是传入的 region center.
    """

    rotation_center = center if center else get_polygon_center(original_vertices)
    cx, cy = rotation_center

    # 1. Get edge vertices in model space
    v1_model_idx = dragged_edge_index
    v2_model_idx = (v1_model_idx + 1) % len(original_vertices)
    v1_model = original_vertices[v1_model_idx]
    v2_model = original_vertices[v2_model_idx]

    # 2. 把鼠标位置从 world space 转回 model space
    #    회전 축은 item pos(= geo.center)인 rotation_center를 그대로 사용
    if angle != 0:
        mouse_model = rotate_point(new_mouse_position[0], new_mouse_position[1], -angle, cx, cy)
    else:
        mouse_model = new_mouse_position

    # 3. 리사이즈 대칭 기준점은 넘겨받은 center가 아니라
    #    '지금 이 박스 자신의 실제 중심'에서 구한다.
    #    geo.center를 쓰면 흰 박스가 원본 중심에서 어긋난 순간
    #    상하/좌우 핸들 시작점이 점프하거나 한 축이 붕괴한다.
    box_cx, box_cy = get_polygon_center(original_vertices)

    # 4. 判断这是水平边还是竖直边（沿用原逻辑，用来决定只调整哪个轴）
    model_edge_dx = abs(v2_model[0] - v1_model[0])
    model_edge_dy = abs(v2_model[1] - v1_model[1])

    new_vertices = []
    if model_edge_dx > model_edge_dy:
        # 水平边 → 拖拽改变的是高度（y 方向），以 box_cy 为对称中心
        new_hh = abs(mouse_model[1] - box_cy)
        for vx, vy in original_vertices:
            sy = 1.0 if vy >= box_cy else -1.0
            new_vertices.append((vx, box_cy + sy * new_hh))
    else:
        # 竖直边 → 拖拽改变的是宽度（x 方向），以 box_cx 为对称中心
        new_hw = abs(mouse_model[0] - box_cx)
        for vx, vy in original_vertices:
            sx = 1.0 if vx >= box_cx else -1.0
            new_vertices.append((box_cx + sx * new_hw, vy))

    return new_vertices


def normalize_distort_quad(value):
    """Return 4 world-space [x, y] points, or None."""
    if value is None:
        return None
    try:
        points = list(value)
        if len(points) == 1 and isinstance(points[0], (list, tuple)):
            points = list(points[0])
        if len(points) != 4:
            return None
        quad = []
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                return None
            quad.append([float(point[0]), float(point[1])])
        return quad
    except (TypeError, ValueError):
        return None


def is_convex_quad(quad, min_area: float = 16.0) -> bool:
    """Reject bowties, flipped, or near-zero quads."""
    pts = normalize_distort_quad(quad)
    if pts is None:
        return False
    signs = []
    area2 = 0.0
    for i in range(4):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % 4]
        x2, y2 = pts[(i + 2) % 4]
        cross = (x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1)
        area2 += x0 * y1 - x1 * y0
        if abs(cross) > 1e-6:
            signs.append(cross > 0)
    if len(set(signs)) != 1:
        return False
    return abs(area2) * 0.5 >= min_area


def white_frame_world_quad(center, angle, rect_local):
    """Bake the current rotated white frame into 4 world-space corners."""
    if not (isinstance(center, (list, tuple)) and len(center) >= 2):
        return None
    if not (isinstance(rect_local, (list, tuple)) and len(rect_local) == 4):
        return None
    try:
        cx, cy = float(center[0]), float(center[1])
        left, top, right, bottom = (float(v) for v in rect_local)
        angle_deg = float(angle or 0.0)
    except (TypeError, ValueError):
        return None
    local_corners = (
        (left, top),
        (right, top),
        (right, bottom),
        (left, bottom),
    )
    quad = []
    for lx, ly in local_corners:
        if angle_deg != 0:
            wx, wy = rotate_point(cx + lx, cy + ly, angle_deg, cx, cy)
        else:
            wx, wy = cx + lx, cy + ly
        quad.append([wx, wy])
    return quad


def distort_quad_to_dst_points(quad):
    pts = normalize_distort_quad(quad)
    if pts is None:
        return None
    import numpy as np
    return np.array([[pts]], dtype=np.float32).reshape(1, 4, 2)


