"""合集页封面优化入口：book / docu / film / tv / game（Music 见 optimize_music_covers.py）。

用法
----
    python tools/optimize_covers.py                # 处理全部合集页
    python tools/optimize_covers.py docu film      # 只处理指定页面
    python tools/optimize_covers.py --dry-run      # 只统计不写盘
    python tools/optimize_covers.py --avif         # 额外生成 AVIF
    python tools/optimize_covers.py --delete-unused # 顺带清理无引用的旧图

增量 + 幂等：已存在的衍生图会跳过，数据文件里已有的 img 会复用，
因此新增条目后重跑通常只需一两秒。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cover_opt import CollectionConfig, optimize  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# 衍生图按宽度生成并保持原始宽高比；240/320/480 档位覆盖常见的 1x/2x 显示尺寸。
COLLECTIONS = [
    CollectionConfig(
        key="book", label="Book",
        root=ROOT / "static" / "book",
        data_file=ROOT / "static" / "book" / "books.json",
        cover_dir=ROOT / "static" / "book" / "covers",
        derivative_dir=ROOT / "static" / "book" / "covers" / "opt",
        widths=(240, 320, 480),
    ),
    CollectionConfig(
        key="docu", label="Docu",
        root=ROOT / "static" / "docu",
        data_file=ROOT / "static" / "docu" / "docus.json",
        cover_dir=ROOT / "static" / "docu" / "covers",
        derivative_dir=ROOT / "static" / "docu" / "covers" / "opt",
        widths=(240, 320, 480),
    ),
    CollectionConfig(
        key="film", label="Film",
        root=ROOT / "static" / "film",
        data_file=ROOT / "static" / "film" / "films.json",
        cover_dir=ROOT / "static" / "film" / "covers",
        derivative_dir=ROOT / "static" / "film" / "covers" / "opt",
        widths=(240, 320, 480),
    ),
    CollectionConfig(
        key="tv", label="TV",
        root=ROOT / "static" / "tv",
        data_file=ROOT / "static" / "tv" / "tvs.json",
        cover_dir=ROOT / "static" / "tv" / "covers",
        derivative_dir=ROOT / "static" / "tv" / "covers" / "opt",
        widths=(240, 320, 480),
    ),
    CollectionConfig(
        key="game", label="Game",
        root=ROOT / "static" / "game",
        data_file=ROOT / "static" / "game" / "games.json",
        cover_dir=ROOT / "static" / "game" / "covers",
        derivative_dir=ROOT / "static" / "game" / "covers" / "opt",
        widths=(240, 320, 480),
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", help="只处理指定合集（默认全部）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--avif", action="store_true")
    ap.add_argument("--delete-unused", action="store_true")
    args = ap.parse_args()

    targets = [c for c in COLLECTIONS if not args.keys or c.key in args.keys]
    if not targets:
        print("没有匹配的合集：", ", ".join(c.key for c in COLLECTIONS), file=sys.stderr)
        return 1

    results = {}
    for cfg in targets:
        results[cfg.key] = optimize(cfg, dry_run=args.dry_run, avif=args.avif)

    if args.delete_unused:
        from urllib.parse import unquote
        print("\n清理无引用的旧图：")
        for cfg in targets:
            import json
            items = json.loads(cfg.data_file.read_text(encoding="utf-8"))
            used = set()
            for it in items:
                cover = it.get(cfg.key_field)
                if cover:
                    rel = unquote(cover)
                    for p in cfg.cover_prefixes:
                        if rel.startswith(p):
                            rel = rel[len(p):]
                            break
                    used.add(rel)
            unused = [p for p in sorted(cfg.cover_dir.iterdir())
                      if p.is_file() and p.name not in used]
            freed = sum(p.stat().st_size for p in unused)
            for p in unused:
                if not args.dry_run:
                    p.unlink()
            print(f"  [{cfg.label}] 删除 {len(unused)} 个，释放 {freed/1048576:.2f} MB")
            for p in unused[:5]:
                print(f"      - {p.name}")

    total_gen = sum(r.get("generated", 0) for r in results.values())
    total_changed = sum(r.get("changed", 0) for r in results.values())
    failed = [k for k, r in results.items() if not r.get("ok")]
    print("\n" + "=" * 68)
    print(f"合计：生成 {total_gen} 个档位，img 字段更新 {total_changed} 条")
    if failed:
        print("失败:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
