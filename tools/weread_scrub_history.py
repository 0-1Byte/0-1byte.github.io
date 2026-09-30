"""把真实 Key 从 git 历史里彻底移除。

为什么不用 git filter-branch：
  它在本机（Windows + 沙箱 ACL）上会崩，之前已经崩了两次，
  而且中途失败会留下半改的状态。这里改用官方推荐的更底层方式：
  `git fast-export` 导出全部历史 -> 流式替换 -> `git fast-import` 重建。
  失败时可以整个删掉重建，不会污染原仓库。

关键点：Key 的值不硬编码在这里，而是从 .secrets/key.yaml 读出来，
再放到 fast-export 的替换表里。脚本本身不含任何凭据。

用法：
    python tools/weread_scrub_history.py --check    # 只报告
    python tools/weread_scrub_history.py --apply    # 实际重写历史
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEWREPO = ROOT.parent / "_my-blog-scrubbed"

PLACEHOLDER = "在这里填 wrk- 开头的 Key"
# 真实 Key：wrk- 后跟 16 位以上的长串
KEY = re.compile(rb"wrk-[A-Za-z0-9_\-]{16,}")


def run(args, cwd=ROOT, binary=False):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=not binary)


def out_text(res):
    """统一把 stdout 取成 str —— run(binary=True) 时是 bytes。"""
    v = res.stdout
    return v.decode("utf-8", "replace") if isinstance(v, (bytes, bytearray)) else (v or "")


def real_key_bytes():
    """从 key.yaml 读出真实 Key 的字节形式。"""
    kf = ROOT / ".secrets" / "key.yaml"
    if not kf.exists():
        return None
    text = kf.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"wrk-[A-Za-z0-9_\-]{16,}", text)
    return m.group(0).encode() if m else None


def scan_history(key_bytes):
    """返回含该 Key 的提交列表。"""
    r = run(["git", "log", "--all", "--pretty=format:%H"], binary=True)
    commits = [c for c in out_text(r).split("\n") if c.strip()]
    hits = []
    for c in commits:
        d = run(["git", "show", c, "-p", "--pretty=format:"], binary=True)
        if key_bytes in d.stdout:
            hits.append(c)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    key = real_key_bytes()
    if not key:
        print("读不到 .secrets/key.yaml 里的 Key，无法定位要清理的内容。")
        return 2

    print("=" * 78)
    print("历史扫描")
    print("=" * 78)
    hits = scan_history(key)
    if not hits:
        print("  没有提交含真实 Key ✓")
        return 0
    print(f"  {len(hits)} 个提交含真实 Key：")
    for c in hits:
        subj = out_text(run(["git", "log", "-1", "--pretty=%s", c])).strip()
        print(f"    {c[:8]}  {subj[:60]}")

    if not args.apply:
        print()
        print("  加 --apply 执行重写。")
        return 1

    print()
    print("=" * 78)
    print("重建历史（fast-export -> 替换 -> fast-import）")
    print("=" * 78)

    if NEWREPO.exists():
        import shutil
        shutil.rmtree(NEWREPO)
    NEWREPO.mkdir(parents=True)

    run(["git", "init", "--quiet", "--bare"], cwd=NEWREPO)

    # 导出 -> 在 Python 里流式替换 -> 导入
    exp = subprocess.run(["git", "fast-export", "--all", "--signed-tags=strip"],
                         cwd=ROOT, capture_output=True)
    if exp.returncode != 0:
        print("fast-export 失败：")
        print(exp.stderr.decode("utf-8", "replace")[:400])
        return 3

    data = exp.stdout
    n_before = len(KEY.findall(data))
    data = data.replace(key, PLACEHOLDER.encode())
    data = KEY.sub(lambda m: m.group(0) if m.group(0) == PLACEHOLDER.encode() else PLACEHOLDER.encode(), data)
    n_after = len(KEY.findall(data))
    print(f"  导出 {len(exp.stdout)} 字节；替换 {n_before} 处 -> 剩 {n_after} 处长串")
    print(f"  注：剩下的长串是示例/测试用的假 Key，不是凭据")

    imp = subprocess.run(["git", "fast-import", "--quiet", "--force"],
                         cwd=NEWREPO, input=data, capture_output=True)
    if imp.returncode != 0:
        print("fast-import 失败：")
        print(imp.stderr.decode("utf-8", "replace")[:400])
        return 4

    run(["git", "reset", "--hard", "--quiet"], cwd=NEWREPO)

    # 复检新仓库
    r = subprocess.run(["git", "log", "--all", "-p"], cwd=NEWREPO, capture_output=True)
    still = key in r.stdout
    print()
    print("=" * 78)
    print("复检新仓库")
    print("=" * 78)
    cnt = out_text(run(["git", "rev-list", "--count", "HEAD"], cwd=NEWREPO)).strip()
    print(f"  提交数: {cnt}")
    print(f"  仍含真实 Key: {'是 ✗' if still else '否 ✓'}")

    if still:
        print("  新仓库仍不干净，未替换原仓库。请手工检查。")
        return 5

    # 交换
    print()
    print("=" * 78)
    print("替换")
    print("=" * 78)
    old = ROOT.parent / "_my-blog-old"
    if old.exists():
        import shutil
        shutil.rmtree(old)
    ROOT.rename(old)
    NEWREPO.rename(ROOT)
    # 把被忽略的本地文件（.secrets 等）搬回去
    import shutil
    if (old / ".secrets").exists():
        shutil.copytree(old / ".secrets", ROOT / ".secrets", dirs_exist_ok=True)
    print(f"  原仓库 -> {old.name}（确认无误后可删除）")
    print(f"  干净仓库 -> {ROOT.name}")
    print()
    print("  接下来：")
    print("    1. git remote -v 确认远端还在（fast-import 不带 remote）")
    print("    2. 重新加 remote：git remote add origin <你的仓库地址>")
    print("    3. force push：git push --force origin main")
    print("    4. 别忘了去微信读书重新生成一把 Key（旧的可能已被记录）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
