"""把仓库里（工作区 + 全部 git 对象）出现的任何真实 Key 替换成占位符。

为什么需要它：真实的 Key 曾被误填进 .secrets/key.example.yaml，
而那个文件是**刻意入库**的模板 —— 于是完整 Key 进了 git 历史。

用法：
    python tools/weread_scrub.py            # 只报告
    python tools/weread_scrub.py --apply    # 实际替换（会改写所有分支的历史）
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "在这里填 wrk- 开头的 Key"

# 真实 Key：wrk- 后面跟足够长的随机串
# 排除明显的占位符（全同字符、示例词）
KEY = re.compile(r"wrk-[A-Za-z0-9_\-]{16,}")
PLACEHOLDERISH = re.compile(r"wrk-([A-Za-z])\1{5,}", re.I)
WORDS = ("yourkey", "your_key", "example", "testkey", "here")


def is_fake(token):
    body = token[4:].lower()
    if any(w in body for w in WORDS):
        return True
    if PLACEHOLDERISH.match(token):
        return True
    return False


def real_keys(text):
    return sorted({t for t in KEY.findall(text or "") if not is_fake(t)})


def run(args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def scan_worktree():
    hits = {}
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith((".git/", "public/", "themes/")):
            continue
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico",
                                ".woff", ".woff2", ".mp3"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        found = real_keys(text)
        if found:
            hits[rel] = found
    return hits


def scan_history():
    """返回 {commit: [keys]}，按提交逐个查。"""
    r = run(["git", "log", "--all", "--pretty=format:%H"])
    commits = [c for c in r.stdout.split("\n") if c.strip()]
    hits = {}
    for c in commits:
        d = run(["git", "show", c, "--pretty=format:", "-p"])
        found = real_keys(d.stdout)
        if found:
            hits[c] = found
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际替换并改写历史")
    args = ap.parse_args()

    print("=" * 78)
    print("1. 工作区扫描")
    print("=" * 78)
    wt = scan_worktree()
    if wt:
        for rel, keys in wt.items():
            print(f"  {rel}: {len(keys)} 处")
    else:
        print("  干净")

    print()
    print("=" * 78)
    print("2. git 历史扫描")
    print("=" * 78)
    hist = scan_history()
    if hist:
        print(f"  {len(hist)} 个提交里含真实 Key")
        for c, keys in list(hist.items())[:5]:
            print(f"    {c[:8]}  {len(keys)} 处")
    else:
        print("  干净")

    if not wt and not hist:
        print()
        print("  ✓ 没有需要处理的内容")
        return 0

    if not args.apply:
        print()
        print("  加 --apply 执行替换。")
        print("  注意：会改写所有分支的历史，已推送的话需要 force push。")
        return 1

    print()
    print("=" * 78)
    print("3. 执行替换")
    print("=" * 78)

    # 3a. 工作区：把所有匹配替换成占位符
    changed = []
    for rel in list(wt.keys()):
        p = ROOT / rel
        text = p.read_text(encoding="utf-8", errors="ignore")
        new = KEY.sub(lambda m: PLACEHOLDER if not is_fake(m.group(0)) else m.group(0), text)
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(rel)
    for rel in changed:
        print(f"  已清理工作区：{rel}")

    # 3b. 历史：用 filter-branch 的 tree-filter 重写工作树里的匹配
    scrub = ROOT / "tools" / "_scrub_tree.py"
    scrub.write_text(
        "import pathlib, re, sys\n"
        "KEY = re.compile(r'wrk-[A-Za-z0-9_\\-]{16,}')\n"
        "PLACE = '\\u5728\\u8fd9\\u91cc\\u586b wrk- \\u5f00\\u5934\\u7684 Key'\n"
        "FAKE = re.compile(r'wrk-([A-Za-z])\\1{5,}', re.I)\n"
        "WORDS = ('yourkey','your_key','example','testkey','here')\n"
        "def sub(m):\n"
        "    t = m.group(0)\n"
        "    b = t[4:].lower()\n"
        "    if any(w in b for w in WORDS) or FAKE.match(t):\n"
        "        return t\n"
        "    return PLACE\n"
        "for p in pathlib.Path('.').rglob('*'):\n"
        "    if not p.is_file() or '.git' in p.parts:\n"
        "        continue\n"
        "    if p.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.gif','.ico','.woff','.woff2','.mp3'}:\n"
        "        continue\n"
        "    try:\n"
        "        t = p.read_text(encoding='utf-8')\n"
        "    except Exception:\n"
        "        continue\n"
        "    n = KEY.sub(sub, t)\n"
        "    if n != t:\n"
        "        p.write_text(n, encoding='utf-8')\n",
        encoding="utf-8")

    py = sys.executable
    env_note = run(["git", "filter-branch", "-f", "--tree-filter",
                    f"{py} tools/_scrub_tree.py", "--", "--all"])
    tail = (env_note.stdout + env_note.stderr).strip().split("\n")[-3:]
    for line in tail:
        print(f"    {line}")

    scrub.unlink(missing_ok=True)

    # 3c. 清掉归档引用与 reflog，避免旧对象还能被翻出来
    run(["git", "for-each-ref", "--format=%(refname)", "refs/original"])
    run(["git", "reflog", "expire", "--expire=now", "--all"])
    run(["git", "gc", "--prune=now", "--quiet"])

    print()
    print("=" * 78)
    print("4. 复检")
    print("=" * 78)
    wt2 = scan_worktree()
    hist2 = scan_history()
    print(f"  工作区: {'干净' if not wt2 else list(wt2)}")
    print(f"  历史  : {'干净' if not hist2 else f'{len(hist2)} 个提交仍有'}")
    if wt2 or hist2:
        print("  仍有残留，需要手工检查。")
        return 2
    print("  ✓ 已清理干净")
    return 0


if __name__ == "__main__":
    sys.exit(main())
