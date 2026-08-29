# Debugging Guide

This document explains how to debug translation quality issues and troubleshoot common problems.

To stay aligned with the current desktop UI, this English version uses the actual current UI labels from the project `i18n`. Where older documentation referred to broad legacy settings tabs, the current desktop UI mostly maps those controls to:

- `Settings` -> `General`
- `Settings` -> `OCR`
- `Settings` -> `Detection`
- `Settings` -> `Inpainting`
- `Settings` -> `Typesetting`
- `Translation Interface`

---

## Debugging Workflow

When translation quality is not ideal, the fastest way to find the problem is to enable detailed logs and inspect the intermediate processing results step by step.

---

## Enable Verbose Logging

In the current desktop UI, enable `Verbose Logging` in:

- `Settings` -> `General` -> `Verbose Logging`

### What `Verbose Logging` generates

- The log panel shows more `DEBUG` level information for intermediate detection, OCR, and rendering steps
- Each run generates:
  - `result/log_<timestamp>.txt` for the Qt UI runtime log
  - `result/<timestamp>-<image>-<target-language>-<translator>/` for intermediate debug files
- It is recommended to turn this on only when troubleshooting. For daily use, keeping it off reduces log noise and disk usage

---

## Debug File Reference

After `Verbose Logging` is enabled, each run creates debug files under:

`result/<timestamp>-<image>-<target-language>-<translator>/`

### Detection stage

- **`detection_raw_boxes.png`**: raw text boxes directly from the detector before filtering
  - Shows all candidate text regions found by the detector
  - Different boxes are usually drawn in different colors

- **`bboxes_unfiltered.png`**: text boxes after detector-side filtering, but before OCR filtering
  - Shows boxes that passed the detector confidence thresholds
  - Usually marked with red borders

- **`hybrid_detection_boxes.png`**: merged detection result when hybrid or multiple detector logic is used
  - Useful when comparing how different detection paths contributed

### OCR stage

- **`ocrs/` folder**: cropped OCR images for each text region
  - `0.png`, `1.png`, `2.png`, and so on each correspond to one text box
  - You can inspect the exact crop sent into OCR
  - Vertical text is automatically rotated for easier reading

- **`bboxes.png`**: final text boxes that survived OCR filtering
  - Shows regions where text was successfully recognized
  - Includes probability or confidence information
  - Also shows the reading order or panel order index

### Mask and inpainting stage

- **`bboxes_with_scores.png`**: text boxes together with confidence scores
  - Useful for checking which boxes are weak or unstable

- **`mask_binary.png`**: binarized text mask
  - A black-and-white mask of text regions

- **`mask_raw.png`**: raw text-erasure mask heatmap
  - The unoptimized original mask
  - Usually includes a color scale that shows confidence intensity

- **`mask_comparison.png`**: mask comparison image, when multiple mask-generation methods are available
  - Helps compare which mask path worked better

- **`mask_final.png`**: final optimized text-erasure mask
  - The mask after dilation and cleanup

- **`inpaint_input.png`**: image fed into the inpainting model
  - Lets you confirm what the inpainter actually received

- **`inpainted.png`**: image after text removal and background repair
  - Useful for checking whether text erasure is complete and whether the background was reconstructed cleanly

### Rendering stage

- **`balloon_fill_boxes.png`**: text boxes used by the smart bubble layout mode
  - Generated when `Layout Mode` is `Smart Bubble`
  - Helps verify whether the bubble-aware typesetting region is reasonable

- **`final.png`**: final translated image
  - The fully rendered output after typesetting

### Other debug files

- **`input.png`**: the original input image in some processing modes
  - Helpful when comparing intermediate steps against the original image

---

## Tunable Parameters

If detection or recognition quality is poor, you can adjust the following settings in the current desktop UI.

### Detection parameters

Current UI section:

- `Settings` -> `Detection`

- **`Text Threshold` (`text_threshold`)**: `0.1 - 0.9`, default `0.5`
  - Confidence threshold for deciding whether a region is text
  - **Lower** it to detect more text, but this may increase false positives
  - **Raise** it to keep only obvious text, but faint text may be missed

- **`Box Generation Threshold` (`box_threshold`)**: `0.1 - 0.9`, default `0.5`
  - Confidence threshold for generating text boxes
  - **Lower** it to create more text boxes
  - **Raise** it to keep only high-confidence boxes

