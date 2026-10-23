# Read 文章管理器

本工具仅在本机运行，直接读取和修改用户明确选择的 `content/read/articles/`
文件夹，不会被 Hugo 构建发布。它不调用外部 API、不联网获取依赖，也不执行
Git 提交、推送或部署。

## 启动

推荐使用最新版 Microsoft Edge 或 Google Chrome：

1. 双击 `index.html`。
2. 点击「选择文章目录」，选择仓库中的 `content/read/articles/` 文件夹。
3. 允许该目录的读取和写入。

若浏览器以 `file://` 打开时不提供本地文件夹访问能力，双击
`Start Read Manager.cmd`。它会使用 PowerShell 启动一个只绑定
`127.0.0.1` 的静态文件服务，并打开浏览器。它只提供管理器自身的三个静态
文件，不提供文章读写 HTTP 接口；实际读写仍由浏览器在目录授权后完成。关闭
PowerShell 窗口即可停止服务。不要将该地址改为公网地址或监听 `0.0.0.0`。

浏览器可能在刷新或重启后要求重新授权。请使用「重新授权」或重新选择文章目录。
已记住的目录句柄保存在浏览器 IndexedDB；文章正文不会存进浏览器存储。

## 功能与数据安全

- 只扫描所选目录顶层的 Markdown 文件；`_index.md` 永远跳过。
- 无法识别的文件只显示警告，不提供编辑和删除操作。
- 新建、编辑和排序直接改对应 Markdown 文件；编辑元数据保留原正文和未管理的
  Front Matter 字段。
- 删除前要求确认，并先在 `.read-manager-backups/` 保存备份。
- 文件名必须使用安全的 ASCII slug。编辑时默认保留文件名；改名需要另行确认。
- 文章顺序写回 Hugo 使用的 `weight` 字段。
- 本工具不备份或修改所选目录之外的文件。

## 测试

在仓库根目录运行：

```powershell
node --test devtools/read-manager/core.test.cjs
```
