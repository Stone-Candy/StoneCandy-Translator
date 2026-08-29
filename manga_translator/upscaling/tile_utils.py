"""
Tile-based image processing utilities for upscaling
Simple external tiling to reduce memory usage
"""

from typing import List, Tuple, Union

import numpy as np
from PIL import Image


def split_image_into_tiles(
    image: Union[Image.Image, np.ndarray],
    tile_size: int = 512,
    overlap: int = 16
) -> List[Tuple[Image.Image, Tuple[int, int, int, int]]]:
    """
    Split image into overlapping tiles
    
    Args:
        image: Input PIL image or numpy array (H, W, C)
        tile_size: Size of each tile (width and height)
        overlap: Overlap between tiles to avoid seam artifacts
    
    Returns:
        List of (tile_image, (x, y, w, h)) tuples
        where (x, y, w, h) is the position in original image
    """
    # 如果是 numpy 数组，转换为 PIL Image
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    
    width, height = image.size
    tiles = []
    
    for y in range(0, height, tile_size - overlap):
        for x in range(0, width, tile_size - overlap):
            # Calculate tile bounds
            x_end = min(x + tile_size, width)
            y_end = min(y + tile_size, height)
            
            # Crop tile
            tile = image.crop((x, y, x_end, y_end))
            
            # Store tile and its position
            tiles.append((tile, (x, y, x_end - x, y_end - y)))
    
    return tiles


def merge_tiles_into_image(
    tiles: List[Tuple[Image.Image, Tuple[int, int, int, int]]],
    original_size: Tuple[int, int],
    scale: int,
    overlap: int = 16
) -> Image.Image:
    """
    Merge upscaled tiles back into a single image
    
    Args:
        tiles: List of (upscaled_tile, (orig_x, orig_y, orig_w, orig_h)) from original positions
        original_size: (width, height) of original image
        scale: Upscale factor
        overlap: Overlap used during splitting
    
    Returns:
        Merged PIL image
    """
    orig_width, orig_height = original_size
    output_width = orig_width * scale
    output_height = orig_height * scale
    
    # Create output image with black background
    output = Image.new('RGB', (output_width, output_height), (0, 0, 0))
    
    scaled_overlap = overlap * scale
    half_overlap = scaled_overlap // 2  # Use half overlap for blending
    
    for tile, (orig_x, orig_y, orig_w, orig_h) in tiles:
        # Calculate position in output image
        out_x = orig_x * scale
        out_y = orig_y * scale
        
        # 计算裁剪区域 - 只裁剪重叠部分的一半，避免缝隙
        # 对于非边缘的 tile，裁剪掉 overlap 的一半
        crop_left = half_overlap if orig_x > 0 else 0
        crop_top = half_overlap if orig_y > 0 else 0
        
        # 右边和下边：如果不是最后一个 tile，裁剪掉 overlap 的一半
        is_right_edge = (orig_x + orig_w >= orig_width)
        is_bottom_edge = (orig_y + orig_h >= orig_height)
        
        crop_right = tile.width if is_right_edge else (tile.width - half_overlap)
        crop_bottom = tile.height if is_bottom_edge else (tile.height - half_overlap)
        
        # Ensure crop bounds are valid
        crop_right = max(crop_left + 1, min(crop_right, tile.width))
        crop_bottom = max(crop_top + 1, min(crop_bottom, tile.height))
        
        # Crop overlap from tile
        cropped_tile = tile.crop((crop_left, crop_top, crop_right, crop_bottom))
        
        # Calculate paste position
        paste_x = out_x + crop_left
        paste_y = out_y + crop_top
        
        # Ensure paste position is within bounds
        paste_x = min(paste_x, output_width - cropped_tile.width)
        paste_y = min(paste_y, output_height - cropped_tile.height)
        
        # Paste into output
        output.paste(cropped_tile, (paste_x, paste_y))
    
    return output

