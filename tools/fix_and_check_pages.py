"""修掉上一轮 Set-Content 引入的 BOM，并校验六个合集页脚本语法。

两件事：
  1. 去掉六个 index.html 开头的 UTF-8 BOM（EF BB BF）。
     来源：我上一轮用 PowerShell `Set-Content -Encoding utf8` 改版本号，
     Windows PowerShell 的 utf8 会写 BOM。现代浏览器能容忍它，
     但它是我不该引入的改动，也不该留在仓库里。
  2. 用 node --check 逐个校验六个 script.js 的语法 ——
     刚才删代码是正则替换，必须确认没删坏。
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = Path(r"C:\Users\chen\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe")
PAGES = ["music", "book", "works", "docu", "film", "tv"]
BOM = b"\xef\xbb\xbf"

problems = []

print("=" * 76)
print("1. 去掉 BOM")
print("=" * 76)
for page in PAGES:
    f = ROOT / "static" / page / "index.html"
    raw = f.read_bytes()
    if raw.startswith(BOM):
        f.write_bytes(raw[len(BOM):])
        print(f"  {page:6} 已去掉 BOM")
    else:
        print(f"  {page:6} 无 BOM")
    after = f.read_bytes()
    if after.startswith(BOM):
        problems.append(f"{page}/index.html 仍有 BOM")

print()
print("=" * 76)
print("2. 六个 script.js 语法校验")
print("=" * 76)
for page in PAGES:
    f = ROOT / "static" / page / "script.js"
    r = subprocess.run([str(NODE), "--check", str(f)], capture_output=True, text=True)
    ok = r.returncode == 0
    if not ok:
        problems.append(f"{page}/script.js 语法错误")
    print(f"  {page:6} {'OK' if ok else 'FAIL ' + r.stderr.strip().splitlines()[-1][:80]}")

print()
print("=" * 76)
print("3. 加载调用仍在（用更宽松的匹配，之前 load\\w+ 漏掉了裸 load()）")
print("=" * 76)
LOADCALL = re.compile(r"^\s*(?:load\w*|boot|init)\s*\(\s*\)\s*;", re.M)
for page in PAGES:
    src = (ROOT / "static" / page / "script.js").read_text(encoding="utf-8")
    hits = LOADCALL.findall(src)
    ok = bool(hits)
    if not ok:
        problems.append(f"{page}/script.js 缺少加载调用")
    print(f"  {page:6} {'OK' if ok else 'FAIL'}  找到 {len(hits)} 处加载调用")

print()
print("=" * 76)
print("4. themeToggle 引用应已清空，storage 监听应保留")
print("=" * 76)
for page in PAGES:
    src = (ROOT / "static" / page / "script.js").read_text(encoding="utf-8")
    toggle = src.count("themeToggle")
    storage = src.count('addEventListener("storage"')
    ok = toggle == 0
    if not ok:
        problems.append(f"{page}/script.js 仍有 themeToggle 引用")
    print(f"  {page:6} {'OK' if ok else 'FAIL'}  themeToggle={toggle}  storage 监听={storage}")

print()
print("=" * 76)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ BOM 已清、语法正常、加载调用都在、按钮引用已清")
print("=" * 76)
sys.exit(1 if problems else 0)
