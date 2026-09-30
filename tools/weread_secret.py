"""读取本地微信读书凭据。任何情况下都不回显完整 Key。

Key 的存放与泄露面（重要）：
  · 只从 .secrets/key.yaml 读（该目录被 .gitignore 忽略）
  · 也支持环境变量 WEREAD_API_KEY 作为备选，便于临时调试
  · 打印时一律用 redact() 处理，只显示前缀与末 4 位
  · assert_no_key_leak() 在写出任何文件前扫一遍内容，
    万一 Key 混进去了就直接拒绝写入 —— 这是最后一道闸

为什么不做成"把 Key 写进配置文件再提交"：
  GitHub Pages 是纯静态托管，任何被提交的文件都会原样发布到公网。
  Key 一旦进仓库，就算之后删掉，历史里仍然存在。
  所以这里的原则是：Key 永远不进入 git 追踪范围。
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = ROOT / ".secrets" / "key.yaml"
ENV_VAR = "WEREAD_API_KEY"
DEFAULT_ENDPOINT = "https://i.weread.qq.com/api/agent/gateway"

# 微信读书官方 Key 形如 wrk-xxxxxxxx
KEY_PATTERN = re.compile(r"wrk-[A-Za-z0-9_\-]{8,}")


class KeyError_(RuntimeError):
    """凭据缺失或格式不对。刻意用独立名字，避免与内置 KeyError 混淆。"""


def redact(value):
    """把 Key 变成可安全打印的形式。

    刻意只显示**首 4 位 + 末 2 位**：
    之前显示首 6 末 4 时，用户把探针输出粘进对话/提交信息，
    这些片段就进了日志与 git 历史 —— 前缀越长，被拼出来的风险越大。
    4+2 位（都是 "wrk-" 之后的部分）足够你自己确认「是不是这把」，
    又不足以还原任何东西。
    """
    if not value:
        return "(空)"
    v = str(value)
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:4]}…{v[-2:]}（共 {len(v)} 字符）"


def _parse_simple_yaml(text):
    """极简 YAML：只解析顶层 key: value。避免为一个字段引入依赖。"""
    out = {}
    for raw in text.splitlines():
        line = raw.split("#")[0].rstrip() if not raw.strip().startswith("#") else ""
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def load_key(required=True):
    """返回 (api_key, endpoint)。

    优先级：环境变量 > .secrets/key.yaml
    """
    key = os.environ.get(ENV_VAR, "").strip()
    endpoint = DEFAULT_ENDPOINT

    if KEY_FILE.exists():
        data = _parse_simple_yaml(KEY_FILE.read_text(encoding="utf-8"))
        if not key:
            key = str(data.get("api_key", "")).strip()
        endpoint = str(data.get("endpoint", "")).strip() or DEFAULT_ENDPOINT

    unresolved = key in ("", "在这里填 wrk- 开头的 Key")
    if unresolved:
        if not required:
            return "", endpoint
        raise KeyError_(
            "没有找到微信读书 API Key。\n"
            f"  1) 复制 .secrets/key.example.yaml 为 .secrets/key.yaml\n"
            f"  2) 到 https://weread.qq.com/r/weread-skills 创建 Key（wrk- 开头）\n"
            f"  3) 填进 .secrets/key.yaml 的 api_key\n"
            f"  （也可以临时设环境变量 {ENV_VAR}）\n"
            f"  当前查找路径：{KEY_FILE}"
        )

    if not key.startswith("wrk-"):
        raise KeyError_(
            f"Key 格式看起来不对：应以 wrk- 开头，实际是 {redact(key)}。\n"
            "  请确认复制完整（不要带多余空格或引号）。"
        )

    # 防呆：Key 必须放在 .secrets/key.yaml。
    # 之前有人把真实 Key 填进了「示例文件」，而那个文件是入库的 ——
    # 于是完整 Key 进了 git 历史。这里主动拦一下。
    if KEY_FILE.name.endswith(".example.yaml") or "example" in KEY_FILE.name:
        raise KeyError_(
            f"看起来你把 Key 填进了示例文件：{KEY_FILE.name}\n"
            "  那个文件是给人看的模板，会被提交、会被发布。\n"
            "  请改成填 .secrets/key.yaml（该文件被 .gitignore 忽略）。"
        )

    return key, endpoint


def assert_no_key_leak(text, where=""):
    """写出文件前的最后一道闸：内容里不允许出现任何 wrk- 形式的 Key。

    为什么需要它：导出脚本会拼接多个来源的内容，
    万一某个字段里混进了 Key（或用户误把 Key 填到了别的地方），
    这一步能在落盘前拦住，而不是等到推送到公网才发现。
    """
    hits = KEY_PATTERN.findall(text or "")
    if hits:
        raise KeyError_(
            f"拒绝写入{(' ' + where) if where else ''}：内容里发现了疑似 API Key "
            f"（{', '.join(redact(h) for h in hits[:3])}）。\n"
            "  这说明 Key 混进了要提交的数据里 —— 请检查 .secrets/key.yaml 是否被误当作数据源读入。"
        )
    return True


def key_status():
    """给自检用：不读文件内容，只报告状态。"""
    present = KEY_FILE.exists()
    from_env = bool(os.environ.get(ENV_VAR, "").strip())
    return {
        "file": str(KEY_FILE),
        "file_exists": present,
        "env_var": ENV_VAR,
        "env_set": from_env,
        "ignored_by_git": _is_git_ignored(),
    }


def _is_git_ignored():
    """用 git check-ignore 确认 .secrets/ 真的被忽略；git 不可用时返回 None。"""
    import subprocess
    try:
        r = subprocess.run(
            ["git", "check-ignore", "-q", str(KEY_FILE)],
            cwd=ROOT, capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return None
