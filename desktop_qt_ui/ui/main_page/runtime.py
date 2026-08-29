from PyQt6.QtCore import QTimer, Qt

from ui.theme import repolish_widget
from ui.widgets.two_line_combo import SUBTITLE_ROLE

MODE_ID_ROLE = Qt.ItemDataRole.UserRole + 1
COLORIZE_UPSCALE_INPAINT_MODE_IDS = frozenset({"colorize", "upscale", "inpaint"})
NOVELAI_MODE_ID = "novelai"

WORKFLOW_MODE_ITEMS = (
    {
        "id": "normal",
        "title_key": "Normal Translation",
        "tip_key": "Tip: Standard translation pipeline with detection, OCR, translation and rendering",
        "title_suffix": "",
    },
    {
        "id": "export_original",
        "title_key": "Export Original Text",
        "tip_key": "Tip: After exporting, manually translate 0000 script.txt in manga_translator_work/translation/, then use 'Import Translation and Render' mode",
        "title_suffix": " A",
    },
    {
        "id": "import_render",
        "title_key": "Import Translation and Render",
        "tip_key": "Tip: Will read TXT files from manga_translator_work/translation/ and render (0000 script.txt / combined script.txt)\nNotice: If you already edited dialogue in the editor, it will be overwritten by the TXT content.",
        "title_suffix": " B",
    },
    {
        "id": "rerender",
        "title_key": "Re-render",
        "tip_key": "Tip: Re-render image files based on JSON and inpaint data",
        "title_suffix": "",
    },
    {
        "id": "colorize",
        "title_key": "Colorize Only",
        "tip_key": "Tip: Only colorize images, no detection, OCR, translation or rendering",
        "title_suffix": "",
    },
    {
        "id": "upscale",
        "title_key": "Upscale Only",
        "tip_key": "Tip: Only upscale images, no detection, OCR, translation or rendering",
        "title_suffix": "",
    },
    {
        "id": "inpaint",
        "title_key": "Inpaint Only",
        "tip_key": "Tip: Detect text regions and inpaint to output clean images, no translation or rendering",
        "title_suffix": "",
    },
    {
        "id": "novelai",
        "title_key": "NovelAI Mode",
        "tip_key": "Tip: Convert image text into text layers. Line-break language is auto-detected per image from OCR text boxes.",
        "title_suffix": "",
    },
)
WORKFLOW_MODE_BY_ID = {item["id"]: item for item in WORKFLOW_MODE_ITEMS}

_WORKFLOW_CLI_FLAGS = (
    "load_text",
    "rerender_only",
    "translate_json_only",
    "template",
    "generate_and_export",
    "colorize_only",
    "upscale_only",
    "inpaint_only",
    "replace_translation",
    "novelai_mode",
)


def _workflow_mode_id_from_config(config) -> str:
    cli = getattr(config, "cli", None)
    if cli is None:
        return "normal"
    if getattr(cli, "novelai_mode", False):
        return "novelai"
    if getattr(cli, "inpaint_only", False):
        return "inpaint"
    if getattr(cli, "upscale_only", False):
        return "upscale"
    if getattr(cli, "colorize_only", False):
        return "colorize"
    if getattr(cli, "rerender_only", False):
        return "rerender"
    if getattr(cli, "load_text", False):
        return "import_render"
    if getattr(cli, "template", False):
        return "export_original"
    return "normal"


def _is_workflow_mode_visible(self, mode_id: str) -> bool:
    if mode_id not in COLORIZE_UPSCALE_INPAINT_MODE_IDS and mode_id != NOVELAI_MODE_ID:
        return True
    try:
        app = self.config_service.get_config().app
    except Exception:
        app = None
    if mode_id in COLORIZE_UPSCALE_INPAINT_MODE_IDS:
        return bool(getattr(app, "show_colorize_upscale_inpaint_modes", False))
    return bool(getattr(app, "show_novelai_mode", False))


def current_workflow_mode_id(self) -> str | None:
    combo = getattr(self, "workflow_mode_combo", None)
    if combo is None:
        return None
    index = combo.currentIndex()
    if index < 0:
        return None
    value = combo.itemData(index, MODE_ID_ROLE)
    return str(value) if value else None


