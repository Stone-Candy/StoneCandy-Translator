"""
权限系统迁移工具

分析现有权限配置并迁移到新的权限模型。
"""

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PermissionMigrationAnalyzer:
    """权限迁移分析器"""
    
    def __init__(self, data_dir: str = "manga_translator/server/data"):
        """
        初始化迁移分析器
        
        Args:
            data_dir: 数据目录路径
        """
        self.data_dir = data_dir
        self.accounts_file = os.path.join(data_dir, "accounts.json")
        self.group_config_file = os.path.join(data_dir, "group_config.json")
        self.permissions_file = os.path.join(data_dir, "permissions.json")
        
        self.migration_report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "accounts_analyzed": 0,
            "groups_analyzed": 0,
            "permissions_to_migrate": [],
            "warnings": [],
            "errors": []
        }
    
    def analyze_accounts(self) -> Dict[str, Any]:
        """
        分析 accounts.json 中的权限配置
        
        Returns:
            分析结果字典
        """
        logger.info("Analyzing accounts.json...")
        
        if not os.path.exists(self.accounts_file):
            error = f"Accounts file not found: {self.accounts_file}"
            logger.error(error)
            self.migration_report["errors"].append(error)
            return {}
        
        try:
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                accounts_data = json.load(f)
            
            accounts = accounts_data.get("accounts", [])
            self.migration_report["accounts_analyzed"] = len(accounts)
            
            analysis = {
                "total_accounts": len(accounts),
                "accounts_with_old_permissions": [],
                "permission_fields_found": set()
            }
            
            for account in accounts:
                username = account.get("username", "unknown")
                permissions = account.get("permissions", {})
                
                # 检查旧的权限字段
                old_fields = []
                
                if "can_upload_files" in permissions:
                    old_fields.append("can_upload_files")
                    analysis["permission_fields_found"].add("can_upload_files")
                
                if "can_delete_files" in permissions:
                    old_fields.append("can_delete_files")
                    analysis["permission_fields_found"].add("can_delete_files")
                
                if old_fields:
                    analysis["accounts_with_old_permissions"].append({
                        "username": username,
                        "old_fields": old_fields,
                        "permissions": permissions
                    })
                    
                    self.migration_report["permissions_to_migrate"].append({
                        "type": "user",
                        "id": username,
                        "old_permissions": {field: permissions.get(field) for field in old_fields}
                    })
            
            # 转换 set 为 list 以便 JSON 序列化
            analysis["permission_fields_found"] = list(analysis["permission_fields_found"])
            
            logger.info(f"Found {len(analysis['accounts_with_old_permissions'])} accounts with old permission fields")
            
            return analysis
            
        except Exception as e:
            error = f"Error analyzing accounts.json: {e}"
            logger.error(error)
            self.migration_report["errors"].append(error)
            return {}
    
    def analyze_group_config(self) -> Dict[str, Any]:
        """
        分析 group_config.json 中的权限配置
        
        Returns:
            分析结果字典
        """
        logger.info("Analyzing group_config.json...")
        
        if not os.path.exists(self.group_config_file):
            error = f"Group config file not found: {self.group_config_file}"
            logger.error(error)
            self.migration_report["errors"].append(error)
            return {}
        
        try:
            with open(self.group_config_file, 'r', encoding='utf-8') as f:
                group_data = json.load(f)
            
            groups = group_data.get("groups", {})
            self.migration_report["groups_analyzed"] = len(groups)
            
            analysis = {
                "total_groups": len(groups),
                "groups_with_permissions": [],
                "groups_without_permissions": []
            }
            
            for group_id, group_config in groups.items():
                # 检查是否有权限配置字段
                has_permissions = any(
                    key in group_config 
                    for key in ["can_upload_files", "can_delete_files", "permissions"]
                )
                
                if has_permissions:
                    analysis["groups_with_permissions"].append({
                        "group_id": group_id,
                        "name": group_config.get("name", ""),
                        "config": group_config
                    })
                else:
                    analysis["groups_without_permissions"].append(group_id)
                    warning = f"Group '{group_id}' has no permission configuration"
                    self.migration_report["warnings"].append(warning)
            
            logger.info(f"Found {len(analysis['groups_with_permissions'])} groups with permission fields")
            
            return analysis
            
        except Exception as e:
            error = f"Error analyzing group_config.json: {e}"
            logger.error(error)
            self.migration_report["errors"].append(error)
            return {}
    
    def analyze_permissions_file(self) -> Dict[str, Any]:
        """
        分析现有的 permissions.json 文件
        
        Returns:
            分析结果字典
        """
        logger.info("Analyzing permissions.json...")
        
        if not os.path.exists(self.permissions_file):
            warning = f"Permissions file not found: {self.permissions_file} (will be created)"
            logger.warning(warning)
            self.migration_report["warnings"].append(warning)
            return {"exists": False}
        
        try:
            with open(self.permissions_file, 'r', encoding='utf-8') as f:
                permissions_data = json.load(f)
            
            analysis = {
                "exists": True,
                "has_global_permissions": "global_permissions" in permissions_data,
                "has_group_permissions": "group_permissions" in permissions_data,
                "has_user_permissions": "user_permissions" in permissions_data,
                "user_count": len(permissions_data.get("user_permissions", {})),
                "group_count": len(permissions_data.get("group_permissions", {})),
                "structure": {
                    "global_fields": list(permissions_data.get("global_permissions", {}).keys()),
                    "user_permissions_count": len(permissions_data.get("user_permissions", {})),
                    "group_permissions_count": len(permissions_data.get("group_permissions", {}))
                }
            }
            
            logger.info(f"Permissions file exists with {analysis['user_count']} users and {analysis['group_count']} groups")
            
            return analysis
            
        except Exception as e:
            error = f"Error analyzing permissions.json: {e}"
            logger.error(error)
            self.migration_report["errors"].append(error)
            return {"exists": False}
    
    def generate_migration_mapping(self) -> Dict[str, Any]:
        """
        生成权限迁移映射
        
        Returns:
            迁移映射字典
        """
        logger.info("Generating migration mapping...")
        
        mapping = {
            "field_mappings": {
                "can_upload_files": {
                    "new_fields": ["can_upload_prompt", "can_upload_font"],
                    "description": "Split into separate prompt and font upload permissions"
                },
                "can_delete_files": {
                    "new_fields": ["can_delete_own_files", "can_delete_all_files"],
                    "description": "Split into own files and all files delete permissions",
                    "default_mapping": {
                        "can_delete_files": True,
                        "maps_to": {
                            "can_delete_own_files": True,
                            "can_delete_all_files": False
                        }
                    }
                }
            },
            "new_permissions": [
                "can_upload_prompt",
                "can_upload_font",
                "can_delete_own_files",
                "can_delete_all_files",
                "view_permission",
                "save_enabled",
                "can_edit_own_env",
                "can_edit_server_env",
                "can_view_own_logs",
                "can_view_all_logs",
                "can_view_system_logs"
            ]
        }
        
        return mapping
    
    def run_full_analysis(self) -> Dict[str, Any]:
        """
        运行完整的迁移分析
        
        Returns:
            完整的分析报告
        """
        logger.info("Starting full permission migration analysis...")
        
        report = {
            "timestamp": self.migration_report["timestamp"],
            "accounts_analysis": self.analyze_accounts(),
            "group_config_analysis": self.analyze_group_config(),
            "permissions_file_analysis": self.analyze_permissions_file(),
            "migration_mapping": self.generate_migration_mapping(),
            "summary": self.migration_report
        }
        
        # 生成建议
        recommendations = []
        
        if report["accounts_analysis"].get("accounts_with_old_permissions"):
            recommendations.append(
                "Migrate old permission fields in accounts.json to new permission model"
            )
        
        if report["group_config_analysis"].get("groups_without_permissions"):
            recommendations.append(
                "Add default permission configuration for groups without permissions"
            )
        
        if not report["permissions_file_analysis"].get("exists"):
            recommendations.append(
                "Create permissions.json file with proper structure"
            )
        
        report["recommendations"] = recommendations
        
        logger.info("Migration analysis complete")
        
        return report
    
    def save_analysis_report(self, report: Dict[str, Any], output_file: Optional[str] = None) -> str:
        """
        保存分析报告到文件
        
        Args:
            report: 分析报告字典
            output_file: 输出文件路径（可选）
        
        Returns:
            保存的文件路径
        """
        if output_file is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(self.data_dir, f"permission_migration_analysis_{timestamp}.json")
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Analysis report saved to: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Error saving analysis report: {e}")
            raise


