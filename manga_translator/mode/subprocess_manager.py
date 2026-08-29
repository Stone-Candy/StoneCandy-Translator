#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
子进程管理器 - 支持内存管理和断点续传
"""
# import json
import multiprocessing
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

ROOT_DIR = Path(__file__).parent.parent.parent

# 内存监控阈值
DEFAULT_MEMORY_THRESHOLD_MB = 0  # 默认不限制绝对内存
DEFAULT_MEMORY_THRESHOLD_PERCENT = 80  # 默认达到系统总内存80%时重启
DEFAULT_BATCH_SIZE_PER_RESTART = 50


def get_memory_usage_mb() -> float:
    """获取当前进程的内存使用量（MB）"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        return 0


def get_total_memory_mb() -> float:
    """获取系统总内存（MB）"""
    try:
        import psutil
        return psutil.virtual_memory().total / 1024 / 1024
    except ImportError:
        return 0


def get_system_memory_percent() -> float:
    """获取系统总内存使用率（包括所有进程）"""
    try:
        import psutil
        return psutil.virtual_memory().percent
    except ImportError:
        return 0





def worker_translate_batch(
    file_paths: List[str],
    output_dir: str,
    config_path: Optional[str],
    verbose: bool,
    overwrite: bool,
    start_index: int,
    total_files: int,
    config_dict: dict,
    memory_limit_mb: int,
    memory_limit_percent: int,
    result_queue: multiprocessing.Queue,
    all_files: Optional[List[str]] = None,
):
    """
    子进程工作函数：翻译一批图片
    """
    import asyncio
    
    async def _do_translate():
        # 添加路径
        sys.path.insert(0, str(ROOT_DIR))
        sys.path.insert(0, str(ROOT_DIR / 'desktop_qt_ui'))
        
        import logging

        from manga_translator import Config, MangaTranslator
        from manga_translator.utils import init_logging, open_pil_image, set_log_level
        
        init_logging()
        set_log_level(logging.DEBUG if verbose else logging.INFO)
        
        # 应用命令行参数
        cli_config = config_dict.get('cli', {})
        cli_config['verbose'] = verbose
        cli_config['overwrite'] = bool(overwrite)
        config_dict['cli'] = cli_config
        
        font_family = config_dict.get('render', {}).get('font_family')
        if font_family:
            config_dict['font_family'] = font_family
        
        # 创建翻译器
        translator_params = cli_config.copy()
        translator_params.update(config_dict)
        translator = MangaTranslator(params=translator_params)
        job_paths = all_files or file_paths
        if job_paths:
            translator._txt_export_job_paths = [os.path.abspath(path) for path in job_paths]
        
        # 创建 Config 对象
        explicit_keys = {'render', 'upscale', 'translator', 'detector', 'colorizer', 'inpainter', 'ocr'}
        config_for_translate = {k: v for k, v in config_dict.items() if k in explicit_keys}
        for key in ['kernel_size', 'mask_dilation_offset', 'bubble_mask_dilation_offset', 'force_simple_sort']:
            if key in config_dict:
                config_for_translate[key] = config_dict[key]
        
        manga_config = Config(**config_for_translate)
        
        # 准备保存信息
        output_format = cli_config.get('format')
        if not output_format or output_format == "不指定":
            output_format = None
        if cli_config.get('inpaint_only', False):
            output_format = 'png'
        
        save_info = {
            'output_folder': output_dir,
            'format': output_format,
            'overwrite': bool(overwrite),
            'input_folders': set()
        }
        
        # 处理图片
        completed = []
        failed = []
        
        for i, file_path in enumerate(file_paths):
            current_index = start_index + i + 1
            print(f"\n[{current_index}/{total_files}] 처리: {os.path.basename(file_path)}")
            
            try:
                with open(file_path, 'rb') as f:
                    image = open_pil_image(f, eager=True)
                image.name = file_path
                
                contexts = await translator.translate_batch(
                    [(image, manga_config)],
                    save_info=save_info,
                    global_offset=current_index - 1,
                    global_total=total_files
                )
                
                if contexts and len(contexts) > 0:
                    ctx = contexts[0]
                    if getattr(ctx, 'success', False) or getattr(ctx, 'result', None):
                        completed.append(file_path)
                        print(f"✅ 완료: {os.path.basename(file_path)}")
                    else:
                        failed.append(file_path)
                        error_msg = getattr(ctx, 'translation_error', '未知错误')
                        print(f"❌ 실패: {os.path.basename(file_path)} - {error_msg}")
                else:
                    failed.append(file_path)
                    print(f"❌ 실패: {os.path.basename(file_path)} - 반환 결과 없음")
                
                if hasattr(image, 'close'):
                    image.close()
                
            except Exception as e:
                failed.append(file_path)
                print(f"❌ 예외: {os.path.basename(file_path)} - {e}")
                if verbose:
                    import traceback
                    traceback.print_exc()
            
            if (i + 1) % 5 == 0:
                pass
                try:
                    import torch
                    if torch.cuda.is_available():
                        pass
                except Exception:
                    pass
            
            # 检查内存使用
            mem_mb = get_memory_usage_mb()
            sys_mem_percent = get_system_memory_percent()
            
            if mem_mb > 0:
                print(f"📊 프로세스 메모리: {mem_mb:.0f} MB | 시스템 메모리: {sys_mem_percent:.1f}%")
                
                # 检查是否超过绝对内存限制
                if memory_limit_mb > 0 and mem_mb > memory_limit_mb:
                    print(f"⚠️ 프로세스 메모리가 한도를 넘었습니다 ({mem_mb:.0f} MB > {memory_limit_mb} MB)，조기 종료")
                    print(f"📊 완료 {len(completed)} 개 파일, 남은 파일은 새 하위 프로세스에서 처리합니다")
                    return completed, failed
                
                # 检查是否超过系统内存百分比限制
                if memory_limit_percent > 0 and sys_mem_percent > memory_limit_percent:
                    print(f"⚠️ 시스템 메모리가 한도를 넘었습니다 ({sys_mem_percent:.1f}% > {memory_limit_percent}%)，조기 종료")
                    print(f"📊 완료 {len(completed)} 개 파일, 남은 파일은 새 하위 프로세스에서 처리합니다")
                    return completed, failed
        
        return completed, failed
    
    try:
        completed, failed = asyncio.run(_do_translate())
        print(f"\n📤 하위 프로세스 결과 전송: 성공 {len(completed)}, 실패 {len(failed)}")
        result_queue.put({
            'status': 'success',
            'completed': completed,
            'failed': failed
        })
    except Exception as e:
        import traceback
        print(f"\n❌ 하위 프로세스 예외: {e}")
        result_queue.put({
            'status': 'error',
            'error': str(e),
            'traceback': traceback.format_exc(),
            'completed': [],
            'failed': []
        })


