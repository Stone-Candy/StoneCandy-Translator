from dataclasses import dataclass

from PIL import Image

from .image_modes import normalize_rgb_image

_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


@dataclass(frozen=True)
class SquareImageRestoreInfo:
    original_width: int
    original_height: int
    padded_width: int
    padded_height: int
    offset_x: int
    offset_y: int

    @property
    def original_size(self) -> tuple[int, int]:
        return self.original_width, self.original_height


def normalize_ai_image(image: Image.Image) -> Image.Image:
    return normalize_rgb_image(image)


def prepare_square_ai_image(
    image: Image.Image,
    background_color: tuple[int, int, int] = (255, 255, 255),
) -> tuple[Image.Image, SquareImageRestoreInfo]:
    image = normalize_ai_image(image)
    width, height = image.size
    side = max(width, height)
    offset_x = (side - width) // 2
    offset_y = (side - height) // 2

    if side == width and side == height:
        return image, SquareImageRestoreInfo(
            original_width=width,
            original_height=height,
            padded_width=width,
            padded_height=height,
            offset_x=0,
            offset_y=0,
        )

    square_image = Image.new("RGB", (side, side), background_color)
    square_image.paste(image, (offset_x, offset_y))
    return square_image, SquareImageRestoreInfo(
        original_width=width,
        original_height=height,
        padded_width=side,
        padded_height=side,
        offset_x=offset_x,
        offset_y=offset_y,
    )


def restore_square_ai_image(image: Image.Image, restore_info: SquareImageRestoreInfo) -> Image.Image:
    image = normalize_ai_image(image)
    if image.size == restore_info.original_size and restore_info.offset_x == 0 and restore_info.offset_y == 0:
        return image

    left = _scale_edge(restore_info.offset_x, image.width, restore_info.padded_width)
    top = _scale_edge(restore_info.offset_y, image.height, restore_info.padded_height)
    right = _scale_edge(
        restore_info.offset_x + restore_info.original_width,
        image.width,
        restore_info.padded_width,
    )
    bottom = _scale_edge(
        restore_info.offset_y + restore_info.original_height,
        image.height,
        restore_info.padded_height,
    )

    left = min(max(left, 0), max(image.width - 1, 0))
    top = min(max(top, 0), max(image.height - 1, 0))
    right = min(max(right, left + 1), image.width)
    bottom = min(max(bottom, top + 1), image.height)

    cropped = image.crop((left, top, right, bottom))
    if cropped.size != restore_info.original_size:
        cropped = cropped.resize(restore_info.original_size, _LANCZOS)
    return cropped


def _scale_edge(edge: int, current_size: int, reference_size: int) -> int:
    if reference_size <= 0:
        return edge
    return int(round(edge * current_size / reference_size))
