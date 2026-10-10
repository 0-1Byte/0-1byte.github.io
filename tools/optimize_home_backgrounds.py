#!/usr/bin/env python3
"""Generate and incrementally refresh responsive WebP homepage backgrounds."""

from __future__ import annotations

import hashlib
import json
import os
import warnings
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import PIL
from PIL import Image, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "static" / "home" / "backgrounds"
OUTPUT_DIR = ROOT / "static" / "home" / "backgrounds-optimized"
CACHE_DIR = ROOT / ".cache" / "homepage-backgrounds"
MANIFEST_PATH = CACHE_DIR / ".manifest.json"
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp"}
CONVERSION_VERSION = 3
QUALITY_LEVELS = (84, 80, 76, 72, 68)
VARIANTS = (
    {"name": "mobile", "size": (840, 1400), "quality": 82, "target": 150 * 1024, "min_scale": 0.6},
    {"name": "desktop", "size": (1920, 1280), "quality": 84, "target": 180 * 1024, "min_scale": 0.65},
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def settings_hash() -> str:
    settings = {
        "version": CONVERSION_VERSION,
        "quality_levels": QUALITY_LEVELS,
        "variants": VARIANTS,
        "encoder": {
            "format": "WEBP",
            "method": 6,
            "icc_profile": True,
            "pillow_version": PIL.__version__,
        },
    }
    packed = json.dumps(settings, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(packed).hexdigest()


def encode_webp(image: Image.Image, icc_profile: bytes | None, quality: int) -> bytes:
    buffer = BytesIO()
    options: dict[str, Any] = {"format": "WEBP", "quality": quality, "method": 6}
    if icc_profile:
        options["icc_profile"] = icc_profile
    image.save(buffer, **options)
    return buffer.getvalue()


def prepare_image(path: Path) -> tuple[Image.Image, bytes | None, tuple[int, int], str, bool]:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        dimensions = image.size
        image_format = source.format or path.suffix.lstrip(".").upper()
        has_alpha = "A" in image.getbands() or "transparency" in image.info
        converted = image.convert("RGBA" if has_alpha else "RGB")
        return converted.copy(), source.info.get("icc_profile"), dimensions, image_format, has_alpha


def mobile_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    aspect_ratio = size[0] / size[1]
    crop_width = min(image.width, round(image.height * aspect_ratio))
    crop_height = min(image.height, round(image.width / aspect_ratio))
    left = round((image.width - crop_width) * 0.54)
    top = (image.height - crop_height) // 2
    return image.crop((left, top, left + crop_width, top + crop_height))


def create_variant(
    source: Path,
    image: Image.Image,
    icc_profile: bytes | None,
    variant: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, tuple[int, int], int]:
    name = variant["name"]
    max_size = variant["size"]
    base = mobile_crop(image, max_size) if name == "mobile" else image
    preferred = variant["quality"]
    qualities = (preferred, *(quality for quality in QUALITY_LEVELS if quality < preferred))
    min_scale = variant["min_scale"]
    scale = 1.0
    best_effort: tuple[bytes, tuple[int, int], int] | None = None

    while True:
        target_size = (max(1, round(max_size[0] * scale)), max(1, round(max_size[1] * scale)))
        resized = base.copy()
        resized.thumbnail(
            target_size,
            getattr(Image, "Resampling", Image).LANCZOS
        )
        for quality in qualities:
            encoded = encode_webp(resized, icc_profile, quality)
            best_effort = (encoded, resized.size, quality)
            if len(encoded) <= variant["target"]:
                extension = source.suffix.lower().lstrip(".")
                destination = output_dir / f"{source.stem}--{extension}--{name}.webp"
                destination.write_bytes(encoded)
                return destination, resized.size, quality

        if scale <= min_scale:
            break
        scale = max(min_scale, scale * 0.9)

    assert best_effort is not None
    encoded, dimensions, quality = best_effort
    extension = source.suffix.lower().lstrip(".")
    destination = output_dir / f"{source.stem}--{extension}--{name}.webp"
    destination.write_bytes(encoded)
    return destination, dimensions, quality


def read_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        with manifest_path.open(encoding="utf-8") as file:
            manifest = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {"settings": None, "sources": {}}
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), dict):
        return {"settings": None, "sources": {}}
    return manifest


def write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, manifest_path)


