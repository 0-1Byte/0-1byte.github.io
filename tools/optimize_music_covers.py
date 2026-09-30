"""生成 Music 页面封面的多尺寸 WebP 衍生图，并把派生信息写回 songs.json。

设计要点
--------
1. 只处理 songs.json 真正引用到的封面，不动引用关系（cover 字段原样保留，作为兜底）。
2. 按「文件内容哈希」去重：213 首歌里只有约 100 张不同的图，
   同一张图只生成一套衍生图，多首歌共用同一组 URL（浏览器只下载一次）。
3. 产出文件名稳定且 URL 安全（无空格、无中文、无百分号编码），由原文件名 slug 化而来。
4. 在每条歌曲记录里加一个 img 字段（文件名主干），JS 用它拼 -240/-320/-480.webp，
   运行期不做复杂字符串转换。
5. 幂等：重复执行结果一致；已存在且最新的衍生图会跳过。

用法
----
    python tools/optimize_music_covers.py            # 生成 + 更新 songs.json
    python tools/optimize_music_covers.py --dry-run  # 只统计，不写盘
    python tools/optimize_music_covers.py --avif     # 额外生成 AVIF 变体
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MUSIC = ROOT / "static" / "music"
ASSETS = MUSIC / "assets"
SONGS = MUSIC / "songs.json"

WIDTHS = (240, 320, 480)
# 质量档为实测选定：在细节密集的封面上，q78→q90 仅提升 0.1~0.3dB
# （瓶颈是源 JPG 自身的压缩痕迹，再高的码率也换不回清晰度），体积却近乎翻倍；
# q82 在其余封面上能稳定 +0.5~1dB，总增量约 13%，性价比最高。
# 复核画质用 tools/verify_music_covers.py。
WEBP_QUALITY = 82
WEBP_METHOD = 6          # 6 = 最高压缩档，离线生成，慢一点无妨
AVIF_QUALITY = 60
SRC_PREFIXES = ("/music/assets/", "/music/", "assets/")


def slugify(name: str) -> str:
    """把封面文件名转成稳定、URL 安全的文件名主干。

    保留中日韩字符（URL 里百分号编码可正常寻址，浏览器也认），
    其余非 ASCII 字符剥离；末尾附原文件名的短哈希，保证唯一且可重复生成。
    """
    stem = Path(name).stem
    stem = unicodedata.normalize("NFKD", stem)
    stem = stem.lower()
    stem = re.sub(r"[’'\"`]", "", stem)                    # 撇号直接去掉：don't -> dont
    stem = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", stem)   # 其余转连字符（保留中日韩）
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    if not stem:
        stem = "cover"
    return f"{stem}-{digest}"


def cover_to_path(cover: str) -> str:
    rel = cover
    for prefix in SRC_PREFIXES:
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
            break
    return unquote(rel)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--avif", action="store_true", help="额外生成 AVIF")
    ap.add_argument("--delete-unused", action="store_true",
                    help="删除未被 songs.json 引用、且能确认已废弃的 JPG")
    args = ap.parse_args()

    songs = json.loads(SONGS.read_text(encoding="utf-8"))
    print(f"songs.json 条目: {len(songs)}")

    # --- 1. 建立 引用文件 -> 内容哈希 / 主干名 ---
    rels = [cover_to_path(s["cover"]) for s in songs]
    missing = [r for r in rels if not (ASSETS / r).exists()]
    if missing:
        print(f"[错误] {len(missing)} 个封面文件不存在，先修复引用：")
        for m in missing[:10]:
            print("   ", m)
        return 1

    hash_of: dict[str, str] = {}
    for r in set(rels):
        hash_of[r] = hashlib.sha256((ASSETS / r).read_bytes()).hexdigest()

    # 同一内容只保留一个代表文件，衍生图只生成一次
    rep_of_hash: dict[str, str] = {}
    for r in sorted(set(rels)):
        rep_of_hash.setdefault(hash_of[r], r)

    unique_hashes = len(rep_of_hash)
    print(f"引用封面文件: {len(set(rels))} 个，其中内容唯一: {unique_hashes} 张"
          f"（重复 {len(set(rels)) - unique_hashes} 个文件是同一张图）")

    # 主干名：按「内容」分配，保证同图同名
    base_of_hash: dict[str, str] = {}
    used_bases: set[str] = set()
    for h, rep in sorted(rep_of_hash.items(), key=lambda kv: kv[1]):
        base = slugify(rep)
        n = 2
        while base in used_bases:
            base = f"{slugify(rep)}-{n}"
            n += 1
        used_bases.add(base)
        base_of_hash[h] = base

    # --- 2. 生成衍生图 ---
    src_total = 0
    out_total = {"webp": 0, "avif": 0}
    generated = skipped = 0
    biggest_src = 0

    for h, rep in sorted(rep_of_hash.items(), key=lambda kv: kv[1]):
        src = ASSETS / rep
        src_bytes = src.stat().st_size
        src_total += src_bytes
        biggest_src = max(biggest_src, src_bytes)
        base = base_of_hash[h]

        with Image.open(src) as im:
            im = im.convert("RGB")
            w0, h0 = im.size

        # 保持原始宽高比：非正方形封面若压成正方形会被拉伸变形。
        # 页面用 object-fit: cover 做中心方形裁切，等比缩放的衍生图
        # 裁切结果与原图一致，视觉不变。
        for w in WIDTHS:
            hh = max(1, round(h0 * w / w0))
            resized = im.resize((w, hh), Image.LANCZOS)

            targets = [("webp", f"{base}-{w}.webp", dict(quality=WEBP_QUALITY, method=WEBP_METHOD))]
            if args.avif:
                targets.append(("avif", f"{base}-{w}.avif", dict(quality=AVIF_QUALITY)))

            for kind, fname, kw in targets:
                out = ASSETS / fname
                if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
                    out_total[kind] += out.stat().st_size
                    skipped += 1
                    continue
                if args.dry_run:
                    import io
                    buf = io.BytesIO()
                    resized.save(buf, kind.upper(), **kw)
                    out_total[kind] += buf.tell()
                    generated += 1
                    continue
                resized.save(out, kind.upper(), **kw)
                out_total[kind] += out.stat().st_size
                generated += 1

    # --- 3. 写回 songs.json（只加 img 字段，其余原样）---
    changed = 0
    for s, rel in zip(songs, rels):
        base = base_of_hash[hash_of[rel]]
        if s.get("img") != base:
            s["img"] = base
            changed += 1

    if not args.dry_run:
        SONGS.write_text(json.dumps(songs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # --- 4. 报告 ---
    print()
    print("=" * 72)
    print(f"源封面（内容唯一）合计 : {src_total/1048576:8.2f} MB  ({unique_hashes} 张)")
    for kind in ("webp", "avif"):
        if out_total[kind]:
            print(f"{kind.upper()} 衍生图合计        : {out_total[kind]/1048576:8.2f} MB  "
                  f"({unique_hashes * len(WIDTHS)} 个文件, {len(WIDTHS)} 种尺寸)")
    if out_total["webp"]:
        print(f"相对源图减少           : {(1 - out_total['webp']/src_total)*100:8.1f}%  (仅比 webp)")
    print(f"本次生成/跳过          : {generated} / {skipped}")
    print(f"songs.json img 字段更新 : {changed} 条")
    print(f"尺寸档位               : {', '.join(str(w) for w in WIDTHS)} px")
    print("=" * 72)

    if args.delete_unused:
        referenced = set(rels)
        unused = [p for p in sorted(ASSETS.iterdir())
                  if p.is_file() and p.suffix.lower() == ".jpg" and p.name not in referenced]
        freed = sum(p.stat().st_size for p in unused)
        for p in unused:
            if not args.dry_run:
                p.unlink()
        print(f"\n已删除未引用 JPG: {len(unused)} 个，释放 {freed/1048576:.2f} MB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