def populate_workflow_mode_combo(self):
    combo = getattr(self, "workflow_mode_combo", None)
    if combo is None:
        return
    previous_id = current_workflow_mode_id(self)
    combo.clear()
    for item in WORKFLOW_MODE_ITEMS:
        if not _is_workflow_mode_visible(self, item["id"]):
            continue
        title = self._t(item["title_key"]) + item.get("title_suffix", "")
        combo.addItem(title)
        index = combo.count() - 1
        combo.setItemData(index, item["id"], MODE_ID_ROLE)
        combo.setItemData(index, self._t(item["tip_key"]), SUBTITLE_ROLE)

    config_id = None
    try:
        config_id = _workflow_mode_id_from_config(self.config_service.get_config())
    except Exception:
        config_id = None
    target_index = combo.findData(config_id, MODE_ID_ROLE) if config_id else -1
    if target_index < 0 and previous_id:
        target_index = combo.findData(previous_id, MODE_ID_ROLE)
    if target_index >= 0:
        combo.setCurrentIndex(target_index)


def refresh_workflow_mode_combo(self):
    combo = getattr(self, "workflow_mode_combo", None)
    if combo is None:
        return
    combo.blockSignals(True)
    populate_workflow_mode_combo(self)
    combo.blockSignals(False)
    update_workflow_mode_description(self)
    if hasattr(self, "update_start_button_text"):
        self.update_start_button_text()



def _set_progress_state(self, state: str):
    if hasattr(self, "progress_bar"):
        self.progress_bar.setProperty("progressState", state)
        repolish_widget(self.progress_bar)


def _set_start_button_state(self, state: str):
    if hasattr(self, "start_button"):
        self.start_button.setProperty("translationState", state)
        repolish_widget(self.start_button)


def update_workflow_mode_description(self, index: int | None = None):
    """根据翻译流程模式更新翻译页标题下方的介绍文字。"""
    if not hasattr(self, "translation_page_subtitle"):
        return

    mode_id = None
    combo = getattr(self, "workflow_mode_combo", None)
    if index is not None and combo is not None and 0 <= index < combo.count():
        mode_id = combo.itemData(index, MODE_ID_ROLE)
    if not mode_id:
        mode_id = current_workflow_mode_id(self)
    item = WORKFLOW_MODE_BY_ID.get(str(mode_id) if mode_id else "") or WORKFLOW_MODE_BY_ID["normal"]
    if hasattr(self, "translation_page_title"):
        self.translation_page_title.setText(self._t(item["title_key"]))
    self.translation_page_subtitle.setText(self._t(item["tip_key"]))







def update_progress(self, current: int, total: int, message: str = ""):
    """更新进度条。"""
    if total > 0:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        percentage = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setFormat(f"{current}/{total} ({percentage}%)")
        if hasattr(self, "progress_info_label"):
            fallback = (
                self._t("Completed {current}/{total}", current=current, total=total)
                if hasattr(self, "_t")
                else f"Completed {current}/{total}"
            )
            self.progress_info_label.setText(message or fallback)

        if not getattr(self, "_progress_active", False):
            self._progress_active = True
            _set_progress_state(self, "active")
    else:
        self._progress_active = False
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0/0 (0%)")
        if hasattr(self, "progress_info_label"):
            self.progress_info_label.setText("")
        _set_progress_state(self, "idle")


def reset_progress(self):
    """重置进度条为初始状态（灰色）。"""
    self._progress_active = False
    self.progress_bar.setMaximum(100)
    self.progress_bar.setValue(0)
    self.progress_bar.setFormat("0/0 (0%)")
    if hasattr(self, "progress_info_label"):
        self.progress_info_label.setText("")
    _set_progress_state(self, "idle")


def on_translation_state_changed(self, is_translating: bool):
    """根据翻译状态更新开始/停止按钮。"""
    if is_translating:
        self.start_button.setEnabled(False)
        self.start_button.setText(self._t("Starting..."))
        QTimer.singleShot(2000, self._enable_stop_button)
    else:
        self.start_button.setEnabled(True)
        _set_start_button_state(self, "ready")

        try:
            self.start_button.clicked.disconnect()
        except TypeError:
            pass
        self.start_button.clicked.connect(self.controller.start_backend_task)
        self.update_start_button_text()