def optimize_backgrounds(
    source_dir: Path,
    output_dir: Path,
    manifest_path: Optional[Path] = None,
) -> dict[str, Any]:
    if manifest_path is None:
        manifest_path = output_dir / ".manifest.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    sources = sorted(
        path for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_FORMATS
    )
    if not sources:
        raise SystemExit(f"No supported homepage backgrounds found in {source_dir}")

    settings = settings_hash()
    previous = read_manifest(manifest_path)
    previous_sources = previous.get("sources", {})
    valid_sources: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    reused = 0
    generated = 0

    for source in sources:
        try:
            source_hash = sha256_file(source)
            old_entry = previous_sources.get(source.name, {})
            if not isinstance(old_entry, dict):
                old_entry = {}
            cached_outputs = old_entry.get("outputs", {})
            variant_details = old_entry.get("variant_details", {})
            if (
                previous.get("settings") == settings
                and old_entry.get("sha256") == source_hash
                and isinstance(cached_outputs, dict)
                and isinstance(variant_details, dict)
                and set(cached_outputs)
                == {
                    f"{source.stem}--{source.suffix.lower().lstrip('.')}--{variant['name']}.webp"
                    for variant in VARIANTS
                }
                and set(variant_details)
                == {variant["name"] for variant in VARIANTS}
                and all(
                    (output_dir / name).is_file()
                    and sha256_file(output_dir / name) == expected_hash
                    for name, expected_hash in cached_outputs.items()
                )
            ):
                reused += len(cached_outputs)
                valid_sources[source.name] = old_entry
                for variant in VARIANTS:
                    output = output_dir / f"{source.stem}--{source.suffix.lower().lstrip('.')}--{variant['name']}.webp"
                    with Image.open(output) as result_image:
                        dimensions = result_image.size
                    results.append({
                        "source": source,
                        "output": output,
                        "variant": variant,
                        "dimensions": dimensions,
                        "quality": variant_details[variant["name"]]["quality"],
                        "alpha": old_entry["alpha"],
                    })
                continue

            image, icc_profile, original_dimensions, image_format, has_alpha = prepare_image(source)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            message = f"{source.name}: could not decode image ({error})"
            failures.append(message)
            warnings.warn(message, RuntimeWarning, stacklevel=1)
            continue

        output_hashes: dict[str, str] = {}
        variant_details: dict[str, dict[str, Any]] = {}
        for variant in VARIANTS:
            output, dimensions, quality = create_variant(source, image, icc_profile, variant, output_dir)
            output_hashes[output.name] = sha256_file(output)
            variant_details[variant["name"]] = {"dimensions": dimensions, "quality": quality}
            generated += 1
            results.append({
                "source": source,
                "output": output,
                "variant": variant,
                "dimensions": dimensions,
                "quality": quality,
                "alpha": has_alpha,
            })
        valid_sources[source.name] = {
            "sha256": source_hash,
            "outputs": output_hashes,
            "variant_details": variant_details,
            "original_dimensions": original_dimensions,
            "format": image_format,
            "alpha": has_alpha,
        }

    expected_outputs = {
        name for entry in valid_sources.values() for name in entry.get("outputs", {})
    }
    for output in output_dir.glob("*.webp"):
        if output.name not in expected_outputs:
            output.unlink()

    write_manifest(manifest_path, {"settings": settings, "sources": valid_sources})
    output_manifest = output_dir / ".manifest.json"
    if output_manifest != manifest_path and output_manifest.exists():
        output_manifest.unlink()
    output_manifest_temporary = output_dir / ".manifest.tmp"
    if output_manifest_temporary != manifest_path.with_suffix(".tmp") and output_manifest_temporary.exists():
        output_manifest_temporary.unlink()

    source_bytes = sum(source.stat().st_size for source in sources)
    source_count = len(sources)
    statistics: dict[str, dict[str, Any]] = {}
    for variant in VARIANTS:
        paths = [result["output"] for result in results if result["variant"]["name"] == variant["name"]]
        sizes = [path.stat().st_size for path in paths]
        original_bytes = sum(result["source"].stat().st_size for result in results if result["variant"]["name"] == variant["name"])
        statistics[variant["name"]] = {
            "count": len(paths),
            "total": sum(sizes),
            "average": round(sum(sizes) / len(sizes)) if sizes else 0,
            "largest": max(sizes, default=0),
            "largest_name": max(paths, key=lambda path: path.stat().st_size).name if paths else None,
            "over_target": sum(size > variant["target"] for size in sizes),
            "target": variant["target"],
            "source_bytes": original_bytes,
        }

    return {
        "source_count": source_count,
        "source_bytes": source_bytes,
        "sources": sources,
        "results": results,
        "failures": failures,
        "generated": generated,
        "reused": reused,
        "statistics": statistics,
    }


def report(result: dict[str, Any]) -> None:
    source_count = result["source_count"]
    source_bytes = result["source_bytes"]
    print(
        f"Homepage backgrounds: {source_count} raster sources ({source_bytes:,} bytes, "
        f"{source_bytes / source_count:,.0f} bytes average)."
    )
    print(f"Variants refreshed: {result['generated']}; reused from cache: {result['reused']}.")
    for name in ("mobile", "desktop"):
        stats = result["statistics"][name]
        reduction = (
            (1 - stats["total"] / stats["source_bytes"]) * 100
            if stats["source_bytes"] else 0
        )
        print(
            f"{name.title()}: {stats['count']} variants; total {stats['total']:,} bytes; "
            f"average {stats['average']:,}; largest {stats['largest']:,} bytes "
            f"({stats['largest_name'] or 'none'}); over {stats['target']:,}-byte target: "
            f"{stats['over_target']}; versus matching source images: {reduction:.1f}% smaller."
        )

    if result["failures"]:
        print(f"Skipped unreadable source images ({len(result['failures'])}):")
        for failure in result["failures"]:
            print(f"  - {failure}")
    else:
        print("Unreadable source images: none.")

    for item in result["results"]:
        source_size = item["source"].stat().st_size
        output_size = item["output"].stat().st_size
        dimensions = item["dimensions"]
        alpha = " with alpha" if item["alpha"] else ""
        quality = f", quality {item['quality']}" if item["quality"] is not None else ""
        print(
            f"  {item['source'].name}: {item['variant']['name']} {dimensions[0]}x"
            f"{dimensions[1]}{alpha}, {output_size:,} bytes from {source_size:,} bytes"
            f"{quality}"
        )

    exceptions = [
        item for item in result["results"]
        if item["output"].stat().st_size > item["variant"]["target"]
    ]
    if exceptions:
        print("Over-target image exceptions (retained at the best tested size/quality):")
        for item in exceptions:
            print(
                f"  - {item['source'].name} [{item['variant']['name']}]: "
                f"{item['output'].stat().st_size:,} bytes, {item['dimensions'][0]}x"
                f"{item['dimensions'][1]}, quality {item['quality']}"
            )
    else:
        print("Over-target image exceptions: none.")


def main() -> None:
    report(optimize_backgrounds(SOURCE_DIR, OUTPUT_DIR, MANIFEST_PATH))


if __name__ == "__main__":
    main()
