"""
并发流水线处理模块 - 真正的并行架构
实现流水线并发：检测+OCR、翻译、修复、渲染 四个步骤在独立线程中运行
每个线程拥有独立的事件循环，互不阻塞
"""
import asyncio
import contextlib
import logging
import os
import queue
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import List

from . import Context, load_image, open_pil_image

# 使用 manga_translator 的主 logger，确保日志能被UI捕获
logger = logging.getLogger('manga_translator')


class PipelineAbortError(asyncio.CancelledError):
    """内部停止信号：用于中止其他工作线程，但不应被当作用户取消。"""


class ConcurrentPipeline:
    """
    流水线并发处理器 - 真正的并行架构
    
    4个独立线程，每个拥有自己的事件循环，互不阻塞：
    1. 检测+OCR线程 → 完成后放入翻译队列和修复队列
    2. 翻译线程 → 批量处理翻译队列（HTTP 请求不会被 GPU 操作阻塞）
    3. 修复线程 → 处理修复队列（GPU 推理不会阻塞翻译）
    4. 渲染线程 → 翻译+修复完成后渲染出图
    
    batch_size 控制翻译批量大小（一次翻译多少张图片），
    同时也限制等待翻译的队列长度，避免 API 太慢时检测/OCR 无限堆积。
    
    使用 queue.Queue 和 threading.Lock 进行线程间通信和同步。
    """
    
    def __init__(self, translator_instance, batch_size: int = 3, max_workers: int = 4):
        """
        初始化并发流水线
        
        Args:
            translator_instance: MangaTranslator实例
            batch_size: 批量大小（一次翻译多少张图片）
            max_workers: 每个步骤的线程池大小
        """
        self.translator = translator_instance
        self.batch_size = batch_size
        
        # ✅ 为每个步骤创建独立的线程池，实现真正的并行处理
        # 每个线程拥有独立的事件循环，互不阻塞
        self._detection_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='DetectionThread')
        self._translation_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='TranslationThread')
        self._inpaint_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='InpaintThread')
        self._render_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='RenderThread')
        
        # 线程安全的队列
        self.translation_queue = queue.Queue(maxsize=max(1, batch_size))  # 翻译队列（带背压）
        self.inpaint_queue = queue.Queue()      # 修复队列
        self.render_queue = queue.Queue()       # 渲染队列
        
        # 结果存储 {image_name: ctx}
        # 使用线程锁保护共享数据
        self._lock = threading.Lock()
        self.translation_done = {}  # 翻译完成的ctx（包含翻译后的text_regions）
        self.inpaint_done = {}      # 修复完成的ctx（包含img_inpainted）
        self.pending_redo = set()   # 翻译过滤后需要重做修复的图片名（用于协调入渲染队列的时机）
        
        # 存储基础ctx（检测+OCR的结果），供翻译和修复使用
        self.base_contexts = {}     # {image_name: ctx}
        
        # 控制标志
        self.stop_workers = False
        self.detection_ocr_done = False  # 检测+OCR是否全部完成
        self.translation_thread_done = False  # 翻译线程是否已结束（不会再投递 redo 修复任务）
        self.has_critical_error = False  # 是否发生严重错误
        self.critical_error_msg = None   # 严重错误信息
        self.critical_error_exception = None  # 原始异常对象
        
        # 统计信息
        self.start_time = None
        self.total_images = 0
        self.stats = {
            'detection_ocr': 0,
            'translation': 0,
            'inpaint': 0,
            'rendering': 0
        }
        
        # 结果列表（线程安全）
        self._results = []
        self._results_lock = threading.Lock()
        
        # ✅ 线程安全的状态消息队列（用于向主线程报告关键日志）
        self._status_queue = queue.Queue()
        self.failed_images = set()
    
    def _emit_status(self, message: str):
        """向主线程发送状态消息（线程安全）"""
        self._status_queue.put(message)
    
    def _flush_status_to_logger(self):
        """将队列中的状态消息输出到 logger（在主线程调用）"""
        while not self._status_queue.empty():
            try:
                msg = self._status_queue.get_nowait()
                logger.info(msg)
            except queue.Empty:
                break

    def _record_failed_image(self, image_name: str | None):
        """记录已失败文件数，避免同一文件在多个阶段重复计数。"""
        normalized_name = str(image_name or "").strip()
        if not normalized_name:
            return
        with self._lock:
            self.failed_images.add(normalized_name)

    def _get_failed_count(self) -> int:
        with self._lock:
            return len(self.failed_images)

    def _pop_translation_task(self, timeout: float):
        """从翻译队列取一个任务。"""
        image_name, config = self.translation_queue.get(timeout=timeout)
        with self._lock:
            ctx = self.base_contexts.get(image_name)
        if not ctx:
            logger.error(f"[번역] {image_name}의 기본 컨텍스트를 찾지 못했습니다")
            return None
        return ctx, config

    def _should_translate_batch(self, batch: List[tuple]):
        """根据图片数判断当前批次是否应该立刻翻译。"""
        if not batch:
            return False, ""

        if len(batch) >= self.batch_size:
            return True, f"批次已满 ({len(batch)}/{self.batch_size} 张图片)"

        if self.detection_ocr_done:
            return True, f"OCR完成，翻译剩余 {len(batch)} 张图片"

        return False, ""

    def _enqueue_translation_task(self, image_name: str, config):
        """
        向翻译队列提交任务。
        当翻译 API 过慢时，这里会形成背压，阻止检测/OCR 无限领先。
        """
        waited = False
        while not self.stop_workers:
            try:
                self.translation_queue.put((image_name, config), timeout=0.1)
                if waited:
                    logger.info(
                        f"[检测+OCR] 翻译队列恢复，继续处理: {image_name} "
                        f"(队列: {self.translation_queue.qsize()}/{self.translation_queue.maxsize})"
                    )
                return
            except queue.Full:
                if not waited:
                    waited = True
                    logger.info(
                        f"[检测+OCR] 翻译队列已满，等待翻译线程消费 "
                        f"({self.translation_queue.qsize()}/{self.translation_queue.maxsize})"
                    )
                self._check_cancelled_or_raise("检测+OCR", f"等待翻译队列释放: {os.path.basename(image_name)}")

        raise RuntimeError("并发流水线已停止，无法继续提交翻译任务")

    def _check_cancelled_or_raise(self, stage: str, detail: str = ""):
        """统一取消检查：区分用户取消与内部停机。"""
        if self.has_critical_error:
            raise PipelineAbortError(self.critical_error_msg or "并发流水线发生严重错误")

        try:
            self.translator._check_cancelled()
        except PipelineAbortError:
            self.stop_workers = True
            raise
        except asyncio.CancelledError:
            self.stop_workers = True
            message = f"[{stage}] 用户取消"
            if detail:
                message = f"{message}，{detail}"
            logger.warning(message)
            raise
    
    def _run_async_in_thread(self, coro):
        """在当前线程中创建事件循环并运行协程"""
        loop = self._create_worker_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            # 关闭事件循环前，先取消并回收所有挂起任务，避免 "Task was destroyed but it is pending!"
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            if pending:
                for task in pending:
                    task.cancel()
                with contextlib.suppress(Exception):
                    loop.run_until_complete(asyncio.wait_for(
                        asyncio.gather(*pending, return_exceptions=True),
                        timeout=1.0
                    ))

            with contextlib.suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())

            if hasattr(loop, "shutdown_default_executor"):
                with contextlib.suppress(Exception):
                    loop.run_until_complete(loop.shutdown_default_executor())

            asyncio.set_event_loop(None)
            loop.close()

    def _create_worker_event_loop(self):
        """
        为工作线程创建事件循环。
        在 Windows 下优先使用 SelectorEventLoop，避免 Proactor 在线程场景下的兼容性问题。
        """
        if os.name == 'nt' and hasattr(asyncio, 'SelectorEventLoop'):
            try:
                return asyncio.SelectorEventLoop()
            except Exception as e:
                logger.warning(f"[동시 파이프라인] SelectorEventLoop 생성 실패, 기본 이벤트 루프로 폴백: {e}")
        return asyncio.new_event_loop()
    
    def _detection_ocr_thread(self, file_paths: List[str], configs: List):
        """
        检测+OCR工作线程（在独立线程中运行）
        完成后将上下文放入翻译队列和修复队列
        """
        self._emit_status("[검출+OCR] 스레드 시작")
        try:
            self._run_async_in_thread(self._detection_ocr_async(file_paths, configs))
        finally:
            self._emit_status(f"[검출+OCR] 스레드 완료 ({self.stats['detection_ocr']}/{self.total_images})")
    
    async def _detection_ocr_async(self, file_paths: List[str], configs: List):
        """检测+OCR的异步实现"""
        self._check_cancelled_or_raise("检测+OCR")
        
        logger.info(f"[검출+OCR 스레드] 처리 시작 {len(file_paths)} 장 이미지 (배치 로드)")
        
        try:
            for idx, (file_path, config) in enumerate(zip(file_paths, configs)):
                self._check_cancelled_or_raise("检测+OCR", f"已处理 {idx}/{len(file_paths)} 张图片")
                
                # 检查是否需要停止（其他线程出错）
                if self.stop_workers:
                    logger.warning(f"[검출+OCR] 중지 신호를 받았고 이미 처리됨 {idx}/{len(file_paths)} 장 이미지")
                    break
                
                image = None
                ctx = None
                current_stage = 'preprocessing'
                try:
                    # 分批加载：只在需要时加载图片
                    current_stage = 'preprocessing'
                    logger.debug(f"[검출+OCR] 이미지 로드: {file_path}")
                    with open(file_path, 'rb') as f:
                        image = open_pil_image(f, eager=True)
                    image.name = file_path
                    
                    # 创建上下文
                    ctx = Context()
                    ctx.input = image
                    ctx.image_name = file_path
                    ctx.verbose = self.translator.verbose
                    ctx.save_quality = self.translator.save_quality
                    ctx.config = config
                    
                    logger.info(f"[검출+OCR] 처리 {idx+1}/{self.total_images}: {ctx.image_name}")
                    
                    # 检查取消
                    self._check_cancelled_or_raise("检测+OCR", f"已处理 {idx}/{len(file_paths)} 张图片")
                    
                    # 预处理：上色、超分
                    if config.colorizer.colorizer.value != 'none':
                        current_stage = 'colorizing'
                        ctx.img_colorized = await self.translator._run_colorizer(config, ctx)
                    else:
                        ctx.img_colorized = ctx.input

                    # 检查取消
                    self._check_cancelled_or_raise("检测+OCR", f"已处理 {idx}/{len(file_paths)} 张图片")

                    if config.upscale.upscale_ratio:
                        current_stage = 'upscaling'
                        ctx.upscaled = await self.translator._run_upscaling(config, ctx)
                    else:
                        ctx.upscaled = ctx.img_colorized

                    current_stage = 'preprocessing'
                    self.translator._save_editor_base_if_needed(ctx, config)

                    # 统一转换为 numpy
                    ctx.img_rgb, ctx.img_alpha = load_image(ctx.upscaled)
                    
                    # 检查取消
                    self._check_cancelled_or_raise("检测+OCR", f"已处理 {idx}/{len(file_paths)} 张图片")
                    
                    # 检测
                    current_stage = 'detection'
                    ctx.textlines, ctx.mask_raw, ctx.mask = await self.translator._run_detection(config, ctx)
                    
                    # 检查取消
                    self._check_cancelled_or_raise("检测+OCR", f"已处理 {idx}/{len(file_paths)} 张图片")
                    
                    # OCR
                    current_stage = 'ocr'
                    ctx.textlines = await self.translator._run_ocr(config, ctx)
                    
                    # 检查取消
                    self._check_cancelled_or_raise("检测+OCR", f"已处理 {idx}/{len(file_paths)} 张图片")
                    
                    # 文本行合并
                    if ctx.textlines:
                        current_stage = 'textline_merge'
                        ctx.text_regions = await self.translator._run_textline_merge(config, ctx)
                    
                    self.stats['detection_ocr'] += 1
                    # ✅ 发送状态日志（每完成一张图）
                    text_count = len(ctx.text_regions) if ctx.text_regions else 0
                    self._emit_status(f"[검출+OCR] 완료 {idx+1}/{self.total_images}: {os.path.basename(file_path)} ({text_count} 개 텍스트 블록)")
                    
                    # 保存图片尺寸
                    if hasattr(image, 'size'):
                        ctx.original_size = image.size
                    
                    ctx.input = image
                    
                    # 保存基础ctx
                    with self._lock:
                        self.base_contexts[ctx.image_name] = ctx
                    
                    # 放入翻译队列和修复队列
                    if ctx.text_regions:
                        # 保存原始 regions 引用集合,供翻译过滤后做差异检测
                        ctx._initial_region_ids = {id(r) for r in ctx.text_regions}
                        self._enqueue_translation_task(ctx.image_name, config)
                        self.inpaint_queue.put((ctx.image_name, config, False))
                        logger.info(f"[검출+OCR] {ctx.image_name} 번역 큐와 복구 큐에 넣었습니다 (번역 큐 크기: {self.translation_queue.qsize()})")
                    else:
                        # 无文本，直接标记完成并放入渲染队列
                        with self._lock:
                            self.translation_done[ctx.image_name] = []
                            self.inpaint_done[ctx.image_name] = True
                        ctx.text_regions = []
                        self.render_queue.put((ctx, config))
                        logger.debug(f"[검출+OCR] {ctx.image_name} 텍스트가 없어 바로 렌더 큐로 갑니다")
                    
                except Exception as e:
                    try:
                        error_msg = str(e)
                    except Exception:
                        error_msg = f"无法获取异常信息 (异常类型: {type(e).__name__})"
                    
                    logger.error(f"[검출+OCR] 실패: {error_msg}")
                    logger.error(traceback.format_exc())
                    if not self.translator.ignore_errors:
                        self.has_critical_error = True
                        self.critical_error_msg = f"检测+OCR失败: {error_msg}"
                        self.critical_error_exception = e
                        self.stop_workers = True
                        break

                    failed_ctx = ctx or Context()
                    if image is not None and getattr(failed_ctx, 'input', None) is None:
                        failed_ctx.input = image
                    failed_ctx.image_name = getattr(failed_ctx, 'image_name', None) or file_path
                    failed_ctx.config = config
                    failed_ctx.text_regions = []
                    failed_ctx = self.translator._mark_context_failure(failed_ctx, e, stage=current_stage)
                    self._record_failed_image(failed_ctx.image_name)

                    with self._lock:
                        self.base_contexts[failed_ctx.image_name] = failed_ctx
                        self.translation_done[failed_ctx.image_name] = []
                        self.inpaint_done[failed_ctx.image_name] = True

                    self.stats['detection_ocr'] += 1
                    self._emit_status(f"[검출+OCR] 실패 파일 건너뜀 {idx+1}/{self.total_images}: {os.path.basename(file_path)}")
                    self.render_queue.put((failed_ctx, config))
                    continue
                except PipelineAbortError:
                    logger.info(f"[검출+OCR] 내부 중지 신호로 종료: {os.path.basename(file_path)}")
                    break
        except PipelineAbortError:
            self.stop_workers = True
        except asyncio.CancelledError:
            self.stop_workers = True
            raise
        finally:
            # 标记检测+OCR全部完成
            self.detection_ocr_done = True
            logger.info("[검출+OCR 스레드] 처리 완료")
    
    def _translation_thread(self):
        """翻译工作线程（在独立线程中运行）"""
        self._emit_status("[번역] 스레드 시작")
        try:
            self._run_async_in_thread(self._translation_async())
        finally:
            logger.info(f"[번역 스레드] 스레드 완료 ({self.stats['translation']}/{self.total_images})")
            self._emit_status(f"[번역] 스레드 완료 ({self.stats['translation']}/{self.total_images})")
    
    async def _translation_async(self):
        """翻译的异步实现"""
        batch = []
        try:
            self._check_cancelled_or_raise("翻译")
            logger.info(f"[번역 스레드] 시작, 배치 크기: {self.batch_size}")
            
            while not self.stop_workers:
                try:
                    self._check_cancelled_or_raise("翻译", f"已完成 {self.stats['translation']}/{self.total_images}")

                    if self.has_critical_error:
                        logger.warning(f"[번역] 심각한 오류를 감지해 번역을 중지합니다 (완료 {self.stats['translation']}/{self.total_images})")
                        break
                    
                    # 从队列获取任务（非阻塞）
                    try:
                        task = self._pop_translation_task(timeout=0.1)
                        if task:
                            ctx, config = task
                            batch.append((ctx, config))
                    except queue.Empty:
                        if not batch:
                            if self.detection_ocr_done and self.translation_queue.empty():
                                break
                            if self.has_critical_error:
                                logger.warning("[번역] 심각한 오류를 감지해 대기를 중지합니다")
                                break
                            continue
                    
                    # 收集更多图片直到达到 batch_size
                    while len(batch) < self.batch_size:
                        try:
                            task = self._pop_translation_task(timeout=0.05)
                            if task:
                                ctx, config = task
                                batch.append((ctx, config))
                        except queue.Empty:
                            break
                    
                    # 判断是否应该翻译当前批次
                    should_translate, reason = self._should_translate_batch(batch)

                    if should_translate:
                        logger.info(f"[번역] {reason}，번역 시작 ({len(batch)} 장 이미지)")
                        await self._process_translation_batch(batch)
                        batch = []
                    
                except PipelineAbortError:
                    logger.info("[번역] 내부 중지 신호로 종료")
                    break
                except asyncio.CancelledError:
                    self.stop_workers = True
                    raise
                except Exception as e:
                    try:
                        error_msg = str(e)
                    except Exception:
                        error_msg = f"无法获取异常信息 (异常类型: {type(e).__name__})"
                    
                    logger.error(f"[번역 스레드] 오류: {error_msg}")
                    logger.error(traceback.format_exc())
                    self.has_critical_error = True
                    self.critical_error_msg = f"翻译线程错误: {error_msg}"
                    self.critical_error_exception = e
                    self.stop_workers = True
                    break
            
            # 处理剩余批次
            if batch and not self.stop_workers:
                logger.info(f"[번역] 남은 번역 {len(batch)} 장 이미지")
                await self._process_translation_batch(batch)
            
            if self.stats['translation'] >= self.total_images:
                logger.info(f"[번역 스레드] 모든 이미지를 번역했습니다 ({self.stats['translation']}/{self.total_images})")
        except PipelineAbortError:
            self.stop_workers = True
        finally:
            self.translation_thread_done = True
            logger.info("[번역 스레드] 중지")
    
    async def _process_translation_batch(self, batch: List[tuple]):
        """处理一个翻译批次"""
        if not batch:
            return
        
        logger.info(f"[번역] 일괄 번역 {len(batch)} 장 이미지")
        
        try:
            self._check_cancelled_or_raise("翻译", f"批量翻译 {len(batch)} 张图片")
            # 直接调用翻译（已经在独立线程的事件循环中）
            translated_batch = await self.translator._batch_translate_contexts(batch, len(batch))
            self._check_cancelled_or_raise("翻译", f"批量翻译 {len(batch)} 张图片")
            
            self.stats['translation'] += len(batch)
            # ✅ 发送状态日志
            self._emit_status(f"[번역] 배치 완료 ({self.stats['translation']}/{self.total_images})")
            
            ready_to_render = 0
            redo_tasks = []  # 锁外推送，避免锁内阻塞 queue.put
            for ctx, config in translated_batch:
                # 计算翻译过滤是否剔除了 region（仅对成功翻译的 ctx 适用）
                has_filtered = False
                filtered_count = 0
                if not getattr(ctx, 'translation_error', None):
                    initial_ids = getattr(ctx, '_initial_region_ids', None)
                    if initial_ids:
                        final_ids = {id(r) for r in (ctx.text_regions or [])}
                        filtered_ids = initial_ids - final_ids
                        has_filtered = bool(filtered_ids)
                        filtered_count = len(filtered_ids)

                with self._lock:
                    self.translation_done[ctx.image_name] = ctx.text_regions
                    if ctx.image_name in self.base_contexts:
                        self.base_contexts[ctx.image_name].text_regions = ctx.text_regions

                    if has_filtered:
                        # 翻译过滤掉了 region，标记待重做。首跑可能还没完成，也可能已完成。
                        # 修复线程首跑分支会因 pending_redo 存在而跳过入渲染，
                        # redo 任务被处理时再入渲染队列。
                        self.pending_redo.add(ctx.image_name)
                        redo_tasks.append((ctx.image_name, config))
                        logger.info(f"[번역] {ctx.image_name} 필터링 {filtered_count} 개 region, 복구를 다시 실행합니다")
                    elif ctx.image_name in self.inpaint_done:
                        # 无差异 + 修复首跑已完成 → 立即入渲染队列
                        self.render_queue.put((ctx, config))
                        ready_to_render += 1
                        logger.info(f"[번역] {ctx.image_name} 번역+복구가 끝나 바로 렌더 큐에 넣습니다")

            # 锁外推送 redo 任务到修复队列
            for image_name, config in redo_tasks:
                self.inpaint_queue.put((image_name, config, True))

            if ready_to_render > 0:
                logger.info(f"[번역] 배치 중 {ready_to_render}/{len(batch)} 장 이미지바로 렌더 큐에 넣습니다")
            if redo_tasks:
                logger.info(f"[번역] 배치 중 {len(redo_tasks)}/{len(batch)} 장 이미지복구 재실행이 발생했습니다")
            if ready_to_render == 0 and not redo_tasks:
                logger.debug(f"[번역] 배치 중 0/{len(batch)} 장 이미지복구가 끝나 렌더 큐에 넣기를 기다립니다")
            
        except PipelineAbortError:
            self.stop_workers = True
            raise
        except asyncio.CancelledError:
            self.stop_workers = True
            raise
        except Exception as e:
            try:
                error_msg = str(e)
            except Exception as str_error:
                error_msg = f"无法获取异常信息 (转换错误: {type(str_error).__name__})"
                logger.error(f"[번역] 예외 변환 실패: {str_error}")
            
            logger.error(f"[번역] 배치 실패: {error_msg}")
            logger.error(f"[번역] 예외 유형: {type(e).__name__}")
            logger.error(traceback.format_exc())

            self.stats['translation'] += len(batch)
            self._emit_status(f"[번역] 실패 배치 건너뜀 ({self.stats['translation']}/{self.total_images})")

            for ctx, config in batch:
                self.translator._mark_context_failure(ctx, e, stage='translation')
                self._record_failed_image(ctx.image_name)
                with self._lock:
                    self.translation_done[ctx.image_name] = []
                    if ctx.image_name in self.base_contexts:
                        self.base_contexts[ctx.image_name].text_regions = []
                    if self.translator.ignore_errors and ctx.image_name in self.inpaint_done:
                        self.render_queue.put((ctx, config))
                ctx.text_regions = []

            if not self.translator.ignore_errors:
                self.has_critical_error = True
                self.critical_error_msg = f"翻译批次失败: {error_msg}"
                self.critical_error_exception = e
                self.stop_workers = True
    
    def _inpaint_thread(self):
        """修复工作线程（在独立线程中运行）"""
        self._emit_status("[복구] 스레드 시작")
        try:
            self._run_async_in_thread(self._inpaint_async())
        finally:
            self._emit_status(f"[복구] 스레드 완료 ({self.stats['inpaint']}/{self.total_images})")
    
    async def _inpaint_async(self):
        """修复的异步实现"""
        self._check_cancelled_or_raise("修复")
        
        logger.info("[복구 스레드] 시작")
        
        inpaint_count = 0
        
        try:
            while not self.stop_workers:
                current_stage = 'inpainting'
                image_name = None
                config = None
                ctx = None
                is_redo = False
                try:
                    self._check_cancelled_or_raise("修复", f"已完成 {inpaint_count}/{self.total_images}")

                    if self.has_critical_error:
                        logger.warning(f"[복구] 심각한 오류를 감지해 복구를 중지합니다 (완료 {inpaint_count}/{self.total_images})")
                        break
                    
                    # 检查是否完成所有任务。
                    # 翻译线程可能在首轮修复队列清空后才发现 region 被过滤，
                    # 并投递 redo 修复任务；必须等翻译线程结束后才可退出。
                    if (
                        self.detection_ocr_done
                        and self.translation_thread_done
                        and self.inpaint_queue.empty()
                    ):
                        await asyncio.sleep(0.5)
                        self._check_cancelled_or_raise("修复", f"已完成 {inpaint_count}/{self.total_images}")
                        if self.translation_thread_done and self.inpaint_queue.empty():
                            logger.info(f"[복구 스레드] 모든 작업이 끝났습니다 ({inpaint_count}/{self.total_images})")
                            break
                    
                    # 尝试获取任务
                    try:
                        image_name, config, is_redo = self.inpaint_queue.get(timeout=1.0)
                    except queue.Empty:
                        if self.has_critical_error:
                            logger.warning("[복구] 심각한 오류를 감지해 대기를 중지합니다")
                            break
                        continue

                    with self._lock:
                        ctx = self.base_contexts.get(image_name)
                    if not ctx:
                        logger.error(f"[복구] {image_name}의 기본 컨텍스트를 찾지 못했습니다")
                        continue

                    if is_redo:
                        logger.info(f"[복구] 재실행(필터 후): {ctx.image_name} (남은 regions: {len(ctx.text_regions) if ctx.text_regions else 0})")
                        # 清除旧 mask 让 _run_mask_refinement 基于过滤后的 regions 重新生成
                        ctx.mask = None
                    else:
                        logger.info(f"[복구] 처리: {ctx.image_name}")

                    if getattr(ctx, 'translation_error', None):
                        self._record_failed_image(ctx.image_name)
                        with self._lock:
                            self.inpaint_done[ctx.image_name] = True
                            self.pending_redo.discard(ctx.image_name)
                            if ctx.image_name in self.translation_done:
                                self.render_queue.put((ctx, config))
                        if not is_redo:
                            self.stats['inpaint'] += 1
                            inpaint_count += 1
                            self._emit_status(f"[복구] 실패 파일 건너뜀 {inpaint_count}/{self.total_images}: {os.path.basename(ctx.image_name)}")
                        continue

                    # Mask refinement
                    if ctx.mask is None and ctx.text_regions:
                        current_stage = 'mask-generation'
                        self._check_cancelled_or_raise("修复", f"处理 {os.path.basename(ctx.image_name)}")
                        ctx.mask = await self.translator._run_mask_refinement(config, ctx)
                        self._check_cancelled_or_raise("修复", f"处理 {os.path.basename(ctx.image_name)}")

                    # Inpainting
                    if ctx.text_regions:
                        current_stage = 'inpainting'
                        self._check_cancelled_or_raise("修复", f"处理 {os.path.basename(ctx.image_name)}")
                        ctx.img_inpainted = await self.translator._run_inpainting(config, ctx)
                        self._check_cancelled_or_raise("修复", f"处理 {os.path.basename(ctx.image_name)}")

                    if not is_redo:
                        self.stats['inpaint'] += 1
                        inpaint_count += 1
                        self._emit_status(f"[복구] 완료 {inpaint_count}/{self.total_images}: {os.path.basename(ctx.image_name)}")
                    else:
                        self._emit_status(f"[복구] 재실행 완료: {os.path.basename(ctx.image_name)}")

                    # 标记修复完成
                    with self._lock:
                        self.inpaint_done[ctx.image_name] = True

                        if is_redo:
                            # 重做后翻译必已完成，且差异已确认。无条件入渲染队列。
                            self.pending_redo.discard(ctx.image_name)
                            render_ctx = self.base_contexts.get(ctx.image_name)
                            if render_ctx:
                                # text_regions 此时已是翻译过滤后的版本（翻译线程已写回）
                                self.render_queue.put((render_ctx, config))
                                logger.info(f"[복구] {ctx.image_name} 재실행이 끝나 렌더 큐에 넣습니다")
                            else:
                                logger.error(f"[복구] {ctx.image_name}의 기본 컨텍스트를 찾지 못했습니다")
                        elif ctx.image_name in self.pending_redo:
                            # 翻译已确认有过滤，正在等 redo 任务被处理，首跑完成不入队
                            logger.info(f"[복구] {ctx.image_name} 첫 실행이 끝나 재실행을 기다립니다")
                        elif ctx.image_name in self.translation_done:
                            # 翻译已完成且无 region 被过滤，加入渲染队列
                            render_ctx = self.base_contexts.get(ctx.image_name)
                            if render_ctx:
                                translated_regions = self.translation_done.get(ctx.image_name)
                                if isinstance(translated_regions, (list, tuple)):
                                    render_ctx.text_regions = translated_regions
                                elif translated_regions:
                                    logger.warning(f"[복구] {ctx.image_name} 의 번역 결과 유형이 이상합니다: {type(translated_regions)}, 빈 목록을 사용합니다")
                                    render_ctx.text_regions = []
                                else:
                                    render_ctx.text_regions = []
                                self.render_queue.put((render_ctx, config))
                                logger.info(f"[복구] {ctx.image_name} 번역+복구가 끝나 렌더 큐에 넣습니다")
                            else:
                                logger.error(f"[복구] {ctx.image_name}의 기본 컨텍스트를 찾지 못했습니다")
                    
                except Exception as e:
                    try:
                        error_msg = str(e)
                    except Exception:
                        error_msg = f"无法获取异常信息 (异常类型: {type(e).__name__})"
                    
                    logger.error(f"[복구 스레드] 오류: {error_msg}")
                    logger.error(traceback.format_exc())
                    if not self.translator.ignore_errors:
                        self.has_critical_error = True
                        self.critical_error_msg = f"修复线程错误: {error_msg}"
                        self.critical_error_exception = e
                        self.stop_workers = True
                        break

                    if ctx is None:
                        ctx = Context()
                        ctx.image_name = image_name
                        ctx.config = config
                    ctx = self.translator._mark_context_failure(ctx, e, stage=current_stage)
                    self._record_failed_image(ctx.image_name)
                    ctx.text_regions = []

                    with self._lock:
                        self.inpaint_done[ctx.image_name] = True
                        if ctx.image_name in self.base_contexts:
                            self.base_contexts[ctx.image_name] = ctx
                        if is_redo:
                            # redo 失败：清除 pending_redo，直接推渲染队列
                            self.pending_redo.discard(ctx.image_name)
                            self.render_queue.put((ctx, config))
                        else:
                            # 首跑失败：若已被翻译标为待重做，则让 redo 任务统一推渲染
                            if (ctx.image_name not in self.pending_redo
                                    and ctx.image_name in self.translation_done):
                                self.render_queue.put((ctx, config))

                    if not is_redo:
                        self.stats['inpaint'] += 1
                        inpaint_count += 1
                        self._emit_status(f"[복구] 실패 파일 건너뜀 {inpaint_count}/{self.total_images}: {os.path.basename(ctx.image_name)}")
                    else:
                        self._emit_status(f"[복구] 재실행 실패: {os.path.basename(ctx.image_name)}")
                    continue
                except PipelineAbortError:
                    logger.info("[복구] 내부 중지 신호로 종료")
                    break
        except PipelineAbortError:
            self.stop_workers = True
        except asyncio.CancelledError:
            self.stop_workers = True
            raise
        finally:
            logger.info("[복구 스레드] 중지")
    
    def _render_thread(self):
        """渲染工作线程（在独立线程中运行）"""
        self._emit_status("[렌더] 스레드 시작")
        try:
            self._run_async_in_thread(self._render_async())
        finally:
            self._emit_status(f"[렌더] 스레드 완료 ({self.stats['rendering']}/{self.total_images})")
    
    async def _render_async(self):
        """渲染的异步实现"""
        self._check_cancelled_or_raise("渲染")
        
        logger.info("[렌더 스레드] 시작")
        
        rendered_count = 0
        
        try:
            while not self.stop_workers or rendered_count < self.total_images:
                ctx = None
                config = None
                try:
                    self._check_cancelled_or_raise("渲染", f"已完成 {rendered_count}/{self.total_images}")

                    if self.has_critical_error:
                        logger.warning(f"[렌더] 심각한 오류를 감지해 렌더링을 중지합니다 (완료 {rendered_count}/{self.total_images})")
                        break
                    
                    # 尝试获取任务
                    try:
                        ctx, config = self.render_queue.get(timeout=1.0)
                    except queue.Empty:
                        # 检查是否应该退出
                        if self.stop_workers:
                            logger.info(f"[렌더] 중지 신호를 받았고 이미 렌더됨 {rendered_count}/{self.total_images} 장 이미지")
                            break
                        if rendered_count >= self.total_images:
                            break
                        if self.has_critical_error:
                            logger.warning("[렌더] 심각한 오류를 감지해 대기를 중지합니다")
                            break
                        continue
                    
                    logger.info(f"[렌더] 큐에서 작업을 가져옵니다: {ctx.image_name} (큐 남은 수: {self.render_queue.qsize()})")
                    
                    # 验证ctx
                    with self._lock:
                        verified_ctx = self.base_contexts.get(ctx.image_name)
                    if not verified_ctx:
                        logger.error(f"[렌더] {ctx.image_name}의 기본 컨텍스트를 찾지 못해 건너뜁니다")
                        continue
                    
                    ctx = verified_ctx
                    logger.info(f"[렌더] 처리 시작: {ctx.image_name}")

                    if getattr(ctx, 'translation_error', None):
                        self._record_failed_image(ctx.image_name)
                        self.stats['rendering'] += 1
                        rendered_count += 1
                        self._emit_status(f"[렌더] 실패 파일 건너뜀 {rendered_count}/{self.total_images}: {os.path.basename(ctx.image_name)}")

                        with self._results_lock:
                            self._results.append(ctx)
                        self.translator._cleanup_context_memory(ctx, keep_result=True)
                        with self._lock:
                            if ctx.image_name in self.base_contexts:
                                del self.base_contexts[ctx.image_name]
                        continue
                    
                    # 检查渲染所需的数据是否完整
                    if not hasattr(ctx, 'img_rgb') or ctx.img_rgb is None:
                        logger.error("[렌더] ctx.img_rgb가 None입니다. 렌더할 수 없습니다. 이 이미지를 건너뜁니다")
                        ctx = self.translator._mark_context_failure(ctx, RuntimeError("缺少原始图片数据"), stage='rendering')
                        self._record_failed_image(ctx.image_name)
                        self.stats['rendering'] += 1
                        rendered_count += 1
                        self._emit_status(f"[렌더] 실패 파일 건너뜀 {rendered_count}/{self.total_images}: {os.path.basename(ctx.image_name)}")
                        with self._results_lock:
                            self._results.append(ctx)
                        self.translator._cleanup_context_memory(ctx, keep_result=True)
                        with self._lock:
                            if ctx.image_name in self.base_contexts:
                                del self.base_contexts[ctx.image_name]
                        continue
                    
                    # 备份修复后图片
                    img_inpainted_copy = None
                    if (self.translator.save_text or self.translator.text_output_file) and hasattr(ctx, 'img_inpainted') and ctx.img_inpainted is not None:
                        import numpy as np
                        img_inpainted_copy = np.copy(ctx.img_inpainted)
                        logger.debug("[렌더] 저장용으로 복구 이미지를 백업했습니다")
                    
                    if not ctx.text_regions:
                        from .generic import dump_image
                        ctx.result = dump_image(ctx.input, ctx.img_rgb, ctx.img_alpha)
                    else:
                        self._check_cancelled_or_raise("渲染", f"处理 {os.path.basename(ctx.image_name)}")
                        ctx.img_rendered = await self.translator._run_text_rendering(config, ctx)
                        self._check_cancelled_or_raise("渲染", f"处理 {os.path.basename(ctx.image_name)}")
                        from .generic import dump_image
                        ctx.result = dump_image(
                            ctx.input,
                            ctx.img_rendered,
                            ctx.img_alpha,
                            mask=ctx.mask,
                            render_alpha=getattr(ctx, 'img_render_alpha', None),
                        )
                    
                    self.stats['rendering'] += 1
                    rendered_count += 1
                    
                    # ✅ 发送状态日志（每完成一张图）
                    self._emit_status(f"[렌더] 완료 {rendered_count}/{self.total_images}: {os.path.basename(ctx.image_name)}")
                    
                    # 保存
                    if ctx.result is not None:
                        logger.info(f"[렌더] ctx.result 설정됨, 유형: {type(ctx.result)}")
                        
                        try:
                            if hasattr(self.translator, '_current_save_info') and self.translator._current_save_info:
                                save_info = self.translator._current_save_info
                                
                                # ✅ 先保存修复图（在PSD导出之前），这样PSD导出时可以找到修复图文件
                                if img_inpainted_copy is not None:
                                    try:
                                        self.translator._save_inpainted_image(ctx.image_name, img_inpainted_copy)
                                    except Exception as e:
                                        logger.error(f"[렌더] 복구 이미지 저장 실패: {e}")
                                    finally:
                                        del img_inpainted_copy
                                        img_inpainted_copy = None
                                
                                # 保存翻译结果和导出PSD
                                self.translator._save_and_cleanup_context(ctx, save_info, config, "CONCURRENT")
                                
                                if (self.translator.save_text or self.translator.text_output_file) and ctx.text_regions is not None:
                                    self.translator._save_text_to_file(ctx.image_name, ctx, config)
                            else:
                                logger.warning("[렌더] save_info가 없어 저장을 건너뜁니다")
                            
                            ctx.success = True
                                    
                        except Exception as save_err:
                            logger.error(f"[렌더] 저장 실패 {os.path.basename(ctx.image_name)}: {save_err}")
                            logger.error(traceback.format_exc())
                            ctx = self.translator._mark_context_failure(ctx, save_err, stage='saving')
                            self._record_failed_image(ctx.image_name)
                    else:
                        logger.error("[렌더] ctx.result 가 None입니다!")
                    
                    # 添加到结果列表
                    with self._results_lock:
                        self._results.append(ctx)

                    # 清理内存 - 调用统一清理函数
                    logger.debug(f"[렌더] 메모리 정리: {ctx.image_name}")
                    self.translator._cleanup_context_memory(ctx, keep_result=True)

                    # 清理base_contexts
                    with self._lock:
                        if ctx.image_name in self.base_contexts:
                            del self.base_contexts[ctx.image_name]
                            logger.debug(f"[렌더] 정리했습니다 {ctx.image_name} 의 기본 컨텍스트")
                    
                except Exception as e:
                    try:
                        error_msg = str(e)
                    except Exception:
                        error_msg = f"无法获取异常信息 (异常类型: {type(e).__name__})"
                    
                    logger.error(f"[렌더 스레드] 오류: {error_msg}")
                    logger.error(traceback.format_exc())
                    if not self.translator.ignore_errors:
                        self.has_critical_error = True
                        self.critical_error_msg = f"渲染线程错误: {error_msg}"
                        self.critical_error_exception = e
                        self.stop_workers = True
                        break

                    if ctx is not None:
                        ctx = self.translator._mark_context_failure(ctx, e, stage='rendering')
                        self._record_failed_image(ctx.image_name)
                        self.stats['rendering'] += 1
                        rendered_count += 1
                        self._emit_status(f"[렌더] 실패 파일 건너뜀 {rendered_count}/{self.total_images}: {os.path.basename(ctx.image_name)}")
                        with self._results_lock:
                            self._results.append(ctx)
                        self.translator._cleanup_context_memory(ctx, keep_result=True)
                        with self._lock:
                            if ctx.image_name in self.base_contexts:
                                del self.base_contexts[ctx.image_name]
                        continue

                    self.has_critical_error = True
                    self.critical_error_msg = f"渲染线程错误: {error_msg}"
                    self.critical_error_exception = e
                    self.stop_workers = True
                    break
                except PipelineAbortError:
                    logger.info("[렌더] 내부 중지 신호로 종료")
                    break
        except PipelineAbortError:
            self.stop_workers = True
        except asyncio.CancelledError:
            self.stop_workers = True
            raise
        finally:
            logger.info("[렌더 스레드] 중지")
    
    async def process_batch(self, file_paths: List[str], configs: List) -> List[Context]:
        """
        并发处理一批图片（流水线模式，分批加载）
        
        Args:
            file_paths: 图片文件路径列表
            configs: 配置列表
            
        Returns:
            处理完成的Context列表
        """
        self.total_images = len(file_paths)
        self.start_time = datetime.now(timezone.utc)
        
        logger.info(f"[동시 파이프라인] 처리 시작 {self.total_images} 장 이미지")
        logger.info("[동시 파이프라인] 진짜 병렬 모드: 4개 독립 스레드(검출+OCR / 번역 / 복구 / 렌더링)")
        
        # 重置统计
        for key in self.stats:
            self.stats[key] = 0
        self.translation_done.clear()
        self.inpaint_done.clear()
        self.pending_redo.clear()
        self.base_contexts.clear()
        self.failed_images.clear()
        self.detection_ocr_done = False
        self.translation_thread_done = False
        self.stop_workers = False
        self.has_critical_error = False
        self.critical_error_msg = None
        self.critical_error_exception = None
        self._results = []
        
        # 将 stop_workers 纳入统一取消回调，确保 in-flight API 也能尽快响应停止
        original_cancel_callback = getattr(self.translator, "_cancel_check_callback", None)
        if hasattr(self.translator, "set_cancel_check_callback"):
            def _pipeline_cancel_check():
                if self.has_critical_error:
                    raise PipelineAbortError(self.critical_error_msg or "并发流水线发生严重错误")
                if original_cancel_callback:
                    try:
                        if bool(original_cancel_callback()):
                            return True
                    except Exception as e:
                        logger.debug(f"[동시 파이프라인] 외부 취소 콜백 예외 (무시 가능): {e}")
                if self.stop_workers:
                    raise PipelineAbortError("并发流水线已停止")
                return False
            self.translator.set_cancel_check_callback(_pipeline_cancel_check)
        
        # 提交4个独立线程任务
        futures = [
            self._detection_executor.submit(self._detection_ocr_thread, file_paths, configs),
            self._translation_executor.submit(self._translation_thread),
            self._inpaint_executor.submit(self._inpaint_thread),
            self._render_executor.submit(self._render_thread),
        ]
        
        try:
            # 等待所有线程完成（在外部循环中检查以便响应取消）
            last_rendered = 0
            while True:
                done, not_done = wait(futures, timeout=0.5)
                
                # ✅ 刷新子线程的状态日志到主线程
                self._flush_status_to_logger()
                self._check_cancelled_or_raise("并发流水线")
                
                # ✅ 报告进度（如果渲染数有变化）
                current_rendered = self.stats['rendering']
                if current_rendered > last_rendered:
                    try:
                        current_failed = self._get_failed_count()
                        await self.translator._report_progress(
                            f"batch:1:{current_rendered}:{self.total_images}:{current_failed}"
                        )
                    except Exception:
                        pass
                    last_rendered = current_rendered
                
                if len(not_done) == 0:
                    break
                # 检查是否有异常
                for f in done:
                    if f.exception():
                        raise f.exception()
                # 让出控制权，检查取消
                await asyncio.sleep(0)
                
        except PipelineAbortError as e:
            logger.info(f"[동시 파이프라인] 내부 중지 신호로 대기 종료: {e}")
            self.stop_workers = True
            done, not_done = wait(futures, timeout=10.0)
            self._flush_status_to_logger()
            if not_done:
                thread_names = []
                for i, future in enumerate(futures):
                    if future in not_done:
                        names = ["检测+OCR", "翻译", "修复", "渲染"]
                        thread_names.append(names[i])
                logger.warning(f"[동시 파이프라인] {len(not_done)} 개 스레드가 10초 안에 멈추지 않았습니다: {', '.join(thread_names)}")
            else:
                logger.info("[동시 파이프라인] 모든 스레드가 멈췄습니다")
        except asyncio.CancelledError:
            # 用户取消了任务
            logger.info("[동시 파이프라인] 취소 신호를 받았습니다")
            self.stop_workers = True
            # 等待所有线程停止（最多等待10秒）
            logger.info("[동시 파이프라인] 모든 스레드 중지를 기다립니다...")
            done, not_done = wait(futures, timeout=10.0)
            self._flush_status_to_logger()
            if not_done:
                # 显示哪些线程没有停止
                thread_names = []
                for i, future in enumerate(futures):
                    if future in not_done:
                        names = ["检测+OCR", "翻译", "修复", "渲染"]
                        thread_names.append(names[i])
                logger.warning(f"[동시 파이프라인] {len(not_done)} 개 스레드가 10초 안에 멈추지 않았습니다: {', '.join(thread_names)}")
            else:
                logger.info("[동시 파이프라인] 모든 스레드가 멈췄습니다")
            raise
        except Exception as e:
            logger.error(f"[동시 파이프라인] 오류: {e}")
            logger.error(traceback.format_exc())
            self.stop_workers = True
            raise
        finally:
            self.stop_workers = True
            if hasattr(self.translator, "set_cancel_check_callback"):
                self.translator.set_cancel_check_callback(original_cancel_callback)
            # 关闭所有线程池
            for executor in [self._detection_executor, self._translation_executor, 
                           self._inpaint_executor, self._render_executor]:
                if executor:
                    executor.shutdown(wait=False)
        
        # 检查是否有严重错误
        if self.has_critical_error:
            error_msg = self.critical_error_msg or "未知错误"
            logger.error(f"[동시 파이프라인] 처리 실패: {error_msg}")
            if self.critical_error_exception:
                raise self.critical_error_exception
            else:
                raise RuntimeError(f"并发流水线处理失败: {error_msg}")
        
        # 统计
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        logger.info("[동시 파이프라인] 완료!")
        logger.info(f"  총 소요: {elapsed:.2f}초")
        logger.info(f"  평균 속도: {elapsed/self.total_images:.2f}초/장")
        logger.info(f"  처리 통계: 검출+OCR={self.stats['detection_ocr']}, "
                   f"翻译={self.stats['translation']}, 修复={self.stats['inpaint']}, "
                   f"渲染={self.stats['rendering']}")
        
        return self._results
