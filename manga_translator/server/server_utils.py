"""
服务器工具函数
"""
import io
import secrets

from fastapi import HTTPException

from manga_translator.server.to_json import to_translation


def generate_nonce():
    """生成随机 nonce"""
    return secrets.token_hex(16)


def transform_to_image(ctx):
    """将翻译上下文转换为图片字节"""
    # 检查 ctx.result 是否存在
    if ctx.result is None:
        raise HTTPException(500, detail="Translation failed: no result image generated")
    
    # 检查是否使用占位符（在web模式下final.png保存后会设置此标记）
    if hasattr(ctx, 'use_placeholder') and ctx.use_placeholder:
        # ctx.result已经是1x1占位符图片，快速传输
        img_byte_arr = io.BytesIO()
        ctx.result.save(img_byte_arr, format="PNG")
        return img_byte_arr.getvalue()

    # 返回完整的翻译结果
    img_byte_arr = io.BytesIO()
    ctx.result.save(img_byte_arr, format="PNG")
    return img_byte_arr.getvalue()


def transform_to_json(ctx):
    """将翻译上下文转换为 JSON 字节"""
    return to_translation(ctx).model_dump_json().encode("utf-8")


def transform_to_bytes(ctx):
    """将翻译上下文转换为字节"""
    return to_translation(ctx).to_bytes()
