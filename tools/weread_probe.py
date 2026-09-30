"""微信读书网关探针 —— 用官方协议先列接口，再确认划线接口可用。

在你自己电脑上运行：

    python tools/weread_probe.py

它做两件事：
  1. 调 /_list 列出网关支持的全部接口（名字 + 说明 + 参数）
  2. 在列表里找「笔记本 / 划线」相关接口，逐个试一次，看哪个能用

为什么之前全部 404
------------------
请求体里少了 `api_name`。网关是一个统一入口，靠 body 里的
`api_name` 路由到具体接口；没有它就无法匹配任何路径。
另外每次请求还必须带 `skill_version`。

它只报告状态与字段，不打印完整 Key，也不回显大段正文。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weread_secret import KeyError_, load_key, redact  # noqa: E402
from weread_gateway import (  # noqa: E402
    SKILL_VERSION, WereadError, call, find_api, list_apis, summarize_apis,
)


def main():
    print("=" * 78)
    print("微信读书网关探针（官方协议）")
    print("=" * 78)

    try:
        api_key, endpoint = load_key()
    except KeyError_ as e:
        print(str(e))
        return 2

    print(f"  Key          : {redact(api_key)}")
    print(f"  网关         : {endpoint}")
    print(f"  skill_version: {SKILL_VERSION}")
    print()

    # ---------- 1. 列出接口 ----------
    print("1) 调用 /_list 列出可用接口")
    print()
    try:
        obj = list_apis(endpoint, api_key)
    except WereadError as e:
        print(f"  失败：{e}")
        print()
        print("  排查方向：")
        print("   · 「网络请求失败」-> 需要代理：set HTTPS_PROXY=http://127.0.0.1:7897")
        print("   · 「404」-> /_list 本身不可用，可能需要升级 skill 版本")
        print("   · 「errcode != 0」-> Key 无效或没有权限")
        return 3

    rows = summarize_apis(obj)
    if not rows:
        print("  取到了响应，但没解析出接口列表。顶层字段：")
        print(f"    {list(obj.keys())[:15]}")
        print("  把这一行贴回来，我据此调整解析。")
        return 4

    print(f"  共 {len(rows)} 个接口：")
    for name, desc, params in rows:
        line = f"    {name}"
        if desc:
            line += f"   —— {desc}"
        print(line)
        if params:
            print(f"        参数: {', '.join(params[:12])}")
    print()

    # ---------- 2. 找划线相关接口并实测 ----------
    print("2) 找「笔记本 / 划线 / 想法」相关接口并试调")
    print()
    wanted = []
    for kws in (("notebook",), ("notes",), ("bookmark",), ("highlight",), ("book",)):
        name = find_api(rows, *kws)
        if name and name not in wanted:
            wanted.append(name)

    if not wanted:
        print("  接口列表里没找到明显相关的名字，请把上面的完整列表贴回来。")
        return 0

    ok_calls = []
    for name in wanted[:6]:
        try:
            obj2 = call(endpoint, api_key, name, {"count": 5})
        except WereadError as e:
            print(f"  [{name}]  失败：{e}")
            continue
        keys = list(obj2.keys())
        print(f"  [OK] {name}")
        print(f"       顶层字段: {keys[:12]}")
        # 粗略看看哪一层像条目列表
        for k, v in obj2.items():
            if isinstance(v, list) and v:
                first = v[0] if isinstance(v[0], dict) else {}
                print(f"       {k}: {len(v)} 条，条目字段 {list(first.keys())[:12]}")
        ok_calls.append((name, obj2))
        print()

    print("=" * 78)
    if ok_calls:
        print(f"可用的划线相关接口：{[n for n, _ in ok_calls]}")
        print("把这些名字与字段贴回来，我就把导出脚本的调用方式固定下来。")
    else:
        print("没有试通任何接口。把上面的输出整段贴回来。")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
