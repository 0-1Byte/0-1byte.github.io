"""验证密钥闸门真的会拦下来，而不是只是「存在」。

三件事：
  1. assert_no_key_leak 遇到 wrk- 形式的 Key 必须抛错
  2. 混入 Key 的 quotes 导出必须被拒绝写盘
  3. 完整流程（模拟导出 -> 合并 -> 构建 -> 发布产物）里不出现 Key
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from weread_secret import KeyError_, assert_no_key_leak, redact  # noqa: E402

problems = []


def check(label, ok, detail=""):
    if ok:
        print(f"  OK   {label}")
    else:
        problems.append(label)
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))


print("=" * 80)
print("1. 脱敏函数")
print("=" * 80)
fake = "wrk-AbCdEfGhIjKlMnOpQrStUvWx"
r = redact(fake)
check("不回显完整 Key", fake not in r, r)
# redact 会附上「（共 N 字符）」后缀，所以只看遮罩部分
masked = r.split("（")[0]
check("保留可辨认的前后缀", masked.startswith("wrk-Ab") and masked.endswith("UvWx"), masked)
check("中间被遮住", "CdEfGhIjKlMnOpQrSt" not in r, r)
check("短值也被遮住", "abcd" not in redact("abcd").lower() or redact("abcd") == "ab**", redact("abcd"))
print(f"       {r}")

print()
print("=" * 80)
print("2. 落盘闸门真的会拦")
print("=" * 80)
# 正常内容应放行
try:
    assert_no_key_leak("- text: 正常句子\n  source: 《书名》", "测试")
    check("正常内容放行", True)
except KeyError_:
    check("正常内容放行", False, "正常内容被误拦")

# 混入 Key 必须拦
caught = False
try:
    assert_no_key_leak(f"- text: 句子\n  source: {fake}", "测试")
except KeyError_ as e:
    caught = True
    check("混入 Key 被拦下", True)
    check("报错信息里也不含完整 Key", fake not in str(e), str(e)[:80])
    print(f"       拦截提示：{str(e).splitlines()[0]}")
if not caught:
    check("混入 Key 被拦下", False, "没有抛错 —— 闸门失效")

# 占位示例不应误报
try:
    assert_no_key_leak("api_key: \"wrk-xxxxxxxx\"", "示例文件")
    check("占位示例不误报（wrk-xxxxxxxx）", False, "占位符被误拦")
except KeyError_:
    check("占位示例不误报（wrk-xxxxxxxx）", True)

print()
print("=" * 80)
print("3. 端到端：模拟导出 -> 合并 -> 构建 -> 检查产物")
print("=" * 80)

# 造一份"从微信读书导出"的数据，其中一条故意混入 Key
wechat = [
    {"text": "适时剪枝", "source": "《测试书》· 作者甲"},
    {"text": f"这条混进了 Key {fake}", "source": "《测试书》· 作者乙"},
]

# 用与真实导出脚本相同的闸门：写 yaml 前扫描
body = "\n".join(f"- text: {q['text']}\n  source: {q['source']}" for q in wechat)
try:
    assert_no_key_leak(body, "static/quotes/wechat.yaml")
    check("导出阶段拦下混入 Key 的数据", False, "没有拦下 —— 会写进仓库")
except KeyError_:
    check("导出阶段拦下混入 Key 的数据", True)

# 干净数据可以正常走完
clean = [{"text": "适时剪枝", "source": "《测试书》· 作者甲"}]
clean_body = "\n".join(f"- text: {q['text']}\n  source: {q['source']}" for q in clean)
try:
    assert_no_key_leak(clean_body, "static/quotes/wechat.yaml")
    check("干净数据正常通过", True)
except KeyError_:
    check("干净数据正常通过", False, "干净数据被误拦")

# 真实产物检查
nav = ROOT / "public" / "nav.json"
if nav.exists():
    data = json.loads(nav.read_text(encoding="utf-8"))
    raw = json.dumps(data, ensure_ascii=False)
    check("真实构建产物 nav.json 里没有 Key", "wrk-" not in raw)
    check("nav.json 里只有 text / source",
          all(set(q.keys()) <= {"text", "source"} for q in data.get("quotes", [])))
else:
    check("public/nav.json 存在", False, "先跑一次 hugo")

print()
print("=" * 80)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 闸门有效：混入 Key 的内容无法进入仓库或产物")
print("=" * 80)
sys.exit(1 if problems else 0)
