"""把微信读书划线合并进首屏句子库。

用法
----
  1. 把你的微信读书 skill / 导出工具的结果整理成 static/quotes/wechat.yaml
     格式与 data/quotes.yaml 一致：
         - text: 划线原文
           source: 《书名》· 作者
  2. 预览：
         python tools/import_wechat_quotes.py --dry-run
  3. 合并：
         python tools/import_wechat_quotes.py

行为
----
  · 按 text 去重（与 data/quotes.yaml 里已有的比对，包括你手工加的）
  · 追加到 data/quotes.yaml 末尾，不改动已有条目与注释
  · 打印新增 / 跳过的条数

为什么不让工具直接生成 data/quotes.yaml：
  那个文件是你手工维护的，整份覆盖会丢掉你的注释和手写句子。
  工具只做「追加去重」这一件事。
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "static" / "quotes" / "wechat.yaml"
TARGET = ROOT / "data" / "quotes.yaml"


def parse_quotes(text):
    """解析 data/quotes.yaml 风格的内容，返回 [(text, source)]。

    只认顶层列表项，且忽略注释行 —— 与 Hugo 的 YAML 解析保持一致的语义。
    """
    items = []
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        m = re.match(r"^-\s*text:\s*(.*)$", stripped)
        if indent == 0 and m:
            if cur:
                items.append(cur)
            cur = [unquote(m.group(1)), ""]
            continue
        m = re.match(r"^source:\s*(.*)$", stripped)
        if cur is not None and m:
            cur[1] = unquote(m.group(1))
    if cur:
        items.append(cur)
    return [(t, s) for t, s in items if t.strip()]


def unquote(value):
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def to_yaml_block(text, source):
    """生成一条 YAML。含冒号等特殊字符时加引号。"""
    def q(value):
        if value == "":
            return '""'
        if re.search(r"[:#\[\]{}&*!|>'\"%@`]", value) or value != value.strip():
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return value

    lines = [f"- text: {q(text)}"]
    if source:
        lines.append(f"  source: {q(source)}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="把微信读书划线合并进 data/quotes.yaml")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    ap.add_argument("--source", default=str(SOURCE), help=f"输入文件（默认 {SOURCE}）")
    args = ap.parse_args()

    src = Path(args.source)
    if not src.is_absolute():
        src = ROOT / src

    if not src.exists():
        print(f"找不到输入文件：{src}")
        print("先让微信读书工具把划线写到这里，格式见 static/quotes/README.md")
        return 1

    if not TARGET.exists():
        print(f"找不到目标文件：{TARGET}")
        return 1

    incoming = parse_quotes(src.read_text(encoding="utf-8"))
    if not incoming:
        print(f"{src.name} 里没有解析到任何句子。")
        print("检查格式是否为：- text: 句子")
        return 1

    existing_text = TARGET.read_text(encoding="utf-8")
    existing = parse_quotes(existing_text)
    seen = {t.strip() for t, _ in existing}

    added, skipped = [], []
    for text, source in incoming:
        if text.strip() in seen:
            skipped.append(text)
            continue
        seen.add(text.strip())
        added.append((text, source))

    print(f"输入 {len(incoming)} 条 / 已有 {len(existing)} 条")
    print(f"  新增 {len(added)} 条，跳过重复 {len(skipped)} 条")
    if skipped:
        for t in skipped[:5]:
            print(f"    · 跳过：{t[:40]}")
        if len(skipped) > 5:
            print(f"    · …另有 {len(skipped) - 5} 条")

    if not added:
        print("\n没有新内容，文件未改动。")
        return 0

    if args.dry_run:
        print("\n--dry-run：以下内容会被追加，文件未改动。")
        for text, source in added[:10]:
            print("  " + to_yaml_block(text, source).replace("\n", "\n  "))
        if len(added) > 10:
            print(f"  …另有 {len(added) - 10} 条")
        return 0

    block = "\n".join(to_yaml_block(t, s) for t, s in added)
    body = existing_text.rstrip() + "\n\n"
    body += "# ---------------------------------------------------------------------------\n"
    body += "# 以下由 tools/import_wechat_quotes.py 从微信读书划线合并而来\n"
    body += "# ---------------------------------------------------------------------------\n\n"
    body += block + "\n"
    TARGET.write_text(body, encoding="utf-8")
    print(f"\n已写入 {TARGET.relative_to(ROOT)}，新增 {len(added)} 条。")
    print("接下来正常构建发布即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
