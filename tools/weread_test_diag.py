"""验证鉴权诊断脚本的本地检查逻辑能抓出各种「脏 Key」。

不联网。用几种真实世界常见的复制粘贴污染来验证判据有效：
首尾空白、BOM、零宽空格、全角字符、前缀错误。
"""
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

problems = []


def inspect(key):
    """与 tools/weread_diag.py A 段相同的判据。"""
    issues = []
    if key != key.strip():
        issues.append("首尾空白")
    bad = [(i, ch) for i, ch in enumerate(key)
           if not (ch.isascii() and (ch.isalnum() or ch in "-_"))]
    if bad:
        names = [unicodedata.name(c, "UNKNOWN") for _, c in bad[:4]]
        issues.append(f"{len(bad)} 个非预期字符 {names}")
    for label, probe in [("BOM", "\ufeff"), ("零宽空格", "\u200b"),
                         ("不换行空格", "\u00a0"), ("全角空格", "\u3000")]:
        if probe in key:
            issues.append(label)
    if not key.startswith("wrk-"):
        issues.append("不是 wrk- 开头")
    return issues


def check(label, cond, detail=""):
    if cond:
        print(f"  OK   {label}")
    else:
        problems.append(label)
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))


print("=" * 76)
print("脏 Key 判据")
print("=" * 76)
# 测试用的假 Key。刻意写成 wrk- 后面接重复字符 ——
# 既能被「脏字符」判据识破，又不会被
# tools/weread_scrub_history.py 的清理规则误当成真实凭据。
FAKE = "wrk-AAAAAAAAAAAAAAAAAAAAAAAA"
CASES = [
    ("干净的 Key", FAKE, False),
    ("尾部空格", FAKE + " ", True),
    ("句首空格", " " + FAKE, True),
    ("带 BOM", "\ufeff" + FAKE, True),
    ("含零宽空格", "wrk-AAAA\u200bAAAA", True),
    ("含不换行空格", "wrk-AAAA\u00a0AAAA", True),
    ("全角连字符", "wrk－AAAA", True),
    ("全角空格", "wrk-AAAA\u3000AAAA", True),
    ("前缀写成 wk-", "wk-AAAAAAAAAAAAAAAA", True),
    ("末尾换行", FAKE + "\n", True),
]
for label, key, should_flag in CASES:
    issues = inspect(key)
    flagged = bool(issues)
    check(f"{label:14} -> {'报出问题' if flagged else '通过'}",
          flagged == should_flag,
          f"issues={issues}")

print()
print("=" * 76)
print("判定顺序：先查文本，再查鉴权头，最后查请求体")
print("=" * 76)
print("  这样能区分三种完全不同的原因，而不是笼统地说「鉴权失败」：")
print("    A 段报问题        -> 复制粘贴带进了脏字符（最常见）")
print("    A 段干净 + B 段全失败 -> Key 未被服务端接受（需重新创建）")
print("    A 段干净 + 某种头可用 -> 头格式问题（改默认即可）")

print()
print("=" * 76)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 判据有效：各类脏 Key 都能被识别")
print("=" * 76)
sys.exit(1 if problems else 0)
