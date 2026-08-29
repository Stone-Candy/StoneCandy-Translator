# Features

This document summarizes the core translation pipeline and the built-in visual editor.

---

## ✨ Core Features

### Text and Translation Pipeline

- **🔍 Smart Text Detection**: automatically detects text regions in manga pages
- **📝 Multilingual OCR**: supports Japanese, Chinese, English, Korean, and more
- **🌐 Multiple Translators**: supports `OpenAI`, `Google Gemini`, `Vertex`, `Sakura`, `OpenAI High Quality`, `Gemini High Quality`, and `Vertex High Quality`
- **🎯 High-Quality Translation**: multimodal translators can use image context for better results
- **📚 Auto Extract Glossary**: automatically collects names, places, organizations, and other terms
- **🎨 Inpainting**: removes source text and repairs the background
- **✍️ Smart Typesetting**: renders translated text with configurable style and layout
- **🤖 AI Line Breaking**: improves readability for supported translators
- **📦 Batch Processing**: processes entire folders in one run
- **📥 PSD Export**: exports layered PSD files with original image, inpainted image, and text layers

---

## 🎨 Visual Editor

The built-in editor is designed for precise post-processing.

### Region Editing

- **Move**: drag a text region anywhere
- **Rotate**: rotate with the handle
- **Reshape**: adjust corners, edges, and freeform geometry
- **Create new regions**: add or paste new regions when needed
- **Edit Shape**: refine the region box shape directly in the editor

> **💡 OCR best practice**: if you want stable OCR results in the editor, try to keep one text line per region whenever possible.

### Text Editing

- **Manual translation edits**: edit the translated text directly
- **Style adjustments**: `Font`, `Font Size`, `Font Color`, `Stroke Color`, `Alignment`, and more
- **Direction control**: horizontal or vertical text

### Mask Editing

- **Brush**: paint the erase mask manually
- **Eraser**: remove incorrect mask regions
- **Mask refinement**: improve cleanup when automatic masks are not ideal

### Advanced Editing Features

- **Undo / Redo**: full history support
- **Multi-selection**: copy, paste, and delete region groups
- **Live preview**: preview render results inside the editor

---

## 🖥️ User Interface

- **Modern Qt UI**: built on PyQt6
- **Drag-and-drop support**: drop files or folders directly into the file list
- **Live logs**: see progress and runtime errors as tasks run
- **Config management**: import, export, and reuse configuration presets
- **Prompt Management**: manage prompt files and use `Apply Selected Prompt`
- **Font Management**: import fonts, preview them, and use `Apply Selected Font`

---

## 🌐 Translator Support

### Online Translators

| Translator | Description |
|--------|------|
| `OpenAI` | OpenAI-compatible text translation |
| `Google Gemini` | Gemini-family text translation |
| `Sakura` | Japanese-focused translation backend |

### High-Quality Translators

| Translator | Strength |
|--------|------|
| `OpenAI High Quality` | Multimodal translation with image context |
| `Gemini High Quality` | Multimodal translation with image context |

**Why high-quality translators matter**:

- 📸 They can see the page content
- 🎯 They usually produce more context-aware translations
- 📝 They work well for multi-page story flow
- 🔧 They pair well with custom prompts and glossary extraction

### Other translator options

| Option | Description |
|------|------|
| `Original` | Keep the original text |
| `None` | Skip translation |

---

## 🔤 OCR Models

| OCR Model | Description |
|------|------|
| `32px` | Legacy lightweight OCR, useful as a compatibility fallback |
| `48px` | Default recommendation |
| `48px_ctc` | Comparison variant of 48px |
| `mocr` | Manga OCR, often strong for Japanese manga |
| `paddleocr` | General multilingual OCR |
| `paddleocr_korean` | Often good for Korean comics |
| `paddleocr_latin` | Recommended for English and Latin-script text |
| `paddleocr_thai` | Recommended for Thai |
| `paddleocr_vl` | Highest accuracy, highest resource usage |
| `openai_ocr` | OpenAI-compatible multimodal OCR |
| `gemini_ocr` | Gemini multimodal OCR |

Recommended Japanese hybrid OCR combination:

- `48px + mocr`

---

## 🎨 Image Processing

### Inpainting Models

| Inpainting Model | Description |
|------|------|
| `lama_large` | Best quality inpainting recommendation |
| `lama_mpe` | Faster LaMa-based option |
| `default` | Default AOT-style inpainter |

### Upscaling

| Feature | Description |
|------|------|
| `waifu2x` | Traditional upscaling model |
| `realcugan` | Recommended upscaler with strong denoise options |
| `mangajanai` | Highest quality, heavier resource usage |
| `Upscale Ratio` | Supports `2x`, `3x`, and `4x` |
| `Real-CUGAN Model` | Multiple pretrained variants, including denoise and conservative modes |
| `Tile Size (0=No Split)` | Helps process large images with limited VRAM |
| `Revert Upscaling` | Returns to original resolution after translation |

### Colorization

| Colorization Model | Description |
|------|------|
| `none` | No colorization |
| `openai_colorizer` | API-based colorization through OpenAI-compatible endpoints |
| `gemini_colorizer` | API-based colorization through Gemini |

---

## 🧰 Typesetting Features

Common typesetting controls from the current Qt UI:

- `Renderer`
- `Alignment`
- `Text Direction`
- `Disable Font Border`
- `Font Size Offset`
- `Minimum Font Size`
- `Maximum Font Size`
- `Font Scale Ratio`
- `Stroke Width Ratio`
- `Center in Bubble`
- `AI Line Breaking`
- `AI Line Break Auto Enlarge`
- `AI Line Break Check`
- `Layout Mode`

Current layout mode names:

- `Smart Scaling`
- `Strict Boundary`
- `Smart Bubble`

---

## 💾 Font Support

The app automatically loads fonts from the `fonts` directory.

You can also use `Font Management` to:

- import fonts
- preview fonts
- apply a selected font to the current workflow

---

## 🔧 Prompt Support

Prompt files can be managed through `Prompt Management`.

Typical prompt-related capabilities:

- import prompt files
- rename prompt files
- delete prompt files
- preview prompt content
- edit prompt content
- apply a prompt to the current workflow

Prompt files are especially useful for:

- translation tone control
- glossary consistency
- project-specific instructions

---

Back to [README_EN](../../README_EN.md)
