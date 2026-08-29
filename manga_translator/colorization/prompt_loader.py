import copy
import os
from dataclasses import dataclass
from typing import Any, Optional

from ..translators.prompt_loader import load_prompt_file
from ..utils import BASE_PATH

DEFAULT_AI_COLORIZER_PROMPT = (
    "You are a manga colorization engine. Colorize the provided manga page while preserving "
    "the original composition, character identities, panel structure, line art, shading, and "
    "readability of all existing details. Keep the page content unchanged except for adding "
    "natural, coherent color. Return only the final colorized image."
)

DEFAULT_AI_COLORIZER_PROMPT_PATH = os.path.join("dict", "ai_colorizer_prompt.yaml").replace("\\", "/")
AI_COLORIZER_PROMPT_KEYS = ("ai_colorizer_prompt", "colorizer_prompt", "prompt")
AI_COLORIZER_RULE_KEYS = ("colorization_rules", "rules", "style_guide")
AI_COLORIZER_REFERENCE_KEYS = ("reference_images", "reference_image_paths", "images")


@dataclass
class ColorizerReferenceImage:
    path: str
    description: str = ""
    resolved_path: Optional[str] = None


DEFAULT_AI_COLORIZER_PROMPT_TEMPLATE = {
    "ai_colorizer_prompt": DEFAULT_AI_COLORIZER_PROMPT,
    "colorization_rules": [],
    "reference_images": [],
}


