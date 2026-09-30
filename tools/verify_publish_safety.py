"""上线前的密钥安全复核 —— 逐条给出结论，不依赖 PowerShell 的退出码。

上一轮的 shell 版误报了「被忽略: 否」，原因是 ConstrainedLanguage 模式下
pwsh 拿不到子进程退出码。这里改用 subprocess 直接读 returncode。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
problems = []


def sh(*args):
    return subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def check(label, ok, detail=""):
    if ok:
        print(f"  OK   {label}")
    else:
        problems.append(label)
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))


def ignored(path):
    r = sh("git", "check-ignore", "-q", path)
    return r.returncode == 0


print("=" * 80)
print("1. 敏感文件确实被 git 忽略")
print("=" * 80)
for p in [".secrets/key.yaml", ".secrets/key.example.yaml", ".secrets/anything.yaml",
          "static/quotes/wechat.yaml"]:
    check(f"{p} 被忽略", ignored(p), "未被忽略 —— 可能被提交")

r = sh("git", "check-ignore", "-v", ".secrets/key.yaml")
print(f"       规则：{r.stdout.strip()}")

print()
print("=" * 80)
print("2. 敏感文件没有进入 git")
print("=" * 80)
tracked = [x for x in sh("git", "ls-files", ".secrets").stdout.split("\n") if x.strip()]
check("当前没有 .secrets/ 文件被追踪", not tracked, f"{tracked}")

tree = [x for x in sh("git", "ls-tree", "-r", "--name-only", "HEAD", "--",
                      ".secrets").stdout.split("\n") if x.strip()]
check("HEAD 的树里没有 .secrets/", not tree, f"{tree}")

tracked_wechat = [x for x in sh("git", "ls-files", "static/quotes").stdout.split("\n")
                  if x.strip() and x.strip().endswith("wechat.yaml")]
check("原始划线 wechat.yaml 未被追踪", not tracked_wechat, f"{tracked_wechat}")

print()
print("=" * 80)
print("3. 历史里没有真实 Key")
print("=" * 80)
import re

# 与 weread_check_secrets.py 用同一套判据，避免两处标准不一致：
#   · 全同字符（wrk-xxxxxxxx）与含 example/yourkey 等词的，都是占位符
#   · 检测/测试脚本里内嵌的假 Key 是验证闸门用的，不算凭据
SELF_FILES = ("tools/weread_check_secrets.py", "tools/weread_test_guard.py",
              "tools/weread_test_diag.py", "tools/weread_scrub_history.py",
              "tools/verify_publish_safety.py", "tools/verify_nav_changes.py")
PLACEHOLDER_WORDS = ("yourkey", "your_key", "example", "testkey", "here", "abcd")


def is_fake(token):
    body = token[4:].lower()
    if any(w in body for w in PLACEHOLDER_WORDS):
        return True
    if len(set(body)) == 1:
        return True
    return False


r = sh("git", "log", "--all", "-p", "--no-color")
current_file = ""
real = []
for line in r.stdout.split("\n"):
    if line.startswith("+++ b/"):
        current_file = line[6:].strip()
        continue
    if not line.startswith("+") or line.startswith("+++"):
        continue
    if current_file in SELF_FILES:
        continue
    for token in re.findall(r"wrk-[A-Za-z0-9_\-]{16,}", line):
        if not is_fake(token):
            real.append(token)

check("历史里没有真实 Key", not real,
      f"命中 {len(real)} 处，例如 {[h[:12] + '…' for h in real[:2]]}")

print()
print("=" * 80)
print("4. 会被发布的产物里没有 Key")
print("=" * 80)
PUB = ROOT / "public"
sus = [p.relative_to(ROOT).as_posix() for p in PUB.rglob("*") if p.is_file()
       and re.search(r"(^|[^a-z])key|secret|credential|token", p.name, re.I)
       and "keys" not in p.name.lower()]
check("public/ 里没有 key/secret 类文件名", not sus, f"{sus[:5]}")

leak = []
for p in PUB.rglob("*"):
    if not p.is_file() or p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp",
                                               ".gif", ".ico", ".woff", ".woff2", ".mp3"}:
        continue
    try:
        t = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    if re.search(r"wrk-[A-Za-z0-9_\-]{16,}", t):
        leak.append(p.relative_to(ROOT).as_posix())
check("public/ 里没有 wrk- 形式的串", not leak, f"{leak[:5]}")
check("public/ 里没有 wechat.yaml", not (PUB / "quotes" / "wechat.yaml").exists())

print()
print("=" * 80)
print("5. 构建流程不会接触 Key")
print("=" * 80)
wf = ROOT / ".github" / "workflows" / "hugo.yml"
src = wf.read_text(encoding="utf-8")
check("工作流没有引用 ${{ secrets.* }}", "secrets." not in src)
check("工作流没有引用 WEREAD_API_KEY", "WEREAD" not in src.upper())
check("工作流只做 hugo 构建（没有联网取数步骤）",
      "weread" not in src.lower())

print()
print("=" * 80)
print("6. 句子库里只有纯文本")
print("=" * 80)
import json
nav = json.loads((PUB / "nav.json").read_text(encoding="utf-8"))
quotes = nav.get("quotes", [])
check("quotes 是数组", isinstance(quotes, list))
check("每条只有 text/source 两个字段",
      all(set(q.keys()) <= {"text", "source"} for q in quotes),
      f"{[q for q in quotes if set(q.keys()) - {'text', 'source'}][:2]}")
print(f"       当前 {len(quotes)} 条句子")

print()
print("=" * 80)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 上线不会泄露 Key")
print("=" * 80)
sys.exit(1 if problems else 0)
