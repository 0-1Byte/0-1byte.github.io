"""静态检查 /ocean/ 的 GLSL：构建产物里抽出着色器源码，做基础语法与语义核对。

无法替你跑 GPU，但能挡掉最常见、也最容易在浏览器里直接报错的几类问题：
  · 调用了未定义的函数（我上一次就是把 JS 函数写进了 GLSL）
  · 内置函数参数个数不对
  · uniform 声明了但没赋值，或赋值了但没声明
  · gl_FragColor 未写入
  · 括号 / 分号明显不平衡
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "public" / "ocean" / "script.js")
if not JS.exists():
    JS = ROOT / "static" / "ocean" / "script.js"
src = JS.read_text(encoding="utf-8")

problems = []

# 抽出着色器字符串（反引号包裹，含 gl_Position 或 gl_FragColor）
shaders = {}
for name, pat in [("VERT", r"gl_Position"), ("FRAG", r"gl_FragColor")]:
    for m in re.finditer(r"`([^`]*)`", src, re.S):
        if pat in m.group(1):
            shaders[name] = m.group(1)
            break

print("=" * 84)
print("抽取到的着色器")
print("=" * 84)
for k, v in shaders.items():
    print(f"  {k}: {len(v.splitlines())} 行")
if len(shaders) != 2:
    problems.append(f"只找到 {len(shaders)} 个着色器，期望 2 个")

# GLSL 内置函数 -> 参数个数范围
BUILTINS = {
    "sin": (1, 1), "cos": (1, 1), "tan": (1, 1), "exp": (1, 1), "log": (1, 1),
    "pow": (2, 2), "sqrt": (1, 1), "abs": (1, 1), "sign": (1, 1), "floor": (1, 1),
    "ceil": (1, 1), "fract": (1, 1), "mod": (2, 2), "min": (2, 2), "max": (2, 2),
    "clamp": (3, 3), "mix": (3, 3), "step": (2, 2), "smoothstep": (3, 3),
    "length": (1, 1), "distance": (2, 2), "dot": (2, 2), "cross": (2, 2),
    "normalize": (1, 1), "reflect": (2, 2), "refract": (3, 3),
    "vec2": (1, 2), "vec3": (1, 3), "vec4": (1, 4), "mat2": (1, 4),
}

for name, code in shaders.items():
    print()
    print("=" * 84)
    print(f"检查 {name}")
    print("=" * 84)

    # 去掉注释，避免注释里的括号/分号干扰
    body = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)

    # 1) 收集自定义函数定义
    defined = set(re.findall(r"\b(?:float|vec2|vec3|vec4|void|int|mat2|mat3|mat4)\s+(\w+)\s*\(", body))
    print(f"  自定义函数: {sorted(defined) or '（无）'}")

    # 2) 收集所有函数调用
    called = {}
    for m in re.finditer(r"\b(\w+)\s*\(", body):
        fn = m.group(1)
        if fn in ("if", "for", "while", "return", "main"):
            continue
        # 计算参数个数（顶层逗号）
        depth, args, i = 0, [], m.end()
        start = i
        while i < len(body):
            ch = body[i]
            if ch in "([":
                depth += 1
            elif ch in ")]":
                if depth == 0:
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                args.append(body[start:i].strip())
                start = i + 1
            i += 1
        tail = body[start:i].strip()
        if tail:
            args.append(tail)
        called.setdefault(fn, []).append(len(args))

    unknown = sorted(set(called) - defined - set(BUILTINS))
    if unknown:
        problems.append(f"{name}: 调用了未定义的函数 {unknown}")
    print(f"  {'OK ' if not unknown else 'FAIL'} 未定义函数调用: {unknown or '无'}")

    # 3) 内置函数参数个数
    bad_arity = []
    for fn, counts in called.items():
        if fn not in BUILTINS:
            continue
        lo, hi = BUILTINS[fn]
        for c in counts:
            if not (lo <= c <= hi):
                bad_arity.append(f"{fn}({c} 个参数，允许 {lo}-{hi})")
    if bad_arity:
        problems.append(f"{name}: 内置函数参数个数异常 {bad_arity}")
    print(f"  {'OK ' if not bad_arity else 'FAIL'} 内置函数参数: {bad_arity or '全部合法'}")

    # 4) uniform：声明 vs 赋值
    declared = set(re.findall(r"uniform\s+\w+\s+(\w+)", body))
    print(f"  声明 uniform: {sorted(declared)}")

    # 5) 括号平衡
    for open_ch, close_ch, label in [("{", "}", "大括号"), ("(", ")", "小括号")]:
        a, b = body.count(open_ch), body.count(close_ch)
        ok = a == b
        if not ok:
            problems.append(f"{name}: {label}不平衡 {a} vs {b}")
        print(f"  {'OK ' if ok else 'FAIL'} {label}平衡: {a} / {b}")

    # 6) 每条语句以分号或 } 结尾（粗查漏分号）
    missing = []
    for i, line in enumerate(body.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.endswith((";", "{", "}", ",")):
            continue
        # 续行（下一行接着写）不算
        missing.append((i, s))
    if missing:
        print(f"  提示：{len(missing)} 行未以 ; {{ }} , 结尾（多为续行，仅供参考）")

# uniform 赋值核对（在 JS 侧）
print()
print("=" * 84)
print("JS 侧 uniform 赋值")
print("=" * 84)

# 现在的写法是：UNIFORMS 数组 + forEach(getUniformLocation)，
# 所以不能只找零散的 getUniformLocation 调用，要把数组内容也读出来。
array = re.search(r"const UNIFORMS = \[(.*?)\];", src, re.S)
from_array = set(re.findall(r'"(\w+)"', array.group(1))) if array else set()
from_calls = set(re.findall(r'getUniformLocation\(\s*program\s*,\s*"(\w+)"\s*\)', src))
assigned = from_array | from_calls
used = set(re.findall(r"uniform1f\(\s*loc\.(\w+)", src)) | set(re.findall(r"uniform2f\(\s*loc\.(\w+)", src)) \
    | set(re.findall(r"uniform3fv\(\s*loc\.(\w+)", src))

print(f"  UNIFORMS 数组: {sorted(from_array)}")
print(f"  实际赋值用到: {sorted(used)}")

declared = set()
for name, code in shaders.items():
    body = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    declared |= set(re.findall(r"uniform\s+\w+\s+(\w+)", body))

missing_assign = declared - assigned
if missing_assign:
    problems.append(f"着色器声明但 JS 未取 location: {sorted(missing_assign)}")
print(f"  {'OK ' if not missing_assign else 'FAIL'} 声明与取值一致: 缺 {sorted(missing_assign) or '无'}")

never_used = assigned - used
if never_used:
    problems.append(f"取了 location 但从未赋值: {sorted(never_used)}")
print(f"  {'OK ' if not never_used else 'FAIL'} 取值后都有赋值: 未用 {sorted(never_used) or '无'}")

# 回退路径是否真的存在
print()
print("=" * 84)
print("回退路径")
print("=" * 84)
has_fallback_css = (ROOT / "static" / "ocean" / "style.css").read_text(encoding="utf-8").count(".ocean-fallback") > 0
has_fallback_js = "ocean-fallback" in src or "canvas.style.display" in src
print(f"  {'OK ' if has_fallback_css else 'FAIL'} CSS 静态海面存在")
print(f"  {'OK ' if has_fallback_js else 'FAIL'} JS 失败时隐藏画布")
if not (has_fallback_css and has_fallback_js):
    problems.append("回退路径不完整")

print()
print("=" * 84)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ GLSL 结构检查通过")
print("=" * 84)
