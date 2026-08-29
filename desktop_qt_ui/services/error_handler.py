"""
错误处理和验证服务
提供统一的错误处理、输入验证功能
"""
import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import List


class ErrorLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool = True
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
    
    def add_error(self, message: str):
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str):
        self.warnings.append(message)

class InputValidator:
    """输入验证器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # API密钥验证模式
        self.api_patterns = {
            'openai': r'^sk-[a-zA-Z0-9]{48}$',
        }
    
    def validate_file_path(self, file_path: str) -> ValidationResult:
        """验证文件路径"""
        result = ValidationResult()
        
        if not file_path:
            result.add_error("파일 경로는 비워 둘 수 없습니다")
            return result
        
        if not os.path.exists(file_path):
            result.add_error("파일이 존재하지 않습니다")
        elif not os.path.isfile(file_path):
            result.add_error("경로가 파일이 아닙니다")
        
        return result
    
    def validate_image_file(self, file_path: str) -> ValidationResult:
        """验证图片文件"""
        result = self.validate_file_path(file_path)
        
        if result.is_valid:
            valid_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.avif', '.heic', '.heif'}
            _, ext = os.path.splitext(file_path)
            
            if ext.lower() not in valid_extensions:
                result.add_error(f"지원하지 않는 이미지 형식: {ext}")
        
        return result
    
    def validate_api_key(self, api_key: str, provider: str) -> ValidationResult:
        """验证API密钥"""
        result = ValidationResult()
        
        if not api_key:
            result.add_error("API 키는 비워 둘 수 없습니다")
            return result
        
        pattern = self.api_patterns.get(provider.lower())
        if pattern and not re.match(pattern, api_key):
            result.add_error(f"{provider} API 키 형식이 올바르지 않습니다")
        
        return result

# 全局验证器
_validator = None

def get_validator() -> InputValidator:
    global _validator
    if _validator is None:
        _validator = InputValidator()
    return _validator