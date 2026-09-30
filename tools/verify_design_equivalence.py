"""阶段 2 等价性验证（规范化版本）。

把颜色与过渡值归一化成统一表示后再比较，消除等价写法造成的噪声：
  #ffffffa8            == rgba(255,255,255,.66)
  rgba(12,12,12,.52)   == rgba(12, 12, 12, .52)
  .45s cubic-bezier(.22,1,.36,1) == .45s cubic-bezier(.22, 1, .36, 1)

只有归一化后仍不同的，才算真正的视觉变化。
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
PAGES = ["music", "book", "works", "docu", "film", "tv"]
PROPS = ("color", "background", "background-color", "border-color", "border",
         "box-shadow", "border-radius", "transition")


# ---------------- 规范化 ----------------
def hex_to_rgba(token):
    """#rgb / #rrggbb / #rrggbbaa -> rgba(r, g, b, a)"""
    m = re.fullmatch(r"#([0-9a-fA-F]{3,8})", token)
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 6:
        h += "ff"
    if len(h) != 8:
        return None
    r, g, b, a = (int(h[i:i + 2], 16) for i in (0, 2, 4, 6))
    return f"rgba({r},{g},{b},{round(a / 255, 4)})"


def canon_color(text):
    """把文本里所有颜色 token 归一化。"""
    def rep(m):
        tok = m.group(0)
        rgba = hex_to_rgba(tok)
        if rgba:
            return rgba
        # rgb()/rgba() 去空格 + 小数补零
        inner = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        return tok
    text = re.sub(r"#[0-9a-fA-F]{3,8}\b", lambda m: hex_to_rgba(m.group(0)) or m.group(0), text)

    def fix_rgb(m):
        head = m.group(1)
        parts = [p.strip() for p in m.group(2).split(",")]
        if len(parts) == 4:
            try:
                # 保留 2 位小数：#ffffffe6 -> 0.90，与 rgba(...,.9) 视为等价
                parts[3] = f"{round(float(parts[3]), 2):g}"
            except ValueError:
                pass
        return f"{head}({','.join(parts)})"
    text = re.sub(r"(rgba?)\(([^()]*)\)", fix_rgb, text)
    # rgb(r,g,b) 补上 alpha=1，便于与 #rrggbb 比较
    text = re.sub(r"\brgb\((\d+),(\d+),(\d+)\)", r"rgba(\1,\2,\3,1)", text)
    return text


def canon_transition(text):
    """过渡：归一化时长与缓动写法，按「顶层逗号」拆分。

    不能用 text.split(",") —— cubic-bezier(.22, 1, .36, 1) 内部含逗号，
    必须按括号深度判断哪些逗号才是属性之间的分隔符。
    """
    t = re.sub(r"\s+", " ", text).strip().lower()
    parts, buf, depth = [], [], 0
    for ch in t:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))

    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        p = re.sub(r"\s*\(\s*", "(", p)
        p = re.sub(r"\s*\)\s*", ")", p)
        p = re.sub(r"\s*,\s*", ",", p)
        p = re.sub(r"\s+", " ", p)
        out.append(p)
    return " | ".join(sorted(out))


def canon(prop, value):
    v = re.sub(r"\s+", " ", value).strip().lower()
    if prop == "transition":
        return canon_transition(v)
    v = canon_color(v)
    return v.replace(" ", "")


# ---------------- CSS 解析 ----------------
def strip_at_blocks(text):
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] == "@":
            j = text.find("{", i)
            if j == -1:
                break
            depth, k = 0, j
            while k < n:
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            i = k + 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def extract_rules(css_text):
    """按大括号配对提取规则。

    注意：声明体里可能出现 `%` 或 `}`？不会 —— 但 `min-height:100%` 里的 `%`
    会让朴素的「找 `}`」写法在遇到 `%}` 时提前收尾，所以这里改成
    「先定位选择器起点，再按深度配对找真正的闭合括号」。
    """
    css = strip_at_blocks(css_text)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules = {}
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j == -1:
            break
        sel = css[i:j].strip()
        depth, k = 0, j
        while k < n:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        body = css[j + 1:k]
        if sel:
            props = {}
            # 声明体内部不会再有大括号，直接按分号切
            for decl in body.split(";"):
                if ":" not in decl:
                    continue
                p, _, v = decl.partition(":")
                p = p.strip().lower()
                if p in PROPS:
                    props[p] = v.strip()
            if props:
                key = normalize_selector(sel)
                rules.setdefault(key, {}).update(props)
        i = k + 1
    return rules


