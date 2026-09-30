# 首屏句子：数据来源与微信读书对接约定

首页首屏那句话来自 **`data/quotes.yaml`**，每次刷新随机抽一句，
由一个字符一个字符打出来（`static/quotes.js`）。

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

## 2. 微信读书划线对接

### 需要产出的东西

把划线整理成一个 YAML 列表，写到 **`static/quotes/wechat.yaml`**，
格式与 `data/quotes.yaml` 完全一致：

```yaml
- text: 划线原文
  source: 《书名》· 作者
```

之所以单独放一个文件而不是直接写进 `data/quotes.yaml`：
工具可以整份覆盖 `wechat.yaml`，不必解析和改写你手工维护的那份。

### 合并进句子库

```powershell
# 预览（不写文件）
python tools/import_wechat_quotes.py --dry-run

# 实际合并：去重后追加到 data/quotes.yaml
python tools/import_wechat_quotes.py
```

工具会：
- 读 `static/quotes/wechat.yaml`
- 按 `text` 去重（与 `data/quotes.yaml` 里已有的比对，含手工添加的）
- 追加到 `data/quotes.yaml` 末尾，保持原有内容与注释不动
- 打印新增 / 跳过的条数

之后正常构建发布即可。

### 一条划线的推荐字段映射

| 微信读书 | 这里的字段 |
|---|---|
| 划线原文 | `text` |
| 书名 + 作者 | `source`，形如 `《书名》· 作者` |

如果之后想保留更多信息（章节、时间、书 ID），先不要直接塞进 `text` ——
当前渲染只认 `text` 与 `source`，加别的字段不会显示。需要的话告诉我，
我再扩数据模型。

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
