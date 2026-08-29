import logging
import sys

import colorama

from .generic import replace_prefix

ROOT_TAG = 'manga-translator'

class Formatter(logging.Formatter):
    def formatMessage(self, record: logging.LogRecord) -> str:
        if record.levelno >= logging.ERROR:
            self._style._fmt = f'{colorama.Fore.RED}%(levelname)s:{colorama.Fore.RESET} [%(name)s] %(message)s'
        elif record.levelno >= logging.WARN:
            self._style._fmt = f'{colorama.Fore.YELLOW}%(levelname)s:{colorama.Fore.RESET} [%(name)s] %(message)s'
        elif record.levelno == logging.DEBUG:
            self._style._fmt = '[%(name)s] %(message)s'
        else:
            self._style._fmt = '[%(name)s] %(message)s'
        result = super().formatMessage(record)
        # ✅ 每次格式化后强制刷新输出
        sys.stdout.flush()
        return result

class Filter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Try to filter out logs from imported modules
        if not (record.name.startswith(ROOT_TAG) or record.name.startswith('desktop-ui')):
            return False
        # Shorten the name
        record.name = replace_prefix(record.name, ROOT_TAG + '.', '')
        record.name = replace_prefix(record.name, 'desktop-ui.', '')
        return super().filter(record)

root = logging.getLogger(ROOT_TAG)
_initialized = False

def init_logging():
    global _initialized
    if _initialized:
        return
    _initialized = True
    
    # ✅ 强制刷新标准输出（解决日志卡住问题）
    import os
    import sys
    # 设置环境变量，禁用 Python 输出缓冲
    os.environ['PYTHONUNBUFFERED'] = '1'
    # 如果 stdout 有 reconfigure 方法，设置为无缓冲
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except Exception:
            pass
    
    # 强制添加 handler（不依赖 basicConfig）
    if not logging.root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        logging.root.addHandler(handler)
    
    # 只修改 StreamHandler（控制台），不修改 FileHandler（日志文件）
    # 这样可以保留 main.py 配置的文件日志处理器的原始格式
    for h in logging.root.handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.setFormatter(Formatter())
            h.addFilter(Filter())
            h.setLevel(logging.INFO)
            # ✅ 强制每次日志后刷新输出
            h.flush()
    
    # Explicitly set the root logger level
    root.setLevel(logging.INFO)
    logging.getLogger().setLevel(logging.INFO)

def set_log_level(level):
    root.setLevel(level)
    # Also set the root logger level to ensure DEBUG messages pass through
    logging.getLogger().setLevel(level)
    # 同时设置所有handler的级别
    for handler in logging.root.handlers:
        handler.setLevel(level)

def get_logger(name: str):
    return root.getChild(name)

file_handlers = {}

def add_file_logger(path: str):
    if path in file_handlers:
        return
    file_handlers[path] = logging.FileHandler(path, encoding='utf8')
    logging.root.addHandler(file_handlers[path])

def remove_file_logger(path: str):
    if path in file_handlers:
        logging.root.removeHandler(file_handlers[path])
        file_handlers[path].close()
        del file_handlers[path]