def normalize_selector(sel):
    """选择器归一化：去多余空白、逗号后统一不加空格，
    这样 `html, body` 与 `html,body` 视为同一个选择器。"""
    s = re.sub(r"\s+", " ", sel).strip().lower()
    s = re.sub(r"\s*,\s*", ",", s)
    s = re.sub(r"\s*([>+~])\s*", r" \1 ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_theme(css_text):
    light, dark = {}, {}
    # 必须锚定行首：否则 :root 的宽松匹配会把紧随其后的
    # `[data-theme="dark"] .something {...}` 也吞进来，导致误报
    for sel, body in re.findall(r"^(:root(?:\[data-theme=\"dark\"\])?)\s*\{([^}]*)\}",
                                strip_at_blocks(css_text), re.M):
        target = dark if 'data-theme="dark"' in sel else light
        for name, val in re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", body):
            target[name.strip()] = val.strip()
    merged = dict(light)
    merged.update(dark)
    return {"light": light, "dark": merged}


def resolve(value, variables, depth=0):
    if depth > 15 or "var(" not in value:
        return value

    def sub(m):
        inner = m.group(1)
        name, _, fb = inner.partition(",")
        name = name.strip()
        if name in variables:
            return resolve(variables[name], variables, depth + 1)
        return resolve(fb.strip(), variables, depth + 1) if fb else ""

    return resolve(re.sub(r"var\(([^()]*(?:\([^()]*\))?[^()]*)\)", sub, value), variables, depth + 1)


def get_at_rev(rel):
    r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


PAPERMOD = {"--primary": ("#1e1e1e", "#dadadb"), "--secondary": ("#8a8781", "#9d9a92"),
            "--tertiary": ("#e4e2dd", "#35342f"), "--radius": ("8px", "8px")}

print("=" * 96)
print("逐页等价性对比（颜色/圆角/过渡，已规范化）")
print("=" * 96)
total = 0
for page in PAGES:
    rel = f"static/{page}/style.css"
    old_css = get_at_rev(rel)
    new_css = (STATIC / page / "style.css").read_text(encoding="utf-8")
    if old_css is None:
        print(f"  {page:6} HEAD 无此文件")
        continue

    theme = load_theme((STATIC / "theme.css").read_text(encoding="utf-8"))
    # 迁移前的变量表：PaperMod 默认 + theme.css(新) + HEAD 里该页自己的声明
    old_vars = {"light": {}, "dark": {}}
    for name, (lv, dv) in PAPERMOD.items():
        old_vars["light"][name], old_vars["dark"][name] = lv, dv
    for mode in ("light", "dark"):
        old_vars[mode].update(theme[mode])
    for sel, body in re.findall(r"(:root(?:\[data-theme=\"dark\"\])?)\s*\{([^}]*)\}", old_css):
        target = "dark" if 'data-theme="dark"' in sel else "light"
        for name, val in re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", body):
            old_vars[target][name.strip()] = val.strip()

    diffs = []
    old_rules = extract_rules(old_css)
    new_rules = extract_rules(new_css)
    for mode in ("light", "dark"):
        for sel in sorted(set(old_rules) | set(new_rules)):
            a, b = old_rules.get(sel, {}), new_rules.get(sel, {})
            for prop in sorted(set(a) | set(b)):
                va = canon(prop, resolve(a[prop], old_vars[mode])) if prop in a else None
                vb = canon(prop, resolve(b[prop], theme[mode])) if prop in b else None
                if va != vb:
                    diffs.append((mode, sel, prop, va, vb))

    total += len(diffs)
    print(f"\n  {page:6} {'一致 ✓' if not diffs else f'差异 {len(diffs)} 处'}")
    for mode, sel, prop, va, vb in diffs[:6]:
        print(f"      [{mode}] {sel[:50]:52} {prop}")
        print(f"            HEAD: {va}")
        print(f"            现在: {vb}")

print()
print("=" * 96)
print(f"规范化后差异合计: {total}")
print("=" * 96)
