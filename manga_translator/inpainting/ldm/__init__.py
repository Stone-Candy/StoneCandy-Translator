import os
import sys

# 使用绝对路径避免 importlib.invalidate_caches() 时的 KeyError
_current_dir = os.path.dirname(os.path.abspath(__file__))
_inpainting_dir = os.path.dirname(_current_dir)
if _inpainting_dir not in sys.path:
    sys.path.append(_inpainting_dir)
