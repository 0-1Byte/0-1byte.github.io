"""微信读书 Agent API Gateway 客户端 —— 官方协议

协议来源：Tencent/WeChatReading 官方 skill 文档（skills/SKILL.md）
以下每一条都是文档明确写出的，不是猜的：

  统一入口   POST https://i.weread.qq.com/api/agent/gateway
  鉴权       Authorization: Bearer $WEREAD_API_KEY      （wrk- 开头）
  请求体     JSON。`api_name` 指定接口，其余为接口参数，
             **每次请求必须带 `skill_version`**（当前 "1.0.4"）
  参数平铺   业务参数与 api_name / skill_version 放在同一层
             —— 文档明确说：不要包在 params / data / body 里
  响应       JSON，经过字段裁剪；`errcode` 为 0 表示成功
  发现接口   发 `{"api_name": "/_list"}` 可列出所有可用接口及参数定义

之前探针之所以全部 404：请求体里没有 `api_name`，
网关无法路由到这个虚拟接口。
"""
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

# 文档里 skills/SKILL.md 头部写的 version，每次请求都要带
SKILL_VERSION = "1.0.4"

DEFAULT_ENDPOINT = "https://i.weread.qq.com/api/agent/gateway"

# 已知接口（文档里出现过的）
API_LIST = "/_list"
API_NOTEBOOKS = "/user/notebooks"
API_NOTES = "/book/bookmarklist"     # 具体名字以 /_list 返回为准
API_SHELF_SYNC = "/shelf/sync"
API_SEARCH = "/store/search"


class WereadError(RuntimeError):
    """网关返回了 errcode != 0。"""


def call(endpoint, api_key, api_name, params=None, timeout=25, skill_version=SKILL_VERSION):
    """调用一个网关接口。

    params 会与 api_name / skill_version 平铺在同一层 —— 这是文档要求的形式。
    返回解析后的 dict。
    """
    body = {"api_name": api_name, "skill_version": skill_version}
    if params:
        body.update(params)

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "my-blog-weread/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw, code = resp.read(), resp.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(), e.code
    except Exception as e:  # noqa: BLE001
        raise WereadError(f"网络请求失败：{type(e).__name__}: {e}") from e

    text = raw.decode("utf-8", "replace")

    # 404 且响应体为空 —— 通常是 api_name 写错，或需要升级 skill
    if code == 404 and not text.strip():
        raise WereadError(
            f"网关返回 404（接口 {api_name}）。\n"
            f"  常见原因：api_name 拼错、该接口不存在，或需要升级 skill 版本。\n"
            f"  先发 {{\"api_name\": \"/_list\"}} 看可用接口列表。"
        )
    if code != 200:
        raise WereadError(f"网关返回 HTTP {code}：{text[:200]!r}")

    try:
        obj = json.loads(text)
    except Exception as e:  # noqa: BLE001
        raise WereadError(f"响应不是 JSON：{text[:200]!r}") from e

    # 文档：返回 upgrade_info 时必须停下并按提示升级，不得忽略
    if isinstance(obj, dict) and "upgrade_info" in obj:
        info = obj.get("upgrade_info") or {}
        msg = info.get("message") if isinstance(info, dict) else str(info)
        raise WereadError(
            f"微信读书要求升级 skill 版本：{msg}\n"
            f"  当前脚本写的是 {skill_version}。请更新 tools/weread_gateway.py 里的 SKILL_VERSION。"
        )

    errcode = obj.get("errcode") if isinstance(obj, dict) else None
    if errcode not in (0, None):
        errmsg = obj.get("errmsg") or obj.get("message") or ""
        raise WereadError(f"网关返回 errcode={errcode}：{errmsg}")

    return obj


def list_apis(endpoint, api_key):
    """调用 /_list 获取全部可用接口与参数定义。"""
    return call(endpoint, api_key, API_LIST)


def summarize_apis(obj):
    """把 /_list 的结果整理成易读的摘要。字段名做多种兼容。"""
    rows = []
    candidates = None
    for key in ("apis", "api_list", "list", "data", "interfaces"):
        v = obj.get(key)
        if isinstance(v, list):
            candidates = v
            break
    if candidates is None:
        # 有时是 {api_name: {...}} 的映射
        for key in ("apis", "api_list", "interfaces", "data"):
            v = obj.get(key)
            if isinstance(v, dict):
                candidates = [{"api_name": k, **(vv if isinstance(vv, dict) else {})}
                              for k, vv in v.items()]
                break

    for item in (candidates or []):
        if not isinstance(item, dict):
            continue
        name = item.get("api_name") or item.get("name") or item.get("api") or ""
        desc = item.get("desc") or item.get("description") or item.get("title") or ""
        params = item.get("params") or item.get("parameters") or item.get("args") or []
        pnames = []
        if isinstance(params, list):
            for p in params:
                if isinstance(p, dict):
                    pnames.append(str(p.get("name") or p.get("key") or "?"))
                else:
                    pnames.append(str(p))
        elif isinstance(params, dict):
            pnames = list(params.keys())
        rows.append((name, desc, pnames))
    return rows


def find_api(rows, *keywords):
    """在 /_list 结果里按关键词找接口名。返回第一个匹配的 api_name。"""
    for kw in keywords:
        for name, _desc, _p in rows:
            if kw.lower() in str(name).lower():
                return name
    return ""


def redact_error(text):
    """错误信息里若混入 Key，抹掉。"""
    return re.sub(r"wrk-[A-Za-z0-9_\-]{8,}", "wrk-***", text or "")
