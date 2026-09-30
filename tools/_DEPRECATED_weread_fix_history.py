"""⚠ 这个方案不完整，保留仅作记录。请用 tools/weread_scrub_history.py。

这里用 `git replace` 让历史遍历时指向改写后的提交。问题是：

  **replace 引用不会随 push 传出去。**

也就是说本地 `git log` 看起来干净了，但远端（以及任何 clone）里
原始提交仍然存在、仍然含 Key。它不能解决问题，只能骗过本地检查。

同样被否掉的方案：
  · git filter-branch —— 在本机（Windows + 沙箱 ACL）会抛栈回溯并中止，实测崩了三次
  · git filter-repo   —— 未安装

最终采用的是 tools/weread_scrub_history.py：
  fast-export -> 内存里替换 -> fast-import 写回同一仓库，
  提交哈希真正改变，push 出去也是干净的。

这个文件仅用于说明「为什么不用 replace」，不参与任何流程。
"""
