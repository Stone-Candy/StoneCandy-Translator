from typing import List

from PIL import Image

from ..config import Upscaler
from .common import CommonUpscaler, OfflineUpscaler
from .esrgan import ESRGANUpscaler
from .esrgan_pytorch import ESRGANUpscalerPytorch
from .mangajanai import MangaJaNaiUpscaler
from .realcugan import RealCUGANUpscaler
from .waifu2x import Waifu2xUpscaler

UPSCALERS = {
    Upscaler.waifu2x: Waifu2xUpscaler,
    Upscaler.esrgan: ESRGANUpscaler,
    Upscaler.upscler4xultrasharp: ESRGANUpscalerPytorch,
    Upscaler.realcugan: RealCUGANUpscaler,
    Upscaler.mangajanai: MangaJaNaiUpscaler,
}
upscaler_cache = {}

def get_upscaler(key: Upscaler, *args, **kwargs) -> CommonUpscaler:
    if key not in UPSCALERS:
        raise ValueError(f'Could not find upscaler for: "{key}". Choose from the following: %s' % ','.join(UPSCALERS))
    
    # Create a cache key that includes the upscaler type and its parameters
    cache_key_parts = [str(key)]
    if key == Upscaler.realcugan and 'model_name' in kwargs:
        cache_key_parts.append(kwargs['model_name'])
    if key == Upscaler.mangajanai and 'model_name' in kwargs:
        cache_key_parts.append(kwargs['model_name'])
    if 'tile_size' in kwargs:
        cache_key_parts.append(f"tile{kwargs['tile_size']}")
    cache_key = '_'.join(cache_key_parts)
    
    if cache_key not in upscaler_cache:
        upscaler = UPSCALERS[key]
        upscaler_cache[cache_key] = upscaler(*args, **kwargs)
    return upscaler_cache[cache_key]

async def prepare(upscaler_key: Upscaler, **kwargs):
    upscaler = get_upscaler(upscaler_key, **kwargs)
    if isinstance(upscaler, OfflineUpscaler):
        await upscaler.download()

async def dispatch(upscaler_key: Upscaler, image_batch: List[Image.Image], upscale_ratio: int, device: str = 'cpu', **kwargs) -> List[Image.Image]:
    if upscale_ratio == 1:
        return image_batch
    upscaler = get_upscaler(upscaler_key, **kwargs)
    if isinstance(upscaler, OfflineUpscaler):
        await upscaler.load(device)
    return await upscaler.upscale(image_batch, upscale_ratio)

async def unload(upscaler_key: Upscaler, **kwargs):
    """卸载超分模型并清理显存"""
    cache_key_parts = [str(upscaler_key)]
    if upscaler_key == Upscaler.realcugan and 'model_name' in kwargs:
        cache_key_parts.append(kwargs['model_name'])
    if upscaler_key == Upscaler.mangajanai and 'model_name' in kwargs:
        cache_key_parts.append(kwargs['model_name'])
    if 'tile_size' in kwargs:
        cache_key_parts.append(f"tile{kwargs['tile_size']}")
    cache_key = '_'.join(cache_key_parts)
    
    if cache_key in upscaler_cache:
        upscaler = upscaler_cache.pop(cache_key)
        if isinstance(upscaler, OfflineUpscaler):
            await upscaler.unload()
        
        # 统一的显存清理（适用于所有超分模型）
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, 'ipc_collect'):
                    torch.cuda.ipc_collect()
                torch.cuda.synchronize()
        except Exception:
            pass


