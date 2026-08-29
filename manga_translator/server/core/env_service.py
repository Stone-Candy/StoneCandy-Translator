"""
环境变量服务（EnvService）

管理 .env 文件的加载、解析、更新和热重载。
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class EnvService:
    """环境变量服务"""
    
    def __init__(self, env_file: str = ".env"):
        """
        初始化环境变量服务
        
        Args:
            env_file: .env 文件路径（相对于工作区根目录）
        """
        self.env_file = env_file
        self.env_vars: Dict[str, str] = {}
        self._load_env_file()
    
    def load_env_file(self, path: Optional[str] = None) -> Dict[str, str]:
        """
        加载 .env 文件
        
        Args:
            path: .env 文件路径（如果为 None，使用初始化时的路径）
        
        Returns:
            Dict[str, str]: 加载的环境变量字典
        """
        if path:
            self.env_file = path
        
        return self._load_env_file()
    
    def save_env_file(self, path: Optional[str] = None, env_vars: Optional[Dict[str, str]] = None) -> bool:
        """
        保存 .env 文件
        
        Args:
            path: .env 文件路径（如果为 None，使用当前路径）
            env_vars: 要保存的环境变量（如果为 None，使用当前环境变量）
        
        Returns:
            bool: 保存是否成功
        """
        if path:
            self.env_file = path
        
        if env_vars is None:
            env_vars = self.env_vars
        
        try:
            env_path = Path(self.env_file)
            
            # 构建 .env 文件内容
            lines = []
            for key, value in env_vars.items():
                # 统一使用双引号包裹所有值，确保 python-dotenv 正确解析
                # 转义双引号和反斜杠
                value = value.replace('\\', '\\\\').replace('"', '\\"')
                lines.append(f'{key}="{value}"')
            
            # 写入文件
            env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            
            logger.info(f"Saved {len(env_vars)} environment variable(s) to {self.env_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save .env file: {e}")
            return False
    
    def reload_env(self) -> bool:
        """
        重新加载环境变量
        
        Returns:
            bool: 重新加载是否成功
        """
        try:
            self._load_env_file()
            logger.info("Environment variables reloaded")
            return True
        except Exception as e:
            logger.error(f"Failed to reload environment variables: {e}")
            return False
    
    def get_env_vars(self, show_values: bool = False) -> Dict[str, str]:
        """
        获取环境变量
        
        Args:
            show_values: 是否显示实际值（False 时隐藏敏感信息）
        
        Returns:
            Dict[str, str]: 环境变量字典
        """
        if show_values:
            return self.env_vars.copy()
        else:
            # 隐藏敏感值
            return {
                key: self._mask_value(value)
                for key, value in self.env_vars.items()
            }
    
    def get_env_var(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        获取单个环境变量
        
        Args:
            key: 环境变量名
            default: 默认值
        
        Returns:
            Optional[str]: 环境变量值
        """
        return self.env_vars.get(key, default)
    
    def update_env_var(self, key: str, value: str) -> bool:
        """
        更新单个环境变量
        
        Args:
            key: 环境变量名
            value: 环境变量值
        
        Returns:
            bool: 更新是否成功
        """
        try:
            # 更新内存中的值
            self.env_vars[key] = value
            
            # 同时更新系统环境变量
            os.environ[key] = value
            
            # 保存到文件
            success = self.save_env_file()
            
            if success:
                logger.info(f"Updated environment variable: {key}")
            
            return success
        except Exception as e:
            logger.error(f"Failed to update environment variable {key}: {e}")
            return False
    
    def delete_env_var(self, key: str) -> bool:
        """
        删除环境变量
        
        Args:
            key: 环境变量名
        
        Returns:
            bool: 删除是否成功
        """
        try:
            if key in self.env_vars:
                del self.env_vars[key]
                
                # 同时从系统环境变量中删除
                if key in os.environ:
                    del os.environ[key]
                
                # 保存到文件
                success = self.save_env_file()
                
                if success:
                    logger.info(f"Deleted environment variable: {key}")
                
                return success
            else:
                logger.warning(f"Environment variable {key} does not exist")
                return False
        except Exception as e:
            logger.error(f"Failed to delete environment variable {key}: {e}")
            return False
    
    def _load_env_file(self) -> Dict[str, str]:
        """
        从 .env 文件加载环境变量
        
        Returns:
            Dict[str, str]: 加载的环境变量字典
        """
        self.env_vars = {}
        
        try:
            env_path = Path(self.env_file)
            
            # 检查文件是否存在
            if not env_path.exists():
                logger.warning(f".env file not found at {self.env_file}")
                return self.env_vars
            
            # 读取文件内容
            content = env_path.read_text(encoding='utf-8')
            
            # 解析每一行
            for line_num, line in enumerate(content.splitlines(), 1):
                try:
                    # 去除首尾空白
                    line = line.strip()
                    
                    # 跳过空行和注释
                    if not line or line.startswith('#'):
                        continue
                    
                    # 解析键值对
                    key, value = self._parse_line(line)
                    
                    if key:
                        # 保存到内存
                        self.env_vars[key] = value
                        
                        # 设置系统环境变量
                        os.environ[key] = value
                
                except Exception as e:
                    # 格式错误容错：记录错误但继续处理其他行
                    logger.warning(f"Failed to parse line {line_num} in .env file: {line} - {e}")
                    continue
            
            logger.info(f"Loaded {len(self.env_vars)} environment variable(s) from {self.env_file}")
            return self.env_vars
        
        except Exception as e:
            logger.error(f"Failed to load .env file: {e}")
            return self.env_vars
    
    def _parse_line(self, line: str) -> tuple[Optional[str], str]:
        """
        解析 .env 文件的一行
        
        Args:
            line: 要解析的行
        
        Returns:
            tuple[Optional[str], str]: (键, 值) 元组，如果解析失败返回 (None, '')
        """
        # 查找第一个等号
        if '=' not in line:
            raise ValueError("Line does not contain '='")
        
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip()
        
        # 验证键名（只允许字母、数字和下划线）
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
            raise ValueError(f"Invalid key name: {key}")
        
        # 处理引号包裹的值
        if value:
            # 单引号
            if value.startswith("'") and value.endswith("'") and len(value) >= 2:
                value = value[1:-1]
                # 处理转义的单引号
                value = value.replace("\\'", "'")
            # 双引号
            elif value.startswith('"') and value.endswith('"') and len(value) >= 2:
                value = value[1:-1]
                # 处理转义字符
                value = value.replace('\\"', '"')
                value = value.replace('\\n', '\n')
                value = value.replace('\\r', '\r')
                value = value.replace('\\t', '\t')
                value = value.replace('\\\\', '\\')
        
        return key, value
    
    def _mask_value(self, value: str) -> str:
        """
        隐藏敏感值
        
        Args:
            value: 原始值
        
        Returns:
            str: 隐藏后的值
        """
        if len(value) <= 4:
            return '*' * len(value)
        else:
            # 显示前2个和后2个字符
            return value[:2] + '*' * (len(value) - 4) + value[-2:]
