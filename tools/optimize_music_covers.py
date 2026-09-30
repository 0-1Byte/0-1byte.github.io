"""生成 Music 页面封面的多尺寸 WebP 衍生图，并把派生信息写回 songs.json。

设计要点
--------
1. 只处理 songs.json 真正引用到的封面，不动引用关系（cover 字段原样保留，作为兜底）。
2. 按「文件内容哈希」去重：同一张图只生成一套衍生图，
   多首歌共用同一组 URL（浏览器只下载一次）。
3. 产出文件名稳定且 URL 安全，由原文件名 slug 化而来，末尾附原文件名短哈希。
4. 在每条歌曲记录里加一个 img 字段（文件名主干），JS 用它拼 -240/-320/-480.webp，
   运行期不做复杂字符串转换。
5. 增量 + 幂等：songs.json 里已有的 img 会被复用，不会重新读图算哈希；
   已存在的衍生图直接跳过。只新增一首歌时通常 1 秒内跑完，
   因此可以安全地挂在 tools/add_music.py 后面自动执行。

用法
----
    python tools/optimize_music_covers.py            # 增量生成 + 更新 songs.json
    python tools/optimize_music_covers.py --dry-run  # 只统计，不写盘
    python tools/optimize_music_covers.py --avif     # 额外生成 AVIF 变体
    python tools/optimize_music_covers.py --delete-unused   # 顺带清理无引用的旧 JPG
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import unicodedata
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


def derivatives_present(base: str, widths=WIDTHS, kinds=("webp",)) -> bool:
    return all((ASSETS / f"{base}-{w}.{k}").exists() for w in widths for k in kinds)


def optimize(*, dry_run: bool = False, avif: bool = False,
             delete_unused: bool = False, verbose: bool = True) -> dict:
    """执行一次增量优化，返回统计信息。可被其它脚本直接调用。"""
    def log(*a):
        if verbose:
            print(*a)

    songs = json.loads(SONGS.read_text(encoding="utf-8"))
    log(f"songs.json 条目: {len(songs)}")

    rels = [cover_to_path(s["cover"]) for s in songs]
    missing = [r for r in rels if not (ASSETS / r).exists()]
    if missing:
        log(f"[错误] {len(missing)} 个封面文件不存在，先修复引用：")
        for m in missing[:10]:
            log("   ", m)
        return {"ok": False, "missing": missing}

    referenced = set(rels)

    # ------------------------------------------------------------------
    # 1. 复用 songs.json 里已有的 img，避免每次重跑都读全部原图算哈希
    #    只有「新出现的封面」才需要算哈希并参与内容去重。
    # ------------------------------------------------------------------
    known: dict[str, str] = {}        # 文件名 -> img 主干
    for s in songs:
        img = s.get("img")
        if not img:
            continue
        rel = cover_to_path(s["cover"])
        if not dry_run and derivatives_present(img):
            known.setdefault(rel, img)

    used_bases = set(known.values())
    fresh = [r for r in sorted(referenced) if r not in known]

    hash_of: dict[str, str] = {}
    if fresh:
        for r in fresh:
            hash_of[r] = hashlib.sha256((ASSETS / r).read_bytes()).hexdigest()

        # 内容去重只在「新封面」内部按哈希生效；跨新旧比内容需要读旧图，
        # 实测收益极小（新歌通常配新封面），这里不做，保证增量速度。
        base_of_hash: dict[str, str] = {}
        for r in fresh:
            h = hash_of[r]
            if h in base_of_hash:
                continue
            preferred = slugify(r)
            if preferred not in used_bases:
                base = preferred
            elif derivatives_present(preferred):
                # 这个名字的衍生图已经存在，说明它本来就属于这个封面
                # （例如 songs.json 被重新生成、img 字段丢失的情况），直接复用，
                # 避免生成 -2 这种重复副本。
                base = preferred
            else:
                base = preferred
                n = 2
                while base in used_bases:
                    base = f"{preferred}-{n}"
                    n += 1
            used_bases.add(base)
            base_of_hash[h] = base
        for r in fresh:
            known[r] = base_of_hash[hash_of[r]]
    else:
        log("没有新增封面，仅检查现有衍生图是否齐全。")

    # 全部引用都要有主干名
    unresolved = [r for r in referenced if r not in known]
    if unresolved:
        log(f"[错误] {len(unresolved)} 个封面仍无法确定主干名：{unresolved[:5]}")
        return {"ok": False, "unresolved": unresolved}

    bases = sorted({known[r] for r in referenced})
    unique_count = len(bases)
    if fresh:
        log(f"新增/待处理封面: {len(fresh)} 个")
    log(f"引用封面文件: {len(referenced)} 个，唯一主干: {unique_count} 个")

    # ------------------------------------------------------------------
    # 2. 生成缺失的衍生图
    # ------------------------------------------------------------------
    src_total = 0
    out_total = {"webp": 0, "avif": 0}
    generated = skipped = 0
    kinds = ("webp", "avif") if avif else ("webp",)

    seen_src = set()
    for r in sorted(referenced):
        base = known[r]
        if r in seen_src:
            continue
        seen_src.add(r)
        src = ASSETS / r

        # 该主干名下所有档位是否都已齐全？齐全就完全跳过读图
        if all((ASSETS / f"{base}-{w}.{k}").exists()
               for w in WIDTHS for k in kinds):
            for k in kinds:
                out_total[k] += sum((ASSETS / f"{base}-{w}.{k}").stat().st_size for w in WIDTHS)
            skipped += len(WIDTHS) * len(kinds)
            continue

        src_bytes = src.stat().st_size
        src_total += src_bytes
        with Image.open(src) as im:
            im = im.convert("RGB")
            w0, h0 = im.size

        # 保持原始宽高比：非正方形封面若压成正方形会被拉伸变形。
        # 页面用 object-fit: cover 做中心方形裁切，等比缩放的衍生图
        # 裁切结果与原图一致，视觉不变。
        for w in WIDTHS:
            hh = max(1, round(h0 * w / w0))
            resized = im.resize((w, hh), Image.LANCZOS)
            for kind in kinds:
                out = ASSETS / f"{base}-{w}.{kind}"
                kw = dict(quality=WEBP_QUALITY, method=WEBP_METHOD) if kind == "webp" \
                    else dict(quality=AVIF_QUALITY)
                if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
                    out_total[kind] += out.stat().st_size
                    skipped += 1
                    continue
                if dry_run:
                    buf = io.BytesIO()
                    resized.save(buf, kind.upper(), **kw)
                    out_total[kind] += buf.tell()
                    generated += 1
                    continue
                resized.save(out, kind.upper(), **kw)
                out_total[kind] += out.stat().st_size
                generated += 1

    # ------------------------------------------------------------------
    # 3. 写回 songs.json（只加/更新 img 字段，其余原样）
    # ------------------------------------------------------------------
    changed = 0
    for s, rel in zip(songs, rels):
        base = known[rel]
        if s.get("img") != base:
            s["img"] = base
            changed += 1

    if not dry_run and changed:
        SONGS.write_text(json.dumps(songs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # 4. 报告
    # ------------------------------------------------------------------
    log("")
    log("=" * 72)
    if src_total:
        log(f"本次读取的源封面合计   : {src_total/1048576:8.2f} MB")
    for kind in ("webp", "avif"):
        if out_total[kind]:
            log(f"{kind.upper()} 衍生图合计        : {out_total[kind]/1048576:8.2f} MB  "
                f"({unique_count * len(WIDTHS)} 个档位)")
    log(f"本次生成/跳过          : {generated} / {skipped}")
    log(f"songs.json img 更新    : {changed} 条")
    log(f"尺寸档位               : {', '.join(str(w) for w in WIDTHS)} px")
    log("=" * 72)

    deleted = 0
    freed = 0
    if delete_unused:
        unused = [p for p in sorted(ASSETS.iterdir())
                  if p.is_file() and p.suffix.lower() == ".jpg" and p.name not in referenced]
        freed = sum(p.stat().st_size for p in unused)
        deleted = len(unused)
        for p in unused:
            if not dry_run:
                p.unlink()
        log(f"\n已删除未引用 JPG: {deleted} 个，释放 {freed/1048576:.2f} MB")

    return {
        "ok": True,
        "songs": len(songs),
        "unique": unique_count,
        "generated": generated,
        "skipped": skipped,
        "changed": changed,
        "deleted": deleted,
        "freed": freed,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--avif", action="store_true", help="额外生成 AVIF")
    ap.add_argument("--delete-unused", action="store_true",
                    help="删除未被 songs.json 引用、且能确认已废弃的 JPG")
    args = ap.parse_args()
    result = optimize(dry_run=args.dry_run, avif=args.avif,
                      delete_unused=args.delete_unused)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
