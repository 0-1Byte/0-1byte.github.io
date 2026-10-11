"""微信读书 Agent API Gateway 客户端 —— 官方协议

协议来源：Tencent/WeChatReading 官方 skill 文档（skills/SKILL.md）
文档要求：

  统一入口   POST https://i.weread.qq.com/api/agent/gateway
  鉴权       Authorization: Bearer <api_key>
  请求体     JSON。`api_name` 指定接口，其余为接口参数，
             每次请求必须带 `skill_version`（当前 1.0.5）
  参数平铺   业务参数与 api_name / skill_version 放在同一层
             —— 文档明确说：不要包在 params / data / body 里
  响应       JSON，经过字段裁剪；`errcode` 为 0 表示成功
  发现接口   发 `{"api_name": "/_list"}` 可列出所有可用接口及参数定义
"""
import json
import os
import re
import time
import traceback
import requests

SKILL_VERSION = "1.0.5"
DEFAULT_ENDPOINT = "https://i.weread.qq.com/api/agent/gateway"
_SESSION = None

API_LIST = "/_list"
API_NOTEBOOKS = "/user/notebooks"
API_BOOKMARKLIST = "/book/bookmarklist"
API_BOOK_UNDERLINES = "/book/underlines"
API_BEST_BOOKMARKS = "/book/bestbookmarks"
API_BOOK_REVIEWS = "/book/readreviews"
API_REVIEW_SINGLE = "/review/single"
API_SHELF_SYNC = "/shelf/sync"
API_SEARCH = "/store/search"


class WereadError(RuntimeError):
    """网关返回了 errcode != 0 或协议错误。"""

    def __init__(self, message, kind="protocol", http_status=None, errcode=None,
                 attempts=0, elapsed_seconds=0.0):
        RuntimeError.__init__(self, message)
        self.kind = kind
        self.http_status = http_status
        self.errcode = errcode
        self.attempts = attempts
        self.elapsed_seconds = elapsed_seconds
        self.transport_type = None
        self.safe_exception_message = ""
        self.exception_errno = None
        self.exception_winerror = None
        self.exception_function = ""
        self.exception_file = ""
        self.exception_line = None


def _exception_details(exc, api_key=""):
    cause = exc
    frames = traceback.extract_tb(cause.__traceback__) if cause.__traceback__ else []
    frame = frames[-1] if frames else None
    message = str(cause)
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    message = re.sub(r"(?i)https?://\S+", "[URL]", message)
    message = re.sub(
        r"(?i)\b(authorization|cookie|api[_-]?key|token)\b\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        message,
    )
    message = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [REDACTED]", message)
    message = re.sub(r"[\r\n\t]+", " ", message).strip()[:180]
    return {
        "exception_type": type(cause).__name__,
        "exception_message": message or "(empty)",
        "errno": getattr(cause, "errno", None),
        "winerror": getattr(cause, "winerror", None),
        "function": frame.name if frame else "",
        "file": os.path.basename(frame.filename) if frame else "",
        "line": frame.lineno if frame else None,
    }


def _attach_exception_details(error, details):
    error.transport_type = details["exception_type"]
    error.safe_exception_message = details["exception_message"]
    error.exception_errno = details["errno"]
    error.exception_winerror = details["winerror"]
    error.exception_function = details["function"]
    error.exception_file = details["file"]
    error.exception_line = details["line"]


def _get_session():
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.trust_env = True
    return _SESSION


