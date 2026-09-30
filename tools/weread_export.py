"""从微信读书导出划线，合并进首页句子库。

在你自己电脑上运行（沙箱环境没有外网，也不需要在这里跑）。

    # 1. 先确认网络与接口可用（会打印实测结果，不打印 Key）
    python tools/weread_export.py --probe

    # 2. 拉取划线，写成 static/quotes/wechat.yaml（该文件被 .gitignore 忽略）
    python tools/weread_export.py

    # 3. 预览会加进句子库的内容
    python tools/import_wechat_quotes.py --dry-run

    # 4. 确认后合并进 data/quotes.yaml（这个文件会被提交、会上线）
    python tools/import_wechat_quotes.py

    # 5. 构建发布
    hugo --minify && git add data/quotes.yaml && git commit && git push

密钥安全
--------
  · Key 只从 .secrets/key.yaml（git 忽略）或环境变量 WEREAD_API_KEY 读取
  · 打印一律脱敏；从不回显完整 Key
  · 写盘前调用 assert_no_key_leak() 扫描内容，发现 Key 直接拒绝写入
  · 上线的内容只有 data/quotes.yaml —— 纯句子文本，没有任何凭据
  · 原始划线（wechat.yaml）默认也不入库：那是私人阅读记录
  · 跑 python tools/weread_check_secrets.py 可随时自检

接口说明
--------
  网关：https://i.weread.qq.com/api/agent/gateway（官方 WeRead Skills Agent Gateway）
  Key：https://weread.qq.com/r/weread-skills 创建，形如 wrk-…

  网关的具体请求形状会随版本变化，所以这里**不写死**：
  用 --probe 先探一次，脚本会把可用的调用方式记录下来，
  之后导出直接复用。探不到就说明需要更新调用方式，而不是悄悄失败。
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weread_secret import KeyError_, assert_no_key_leak, load_key, redact  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_YAML = ROOT / "static" / "quotes" / "wechat.yaml"
PROBE_CACHE = ROOT / ".secrets" / "probe.json"


def http_json(endpoint, api_key, path, method="GET", params=None, body=None,
              extra_headers=None, timeout=25):
    """一次请求 -> (状态码, 解析后的对象或 None, 说明)。"""
    url = endpoint.rstrip("/") + path
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "my-blog-weread-export/1.0",
    }
    if extra_headers:
        headers.update(extra_headers)

    data = None
    if method == "GET" and params:
        from urllib.parse import urlencode
        url += ("&" if "?" in url else "?") + urlencode(params)
    elif method == "POST":
        data = json.dumps(body or {}).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw, code = resp.read(), resp.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(), e.code
    except Exception as e:  # noqa: BLE001
        return None, None, f"{type(e).__name__}: {e}"

    text = raw.decode("utf-8", "replace")
    try:
        return code, json.loads(text), ""
    except Exception:  # noqa: BLE001
        return code, None, f"响应不是 JSON（前 120 字符）：{text[:120]!r}"


# 候选调用方式，按「最可能」排序。--probe 会逐个试，第一个通的就记下来。
CANDIDATES = [
    {"path": "/", "method": "POST", "body": {"skill": "notes"}},
    {"path": "/", "method": "POST", "body": {"action": "notes"}},
    {"path": "/", "method": "GET", "params": {"skill": "notes"}},
    {"path": "/", "method": "GET", "params": {}},
    {"path": "/notes", "method": "GET", "params": {}},
    {"path": "/notes", "method": "POST", "body": {}},
    {"path": "/shelf", "method": "GET", "params": {}},
]


def do_probe(api_key, endpoint):
    print("=" * 78)
    print("探测可用调用方式")
    print("=" * 78)
    print(f"  网关 : {endpoint}")
    print(f"  Key  : {redact(api_key)}")
    print()

    found = None
    network_failed = False
    for c in CANDIDATES:
        label = f"{c['method']} {c['path']}"
        if c.get("body") is not None:
            label += f" body={c['body']}"
        if c.get("params") is not None:
            label += f" query={c['params']}"

        code, obj, note = http_json(endpoint, api_key, c["path"], c["method"],
                                    c.get("params"), c.get("body"))
        if code is None:
            print(f"  [网络失败] {label}")
            print(f"             {note}")
            network_failed = True
            break

        if code == 200 and isinstance(obj, dict):
            keys = list(obj.keys())[:10]
            print(f"  [可用] {code}  {label}")
            print(f"         顶层字段={keys}")
            if not found:
                found = c
        else:
            print(f"  [  {code:>3}] {label}")
            if note:
                print(f"         {note}")
            elif isinstance(obj, dict):
                err = obj.get("errmsg") or obj.get("message") or obj.get("error") or ""
                print(f"         {list(obj.keys())[:8]}{'  提示=' + str(err)[:60] if err else ''}")

    print()
    if network_failed:
        print("网络层就失败了。如果需要代理：")
        print("    set HTTPS_PROXY=http://127.0.0.1:7897      （改成你的端口）")
        print("然后重跑 --probe。")
        return None
    if found:
        PROBE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        PROBE_CACHE.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已记录可用调用方式到 {PROBE_CACHE.relative_to(ROOT)}（该文件同样被 git 忽略）")
        print(f"  {found}")
        return found
    print("没有探测到可用调用方式。")
    print("请把上面的输出贴回来 —— 状态码与错误提示能定位问题。")
    return None


def collect_highlights(api_key, endpoint, call):
    """按探测到的调用方式拉取划线。返回 [{text, source}]。"""
    code, obj, note = http_json(endpoint, api_key, call["path"], call["method"],
                                call.get("params"), call.get("body"))
    if code != 200 or not isinstance(obj, dict):
        raise RuntimeError(f"拉取失败：HTTP {code} {note or ''}".strip())

    # 网关的字段名会变，这里做多种兼容，而不是写死一种
    def walk(node, out):
        if isinstance(node, dict):
            text = node.get("markedText") or node.get("text") or node.get("content")
            if isinstance(text, str) and text.strip():
                out.append({
                    "text": text.strip(),
                    "source": build_source(node),
                })
            for v in node.values():
                walk(v, out)
        elif isinstance(node, list):
            for v in node:
                walk(v, out)

    def build_source(node):
        book = node.get("book") if isinstance(node.get("book"), dict) else {}
        title = (node.get("bookTitle") or book.get("title") or node.get("title") or "").strip()
        author = (node.get("author") or book.get("author") or "").strip()
        if title and author:
            return f"《{title}》· {author}"
        if title:
            return f"《{title}》"
        return ""

    items = []
    walk(obj, items)

    # 去重（同一句可能在多本书/多个字段里重复出现）
    seen, out = set(), []
    for it in items:
        if it["text"] in seen:
            continue
        seen.add(it["text"])
        out.append(it)
    return out


def write_yaml(items):
    """写入 static/quotes/wechat.yaml，落盘前过一遍 Key 闸门。"""
    def q(value):
        if value == "":
            return '""'
        if any(c in value for c in ':#[]{}&*!|>\'"%@`') or value != value.strip():
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return value

    lines = [
        "# 由 tools/weread_export.py 生成 —— 请勿手工编辑（会被下次导出覆盖）",
        "# 这个文件被 .gitignore 忽略，不会提交、不会上线。",
        f"# 共 {len(items)} 条",
        "",
    ]
    for it in items:
        lines.append(f"- text: {q(it['text'])}")
        if it["source"]:
            lines.append(f"  source: {q(it['source'])}")
    body = "\n".join(lines) + "\n"

    # 最后一道闸：内容里出现 Key 就拒绝写盘
    assert_no_key_leak(body, str(OUT_YAML.relative_to(ROOT)))

    OUT_YAML.parent.mkdir(parents=True, exist_ok=True)
    OUT_YAML.write_text(body, encoding="utf-8")
    return OUT_YAML


def main():
    ap = argparse.ArgumentParser(description="从微信读书导出划线到 static/quotes/wechat.yaml")
    ap.add_argument("--probe", action="store_true", help="只探测可用调用方式，不导出")
    ap.add_argument("--limit", type=int, default=0, help="最多导出多少条（0=全部）")
    args = ap.parse_args()

    try:
        api_key, endpoint = load_key()
    except KeyError_ as e:
        print(str(e))
        return 2

    if args.probe:
        return 0 if do_probe(api_key, endpoint) else 3

    call = None
    if PROBE_CACHE.exists():
        try:
            call = json.loads(PROBE_CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            call = None
    if not call:
        print("还没有记录可用的调用方式，先探测一次：")
        print("    python tools/weread_export.py --probe")
        print()
        call = do_probe(api_key, endpoint)
        if not call:
            return 3

    try:
        items = collect_highlights(api_key, endpoint, call)
    except Exception as e:  # noqa: BLE001
        print(f"导出失败：{e}")
        return 4

    if not items:
        print("没有取到任何划线。")
        print("  可能原因：这个账号还没有划线；或网关返回的字段名变了。")
        print("  先跑 --probe 看返回的顶层字段，确认结构。")
        return 5

    if args.limit and len(items) > args.limit:
        items = items[:args.limit]

    path = write_yaml(items)
    print(f"已导出 {len(items)} 条到 {path.relative_to(ROOT)}")
    print()
    print("接下来：")
    print("    python tools/import_wechat_quotes.py --dry-run   # 预览")
    print("    python tools/import_wechat_quotes.py             # 合并进 data/quotes.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
