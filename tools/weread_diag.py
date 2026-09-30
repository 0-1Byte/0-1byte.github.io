"""鉴权诊断 —— 当网关返回 -2013「鉴权失败」时，逐项定位是哪一环。

    python tools/weread_diag.py

它做四件事：

  A. 本地检查 Key 文本本身
     前后空白、BOM、零宽字符、不可见字符、长度、字符集。
     复制粘贴最常见的失败原因就藏在这里 —— 肉眼看不出来。

  B. 用同一个请求体，只换鉴权头形式
     确认是「头格式不对」还是「Key 本身不被接受」。

  C. 用同一个鉴权头，只换请求体
     确认是「body 不被接受」还是「鉴权问题」（排除 body 干扰）。

  D. 给出后续动作清单

全程不打印完整 Key，也不打印完整响应正文。
"""
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weread_secret import KEY_FILE, load_key, redact  # noqa: E402
from weread_gateway import SKILL_VERSION  # noqa: E402

problems = []


def post(endpoint, api_key, body, auth_style="bearer", timeout=20):
    """发一次请求，返回 (状态码, 解析后的对象或 None, 原始文本前 200 字符)。"""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "my-blog-weread/1.0",
    }
    if auth_style == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    elif auth_style == "raw":
        headers["Authorization"] = api_key
    elif auth_style == "x-api-key":
        headers["X-API-Key"] = api_key
    elif auth_style == "x-weread-key":
        headers["X-Weread-Key"] = api_key

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw, code = resp.read(), resp.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(), e.code
    except Exception as e:  # noqa: BLE001
        return None, None, f"{type(e).__name__}: {e}"

    text = raw.decode("utf-8", "replace")
    try:
        return code, json.loads(text), text
    except Exception:  # noqa: BLE001
        return code, None, text[:200]


def main():
    print("=" * 80)
    print("A. 本地检查 Key 文本")
    print("=" * 80)

    try:
        api_key, endpoint = load_key()
    except Exception as e:  # noqa: BLE001
        print(str(e))
        return 2

    print(f"  路径   : {KEY_FILE}")
    print(f"  长度   : {len(api_key)} 字符")
    print(f"  脱敏   : {redact(api_key)}")

    issues = []

    if api_key != api_key.strip():
        issues.append("首尾有空白字符（复制时最容易带上）")

    # 找出所有非预期字符
    bad_chars = []
    for i, ch in enumerate(api_key):
        allowed = ch.isascii() and (ch.isalnum() or ch in "-_")
        if not allowed:
            bad_chars.append((i, ch, unicodedata.name(ch, "UNKNOWN")))
    if bad_chars:
        issues.append(f"含 {len(bad_chars)} 个非预期字符")
        for i, ch, name in bad_chars[:8]:
            print(f"         位置 {i}: U+{ord(ch):04X} {name}")

    # 常见的隐形字符
    for label, probe in [("BOM", "\ufeff"), ("零宽空格", "\u200b"),
                         ("不换行空格", "\u00a0"), ("全角空格", "\u3000")]:
        if probe in api_key:
            issues.append(f"含{label}")

    if not api_key.startswith("wrk-"):
        issues.append("不是以 wrk- 开头")

    # 原始文件层面再看一次：BOM 会在读文件时就出问题
    if KEY_FILE.exists():
        raw_bytes = KEY_FILE.read_bytes()
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            issues.append("key.yaml 文件本身带 UTF-8 BOM")

    if issues:
        problems.extend(issues)
        for it in issues:
            print(f"  FAIL {it}")
        print()
        print("  ⚠ 请先修掉上面这些问题再继续。")
        print("    建议：删掉 .secrets/key.yaml，重新从")
        print("    https://weread.qq.com/r/weread-skills 复制一次 Key，")
        print("    粘贴后确认行尾没有多余空格。")
    else:
        print("  OK   Key 文本干净：无非预期字符、无空白、无 BOM")

    print()
    print("=" * 80)
    print("B. 只换鉴权头形式（请求体固定不变）")
    print("=" * 80)
    base_body = {"api_name": "/user/notebooks", "count": 5, "skill_version": SKILL_VERSION}
    print(f"  请求体 : {base_body}")
    print()

    auth_results = {}
    for style in ("bearer", "raw", "x-api-key", "x-weread-key"):
        code, obj, text = post(endpoint, api_key, base_body, style)
        if code is None:
            print(f"  [网络失败] {style}: {text}")
            continue
        err = ""
        if isinstance(obj, dict):
            err = obj.get("errmsg") or obj.get("errlog") or ""
            errcode = obj.get("errcode")
            err = f"errcode={errcode} {err}"
        auth_results[style] = (code, err)
        mark = "可用" if code == 200 and isinstance(obj, dict) and obj.get("errcode") in (0, None) else "    "
        print(f"  [{mark}] {code:>3}  {style:<14} {err or text[:80]}")

    ok_styles = [s for s, (c, e) in auth_results.items() if c == 200 and "errcode=-" not in e]
    print()
    if ok_styles:
        print(f"  可用的鉴权头形式：{ok_styles}")
    elif auth_results:
        print("  四种鉴权头形式都失败 —— 说明不是头格式问题，")
        print("  而是 Key 本身不被服务端接受（或 body 有问题，见 C 段）。")

    print()
    print("=" * 80)
    print("C. 只换请求体（鉴权头固定为 bearer）")
    print("=" * 80)
    bodies = [
        ("完整正规", {"api_name": "/user/notebooks", "count": 5, "skill_version": SKILL_VERSION}),
        ("不带业务参数", {"api_name": "/user/notebooks", "skill_version": SKILL_VERSION}),
        ("不带 skill_version", {"api_name": "/user/notebooks", "count": 5}),
        ("最小体", {"api_name": "/user/notebooks"}),
        ("version 1.0.0", {"api_name": "/user/notebooks", "skill_version": "1.0.0"}),
        ("version 1.0.3", {"api_name": "/user/notebooks", "skill_version": "1.0.3"}),
        ("version 1.0.5", {"api_name": "/user/notebooks", "skill_version": "1.0.5"}),
        ("/store/search 探活", {"api_name": "/store/search", "keyword": "三体",
                                "count": 1, "skill_version": SKILL_VERSION}),
    ]
    for label, body in bodies:
        code, obj, text = post(endpoint, api_key, body)
        if code is None:
            print(f"  [网络失败] {label}: {text}")
            continue
        detail = ""
        if isinstance(obj, dict):
            detail = f"errcode={obj.get('errcode')} {obj.get('errmsg') or ''}"
        print(f"  [{code:>3}] {label:<22} {detail or text[:70]}")

    print()
    print("=" * 80)
    print("结论与后续动作")
    print("=" * 80)
    if problems:
        print("  1) 先按 A 段修掉 Key 文本问题（这是最常见的失败原因）")
    print("  2) 如果 A 段干净、B 段四种头都返回 -2013：")
    print("     Key 未被服务端接受。请到 https://weread.qq.com/r/weread-skills")
    print("     确认：Key 是否已激活、是否过期，或删除后重新创建一个。")
    print("  3) 如果 B 段有某种头可用：把可用的那种告诉我，我改成默认。")
    print("  4) 如果 C 段某个 skill_version 可用：把版本号告诉我。")
    print()
    print("  把 A/B/C 三段输出贴回来即可（已脱敏，可安全粘贴）。")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