def call(endpoint, api_key, api_name, params=None, timeout=25,
         skill_version=SKILL_VERSION, retries=4, diagnostics=None):
    """按官方协议调用一个网关接口。"""
    if not endpoint:
        endpoint = DEFAULT_ENDPOINT
    if endpoint != DEFAULT_ENDPOINT:
        raise WereadError("只允许向官方网关发送请求。", kind="endpoint")
    if not api_key:
        raise WereadError("缺少微信读书 API Key，无法调用网关。", kind="credentials")

    body = {"api_name": api_name, "skill_version": skill_version}
    if params:
        if "api_name" in params or "skill_version" in params:
            raise WereadError("请求参数不得覆盖 api_name 或 skill_version。", kind="parameters")
        body.update(params)

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "my-blog-weread/1.0",
    }

    attempt = 0
    started = time.monotonic()
    def network_error(exc, http_status=None):
        details = _exception_details(exc, api_key)
        error = WereadError(
            "官方网关网络请求失败（有限重试已用尽）。",
            kind="network",
            http_status=http_status,
            attempts=attempt,
            elapsed_seconds=time.monotonic() - started,
        )
        _attach_exception_details(error, details)
        return error

    def unclassified_transport_error(exc, http_status=None):
        error = WereadError(
            "请求期间发生未分类异常，未按网络错误重试。",
            kind="transport_unclassified",
            http_status=http_status,
            attempts=attempt,
            elapsed_seconds=time.monotonic() - started,
        )
        _attach_exception_details(error, _exception_details(exc, api_key))
        return error

    def report_attempt(http_status=None, exc=None, exception_type=None):
        if diagnostics is not None:
            info = {
                "api_name": api_name,
                "attempt": attempt,
                "max_attempts": retries + 1,
                "http_status": http_status,
                "exception_type": exception_type,
                "elapsed_seconds": time.monotonic() - started,
            }
            if exc is not None:
                info.update(_exception_details(exc, api_key))
            diagnostics(info)

    while True:
        attempt += 1
        code = None
        attempt_exception_type = None
        response = None
        try:
            response = _get_session().post(
                endpoint,
                data=data,
                headers=headers,
                timeout=timeout,
                verify=True,
            )
            code = response.status_code
            raw = response.content
        except requests.exceptions.SSLError as exc:
            report_attempt(http_status=code, exc=exc)
            message = str(exc).lower()
            certificate_error = any(token in message for token in (
                "certificate verify failed",
                "certificate_verify_failed",
                "hostname mismatch",
                "self signed certificate",
            ))
            if certificate_error:
                error = unclassified_transport_error(exc, http_status=code)
                error.kind = "tls_certificate"
                raise error from exc
            if attempt <= retries:
                time.sleep(min(2 ** (attempt - 1), 8))
                continue
            raise network_error(exc, http_status=code) from exc
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            report_attempt(http_status=code, exc=exc)
            if attempt <= retries:
                time.sleep(min(2 ** (attempt - 1), 8))
                continue
            raise network_error(exc, http_status=code) from exc
        except Exception as exc:
            report_attempt(http_status=code, exc=exc)
            raise unclassified_transport_error(exc, http_status=code) from exc
        finally:
            if response is not None:
                response.close()

        if code not in (429, 500, 502, 503, 504):
            report_attempt(
                http_status=code,
                exception_type=attempt_exception_type or (
                    "HTTPError" if code != 200 else None
                ),
            )
        if code in (429, 500, 502, 503, 504) and attempt <= retries:
            report_attempt(http_status=code, exception_type=attempt_exception_type)
            time.sleep(min(2 ** (attempt - 1), 8))
            continue
        break

    elapsed = time.monotonic() - started
    text = raw.decode("utf-8", "replace")
    try:
        obj = json.loads(text)
    except (TypeError, ValueError) as exc:
        if code != 200:
            raise WereadError(
                "官方网关返回非 JSON 错误响应。",
                kind="http",
                http_status=code,
                attempts=attempt,
                elapsed_seconds=elapsed,
            ) from exc
        raise WereadError(
            "官方网关成功响应无法解析为 JSON。",
            kind="response_parse",
            http_status=code,
            attempts=attempt,
            elapsed_seconds=elapsed,
        ) from exc

    if code != 200:
        error_code = obj.get("errcode") if isinstance(obj, dict) else None
        raise WereadError(
            "官方网关请求失败。",
            kind="http",
            http_status=code,
            errcode=error_code,
            attempts=attempt,
            elapsed_seconds=elapsed,
        )
    if not isinstance(obj, dict):
        raise WereadError(
            "官方网关响应顶层结构不是对象。",
            kind="response_shape",
            http_status=code,
            attempts=attempt,
            elapsed_seconds=elapsed,
        )
    if "upgrade_info" in obj:
        raise WereadError(
            "官方网关要求升级。",
            kind="upgrade_required",
            http_status=code,
            errcode=obj.get("errcode"),
            attempts=attempt,
            elapsed_seconds=elapsed,
        )

    errcode = obj.get("errcode")
    if errcode not in (0, None):
        raise WereadError(
            "官方网关返回非零业务错误码。",
            kind="api_error",
            http_status=code,
            errcode=errcode,
            attempts=attempt,
            elapsed_seconds=elapsed,
        )

    return obj


def list_apis(endpoint, api_key):
    """调用 /_list 获取全部可用接口与参数定义。"""
    return call(endpoint, api_key, API_LIST)


def summarize_apis(obj):
    """把 /_list 的结果整理成易读的摘要。字段名做多种兼容。"""
    rows = []
    candidates = None
    for key in ("apis", "api_list", "list", "data", "interfaces"):
        value = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(value, list):
            candidates = value
            break
    if candidates is None:
        for key in ("apis", "api_list", "interfaces", "data"):
            value = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(value, dict):
                candidates = [{"api_name": k, **(vv if isinstance(vv, dict) else {})}
                              for k, vv in value.items()]
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
    """错误信息里若混入 Key 或 Authorization Header，则抹掉。"""
    text = str(text or "")
    text = re.sub(r"Bearer\s+[A-Za-z0-9_.\-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"wrk-[A-Za-z0-9_\-]{8,}", "wrk-***", text)
    return text
