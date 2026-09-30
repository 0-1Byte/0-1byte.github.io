"""密钥安全自检 —— 确认 API Key 没有任何可能被发布上线。

这个脚本不需要网络、不需要真实 Key，随时可以跑：

    python tools/weread_check_secrets.py

检查七件事：
  1. .gitignore 是否确实忽略了 .secrets/ 与 static/quotes/wechat.yaml
  2. Key 文件是否从未被 git 追踪（含历史）
  3. 仓库里（含历史）是否出现过 wrk- 形式的字符串
  4. 会被发布的内容里是否混入 Key
  5. 导出脚本是否具备「写出前扫描 Key」的闸门
  6. 前端的 quotes 数据是否只有纯句子
  7. 构建产物（public/）里是否出现过 Key
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = ROOT / ".secrets" / "key.yaml"
WECHAT_YAML = ROOT / "static" / "quotes" / "wechat.yaml"
PUBLIC = ROOT / "public"

KEY_PATTERN = re.compile(r"wrk-[A-Za-z0-9_\-]{8,}")

problems = []


def run(args, **kw):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def check(label, ok, detail=""):
    if ok:
        print(f"  OK   {label}")
    else:
        problems.append(f"{label} {detail}".strip())
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))


print("=" * 84)
print("1. .gitignore 是否覆盖敏感路径")
print("=" * 84)
gi = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").exists() else ""
check(".gitignore 存在", bool(gi))
for pattern in [".secrets/", "static/quotes/wechat.yaml"]:
    check(f".gitignore 含 {pattern}", pattern in gi)

# 用 git 自己判断，比字符串匹配可靠
for path in [".secrets/key.yaml", ".secrets/key.example.yaml", "static/quotes/wechat.yaml"]:
    r = run(["git", "check-ignore", "-q", path])
    ignored = r.returncode == 0
    if path.endswith("key.example.yaml"):
        # 示例文件应当可以被提交（它不含真实 Key）
        check(f"{path} 未被忽略（示例文件需要入库）", not ignored,
              "被忽略了 —— 示例文件应该入库，方便照着填")
    else:
        check(f"{path} 被 git 忽略", ignored, "未被忽略！这个文件可能被提交")

print()
print("=" * 84)
print("2. Key 文件是否曾进入 git 追踪")
print("=" * 84)
r = run(["git", "ls-files", ".secrets"])
tracked = [x for x in r.stdout.split("\n") if x.strip()]
check("当前没有被追踪的 .secrets 文件", not tracked, f"被追踪：{tracked}")

r = run(["git", "log", "--all", "--pretty=format:", "--name-only"])
history = [x.strip() for x in r.stdout.split("\n") if x.strip()]
hist_secrets = sorted({h for h in history if h.startswith(".secrets/")})
check("历史中从未出现过 .secrets/ 下的文件", not hist_secrets, f"历史里有：{hist_secrets[:5]}")

print()
print("=" * 84)
print("3. 仓库内容（含历史）里是否有 wrk- 形式的 Key")
print("=" * 84)

# 检测用的正则本身、以及明显的占位示例不算泄露。
# 占位判据：去掉 wrk- 后全是同一个字符，或属于常见示例词。
PLACEHOLDERS = {"xxxxxxxx", "yourkey", "your_key", "yourkeyhere", "example", "testkey"}


def is_placeholder(token):
    body = token[4:].lower()
    if body in PLACEHOLDERS:
        return True
    if len(set(body)) == 1:          # 如 wrk-xxxxxxxx
        return True
    return False


def real_keys(text):
    return [t for t in KEY_PATTERN.findall(text or "") if not is_placeholder(t)]


# 工作区（跳过两处「自己人」：
#   · 本脚本自己 —— 它的正则常量必然会命中
#   · weread_test_guard.py —— 它故意内嵌一个假 Key 来验证闸门会拦
# 这两处的字符串都不是真实凭据。除此之外任何命中都算泄露。）
SELF_FILES = {"tools/weread_check_secrets.py", "tools/weread_test_guard.py"}
hits = []
for p in ROOT.rglob("*"):
    if not p.is_file():
        continue
    rel = p.relative_to(ROOT).as_posix()
    if rel.startswith(("public/", ".git/", "themes/", ".secrets/")):
        continue
    if rel in SELF_FILES:
        continue
    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2", ".mp3"}:
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        continue
    found = real_keys(text)
    if found:
        hits.append((rel, [t[:12] + "…" for t in found[:2]]))
check("工作区源码里没有真实 Key（已排除检测脚本自身与其测试夹具）", not hits, f"命中：{hits[:3]}")

# git 历史
r = run(["git", "log", "--all", "-p", "--", ".", ":(exclude)public", ":(exclude)themes"])
hist_hits = real_keys(r.stdout)
check("git 历史里没有真实 Key", not hist_hits,
      f"命中 {len(hist_hits)} 处，例如 {[h[:12] + '…' for h in hist_hits[:2]]}")

print()
print("=" * 84)
print("4. 会被发布的内容里是否混入 Key")
print("=" * 84)
# 发布内容 = data/ + static/（static 会原样复制到 public）
pub_sources = []
for folder in ["data", "static", "content", "layouts"]:
    d = ROOT / folder
    if d.exists():
        pub_sources.extend(p for p in d.rglob("*") if p.is_file())
leak = []
for p in pub_sources:
    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2", ".mp3"}:
        continue
    if p.resolve() == WECHAT_YAML.resolve():
        continue  # 已被 .gitignore 忽略，不会发布
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        continue
    if KEY_PATTERN.search(text):
        leak.append(p.relative_to(ROOT).as_posix())
check("会被发布的内容里没有 Key", not leak, f"命中：{leak[:5]}")

print()
print("=" * 84)
print("5. 导出脚本是否具备落盘前的 Key 扫描闸门")
print("=" * 84)
sec = ROOT / "tools" / "weread_secret.py"
text = sec.read_text(encoding="utf-8") if sec.exists() else ""
check("tools/weread_secret.py 存在", sec.exists())
check("含 assert_no_key_leak 闸门", "def assert_no_key_leak" in text)
check("含 Key 正则", "wrk-" in text)
check("打印时做脱敏（redact）", "def redact" in text)
check("不回显完整 Key（无直接 print(api_key)）",
      "print(api_key)" not in text and "print(key)" not in text)

# 调用方是否真的用了闸门
importers = list((ROOT / "tools").glob("*.py"))
users = [p.name for p in importers if "assert_no_key_leak" in p.read_text(encoding="utf-8", errors="ignore")
         and p.name != "weread_secret.py"]
check("有工具实际调用该闸门", bool(users), f"调用者：{users}")

print()
print("=" * 84)
print("6. 前端拿到的 quotes 数据只有纯句子")
print("=" * 84)
navfile = PUBLIC / "nav.json"
if navfile.exists():
    data = json.loads(navfile.read_text(encoding="utf-8"))
    quotes = data.get("quotes", [])
    check("nav.json 里 quotes 是数组", isinstance(quotes, list))
    bad = [q for q in quotes if set(q.keys()) - {"text", "source"}]
    check("每条只有 text / source 两个字段", not bad, f"多出字段：{bad[:2]}")
    check("quotes 内容里没有 Key", not real_keys(json.dumps(quotes, ensure_ascii=False)))
    print(f"       当前 {len(quotes)} 条句子")
else:
    check("public/nav.json 存在（先跑一次 hugo）", False, "文件不存在")

print()
print("=" * 84)
print("7. 构建产物里是否出现 Key")
print("=" * 84)
if PUBLIC.exists():
    found_in_public = []
    for p in PUBLIC.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2", ".mp3"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        if real_keys(text):
            found_in_public.append(p.relative_to(ROOT).as_posix())
    check("public/ 里没有 Key", not found_in_public, f"命中：{found_in_public[:5]}")
    check("public/ 里没有 wechat.yaml（原始划线不入库）",
          not (PUBLIC / "quotes" / "wechat.yaml").exists())
else:
    check("public/ 存在（先跑一次 hugo）", False, "目录不存在")

print()
print("=" * 84)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 密钥不会以任何形式被发布上线")
print("=" * 84)
sys.exit(1 if problems else 0)
