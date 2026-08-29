import os
from typing import Optional

from ..translators.prompt_loader import load_prompt_file
from ..utils import BASE_PATH

DEFAULT_AI_OCR_PROMPT = (
    "You are an OCR engine for manga text regions. "
    "Read the text in the image and return only the recognized text. "
    "Preserve line breaks. Do not translate, summarize, explain, add markdown, "
    "or add surrounding quotes. If no text is visible, return an empty string."
)

DEFAULT_AI_OCR_PROMPT_PATH = os.path.join("dict", "ai_ocr_prompt.yaml").replace("\\", "/")
LEGACY_AI_OCR_PROMPT_PATH = os.path.join("dict", "ai_ocr_prompt.json").replace("\\", "/")
AI_OCR_PROMPT_KEYS = ("ai_ocr_prompt", "ocr_prompt", "prompt")
AI_OCR_PROMPT_EXTENSIONS = (".yaml", ".yml", ".json")


def resolve_ai_ocr_prompt_path(path: Optional[str]) -> str:
    rel_path = (path or DEFAULT_AI_OCR_PROMPT_PATH).replace("\\", "/")
    if os.path.isabs(rel_path):
        return os.path.normpath(rel_path)
    return os.path.normpath(os.path.join(BASE_PATH, rel_path))


def load_ai_ocr_prompt_file(path: Optional[str]) -> str:
    resolved_path = resolve_ai_ocr_prompt_path(path)
    if not os.path.exists(resolved_path):
        return ""

    data = load_prompt_file(resolved_path)
    if not isinstance(data, dict):
        return ""

    for key in AI_OCR_PROMPT_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def save_ai_ocr_prompt_file(path: Optional[str], prompt_text: str) -> str:
    resolved_path = resolve_ai_ocr_prompt_path(path)
    os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

    ext = os.path.splitext(resolved_path)[1].lower()

    if ext == ".json":
        import json

        payload = {"ai_ocr_prompt": prompt_text}
        with open(resolved_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return resolved_path

    lines = prompt_text.splitlines() or [""]
    content = ["ai_ocr_prompt: |"]
    content.extend(f"  {line}" if line else "  " for line in lines)
    with open(resolved_path, "w", encoding="utf-8") as f:
        f.write("\n".join(content) + "\n")
    return resolved_path


def ensure_ai_ocr_prompt_file(path: Optional[str] = None) -> str:
    resolved_path = resolve_ai_ocr_prompt_path(path)
    if not os.path.exists(resolved_path):
        prompt_text = DEFAULT_AI_OCR_PROMPT
        if path is None:
            legacy_path = resolve_ai_ocr_prompt_path(LEGACY_AI_OCR_PROMPT_PATH)
            if os.path.exists(legacy_path):
                legacy_prompt = load_ai_ocr_prompt_file(legacy_path)
                if legacy_prompt:
                    prompt_text = legacy_prompt
        save_ai_ocr_prompt_file(resolved_path, prompt_text)
    return resolved_path


def list_ai_ocr_prompt_files(dict_dir: str) -> list[str]:
    if not os.path.isdir(dict_dir):
        return []

    files = []
    for filename in sorted(os.listdir(dict_dir)):
        if not filename.lower().endswith(AI_OCR_PROMPT_EXTENSIONS):
            continue
        file_path = os.path.join(dict_dir, filename)
        if load_ai_ocr_prompt_file(file_path):
            files.append(filename)
    return files
