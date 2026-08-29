"""核心类型定义

定义编辑器中使用的所有枚举类型和常量。
"""

from enum import Enum
from typing import Dict, List


class EditorState(str, Enum):
    """编辑器状态"""
    IDLE = "idle"              # 空闲，没有加载图片
    LOADING = "loading"        # 正在加载图片
    READY = "ready"            # 图片已加载，可以编辑
    EDITING = "editing"        # 正在编辑（修改区域等）
    PROCESSING = "processing"  # 后台处理中（OCR、翻译、修复等）
    EXPORTING = "exporting"    # 导出中
    ERROR = "error"            # 错误状态


class MaskType(str, Enum):
    """蒙版类型"""
    RAW = "raw"              # 原始蒙版
    REFINED = "refined"      # 优化后的蒙版
    INPAINTED = "inpainted"  # 修复后的蒙版
    CUSTOM = "custom"        # 自定义蒙版


class ResourceType(str, Enum):
    """资源类型"""
    IMAGE = "image"          # 图片资源
    MASK = "mask"            # 蒙版资源
    REGION = "region"        # 文本区域资源
    PREVIEW = "preview"      # 预览资源


# 合法的状态转换
ALLOWED_TRANSITIONS: Dict[EditorState, List[EditorState]] = {
    EditorState.IDLE: [EditorState.LOADING],
    EditorState.LOADING: [EditorState.READY, EditorState.ERROR, EditorState.IDLE],
    EditorState.READY: [
        EditorState.EDITING,
        EditorState.PROCESSING,
        EditorState.EXPORTING,
        EditorState.LOADING,
        EditorState.IDLE,
    ],
    EditorState.EDITING: [EditorState.READY, EditorState.PROCESSING],
    EditorState.PROCESSING: [EditorState.READY, EditorState.ERROR],
    EditorState.EXPORTING: [EditorState.READY, EditorState.ERROR],
    EditorState.ERROR: [EditorState.IDLE, EditorState.LOADING],
}