async def translate_with_subprocess(
    all_files: List[str],
    output_dir: str,
    config_dict: dict,
    config_path: Optional[str],
    verbose: bool,
    overwrite: bool,
    memory_limit_mb: int = DEFAULT_MEMORY_THRESHOLD_MB,
    memory_limit_percent: int = DEFAULT_MEMORY_THRESHOLD_PERCENT,
    batch_per_restart: int = DEFAULT_BATCH_SIZE_PER_RESTART,
    resume: bool = False
) -> Tuple[int, int]:
    """
    使用子进程模式翻译，支持内存管理
    
    Args:
        memory_limit_mb: 绝对内存限制（MB），0表示不限制
        memory_limit_percent: 内存百分比限制，超过系统总内存的这个百分比时重启
    
    Returns:
        (success_count, failed_count)
    """
    completed_files = set()
    total_files = len(all_files)
    success_count = 0
    failed_count = 0
    
    # 获取系统总内存用于显示
    total_mem = get_total_memory_mb()
    
    print(f"\n{'='*60}")
    print("🚀 하위 프로세스 번역 모드")
    print(f"📊 총 파일 수: {total_files}")
    # 如果设置了绝对内存限制，只显示绝对限制；否则显示百分比限制
    if memory_limit_mb > 0:
        print(f"📊 메모리 제한: {memory_limit_mb} MB")
    elif memory_limit_percent > 0:
        limit_mb = total_mem * memory_limit_percent / 100
        print(f"📊 메모리 제한: {memory_limit_percent}% (약 {limit_mb:.0f} MB)")
    if batch_per_restart > 0:
        print(f"📊 배치당 처리: {batch_per_restart} 장")
    print(f"{'='*60}\n")
    
    restart_count = 0
    
    while True:
        # 每次循环开始时，过滤掉已完成的文件
        pending_files = [f for f in all_files if f not in completed_files]
        
        if not pending_files:
            break
        
        # 取一批文件处理（0 表示不限制，一次处理所有）
        if batch_per_restart > 0:
            batch_files = pending_files[:batch_per_restart]
        else:
            batch_files = pending_files
        
        print(f"\n{'='*40}")
        print(f"🔄 배치 {restart_count + 1}: {len(batch_files)}개 파일 처리")
        print(f"📊 진행: {len(completed_files)}/{total_files}")
        print(f"{'='*40}")
        
        result_queue = multiprocessing.Queue()
        
        process = multiprocessing.Process(
            target=worker_translate_batch,
            args=(
                batch_files,
                output_dir,
                config_path,
                verbose,
                overwrite,
                len(completed_files),
                total_files,
                config_dict,
                memory_limit_mb,
                memory_limit_percent,
                result_queue,
                all_files,
            )
        )
        
        process.start()
        
        try:
            # 先尝试从队列获取结果（子进程会在发送结果后退出）
            timeout = len(batch_files) * 600
            try:
                result = result_queue.get(timeout=timeout)
                
                if result['status'] == 'success':
                    batch_completed = result.get('completed', [])
                    batch_failed = result.get('failed', [])
                    
                    success_count += len(batch_completed)
                    failed_count += len(batch_failed)
                    completed_files.update(batch_completed)
                    
                    print(f"\n📊 배치 완료: 성공 {len(batch_completed)}, 실패 {len(batch_failed)}")
                else:
                    print(f"\n❌ 배치 오류: {result.get('error', '알 수 없는 오류')}")
                    if verbose and 'traceback' in result:
                        print(result['traceback'])
                    
            except Exception as e:
                print(f"\n⚠️ 하위 프로세스 결과를 가져올 수 없습니다: {e}")
                # 如果无法获取结果，将这批文件标记为失败
                failed_count += len(batch_files)
            
            # 等待子进程退出
            process.join(timeout=30)
            if process.is_alive():
                print("⚠️ 하위 프로세스가 정상 종료되지 않아 강제 종료합니다")
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                    process.join()
        
        except KeyboardInterrupt:
            print("\n\n⚠️ 사용자 중단")
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
            raise
        
        main_mem = get_memory_usage_mb()
        if main_mem > 0:
            print(f"📊 메인 프로세스 메모리: {main_mem:.0f} MB")
        
        restart_count += 1
    
    if failed_count == 0:
        print("\n✅ 모든 파일 처리를 마쳤습니다")
    else:
        print(f"\n⚠️  {failed_count} 개 파일 실패")
    
    return success_count, failed_count


