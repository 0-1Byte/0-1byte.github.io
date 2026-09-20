# Music

这是 Hugo 网站里的个人音乐收藏页。

## 当前设计

页面只展示：

- 歌名
- 歌手
- 封面

不托管/播放 MP3。

你之前已经上传到 `static/music/assets/` 的 MP3 可以继续保留，不会被此版本引用或删除。

## 添加歌曲

1. 把封面放进：

```text
static/music/assets/
```

2. 修改：

```text
static/music/songs.json
```

加入：

```json
{
  "id": "unique-id",
  "title": "Song Title",
  "artist": "Artist",
  "cover": "/music/assets/cover.jpg"
}
```

多个条目用逗号分隔。

## 本地预览

在 Hugo 项目根目录：

```bash
hugo server
```

打开：

```text
http://localhost:1313/music/
```