def enable_stop_button(self):
    """启用停止按钮（延迟调用）。"""
    if self.controller.state_manager.is_translating():
        self.start_button.setEnabled(True)
        self.start_button.setText(self._t("Stop Translation"))
        _set_start_button_state(self, "stop")
        try:
            self.start_button.clicked.disconnect()
        except TypeError:
            pass
        self.start_button.clicked.connect(self.controller.stop_task)


def set_stopping_state(self):
    """设置按钮为“停止中...”状态，避免重复点击。"""
    self.start_button.setEnabled(False)
    self.start_button.setText(self._t("Stopping..."))
    _set_start_button_state(self, "stopping")
    try:
        self.start_button.clicked.disconnect()
    except TypeError:
        pass


def sync_workflow_mode_from_config(self):
    """从配置同步下拉框的选择。"""
    try:
        config = self.config_service.get_config()
        # Hidden from dropdown: Export Translation / Translate JSON Only / Replace Translation
        if (
            config.cli.replace_translation
            or config.cli.translate_json_only
            or config.cli.generate_and_export
        ):
            config.cli.replace_translation = False
            config.cli.translate_json_only = False
            config.cli.generate_and_export = False
            self.config_service.set_config(config)
            self.config_service.save_config_file()
        refresh_workflow_mode_combo(self)
    except Exception as e:
        print(f"Error syncing workflow mode: {e}")


def on_workflow_mode_changed(self, index: int):
    """处理翻译流程模式改变并持久化。"""
    config = self.config_service.get_config()
    for flag in _WORKFLOW_CLI_FLAGS:
        setattr(config.cli, flag, False)

    mode_id = None
    combo = getattr(self, "workflow_mode_combo", None)
    if combo is not None and index >= 0:
        mode_id = combo.itemData(index, MODE_ID_ROLE)

    if mode_id == "export_original":
        config.cli.template = True
    elif mode_id == "import_render":
        config.cli.load_text = True
    elif mode_id == "rerender":
        config.cli.rerender_only = True
    elif mode_id == "colorize":
        config.cli.colorize_only = True
    elif mode_id == "upscale":
        config.cli.upscale_only = True
    elif mode_id == "inpaint":
        config.cli.inpaint_only = True
    elif mode_id == "novelai":
        config.cli.novelai_mode = True

    self.config_service.set_config(config)
    self.config_service.save_config_file()
    self.update_start_button_text()
    update_workflow_mode_description(self, index)


def update_start_button_text(self):
    """根据当前模式更新开始按钮文案。"""
    if self.controller.state_manager.is_translating():
        return

    try:
        config = self.config_service.get_config()
        if getattr(config.cli, "novelai_mode", False):
            self.start_button.setText(self._t("Start NovelAI Mode"))
        elif config.cli.inpaint_only:
            self.start_button.setText(self._t("Start Inpainting"))
        elif config.cli.upscale_only:
            self.start_button.setText(self._t("Start Upscaling"))
        elif config.cli.colorize_only:
            self.start_button.setText(self._t("Start Colorizing"))
        elif getattr(config.cli, "rerender_only", False):
            self.start_button.setText(self._t("Re-render"))
        elif config.cli.load_text:
            self.start_button.setText(self._t("Import Translation and Render") + " B")
        elif config.cli.template:
            self.start_button.setText(self._t("Generate Original Text Template") + " A")
        # elif config.cli.replace_translation:
        #     self.start_button.setText(self._t("Start Replace Translation"))
        # elif config.cli.translate_json_only:
        #     self.start_button.setText(self._t("Start JSON Translation"))
        # elif config.cli.generate_and_export:
        #     self.start_button.setText(self._t("Export Translation"))
        else:
            self.start_button.setText(self._t("Start Translation"))
    except Exception as e:
        self.start_button.setText(self._t("Start Translation"))
        print(f"Could not update button text: {e}")