- **`Unclip Ratio` (`unclip_ratio`)**: `1.0 - 3.0`, default `2.5`
  - Expansion ratio for detected text boxes
  - **Increase** it to make boxes larger and include more surrounding area
  - **Decrease** it to keep boxes tighter around text edges

### OCR parameters

Current UI sections:

- `Settings` -> `OCR`
- `Settings` -> `OCR` -> `Advanced`

- **`Text Region Min Probability` (`prob`)**: `0.0 - 1.0`, default `0.1`
  - OCR confidence threshold
  - **Lower** it to keep more OCR results, but that can include more mistakes
  - **Raise** it to keep only high-confidence OCR results, but some valid text may be dropped

---

## Example Debugging Flow

1. **Check the detection stage**
   - Open `bboxes_unfiltered.png` and confirm whether the detector found all text regions
   - If text is missing, lower `Text Threshold` and `Box Generation Threshold`
   - If too many non-text regions are detected, raise `Text Threshold` and `Box Generation Threshold`

2. **Check the OCR stage**
   - Open the images under `ocrs/` and confirm whether each crop is readable
   - Open `bboxes.png` and confirm which regions were recognized successfully
   - If OCR misses too much text, lower `Text Region Min Probability` or increase `Unclip Ratio`
   - If OCR errors are frequent, raise `Text Region Min Probability`

---

## Common Troubleshooting

### Text is not detected

**Possible causes**:

- detection confidence is too strict
- image resolution is too low
- text and background have poor contrast

**Fixes**:

1. Lower `Text Threshold` and `Box Generation Threshold`
2. Increase `Detection Size`, for example to `2560` or `3072`
3. Improve image quality first, or prioritize raising `Detection Size`

### OCR recognition is inaccurate

**Possible causes**:

- text boxes are too small or too large
- the text is blurry or distorted
- the OCR model is not a good fit

**Fixes**:

1. Adjust `Unclip Ratio` so the text box size is more appropriate
2. Try another `OCR Model`, such as `48px`, `48px_ctc`, or `mocr`
3. Enable `Enable Hybrid OCR` so two OCR models work together

### Translation layout looks wrong

**Possible causes**:

- font size is not appropriate
- the layout mode does not fit the page
- text-box positions are inaccurate

**Fixes**:

1. Adjust `Layout Mode`, with `Smart Scaling` usually being a good general choice
2. Change `Font Size Offset`
3. Fine-tune text boxes manually in `Editor View`

### Text removal is not clean

**Possible causes**:

- the mask coverage is too small
- the inpainting model is not performing well enough

**Fixes**:

1. Increase `Mask Dilation Offset`
   - Default is usually `70`
   - You can try `100-150` when text remnants remain
2. Switch `Inpainting Model` to `lama_large` for the best quality
3. Edit the mask manually in `Editor View`

---

## Clean Up Logs (Qt UI)

After you finish troubleshooting, it is a good idea to clean old logs and debug directories regularly.

### Method 1: Manual cleanup

1. Close the Qt UI so the program is no longer writing logs
2. Open the `result/` directory in the project root
3. Delete anything you no longer need:
   - `log_*.txt` runtime logs
   - debug directories named like `<timestamp>-<image>-<target-language>-<translator>`
4. Keep any sample directories you still need for comparison

### Method 2: One-click cleanup with Windows PowerShell

Run this in the project root:

```powershell
# Delete all log files
Get-ChildItem .\result -File -Filter "log_*.txt" | Remove-Item -Force

# Delete all debug directories
Get-ChildItem .\result -Directory | Where-Object { $_.Name -match '^\d{14}-' } | Remove-Item -Recurse -Force
```

### Method 3: Keep only the most recent 7 days

```powershell
$deadline = (Get-Date).AddDays(-7)
Get-ChildItem .\result -File -Filter "log_*.txt" | Where-Object { $_.LastWriteTime -lt $deadline } | Remove-Item -Force
Get-ChildItem .\result -Directory | Where-Object { $_.LastWriteTime -lt $deadline -and $_.Name -match '^\d{14}-' } | Remove-Item -Recurse -Force
```

---

Related documents:

- [Settings Reference](SETTINGS.md)
- [Usage Guide](USAGE.md)
- [README_EN](../../README_EN.md)