def resolve_ai_colorizer_prompt_path(path: Optional[str]) -> str:
    rel_path = (path or DEFAULT_AI_COLORIZER_PROMPT_PATH).replace("\\", "/")
    if os.path.isabs(rel_path):
        return os.path.normpath(rel_path)
    return os.path.normpath(os.path.join(BASE_PATH, rel_path))


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _extract_first_text(data: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _coerce_text(data.get(key))
        if value:
            return value
    return ""


def _extract_rule_list(data: dict) -> list[str]:
    for key in AI_COLORIZER_RULE_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return [_coerce_text(item) for item in value if _coerce_text(item)]
        if isinstance(value, str):
            return [_coerce_text(line) for line in value.splitlines() if _coerce_text(line)]
    return []


def _extract_reference_images(data: dict) -> list[ColorizerReferenceImage]:
    raw_items = None
    for key in AI_COLORIZER_REFERENCE_KEYS:
        candidate = data.get(key)
        if isinstance(candidate, list):
            raw_items = candidate
            break
    if raw_items is None:
        return []

    images: list[ColorizerReferenceImage] = []
    for item in raw_items:
        if isinstance(item, str):
            path = _coerce_text(item)
            if path:
                images.append(ColorizerReferenceImage(path=path))
            continue
        if not isinstance(item, dict):
            continue
        path = _coerce_text(
            item.get("path")
            or item.get("image_path")
            or item.get("file")
            or item.get("value")
        )
        if not path:
            continue
        description = _coerce_text(
            item.get("description")
            or item.get("note")
            or item.get("label")
            or item.get("purpose")
        )
        images.append(ColorizerReferenceImage(path=path, description=description))
    return images


def resolve_colorizer_reference_image_path(
    raw_path: str,
    *,
    prompt_path: Optional[str] = None,
    image_path: Optional[str] = None,
) -> Optional[str]:
    candidate = os.path.expanduser((raw_path or "").strip())
    if not candidate:
        return None
    if os.path.isabs(candidate):
        return os.path.normpath(candidate) if os.path.exists(candidate) else None

    search_dirs: list[str] = []
    if prompt_path:
        search_dirs.append(os.path.dirname(resolve_ai_colorizer_prompt_path(prompt_path)))
    if image_path:
        search_dirs.append(os.path.dirname(os.path.abspath(image_path)))
    search_dirs.append(BASE_PATH)
    search_dirs.append(os.getcwd())

    seen: set[str] = set()
    for base_dir in search_dirs:
        norm_base = os.path.normpath(base_dir)
        if norm_base in seen:
            continue
        seen.add(norm_base)
        resolved = os.path.normpath(os.path.join(norm_base, candidate))
        if os.path.exists(resolved):
            return resolved
    return None


def load_ai_colorizer_prompt_template(path: Optional[str]) -> dict[str, Any]:
    resolved_path = resolve_ai_colorizer_prompt_path(path)
    if not os.path.exists(resolved_path):
        return copy.deepcopy(DEFAULT_AI_COLORIZER_PROMPT_TEMPLATE)

    data = load_prompt_file(resolved_path)
    if not isinstance(data, dict):
        return copy.deepcopy(DEFAULT_AI_COLORIZER_PROMPT_TEMPLATE)

    template = copy.deepcopy(DEFAULT_AI_COLORIZER_PROMPT_TEMPLATE)
    prompt_text = _extract_first_text(data, AI_COLORIZER_PROMPT_KEYS)
    if prompt_text:
        template["ai_colorizer_prompt"] = prompt_text

    template["colorization_rules"] = _extract_rule_list(data)
    template["reference_images"] = [
        {
            "path": ref.path,
            "description": ref.description,
        }
        for ref in _extract_reference_images(data)
    ]
    return template


def load_ai_colorizer_prompt_file(path: Optional[str]) -> str:
    data = load_ai_colorizer_prompt_template(path)
    return _coerce_text(data.get("ai_colorizer_prompt"))


def build_ai_colorizer_prompt_payload(
    path: Optional[str],
    *,
    image_path: Optional[str] = None,
) -> dict[str, Any]:
    resolved_prompt_path = resolve_ai_colorizer_prompt_path(path)
    template = load_ai_colorizer_prompt_template(path)

    prompt_text = _coerce_text(template.get("ai_colorizer_prompt")) or DEFAULT_AI_COLORIZER_PROMPT
    rules = [_coerce_text(item) for item in template.get("colorization_rules", []) if _coerce_text(item)]

    reference_images: list[ColorizerReferenceImage] = []
    for item in template.get("reference_images", []):
        if not isinstance(item, dict):
            continue
        raw_path = _coerce_text(item.get("path"))
        if not raw_path:
            continue
        resolved_path = resolve_colorizer_reference_image_path(
            raw_path,
            prompt_path=resolved_prompt_path,
            image_path=image_path,
        )
        reference_images.append(
            ColorizerReferenceImage(
                path=raw_path,
                description=_coerce_text(item.get("description")),
                resolved_path=resolved_path,
            )
        )

    sections = [prompt_text]
    if rules:
        sections.append("Colorization rules:\n" + "\n".join(f"- {rule}" for rule in rules))
    if reference_images:
        ref_lines = []
        for idx, ref in enumerate(reference_images, start=1):
            label = ref.description or os.path.basename(ref.path) or ref.path
            ref_lines.append(f"{idx}. {label}")
        sections.append(
            "Reference images are attached separately. Use them only for palette, character consistency, materials, and lighting. "
            "Do not copy their composition or redraw the page.\n"
            + "\n".join(ref_lines)
        )

    return {
        "prompt_text": "\n\n".join(section for section in sections if section.strip()).strip(),
        "reference_images": reference_images,
        "template": template,
    }


def save_ai_colorizer_prompt_file(path: Optional[str], prompt_text: str) -> str:
    resolved_path = resolve_ai_colorizer_prompt_path(path)
    os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

    payload = copy.deepcopy(DEFAULT_AI_COLORIZER_PROMPT_TEMPLATE)
    payload["ai_colorizer_prompt"] = prompt_text.strip() or DEFAULT_AI_COLORIZER_PROMPT
    try:
        import yaml

        content = yaml.dump(payload, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except ImportError:
        lines = payload["ai_colorizer_prompt"].splitlines() or [""]
        content = ["ai_colorizer_prompt: |"]
        content.extend(f"  {line}" if line else "  " for line in lines)
        content.append("colorization_rules: []")
        content.append("reference_images: []")
        content = "\n".join(content) + "\n"

    with open(resolved_path, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else "\n".join(content) + "\n")
    return resolved_path


def ensure_ai_colorizer_prompt_file(path: Optional[str] = None) -> str:
    resolved_path = resolve_ai_colorizer_prompt_path(path)
    if not os.path.exists(resolved_path):
        save_ai_colorizer_prompt_file(resolved_path, DEFAULT_AI_COLORIZER_PROMPT)
    return resolved_path
