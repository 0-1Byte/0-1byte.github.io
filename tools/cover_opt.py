"""合集页封面优化：多尺寸 WebP 生成 + 增量更新数据文件。

被 tools/optimize_covers.py 调用，负责所有「JSON 数据 + covers 目录」
型页面（book / docu / film / tv / game）。

与 Music 版（tools/optimize_music_covers.py）的关系
------------------------------------------------
Music 版本的逻辑、参数、命名、幂等性都已经过实测验证并已上线，
本模块是从它抽取出来的通用实现，保持完全相同的算法：
  · 按文件内容哈希去重（同一张图只生成一套衍生图）
  · slugify 生成稳定、URL 安全的文件名主干
  · 增量执行：复用数据文件里已有的 img 字段，只处理新封面
  · 保持原始宽高比（避免缩放封面时发生拉伸变形）

产出存放在 covers/opt/ 下，命名 {主干}-{宽度}.webp。
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from PIL import Image

# 质量档与 Music 一致，理由见 optimize_music_covers.py 的注释。
WEBP_QUALITY = 82
WEBP_METHOD = 6
AVIF_QUALITY = 60


@dataclass
class CollectionConfig:
    """一个合集页的配置。"""
    key: str                              # 短名，用于日志
    root: Path                            # 例如 static/docu
    data_file: Path                       # 例如 static/docu/docus.json
    cover_dir: Path                       # 例如 static/docu/covers
    derivative_dir: Path                  # 例如 static/docu/covers/opt
    widths: tuple = (240, 320, 480)
    # 合集页封面是 2:3 竖版；四列时显示约 235x353，2x 屏需要 470 宽
    cover_prefixes: tuple = ("covers/", "./covers/", "covers\\")
    key_field: str = "cover"
    img_field: str = "img"
    label: str = ""

    def __post_init__(self):
        if not self.label:
            self.label = self.key


def slugify(name: str) -> str:
    """把封面文件名转成稳定、URL 安全的文件名主干。

    保留中日韩字符（URL 里百分号编码可正常寻址），其余非 ASCII 剥离；
    末尾附原文件名的短哈希，保证唯一且可重复生成。
    """
    stem = Path(name).stem
    stem = unicodedata.normalize("NFKD", stem)
    stem = stem.lower()
    stem = re.sub(r"[’'\"`]", "", stem)
    stem = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", stem)
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    if not stem:
        stem = "cover"
    return f"{stem}-{digest}"


def cover_to_rel(cfg: CollectionConfig, cover: str) -> str:
    """把数据文件里的 cover 值转成相对 covers 目录的文件名。"""
    rel = unquote(cover)
    for prefix in cfg.cover_prefixes:
        if rel.startswith(prefix):
            return rel[len(prefix):]
    return rel


def is_remote(cover: str) -> bool:
    """第三方 URL（如 douban CDN）的封面无法在本地生成衍生图，单独跳过。

    这类条目保持原样：JS 会退回直接使用远程 URL，页面照常显示，
    只是拿不到 WebP 的体积收益。
    """
    return bool(re.match(r"^(https?:)?//", cover or ""))


def derivatives_present(cfg: CollectionConfig, base: str, kinds=("webp",)) -> bool:
    return all((cfg.derivative_dir / f"{base}-{w}.{k}").exists()
               for w in cfg.widths for k in kinds)


def optimize(cfg: CollectionConfig, *, dry_run: bool = False, avif: bool = False,
             verbose: bool = True) -> dict:
    """对一个合集页执行增量封面优化，返回统计信息。"""
    def log(*a):
        if verbose:
            print(*a)

    items = json.loads(cfg.data_file.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        log(f"[错误] {cfg.data_file} 不是数组")
        return {"ok": False, "reason": "not-a-list"}

    rels = []
    skipped_remote = []
    for it in items:
        cover = it.get(cfg.key_field)
        if not cover:
            continue
        if is_remote(cover):
            skipped_remote.append(it.get("title") or it.get("id") or cover)
            continue
        rels.append(cover_to_rel(cfg, cover))

    if skipped_remote:
        log(f"跳过 {len(skipped_remote)} 个远程封面（无法本地优化，页面仍会直接加载）："
            + "、".join(str(t) for t in skipped_remote[:4]))

    missing = [r for r in rels if not (cfg.cover_dir / r).exists()]
    if missing:
        log(f"[错误] {len(missing)} 个封面文件不存在：{missing[:5]}")
        return {"ok": False, "missing": missing}

    referenced = set(rels)
    kinds = ("webp", "avif") if avif else ("webp",)
    if not dry_run and not cfg.derivative_dir.exists() and referenced:
        cfg.derivative_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 复用数据文件里已有的 img，避免每次重跑都读全部原图算哈希
    # ------------------------------------------------------------------
    known: dict[str, str] = {}
    for it in items:
        img = it.get(cfg.img_field)
        cover = it.get(cfg.key_field)
        if not img or not cover:
            continue
        rel = cover_to_rel(cfg, cover)
        if not dry_run and derivatives_present(cfg, img, kinds):
            known.setdefault(rel, img)

    used_bases = set(known.values())
    fresh = [r for r in sorted(referenced) if r not in known]

    hash_of: dict[str, str] = {}
    if fresh:
        for r in fresh:
            hash_of[r] = hashlib.sha256((cfg.cover_dir / r).read_bytes()).hexdigest()

        base_of_hash: dict[str, str] = {}
        for r in fresh:
            h = hash_of[r]
            if h in base_of_hash:
                continue
            preferred = slugify(r)
            if preferred not in used_bases or derivatives_present(cfg, preferred, kinds):
                # 名字空闲，或该名字的衍生图本来就属于这个封面
                # （数据文件被重新生成、img 字段丢失时），直接复用
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

    unresolved = [r for r in referenced if r not in known]
    if unresolved:
        log(f"[错误] {len(unresolved)} 个封面无法确定主干名：{unresolved[:5]}")
        return {"ok": False, "unresolved": unresolved}

    bases = sorted({known[r] for r in referenced})
    if fresh:
        log(f"新增/待处理封面: {len(fresh)} 个")
    log(f"引用封面文件: {len(referenced)} 个，唯一主干: {len(bases)} 个")

    # ------------------------------------------------------------------
    # 生成缺失的衍生图
    # ------------------------------------------------------------------
    src_total = 0
    out_total = {k: 0 for k in kinds}
    generated = skipped = 0

    seen = set()
    for r in sorted(referenced):
        base = known[r]
        if r in seen:
            continue
        seen.add(r)

        if all((cfg.derivative_dir / f"{base}-{w}.{k}").exists()
               for w in cfg.widths for k in kinds):
            for k in kinds:
                out_total[k] += sum((cfg.derivative_dir / f"{base}-{w}.{k}").stat().st_size
                                    for w in cfg.widths)
            skipped += len(cfg.widths) * len(kinds)
            continue

        src = cfg.cover_dir / r
        src_total += src.stat().st_size
        with Image.open(src) as im:
            im = im.convert("RGB")
            w0, h0 = im.size

        # 保持原始宽高比：2:3 竖版封面压成正方形会被拉伸变形。
        # 页面用 object-fit: cover 做中心裁切，等比缩放的衍生图裁切结果与原图一致。
        for w in cfg.widths:
            hh = max(1, round(h0 * w / w0))
            resized = im.resize((w, hh), Image.LANCZOS)
            for kind in kinds:
                out = cfg.derivative_dir / f"{base}-{w}.{kind}"
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
    # 写回数据文件（只加/更新 img 字段，其余原样）
    # ------------------------------------------------------------------
    changed = 0
    for it in items:
        cover = it.get(cfg.key_field)
        if not cover or is_remote(cover):
            continue
        rel = cover_to_rel(cfg, cover)
        base = known.get(rel)
        if base and it.get(cfg.img_field) != base:
            it[cfg.img_field] = base
            changed += 1

    if not dry_run and changed:
        cfg.data_file.write_text(
            json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    log("")
    log("-" * 68)
    log(f"[{cfg.label}] 条目 {len(items)}  唯一封面 {len(bases)}"
        + (f"  远程跳过 {len(skipped_remote)}" if skipped_remote else ""))
    if src_total:
        log(f"  本次读取源封面 : {src_total/1048576:7.2f} MB")
    for k in kinds:
        if out_total[k]:
            log(f"  {k.upper()} 衍生图合计 : {out_total[k]/1048576:7.2f} MB "
                f"({len(bases) * len(cfg.widths)} 个档位)")
    log(f"  本次生成/跳过  : {generated} / {skipped}")
    log(f"  img 字段更新   : {changed} 条")

    return {
        "ok": True, "items": len(items), "unique": len(bases),
        "generated": generated, "skipped": skipped, "changed": changed,
        "src_total": src_total, "out_total": out_total,
        "remote_skipped": len(skipped_remote),
    }


def run_after_add(key: str) -> None:
    """加条目脚本的统一收尾钩子：只刷新指定合集的封面衍生图。

    增量执行（已存在的档位直接跳过），新增一两条通常 1~2 秒。
    任何异常都只打警告 —— 图片优化绝不能影响加数据本身。
    """
    import sys as _sys
    try:
        spec = importlib.util.spec_from_file_location(
            "optimize_covers", Path(__file__).resolve().parent / "optimize_covers.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = next((c for c in module.COLLECTIONS if c.key == key), None)
        if config is None:
            print("[cover] 没有名为 {} 的合集配置，跳过封面优化。".format(key), file=_sys.stderr)
            return
        print()
        print("正在生成 {} 封面 WebP 衍生图 ...".format(config.label))
        result = optimize(config, verbose=False)
        if result.get("ok"):
            remote = result.get("remote_skipped", 0)
            print("封面衍生图已就绪：生成 {} 个，跳过 {} 个，img 字段更新 {} 条{}。".format(
                result["generated"], result["skipped"], result["changed"],
                "，远程封面跳过 {} 个".format(remote) if remote else ""))
        else:
            print("封面衍生图未全部生成，可手动运行 python tools/optimize_covers.py 排查。",
                  file=_sys.stderr)
    except Exception as error:  # noqa: BLE001
        print("封面衍生图生成失败（不影响本次数据更新）：{}".format(error), file=_sys.stderr)
        print("可手动运行 python tools/optimize_covers.py 重试。", file=_sys.stderr)
