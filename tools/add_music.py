"""Deprecated old Music importer.

Use python tools/music_library.py add instead.
"""

from __future__ import annotations

import sys


print(
    "此旧加歌入口已停用。请在仓库根目录运行："
    "python tools/music_library.py add",
    file=sys.stderr,
)
raise SystemExit(2)
