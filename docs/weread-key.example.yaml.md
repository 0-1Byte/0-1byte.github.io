# 微信读书 API Key 模板（**不要**把真实 Key 填在这个文件里）

这个文件放在 `docs/` 下是刻意的：它离真正会被读取的路径
（`.secrets/key.yaml`）有一步距离，不容易误填。

## 曾经的教训

之前模板放在 `.secrets/key.example.yaml`，并在 `.gitignore` 里加了一条
`!.secrets/key.example.yaml` 反选让它入库。结果真实 Key 被填进了那个
「示例」文件，于是**完整 Key 进了 git 历史**，不得不重写全部提交。

**现在的规则：`.secrets/` 下的一切，一律不入库，没有例外。**

## 正确做法

1. 建立真正的 Key 文件：

   ```powershell
   copy .secrets\key.example.yaml .secrets\key.yaml
   ```

   （如果 `.secrets\key.example.yaml` 不存在，直接新建 `key.yaml` 即可，
     内容就下面这四行。）

2. 到 <https://weread.qq.com/r/weread-skills> 用微信读书账号登录，
   点「创建 Key」，复制 `wrk-` 开头的那串。

3. 填进 **`.secrets/key.yaml`**（不是这个文件）：

   ```yaml
   api_key: "wrk-你的Key"
   ```

4. 确认它不会被提交：

   ```powershell
   git check-ignore -v .secrets/key.yaml
   ```

   应当输出 `.gitignore` 里对应的规则行。

## 文件格式

```yaml
api_key: "wrk-xxxxxxxxxxxxxxxxxxxxxxxx"

# 可选：网关地址，正常情况不用改
# endpoint: "https://i.weread.qq.com/api/agent/gateway"
```

也支持用环境变量临时覆盖：`set WEREAD_API_KEY=wrk-...`

## 验证 Key 是否可用

```powershell
python tools/weread_probe.py        # 正常应列出你的笔记本
python tools/weread_diag.py         # 出问题时逐项定位
```
