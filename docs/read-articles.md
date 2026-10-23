# Articles 文章维护

日常推荐使用项目内的本地可视化管理器，无需输入命令或手动编辑 Markdown：

1. 双击 `devtools/read-manager/index.html`。
2. 点击「选择文章目录」，选择项目里的 `content/read/articles/`。
3. 用「新增文章」选择外部文章或站内全文，填写表单后保存。
4. 使用每篇文章旁的「上移」「下移」调整列表顺序。

如果浏览器直接打开 HTML 时不支持本地文件夹访问，双击
`devtools/read-manager/Start Read Manager.cmd`，再在打开的浏览器中操作。
首次使用需允许浏览器访问所选目录。删除前会要求确认，并在文章目录下的
`.read-manager-backups/` 留存备份。

管理器写入的仍是同一套 Markdown 文件：`content/read/articles/*.md`。
外部文章使用 `target: external` 和 `external_url`；站内全文使用
`target: local`，正文保存在同一个 Markdown 文件中。排序通过 `weight`
字段保存。Read 列表只显示标题。

本地预览网站可使用项目现有的 Hugo 预览流程；管理器只改本地文件，不会自动
提交、推送或发布。
