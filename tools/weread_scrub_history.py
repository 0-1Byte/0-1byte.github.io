"""把真实 Key 从 git 历史里彻底移除（不含 replace 引用，是真正的重写）。

背景：filter-branch 在本机（Windows + 沙箱 ACL）会崩；filter-repo 没装；
replace 引用又不会随 push 传出去。所以这里用官方推荐的底层方式：

    git fast-export --all      -> 读出完整历史（内存里，不落盘）
    Python 里替换 Key           -> 纯字节替换
    git fast-import --force     -> 写回同一个仓库，分支被移到新提交

整个过程在内存里完成，不需要在仓库外建临时目录
（沙箱不允许写工作区之外，这也是之前失败的原因之一）。

Key 的值从 .secrets/key.yaml 读，不硬编码。

用法：
    python tools/weread_scrub_history.py --check
    python tools/weread_scrub_history.py --apply
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "在这里填 wrk- 开头的 Key"
TARGET = ".secrets/key.example.yaml"


def git(*args, binary=False, check=True, **kw):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                       text=not binary, **kw)
    if check and r.returncode != 0:
        err = r.stderr
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        raise RuntimeError(f"git {' '.join(args)} 失败：{(err or '')[:300]}")
    return r


def out(r):
    v = r.stdout
    return v.decode("utf-8", "replace") if isinstance(v, (bytes, bytearray)) else (v or "")


def real_key():
    kf = ROOT / ".secrets" / "key.yaml"
    if not kf.exists():
        return None
    m = re.search(r"wrk-[A-Za-z0-9_\-]{16,}", kf.read_text(encoding="utf-8", errors="ignore"))
    return m.group(0) if m else None


def count_in_history(key_bytes):
    r = git("log", "--all", "-p", binary=True)
    return r.stdout.count(key_bytes)


def working_tree_clean():
    r = git("status", "--porcelain")
    lines = [x for x in out(r).split("\n") if x.strip()]
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    key = real_key()
    if not key:
        print("读不到 .secrets/key.yaml 里的 Key，无法定位要清理的内容。")
        return 2
    key_bytes = key.encode()

    print("=" * 78)
    print("扫描")
    print("=" * 78)
    n = count_in_history(key_bytes)
    if n == 0:
        print("  历史里没有真实 Key ✓")
        return 0
    print(f"  历史里出现 {n} 次真实 Key")

    # 定位是哪些提交
    r = git("log", "--all", "--format=%H", "--", TARGET)
    hits = []
    for c in out(r).split("\n"):
        c = c.strip()
        if not c:
            continue
        blob = git("show", f"{c}:{TARGET}", check=False, binary=True)
        if key_bytes in (blob.stdout or b""):
            hits.append(c)
    for c in hits:
        subj = out(git("log", "-1", "--pretty=%s", c)).strip()
        print(f"    {c[:8]}  {subj[:56]}")

    # replace 引用会让 log 看到的是新提交，但它不会被 push，
    # 所以这里必须先删掉，改成真正重写历史。
    repl = out(git("replace", "-l")).strip()
    if repl:
        print()
        print("  发现 replace 引用（之前尝试留下的），先删除：")
        for line in repl.split("\n"):
            parts = line.split()
            if parts:
                git("replace", "-d", parts[0], check=False)
                print(f"    已删除 {parts[0][:12]}")

    if not args.apply:
        print()
        print("  加 --apply 执行重写。")
        return 1

    dirty = working_tree_clean()
    if dirty:
        print()
        print("  工作区不干净，先提交或 stash，避免重写时丢改动：")
        for line in dirty[:10]:
            print(f"    {line}")
        return 3

    print()
    print("=" * 78)
    print("重写历史")
    print("=" * 78)

    # 1) 导出（内存）
    exp = git("fast-export", "--all", "--signed-tags=strip", "--no-data" if False else "--all",
              binary=True, check=False)
    if exp.returncode != 0:
        print(f"  fast-export 失败：{(exp.stderr or b'').decode('utf-8', 'replace')[:300]}")
        return 4
    data = exp.stdout
    print(f"  导出 {len(data)} 字节")

    # 2) 替换
    before = data.count(key_bytes)
    data = data.replace(key_bytes, PLACEHOLDER.encode())
    after = data.count(key_bytes)
    print(f"  替换 {before} 处 -> 剩 {after} 处")

    # 3) 导入（同一仓库，--force 覆盖同名 ref）
    imp = subprocess.run(["git", "fast-import", "--force", "--quiet"],
                         cwd=ROOT, input=data, capture_output=True)
    if imp.returncode != 0:
        print(f"  fast-import 失败：{imp.stderr.decode('utf-8', 'replace')[:300]}")
        return 5
    print("  导入完成")

    # 4) 让工作区跟上新提交
    git("reset", "--hard", "--quiet", check=False)
    git("reflog", "expire", "--expire=now", "--all", check=False)
    git("gc", "--prune=now", "--quiet", check=False)

    print()
    print("=" * 78)
    print("复检")
    print("=" * 78)
    left = count_in_history(key_bytes)
    print(f"  历史里仍出现真实 Key：{left} 次")
    commits = out(git("rev-list", "--count", "HEAD")).strip()
    print(f"  提交数：{commits}")

    if left:
        print()
        print("  仍有残留 —— 可能在 reflog 或悬空对象里。试：")
        print("    git reflog expire --expire=now --all")
        print("    git gc --prune=now --aggressive")
        return 6

    print()
    print("  ✓ 历史已干净")
    print()
    print("  因为提交哈希被改写，推送需要 force：")
    print("    git push --force-with-lease origin main")
    print()
    print("  ⚠ 仍然建议去 https://weread.qq.com/r/weread-skills 重新生成一把 Key：")
    print("     片段曾在对话里出现过，轮换一次才算彻底干净。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
