#!/usr/bin/env python3
"""Generate desktop/mobile WebP derivatives for homepage background images."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "static" / "home" / "backgrounds"
OUTPUT_DIR = ROOT / "static" / "home" / "backgrounds-optimized"
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp"}
VARIANTS = (("mobile", (840, 1400), 80), ("desktop", (1920, 1280), 84))
QUALITY_FALLBACKS = (84, 80, 76)
TARGET_BYTES = 180 * 1024


def encode_webp(image: Image.Image, icc_profile: bytes | None, quality: int) -> bytes:
    buffer = BytesIO()
    options = {"format": "WEBP", "quality": quality, "method": 6}
    if icc_profile:
        options["icc_profile"] = icc_profile
    image.save(buffer, **options)
    return buffer.getvalue()


def prepare_image(path: Path) -> tuple[Image.Image, bytes | None, tuple[int, int], str]:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        dimensions = image.size
        image_format = source.format or path.suffix.lstrip(".").upper()
        has_alpha = "A" in image.getbands() or "transparency" in image.info
        image = image.convert("RGBA" if has_alpha else "RGB")
        return image.copy(), source.info.get("icc_profile"), dimensions, image_format


def create_variant(
    source: Path,
    image: Image.Image,
    icc_profile: bytes | None,
    name: str,
    max_size: tuple[int, int],
    preferred_quality: int,
) -> Path:
    qualities = [preferred_quality, *(quality for quality in QUALITY_FALLBACKS if quality < preferred_quality)]
    max_dimension = max(max_size)
    min_dimension = max(640, max_dimension * 2 // 3)
    dimension = max_dimension
    while True:
        if name == "mobile":
            aspect_ratio = max_size[0] / max_size[1]
            crop_width = min(image.width, round(image.height * aspect_ratio))
            crop_height = min(image.height, round(image.width / aspect_ratio))
            left = round((image.width - crop_width) * 0.54)
            top = (image.height - crop_height) // 2
            variant = image.crop((left, top, left + crop_width, top + crop_height))
            target_width = min(max_size[0], round(dimension * aspect_ratio))
            target_height = min(max_size[1], dimension)
            variant.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
        else:
            variant = image.copy()
            scale = dimension / max_dimension
            target_size = (round(max_size[0] * scale), round(max_size[1] * scale))
            variant.thumbnail(target_size, Image.Resampling.LANCZOS)
        encoded = b""
        for quality in qualities:
            encoded = encode_webp(variant, icc_profile, quality)
            if len(encoded) <= TARGET_BYTES or quality == qualities[-1]:
                break
        if len(encoded) <= TARGET_BYTES or dimension <= min_dimension:
            break
        dimension = max(min_dimension, int(dimension * 0.9))

    extension = source.suffix.lower().lstrip(".")
    destination = OUTPUT_DIR / f"{source.stem}--{extension}--{name}.webp"
    destination.write_bytes(encoded)
    return destination


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT_DIR.glob("*.webp"):
        stale.unlink()

    sources = sorted(
        path for path in SOURCE_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_FORMATS
    )
    if not sources:
        raise SystemExit(f"No supported homepage backgrounds found in {SOURCE_DIR}")

    results: list[tuple[Path, tuple[int, int], str, Path, Path]] = []
    for source in sources:
        image, icc_profile, dimensions, image_format = prepare_image(source)
        mobile = create_variant(source, image, icc_profile, *VARIANTS[0])
        desktop = create_variant(source, image, icc_profile, *VARIANTS[1])
        results.append((source, dimensions, image_format, mobile, desktop))

    source_bytes = sum(source.stat().st_size for source in sources)
    mobile_outputs = [mobile for _, _, _, mobile, _ in results]
    desktop_outputs = [desktop for _, _, _, _, desktop in results]
    outputs = mobile_outputs + desktop_outputs
    mobile_bytes = sum(path.stat().st_size for path in mobile_outputs)
    desktop_bytes = sum(path.stat().st_size for path in desktop_outputs)
    output_bytes = mobile_bytes + desktop_bytes
    largest = max(outputs, key=lambda path: path.stat().st_size)
    largest_source = max(sources, key=lambda path: path.stat().st_size)
    average_source = source_bytes / len(sources)

    print(
        f"Homepage backgrounds: {len(sources)} sources ({source_bytes:,} bytes); "
        f"average {average_source:,.0f} bytes, largest {largest_source.name} "
        f"({largest_source.stat().st_size:,} bytes)."
    )
    print(
        f"{len(outputs)} WebP variants: {mobile_bytes:,} mobile + "
        f"{desktop_bytes:,} desktop = {output_bytes:,} bytes."
    )
    print(
        f"Largest variant: {largest.name} ({largest.stat().st_size:,} bytes); "
        f"target per variant: <= {TARGET_BYTES:,} bytes when quality permits."
    )
    for source, dimensions, image_format, mobile, desktop in results:
        with Image.open(mobile) as mobile_image, Image.open(desktop) as desktop_image:
            mobile_dimensions = mobile_image.size
            desktop_dimensions = desktop_image.size
        print(
            f"{source.name}: {image_format} {dimensions[0]}x{dimensions[1]}, "
            f"{source.stat().st_size:,} bytes original; "
            f"{mobile_dimensions[0]}x{mobile_dimensions[1]} mobile "
            f"{mobile.stat().st_size:,} bytes; "
            f"{desktop_dimensions[0]}x{desktop_dimensions[1]} desktop "
            f"{desktop.stat().st_size:,} bytes"
        )


if __name__ == "__main__":
    main()
