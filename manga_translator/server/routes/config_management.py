"""
Configuration Management API Routes

Provides endpoints for managing .env configurations, presets, and user configs.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from manga_translator.server.core.config_management_service import (
    ConfigManagementService,
)
from manga_translator.server.core.middleware import require_admin, require_auth

router = APIRouter(prefix="/api", tags=["config-management"])

# Initialize service
config_service = ConfigManagementService()


# ============================================================================
# Request/Response Models
# ============================================================================

class ServerConfigUpdate(BaseModel):
    """Model for server configuration updates."""
    config: Dict[str, str]


class PresetCreate(BaseModel):
    """Model for creating a preset."""
    name: str
    description: str
    config: Dict[str, str]
    visible_to_groups: Optional[List[str]] = None


class PresetUpdate(BaseModel):
    """Model for updating a preset."""
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, str]] = None
    visible_to_groups: Optional[List[str]] = None


class UserConfigUpdate(BaseModel):
    """Model for user configuration updates."""
    api_keys: Optional[Dict[str, str]] = None
    selected_preset_id: Optional[str] = None
    custom_settings: Optional[Dict] = None
    config_mode: Optional[str] = None


class BackupRestore(BaseModel):
    """Model for backup restore request."""
    backup_path: str


# ============================================================================
# Server Configuration Endpoints (Admin Only)
# ============================================================================

@router.get("/admin/config/server")
async def get_server_config(
    show_values: bool = False,
    session = Depends(require_admin)
):
    """
    Get server .env configuration.
    
    Args:
        show_values: Whether to show actual values (default: masked)
        session: Admin session from authentication
    
    Returns:
        Server configuration dictionary
    
    Requirements: 16.1, 19.1
    """
    try:
        config = config_service.get_server_config(mask_sensitive=not show_values)
        return {
            "success": True,
            "config": config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get server config: {str(e)}")


@router.put("/admin/config/server")
async def update_server_config(
    update: ServerConfigUpdate,
    create_backup: bool = True,
    session = Depends(require_admin)
):
    """
    Update server .env configuration.
    
    Args:
        update: Configuration update data
        create_backup: Whether to create a backup before updating
        session: Admin session from authentication
    
    Returns:
        Success status
    
    Requirements: 16.2, 16.3, 16.4, 19.2, 19.3
    """
    try:
        admin_id = session.username
        
        success = config_service.update_server_config(
            config=update.config,
            admin_id=admin_id,
            create_backup=create_backup
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update server config")
        
        return {
            "success": True,
            "message": "Server configuration updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update server config: {str(e)}")


@router.get("/admin/config/backups")
async def list_backups(session = Depends(require_admin)):
    """
    List available .env backups.
    
    Args:
        session: Admin session from authentication
    
    Returns:
        List of backup information
    
    Requirements: 16.4
    """
    try:
        backups = config_service.list_backups()
        return {
            "success": True,
            "backups": backups
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list backups: {str(e)}")


@router.post("/admin/config/restore")
async def restore_from_backup(
    restore: BackupRestore,
    session = Depends(require_admin)
):
    """
    Restore .env from a backup.
    
    Args:
        restore: Backup restore data
        session: Admin session from authentication
    
    Returns:
        Success status
    
    Requirements: 16.4
    """
    try:
        admin_id = session.username
        
        success = config_service.restore_from_backup(
            backup_path=restore.backup_path,
            admin_id=admin_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Backup file not found or restore failed")
        
        return {
            "success": True,
            "message": "Configuration restored from backup successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore from backup: {str(e)}")


# ============================================================================
# Configuration Preset Endpoints
# ============================================================================

@router.post("/admin/presets")
async def create_preset(
    preset: PresetCreate,
    session = Depends(require_admin)
):
    """
    Create a new configuration preset.
    
    Args:
        preset: Preset creation data
        session: Admin session from authentication
    
    Returns:
        Created preset information
    
    Requirements: 17.1
    """
    try:
        admin_id = session.username
        
        created_preset = config_service.create_preset(
            name=preset.name,
            description=preset.description,
            config=preset.config,
            created_by=admin_id,
            visible_to_groups=preset.visible_to_groups
        )
        
        if not created_preset:
            raise HTTPException(status_code=409, detail="Preset with this name already exists")
        
        return {
            "success": True,
            "preset": {
                "id": created_preset.id,
                "name": created_preset.name,
                "description": created_preset.description,
                "visible_to_groups": created_preset.visible_to_groups,
                "created_at": created_preset.created_at
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create preset: {str(e)}")


@router.get("/presets")
async def get_presets(
    session = Depends(require_auth)
):
    """
    Get configuration presets visible to the current user.
    
    Args:
        session: Current session from authentication
    
    Returns:
        List of visible presets (without config details)
    
    Requirements: 18.1, 22.2
    """
    try:
        # Get user's group
        user_group = session.group if hasattr(session, 'group') else 'default'
        
        # Get presets visible to this group
        presets = config_service.get_presets_for_group(user_group)
        
        return {
            "success": True,
            "presets": presets
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get presets: {str(e)}")


@router.get("/admin/presets")
async def get_all_presets(
    include_config: bool = False,
    session = Depends(require_admin)
):
    """
    Get all configuration presets (admin only).
    
    Args:
        include_config: Whether to include configuration details
        session: Admin session from authentication
    
    Returns:
        List of all presets
    
    Requirements: 17.1
    """
    try:
        presets = config_service.get_all_presets(include_config=include_config)
        
        return {
            "success": True,
            "presets": presets
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get presets: {str(e)}")


@router.get("/admin/presets/{preset_id}")
async def get_preset(
    preset_id: str,
    decrypt: bool = False,
    session = Depends(require_admin)
):
    """
    Get a specific preset by ID (admin only).
    
    Args:
        preset_id: Preset ID
        decrypt: Whether to decrypt configuration
        session: Admin session from authentication
    
    Returns:
        Preset details
    
    Requirements: 17.1
    """
    try:
        preset = config_service.get_preset(preset_id, decrypt=decrypt)
        
        if not preset:
            raise HTTPException(status_code=404, detail="Preset not found")
        
        return {
            "success": True,
            "preset": preset
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get preset: {str(e)}")


@router.put("/admin/presets/{preset_id}")
async def update_preset(
    preset_id: str,
    update: PresetUpdate,
    session = Depends(require_admin)
):
    """
    Update a configuration preset.
    
    Args:
        preset_id: Preset ID
        update: Preset update data
        session: Admin session from authentication
    
    Returns:
        Success status
    
    Requirements: 17.2
    """
    try:
        admin_id = session.username
        
        # Build updates dictionary
        updates = {}
        if update.name is not None:
            updates['name'] = update.name
        if update.description is not None:
            updates['description'] = update.description
        if update.config is not None:
            updates['config'] = update.config
        if update.visible_to_groups is not None:
            updates['visible_to_groups'] = update.visible_to_groups
        
        success = config_service.update_preset(
            preset_id=preset_id,
            updates=updates,
            admin_id=admin_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Preset not found or update failed")
        
        return {
            "success": True,
            "message": "Preset updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update preset: {str(e)}")


@router.delete("/admin/presets/{preset_id}")
async def delete_preset(
    preset_id: str,
    session = Depends(require_admin)
):
    """
    Delete a configuration preset.
    
    Args:
        preset_id: Preset ID
        session: Admin session from authentication
    
    Returns:
        Success status
    
    Requirements: 17.3
    """
    try:
        admin_id = session.username
        
        success = config_service.delete_preset(
            preset_id=preset_id,
            admin_id=admin_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Preset not found or delete failed")
        
        return {
            "success": True,
            "message": "Preset deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete preset: {str(e)}")


@router.post("/presets/{preset_id}/apply")
async def apply_preset(
    preset_id: str,
    session = Depends(require_auth)
):
    """
    Apply a preset to the current user's configuration.
    
    Args:
        preset_id: Preset ID to apply
        session: Current session from authentication
    
    Returns:
        Success status and preset config for UI application
    
    Requirements: 18.2
    """
    try:
        user_id = session.username
        
        # 先获取预设配置
        preset = config_service.get_preset(preset_id, decrypt=False)
        if not preset:
            raise HTTPException(status_code=404, detail="Preset not found")
        
        success = config_service.apply_preset_to_user(
            user_id=user_id,
            preset_id=preset_id
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to apply preset")
        
        preset_config = preset.get('config', {}) if isinstance(preset, dict) else {}
        ui_config = {
            key: value
            for key, value in preset_config.items()
            if not str(key).isupper()
        } if isinstance(preset_config, dict) else {}

        # 返回预设配置供前端应用到UI
        return {
            "success": True,
            "message": "Preset applied successfully",
            "config": ui_config
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply preset: {str(e)}")


@router.delete("/config/user/preset")
async def clear_selected_preset(
    session = Depends(require_auth)
):
    """Clear the current user's selected preset."""
    try:
        user_id = session.username
        success = config_service.clear_user_selected_preset(user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to clear selected preset")

        return {
            "success": True,
            "message": "Selected preset cleared successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear selected preset: {str(e)}")


# ============================================================================
# User Configuration Endpoints
# ============================================================================

@router.get("/config/user")
async def get_user_config(
    session = Depends(require_auth)
):
    """
    Get current user's configuration.
    
    Args:
        session: Current session from authentication
    
    Returns:
        User configuration (with masked API keys)
    
    Requirements: 15.1, 21.1
    """
    try:
        user_id = session.username
        
        config = config_service.get_user_config(user_id, decrypt=False)
        
        if not config:
            # Return default config
            return {
                "success": True,
                "config": {
                    "user_id": user_id,
                    "api_keys": {},
                    "selected_preset_id": None,
                    "custom_settings": {},
                    "config_mode": "server"
                }
            }
        
        return {
            "success": True,
            "config": config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user config: {str(e)}")


@router.put("/config/user")
async def save_user_config(
    update: UserConfigUpdate,
    session = Depends(require_auth)
):
    """
    Save current user's configuration.
    
    Args:
        update: User configuration update data
        session: Current session from authentication
    
    Returns:
        Success status
    
    Requirements: 15.2, 15.3, 21.2, 21.3, 21.4
    """
    try:
        user_id = session.username
        
        success = config_service.save_user_config(
            user_id=user_id,
            api_keys=update.api_keys,
            selected_preset_id=update.selected_preset_id,
            custom_settings=update.custom_settings,
            config_mode=update.config_mode
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save user config")
        
        return {
            "success": True,
            "message": "User configuration saved successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save user config: {str(e)}")
