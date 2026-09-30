# 首屏句子：数据来源、微信读书对接、密钥安全

首页首屏那句话来自 **`data/quotes.yaml`**，每次刷新随机抽一句，
由一个字符一个字符打出来（`static/quotes.js`）。

---

## 0. 密钥安全（先看这个）

微信读书 API Key 形如 `wrk-…`，从 <https://weread.qq.com/r/weread-skills> 创建。

**Key 永远不会被发布上线**，靠四层保证：

| 层 | 做法 |
|---|---|
| 存放 | 只放 `.secrets/key.yaml`，该目录被 `.gitignore` 忽略；不写进任何被追踪的文件 |
| 打印 | 一律走 `redact()`，只显示 `wrk-Ab…UvWx（共 28 字符）` |
| 落盘 | 写任何数据文件前调用 `assert_no_key_leak()`，内容里出现 Key 直接拒绝写入 |
| 自检 | `python tools/weread_check_secrets.py` 检查 7 项，含 git 历史扫描 |

原始划线（`static/quotes/wechat.yaml`）**默认也不入库** —— 那是私人阅读记录，
没必要公开。会上线的只有 `data/quotes.yaml`，内容全是纯句子文本。

想确认某个文件确实被忽略：

```powershell
git check-ignore -v .secrets/key.yaml
# 应输出 .gitignore 里对应的规则行
```

---

## 1. 数据结构

`data/quotes.yaml` 是一个列表，每条两种写法都支持：

```yaml
# 写法一：带出处
- text: 慢一点，再慢一点。
  source: 《xxx》· 某某

# 写法二：只有句子（简写，出处不显示）
- text: building small things,
```

规则：

| 项 | 说明 |
|---|---|
| `text` | 必填。空字符串的条目会被丢弃，不会渲染成空白 |
| `source` | 选填。为空时页面上整行隐藏，不留空行 |
| 冒号 | `text` / `source` 里出现 `:` 时，整行要用引号包起来：`- text: "他说：慢一点。"` |
| 长度 | 建议 ≤ 60 字。打字速度约 19 字符/秒，60 字约 3 秒打完 |
| 顺序 | 不影响抽取（随机），但建议按加入时间排列便于自己查看 |

构建时，Hugo 把这份数据渲染进 `/nav.json` 的 `quotes` 数组：

```json
{
  "groups": [ ... ],
  "standalone": [ ... ],
  "quotes": [
    { "text": "慢一点，再慢一点。", "source": "《xxx》· 某某" }
  ]
}
```

> 为什么句子的端点在 `nav.json` 里：实测 Hugo 会把首页的多个自定义输出格式
> 都交给同一个模板文件（按 kind 找模板，`baseName` 只决定文件名），
> 所以拆不出第二个端点。共用一个反而少发一次请求 —— `site-nav.js`
> 本来就会拉这个文件。

---

## 2. 从微信读书导出划线

**在你的电脑上运行**（导出脚本需要外网访问微信读书网关；
这不影响安全，Key 始终只在本机）。

### 2.1 填 Key

```powershell
copy .secrets\key.example.yaml .secrets\key.yaml
# 然后编辑 .secrets\key.yaml，把 wrk- 开头的 Key 填进去
```

### 2.2 先探测接口（一次就够）

网关的请求形状会随版本变化，所以脚本不写死调用方式，而是先探一次：

```powershell
python tools/weread_export.py --probe
```

- 探到可用方式 → 记进 `.secrets/probe.json`（同样被忽略），之后直接复用
- 网络不通 → 按提示设代理后重跑：
  ```powershell
  set HTTPS_PROXY=http://127.0.0.1:7897
  ```
- 都探不到 → 把输出贴回来，状态码与错误提示能定位问题

### 2.3 导出并合并

```powershell
python tools/weread_export.py                        # -> static/quotes/wechat.yaml
python tools/import_wechat_quotes.py --dry-run       # 预览会加什么
python tools/import_wechat_quotes.py                 # 合并进 data/quotes.yaml
hugo --minify                                        # 本地看一眼
git add data/quotes.yaml && git commit && git push    # 只有这一份文件会上线
```

`import_wechat_quotes.py` 会按 `text` 去重（包含你手工加的句子），
只追加、不覆盖，你写在 `data/quotes.yaml` 里的注释与手写句子都不会被动。

### 2.4 一条划线的字段映射

| 微信读书 | 这里的字段 |
|---|---|
| 划线原文 | `text` |
| 书名 + 作者 | `source`，形如 `《书名》· 作者` |

导出脚本对网关返回的字段名做了多种兼容（`markedText` / `text` / `content`，
`bookTitle` / `book.title`），网关字段改名时不会直接崩，会取不到内容并提示。
想保留更多信息（章节、划线时间、书 ID），先告诉我 —— 当前渲染只认
`text` 与 `source`，扩数据模型是小事，但需要先定要留哪些。

---

## 3. 边界情况

| 情况 | 表现 |
|---|---|
| `data/quotes.yaml` 为空 / 全部注释 | 首页显示兜底文案，不会空白；console 有一条 `warn` |
| `/nav.json` 请求失败或超时 | 保留服务端渲染的那句，console 有一条 `warn`（不打扰访客） |
| 句子超长 | 截断到 140 字符，避免打字太久 |
| 只有一句 | 每次刷新都是它，不做「避开上一句」的尝试 |
| `prefers-reduced-motion` | 直接显示整句，不打字 |
| 切换标签页 | 停止打字，不会在后台继续跑 |
| 导出时内容混入 Key | 拒绝写盘并报错，不会进仓库 |
| 导出到 0 条划线 | 明确提示可能原因，不写空文件 |