class PermissionMigrator:
    """权限迁移执行器"""
    
    def __init__(self, data_dir: str = "manga_translator/server/data"):
        """
        初始化迁移执行器
        
        Args:
            data_dir: 数据目录路径
        """
        self.data_dir = data_dir
        self.accounts_file = os.path.join(data_dir, "accounts.json")
        self.group_config_file = os.path.join(data_dir, "group_config.json")
        self.permissions_file = os.path.join(data_dir, "permissions.json")
        
        self.migration_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "backups_created": [],
            "migrations_performed": [],
            "errors": []
        }
    
    def create_backup(self, file_path: str) -> str:
        """
        创建文件备份
        
        Args:
            file_path: 要备份的文件路径
        
        Returns:
            备份文件路径
        """
        if not os.path.exists(file_path):
            logger.warning(f"File not found for backup: {file_path}")
            return ""
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = f"{file_path}.backup_{timestamp}"
        
        try:
            shutil.copy2(file_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            self.migration_log["backups_created"].append(backup_path)
            return backup_path
        except Exception as e:
            error = f"Failed to create backup for {file_path}: {e}"
            logger.error(error)
            self.migration_log["errors"].append(error)
            return ""
    
    def migrate_account_permissions(self, account: Dict[str, Any]) -> Dict[str, Any]:
        """
        迁移单个账户的权限
        
        Args:
            account: 账户数据字典
        
        Returns:
            迁移后的权限字典
        """
        old_perms = account.get("permissions", {})
        new_perms = {}
        
        # 迁移 can_upload_files -> can_upload_prompt + can_upload_font
        if "can_upload_files" in old_perms:
            can_upload = old_perms["can_upload_files"]
            new_perms["can_upload_prompt"] = can_upload
            new_perms["can_upload_font"] = can_upload
            logger.info(f"Migrated can_upload_files={can_upload} to can_upload_prompt and can_upload_font")
        
        # 迁移 can_delete_files -> can_delete_own_files + can_delete_all_files
        if "can_delete_files" in old_perms:
            can_delete = old_perms["can_delete_files"]
            # 如果用户是管理员，给予删除所有文件的权限
            is_admin = account.get("role") == "admin"
            new_perms["can_delete_own_files"] = can_delete
            new_perms["can_delete_all_files"] = can_delete if is_admin else False
            logger.info(
                f"Migrated can_delete_files={can_delete} to "
                f"can_delete_own_files={can_delete}, can_delete_all_files={new_perms['can_delete_all_files']}"
            )
        
        return new_perms
    
    def migrate_accounts_file(self) -> bool:
        """
        迁移 accounts.json 文件
        
        Returns:
            是否成功
        """
        logger.info("Migrating accounts.json...")
        
        # 创建备份
        backup_path = self.create_backup(self.accounts_file)
        if not backup_path:
            return False
        
        try:
            # 读取账户数据
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                accounts_data = json.load(f)
            
            accounts = accounts_data.get("accounts", [])
            migrated_count = 0
            
            # 迁移每个账户
            for account in accounts:
                username = account.get("username", "unknown")
                old_perms = account.get("permissions", {})
                
                # 检查是否需要迁移
                needs_migration = (
                    "can_upload_files" in old_perms or
                    "can_delete_files" in old_perms
                )
                
                if needs_migration:
                    # 执行迁移
                    new_perms = self.migrate_account_permissions(account)
                    
                    # 更新权限（保留其他字段）
                    account["permissions"].update(new_perms)
                    
                    # 移除旧字段
                    account["permissions"].pop("can_upload_files", None)
                    account["permissions"].pop("can_delete_files", None)
                    
                    migrated_count += 1
                    
                    self.migration_log["migrations_performed"].append({
                        "type": "account",
                        "id": username,
                        "new_permissions": new_perms
                    })
            
            # 保存更新后的数据
            with open(self.accounts_file, 'w', encoding='utf-8') as f:
                json.dump(accounts_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Migrated {migrated_count} accounts")
            return True
            
        except Exception as e:
            error = f"Error migrating accounts.json: {e}"
            logger.error(error)
            self.migration_log["errors"].append(error)
            return False
    
    def initialize_group_permissions(self) -> bool:
        """
        为用户组初始化默认权限配置
        
        Returns:
            是否成功
        """
        logger.info("Initializing group permissions...")
        
        try:
            # 读取 permissions.json
            with open(self.permissions_file, 'r', encoding='utf-8') as f:
                permissions_data = json.load(f)
            
            # 读取 group_config.json
            with open(self.group_config_file, 'r', encoding='utf-8') as f:
                group_data = json.load(f)
            
            groups = group_data.get("groups", {})
            
            # 为每个用户组设置默认权限
            for group_id in groups.keys():
                if group_id not in permissions_data.get("group_permissions", {}):
                    # 根据用户组类型设置不同的默认权限
                    if group_id == "admin":
                        # 管理员组：所有权限
                        group_perms = {
                            "can_upload_prompt": True,
                            "can_upload_font": True,
                            "can_delete_own_files": True,
                            "can_delete_all_files": True,
                            "view_permission": "all",
                            "save_enabled": True,
                            "can_edit_own_env": True,
                            "can_edit_server_env": True,
                            "can_view_own_logs": True,
                            "can_view_all_logs": True,
                            "can_view_system_logs": True
                        }
                    elif group_id == "guest":
                        # 访客组：受限权限
                        group_perms = {
                            "can_upload_prompt": False,
                            "can_upload_font": False,
                            "can_delete_own_files": False,
                            "can_delete_all_files": False,
                            "view_permission": "own",
                            "save_enabled": False,
                            "can_edit_own_env": False,
                            "can_edit_server_env": False,
                            "can_view_own_logs": True,
                            "can_view_all_logs": False,
                            "can_view_system_logs": False
                        }
                    else:
                        # 默认组：标准权限
                        group_perms = {
                            "can_upload_prompt": True,
                            "can_upload_font": True,
                            "can_delete_own_files": True,
                            "can_delete_all_files": False,
                            "view_permission": "own",
                            "save_enabled": True,
                            "can_edit_own_env": True,
                            "can_edit_server_env": False,
                            "can_view_own_logs": True,
                            "can_view_all_logs": False,
                            "can_view_system_logs": False
                        }
                    
                    permissions_data["group_permissions"][group_id] = group_perms
                    
                    self.migration_log["migrations_performed"].append({
                        "type": "group",
                        "id": group_id,
                        "permissions": group_perms
                    })
                    
                    logger.info(f"Initialized permissions for group '{group_id}'")
            
            # 更新 last_updated
            permissions_data["last_updated"] = datetime.now(timezone.utc).isoformat()
            
            # 保存更新后的数据
            with open(self.permissions_file, 'w', encoding='utf-8') as f:
                json.dump(permissions_data, f, indent=2, ensure_ascii=False)
            
            logger.info("Group permissions initialized")
            return True
            
        except Exception as e:
            error = f"Error initializing group permissions: {e}"
            logger.error(error)
            self.migration_log["errors"].append(error)
            return False
    
    def run_migration(self) -> Dict[str, Any]:
        """
        运行完整的权限迁移
        
        Returns:
            迁移日志
        """
        logger.info("Starting permission migration...")
        
        # 1. 迁移账户权限
        accounts_success = self.migrate_accounts_file()
        
        # 2. 初始化用户组权限
        groups_success = self.initialize_group_permissions()
        
        # 生成迁移报告
        self.migration_log["success"] = accounts_success and groups_success
        self.migration_log["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        if self.migration_log["success"]:
            logger.info("Permission migration completed successfully")
        else:
            logger.error("Permission migration completed with errors")
        
        return self.migration_log
    
    def save_migration_log(self, log: Dict[str, Any], output_file: Optional[str] = None) -> str:
        """
        保存迁移日志到文件
        
        Args:
            log: 迁移日志字典
            output_file: 输出文件路径（可选）
        
        Returns:
            保存的文件路径
        """
        if output_file is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(self.data_dir, f"permission_migration_log_{timestamp}.json")
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Migration log saved to: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Error saving migration log: {e}")
            raise


def analyze_permissions(data_dir: str = "manga_translator/server/data") -> Dict[str, Any]:
    """
    便捷函数：分析权限配置
    
    Args:
        data_dir: 数据目录路径
    
    Returns:
        分析报告
    """
    analyzer = PermissionMigrationAnalyzer(data_dir)
    report = analyzer.run_full_analysis()
    
    # 保存报告
    report_file = analyzer.save_analysis_report(report)
    report["report_file"] = report_file
    
    return report


def migrate_permissions(data_dir: str = "manga_translator/server/data") -> Dict[str, Any]:
    """
    便捷函数：执行权限迁移
    
    Args:
        data_dir: 数据目录路径
    
    Returns:
        迁移日志
    """
    migrator = PermissionMigrator(data_dir)
    log = migrator.run_migration()
    
    # 保存日志
    log_file = migrator.save_migration_log(log)
    log["log_file"] = log_file
    
    return log


if __name__ == "__main__":
    import sys
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 检查命令行参数
    mode = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    
    if mode == "migrate":
        # 运行迁移
        print("\n" + "="*80)
        print("Starting Permission Migration")
        print("="*80)
        
        log = migrate_permissions()
        
        print("\n" + "="*80)
        print("Permission Migration Summary")
        print("="*80)
        print(f"Success: {log.get('success', False)}")
        print(f"Backups created: {len(log.get('backups_created', []))}")
        print(f"Migrations performed: {len(log.get('migrations_performed', []))}")
        print(f"Errors: {len(log.get('errors', []))}")
        print(f"\nLog saved to: {log.get('log_file', 'N/A')}")
        print("="*80)
        
        if log.get("errors"):
            print("\nErrors:")
            for error in log["errors"]:
                print(f"  - {error}")
        
        if log.get("backups_created"):
            print("\nBackups created:")
            for backup in log["backups_created"]:
                print(f"  - {backup}")
    
    else:
        # 运行分析
        report = analyze_permissions()
        
        # 打印摘要
        print("\n" + "="*80)
        print("Permission Migration Analysis Summary")
        print("="*80)
        print(f"Accounts analyzed: {report['summary']['accounts_analyzed']}")
        print(f"Groups analyzed: {report['summary']['groups_analyzed']}")
        print(f"Permissions to migrate: {len(report['summary']['permissions_to_migrate'])}")
        print(f"Warnings: {len(report['summary']['warnings'])}")
        print(f"Errors: {len(report['summary']['errors'])}")
        print(f"\nReport saved to: {report.get('report_file', 'N/A')}")
        print("="*80)
        
        # 打印建议
        if report.get("recommendations"):
            print("\nRecommendations:")
            for i, rec in enumerate(report["recommendations"], 1):
                print(f"{i}. {rec}")
        
        print("\nTo run migration, use: python -m manga_translator.server.core.permission_migration migrate")
