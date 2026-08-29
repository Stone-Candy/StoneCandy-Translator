import os
import sys

# 添加onnxruntime的capi目录到DLL搜索路径
if sys.platform == 'win32':
    if hasattr(os, 'add_dll_directory'):
        # Python 3.8+
        onnx_capi_dir = os.path.join(sys._MEIPASS, 'onnxruntime', 'capi')
        if os.path.exists(onnx_capi_dir):
            os.add_dll_directory(onnx_capi_dir)
