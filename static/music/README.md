# Personal Music Archive

一个适合 GitHub Pages 的个人音乐档案页。

它是纯静态网站：

- HTML
- CSS
- Vanilla JavaScript
- JSON
- 浏览器原生 `<audio>`

不需要 Node、数据库、后端或构建工具。

## 1. 文件结构

```text
music/
├── index.html
├── style.css
├── script.js
├── songs.json
└── assets/
    ├── cover-placeholder.svg
    ├── covers/
    └── audio/
```

把整个 `music/` 文件夹放进你的个人网站仓库即可：

```text
yourname.github.io/
├── index.html
├── ...
└── music/
    ├── index.html
    ├── style.css
    ├── script.js
    ├── songs.json
    └── assets/
```

上线后访问：

```text
https://yourname.github.io/music/
```

## 2. 添加一首歌

把音频放到：

```text
music/assets/audio/
```

例如：

```text
music/assets/audio/hurt.mp3
```

把封面放到：

```text
music/assets/covers/
```

例如：

```text
music/assets/covers/hurt.jpg
```

然后在 `songs.json` 增加：

```json
{
  "id": "hurt",
  "title": "Hurt",
  "artist": "Johnny Cash",
  "album": "American IV: The Man Comes Around",
  "year": 2002,
  "tags": ["Rock", "Night"],
  "cover": "./assets/covers/hurt.jpg",
  "audio": "./assets/audio/hurt.mp3",
  "note": "写一点你为什么喜欢这首歌。",
  "youtube": "",
  "spotify": "",
  "appleMusic": ""
}
```

注意：

1. 最后一条歌曲记录后面不能有逗号。
2. `id` 每首歌保持唯一。
3. 路径区分大小写，部署到服务器以后尤其要注意。

## 3. 不托管 MP3 也可以

如果你不想把原始音乐文件公开在 GitHub Pages，可以把：

```json
"audio": "./assets/audio/hurt.mp3"
```

改成：

```json
"audio": ""
```

网站仍然可以作为一个“音乐档案馆”使用，并保留：

- 歌曲名
- 歌手
- 专辑
- 年份
- 标签
- 个人笔记
- YouTube / Spotify / Apple Music 链接

例如：

```json
{
  "id": "hurt",
  "title": "Hurt",
  "artist": "Johnny Cash",
  "album": "American IV: The Man Comes Around",
  "year": 2002,
  "tags": ["Rock", "Night"],
  "cover": "./assets/covers/hurt.jpg",
  "audio": "",
  "note": "这首歌让我想起……",
  "youtube": "https://www.youtube.com/...",
  "spotify": "https://open.spotify.com/...",
  "appleMusic": "https://music.apple.com/..."
}
```

## 4. 播放器功能

已经包含：

- 播放 / 暂停
- 上一首 / 下一首
- 进度条
- 音量
- 随机播放
- 循环全部 / 单曲 / 关闭
- 搜索
- 分类标签
- 深色 / 浅色主题
- localStorage 保存音量、主题、当前歌曲和播放位置
- 自动播放下一首
- 移动端适配

键盘快捷键：

```text
Space       播放 / 暂停
← / →       前后移动 5 秒
N           下一首
P           上一首
/           聚焦搜索框
```

## 5. 本地预览

不要直接双击 `index.html`。

因为浏览器通常会阻止：

```text
file:///...
```

页面读取：

```text
songs.json
```

推荐用 VS Code 的 Live Server，或者在 `music/` 目录运行：

```bash
python -m http.server 8000
```

然后打开：

```text
http://localhost:8000
```

## 6. 关于文件大小

如果把 MP3 直接放进 Git 仓库，个人小型歌单比较合适。

如果音乐库越来越大，可以把音频迁移到对象存储，把 `songs.json` 中的 `audio` 改成完整 URL：

```json
"audio": "https://music.example.com/hurt.mp3"
```

这样 GitHub 仓库只负责网站代码和歌曲元数据。

## 7. 一个建议

不要一开始把它做成“音乐平台”。

先把它当成：

> 我的数字唱片架。

歌曲本身只是数据，真正长期有价值的是：

```text
我什么时候听到它
为什么喜欢
它让我想到谁 / 什么地方
它属于哪个阶段
```

所以 `note`、`tags`、`year` 这些字段可以慢慢积累。

几年后，这个页面会更像一份个人音乐记忆，而不只是播放器。
