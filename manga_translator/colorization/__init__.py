from PIL import Image

from ..config import Colorizer
from .common import CommonColorizer, OfflineColorizer
from .manga_colorization_v2 import MangaColorizationV2
from .model_api_colorizer import GeminiColorizer, OpenAIColorizer

COLORIZERS = {
    Colorizer.mc2: MangaColorizationV2,
    Colorizer.openai_colorizer: OpenAIColorizer,
    Colorizer.gemini_colorizer: GeminiColorizer,
}
colorizer_cache = {}
NON_CACHED_COLORIZERS = {
    Colorizer.openai_colorizer,
    Colorizer.gemini_colorizer,
}

def get_colorizer(key: Colorizer, *args, **kwargs) -> CommonColorizer:
    if key not in COLORIZERS:
        raise ValueError(f'Could not find colorizer for: "{key}". Choose from the following: %s' % ','.join(COLORIZERS))
    if key in NON_CACHED_COLORIZERS:
        return COLORIZERS[key](*args, **kwargs)
    if not colorizer_cache.get(key):
        upscaler = COLORIZERS[key]
        colorizer_cache[key] = upscaler(*args, **kwargs)
    return colorizer_cache[key]

async def prepare(key: Colorizer):
    upscaler = get_colorizer(key)
    if isinstance(upscaler, OfflineColorizer):
        await upscaler.download()

async def dispatch(key: Colorizer, device: str = 'cpu', **kwargs) -> Image.Image:
    colorizer = get_colorizer(key)
    if isinstance(colorizer, OfflineColorizer):
        await colorizer.load(device)
    return await colorizer.colorize(**kwargs)

async def unload(key: Colorizer):
    colorizer = colorizer_cache.pop(key, None)
    if isinstance(colorizer, OfflineColorizer):
        await colorizer.unload()
