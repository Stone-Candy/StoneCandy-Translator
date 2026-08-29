"""
替换翻译专用的检测模块

和 win.py 的流程一致：
1. 调用 CTD 检测器获取原始蒙版（跳过检测器内部的精炼）
2. 使用 ctd_utils/textmask.refine_mask 处理原始蒙版
3. 使用 REFINEMASK_INPAINT 模式（会进行5x5膨胀）
"""

from typing import List, Tuple

import cv2
import numpy as np
import torch

from ..detection.ctd import ComicTextDetector
from ..detection.ctd_utils.textmask import REFINEMASK_INPAINT, refine_mask
from ..detection.ctd_utils.utils.db_utils import postprocess_mask
from ..detection.ctd_utils.utils.imgproc_utils import preprocess_img
from ..utils import Quadrilateral, det_rearrange_forward


class ReplaceTranslationCTD:
    """
    替换翻译专用的 CTD 检测器封装
    
    和 win.py 完全一致的蒙版精炼流程
    """
    
    def __init__(self, detector: ComicTextDetector):
        self.detector = detector
    
    async def detect_with_winpy_refine(
        self,
        image: np.ndarray,
        detect_size: int = 1536,
        text_threshold: float = 0.5,
        box_threshold: float = 0.7,
        unclip_ratio: float = 2.3,
        verbose: bool = False
    ) -> Tuple[List[Quadrilateral], np.ndarray, np.ndarray]:
        """
        使用 win.py 风格的蒙版精炼流程
        
        Returns:
            (textlines, mask_raw, mask_refined)
            - textlines: 检测到的文本行
            - mask_raw: 原始蒙版（神经网络直接输出）
            - mask_refined: 精炼后的蒙版（使用 REFINEMASK_INPAINT）
        """
        # 使用检测器的内部方法获取原始输出
        im_h, im_w = image.shape[:2]
        
        # 调用 det_rearrange_forward 获取原始 mask
        lines_map, mask = det_rearrange_forward(
            image, 
            self.detector.det_batch_forward_ctd, 
            self.detector.input_size[0], 
            4, 
            self.detector.device, 
            verbose
        )
        
        if lines_map is None:
            img_in, ratio, dw, dh = preprocess_img(
                image, 
                input_size=self.detector.input_size, 
                device=self.detector.device, 
                half=self.detector.half, 
                to_tensor=self.detector.backend=='torch'
            )
            blks, mask, lines_map = self.detector.model(img_in)
            
            if self.detector.backend == 'opencv':
                if mask.shape[1] == 2:
                    tmp = mask
                    mask = lines_map
                    lines_map = tmp
            mask = mask.squeeze()
            mask = mask[..., :mask.shape[0]-dh, :mask.shape[1]-dw]
            lines_map = lines_map[..., :lines_map.shape[2]-dh, :lines_map.shape[3]-dw]
        
        mask = postprocess_mask(mask)
        lines, scores = self.detector.seg_rep(None, lines_map, height=im_h, width=im_w)
        box_thresh = 0.6
        idx = np.where(scores[0] > box_thresh)
        lines, scores = lines[0][idx], scores[0][idx]
        
        # 调整 mask 到原始图像尺寸
        mask = cv2.resize(mask, (im_w, im_h), interpolation=cv2.INTER_LINEAR)
        
        # 创建 textlines
        textlines = [Quadrilateral(pts.astype(int), '', score) for pts, score in zip(lines, scores)]
        
        # 关键：使用 REFINEMASK_INPAINT 模式精炼（和 win.py 一致）
        mask_refined = refine_mask(image, mask, textlines, refine_mode=REFINEMASK_INPAINT)
        
        # 清理 GPU 内存
        if self.detector.device.startswith('cuda') or self.detector.device == 'mps':
            try:
                if torch.cuda.is_available():
                    pass
            except Exception:
                pass
        
        # 返回和 win.py 一样的格式：(textlines, mask_raw, mask_refined)
        return textlines, mask, mask_refined


async def detect_for_replace_translation(
    detector: ComicTextDetector,
    image: np.ndarray,
    detect_size: int = 1536,
    text_threshold: float = 0.5,
    box_threshold: float = 0.7,
    unclip_ratio: float = 2.3,
    verbose: bool = False
) -> Tuple[List[Quadrilateral], np.ndarray, np.ndarray]:
    """
    替换翻译专用的检测函数
    
    和 win.py 完全一致：返回 (textlines, mask_raw, mask_refined)
    """
    wrapper = ReplaceTranslationCTD(detector)
    return await wrapper.detect_with_winpy_refine(
        image, detect_size, text_threshold, box_threshold, unclip_ratio, verbose
    )

