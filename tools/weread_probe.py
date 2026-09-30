"""微信读书网关连通性探针 —— 在你自己电脑上运行，用来确定可用的调用方式。

为什么需要它
------------
导出脚本要调用官方网关（i.weread.qq.com/api/agent/gateway），
但不同版本网关对「路径 / 方法 / 鉴权头 / 请求体字段」的要求会变。
与其在代码里写死一套可能过时的调用方式，不如先探一次，用实测结果说话。

它做什么
--------
用你的 Key 依次尝试若干种调用组合，只报告：
  · HTTP 状态码
  · 响应是不是 JSON、顶层有哪些字段
  · 错误信息（如果有）
**绝不打印完整 Key，也绝不回显大段正文。**

用法
----
    python tools/weread_probe.py

如果探针报「网络不可达」，通常是需要代理：
    set HTTPS_PROXY=http://127.0.0.1:7897      （按你的实际端口改）
    python tools/weread_probe.py

把输出贴回来，我据此把导出脚本的调用方式固定下来。
"""
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weread_secret import KeyError_, load_key, redact  # noqa: E402


def attempt(endpoint, api_key, path, method, params=None, body=None, headers=None, timeout=20):
    """发一次请求，返回 (状态码, 说明, 是否为 JSON, 顶层字段)。"""
    url = endpoint.rstrip("/") + path
    data = None
    hdrs = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "my-blog-weread-probe/1.0",
    }
    if headers:
        hdrs.update(headers)

    if method == "GET" and params:
        from urllib.parse import urlencode
        url += ("&" if "?" in url else "?") + urlencode(params)
    elif method == "POST":
        data = json.dumps(body or {}).encode("utf-8")
        hdrs["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)

    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            code = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        code = e.code
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}", False, None

    text = raw.decode("utf-8", "replace")
    try:
        obj = json.loads(text)
    except Exception:  # noqa: BLE001
        return code, f"非 JSON，前 120 字符：{text[:120]!r}", False, None

    if isinstance(obj, dict):
        keys = list(obj.keys())[:12]
        # 只取错误信息，不回显正文
        err = obj.get("errmsg") or obj.get("message") or obj.get("error") or ""
        hint = f"字段={keys}"
        if err:
            hint += f"  提示={str(err)[:80]}"
        return code, hint, True, keys
    return code, f"JSON 顶层是 {type(obj).__name__}，长度 {len(obj)}", True, None


def main():
    print("=" * 78)
    print("微信读书网关探针")
    print("=" * 78)

    try:
        api_key, endpoint = load_key()
    except KeyError_ as e:
        print("\n" + str(e))
        return 2

    print(f"  Key      : {redact(api_key)}")
    print(f"  网关     : {endpoint}")
    print()

    # 组合尽量覆盖常见约定，按「最可能」到「最不可能」排列
    TRIALS = [
        ("/", "POST", None, {"skill": "notes"}, None),
        ("/", "POST", None, {"action": "notes"}, None),
        ("/", "POST", None, {"skill_id": "notes"}, None),
        ("/", "GET", {}, None, None),
        ("/", "GET", {"skill": "notes"}, None, None),
        ("/notes", "POST", None, {}, None),
        ("/notes", "GET", {}, None, None),
        ("/shelf", "POST", None, {}, None),
        ("/", "POST", None, {}, {"X-API-Key": api_key}),
    ]

    ok = []
    for path, method, params, body, extra in TRIALS:
        label = f"{method} {path}"
        if body is not None:
            label += f"  body={body}"
        if params:
            label += f"  query={params}"
        if extra:
            label += "  （改用 X-API-Key 头）"

        code, note, is_json, keys = attempt(endpoint, api_key, path, method, params, body, extra)

        if code is None:
            print(f"  [网络失败] {label}")
            print(f"             {note}")
            print()
            print("  看起来是网络层就失败了，不是接口问题。")
            print("  如果这里需要代理，先设 HTTPS_PROXY 再重跑：")
            print("      set HTTPS_PROXY=http://127.0.0.1:7897")
            return 3

        mark = "OK " if code == 200 and is_json else "   "
        print(f"  [{mark}] {code:>3}  {label}")
        print(f"          {note}")
        if code == 200 and is_json:
            ok.append((path, method, params, body, extra))

    print()
    print("=" * 78)
    if ok:
        print(f"可用组合 {len(ok)} 个，第一个是：{ok[0][1]} {ok[0][0]}")
        print("把这个结果告诉我，我据此固定导出脚本的调用方式。")
    else:
        print("没有任何组合返回可用的 JSON。")
        print("请把上面的完整输出贴回来 —— 状态码和错误提示能定位问题。")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
