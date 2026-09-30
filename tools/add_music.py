"""Batch-add songs from a UTF-8 text file using the iTunes Search API."""

from __future__ import print_function

import argparse
import http.client
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "static" / "music" / "songs.json"
COVERS_DIR = DATA_FILE.parent / "assets"
SEARCH_URL = (
    "https://itunes.apple.com/search?term={term}&entity=song&limit=50"
    "&country={country}"
)
SEARCH_COUNTRIES = ("HK", "TW", "CN", "SG", "US")
# Note: do NOT wrap CJK terms in %22 quotes — MusicBrainz Lucene often returns
# zero hits for quoted Chinese (e.g. work:"十年"), while unquoted terms work.
MUSICBRAINZ_SEARCH_URL = (
    "https://musicbrainz.org/ws/2/recording/?query=recording:{}%20AND%20artist:{}"
    "&fmt=json&limit=8"
)
MUSICBRAINZ_LOOKUP_URL = (
    "https://musicbrainz.org/ws/2/recording/{}"
    "?inc=artist-rels+work-rels&fmt=json"
)
MUSICBRAINZ_WORK_URL = (
    "https://musicbrainz.org/ws/2/work/{}"
    "?inc=artist-rels&fmt=json"
)
MUSICBRAINZ_WORK_SEARCH_URL = (
    "https://musicbrainz.org/ws/2/work/?query=work:{}%20AND%20artist:{}"
    "&fmt=json&limit=8"
)
USER_AGENT = "0-1byte.github.io music importer/1.0"

# Compressed Traditional→Simplified single-char map (fallback when zhconv is absent).
_CJK_HANS_B64 = (
    "eNokm9fWqzwPoM/nqtMhvfdGQi9JSCCQRnIv/4ss6Wi4hPH+Zi2eYGRJlo0tm4P8lTp/pe5fqfdX6v8Nz3/Dy98w+hsmf6Px3+j1N678jWt/Y+dv0v6blv+m"
    "w7/p4m9q/s3Of/Pb3/z3t2j+LcZ/i8nfYvW3OP2tt3+b2t+m/7cZ/G3mf5vj3yb9267/ttrfbve3f/1ppT+t/6fpf9rlT0v+Dp2/4/zvuPg7bv+M5Z9p/Znn"
    "P6v3Z63/rN2fM/9zvD/n/ef8/tz2nzv/czd/rvXnRn/u/c/r/XmrP2//FzT/Au/vYvxdTn/h8u9a/YtGf/H17z7/u3//ksZf2v1Lf38P5e+Z/b36f6/N3zv5"
    "+2z/st3fb/b3m//9Nn8/Oy8189IzL3t5+Z1Xenn1nNcHeT3KG81cDfPmMG8u82aQN295M8lbpbx1yltp3nrl7WrenuTtZd5e5W0rbz/z9jtvf/L2L++oeaed"
    "d2Z5Z5t39nnHzDth3jXyrpV3s7y3zHvXfKznUyOfRvmsns/lFeTzX77o54thvljly0m+POTLa75y83UtXw/y9SFfR/mmlG9m+XaSb0/59p1vP/lOzXftfDfO"
    "99V838j3g1wr5Voj1665luSHQX5w88M9Pzq5YeRmLTeV3Bzm5jQ357lp5qabm5fcvObWIrfWubXPrUtuRbl9zL1W7vVzb557i9yLc++b+6Xcr+T+Pvfj3E9y"
    "/5373zyo5sE4DxZ5sM2DXR7Y+amUn6r5aZifJvnpm59++bmWn7f5eZeftfzs5+cwP0f5+ZtfSvnFyMN9Hn7zaym/lvPrMr/a+TXIr2F+TfPrI79m+a2c3+r5"
    "bZbfFvktzKNFHm3y6JhHRh7ZeeTncTOP23kc5PE1j+M8zvJ7lN/jPGnlyTRPbvljnz/0/GHlz3n+fObPb/4q569K/lrmr23+2uWva/5K89c3z5Q8U/Nskmf3"
    "/NvIv7P8m+TfNP+V818l/43z3yT/afnPzH9B/ntDqQSlBpRUKDWh1IbSAEpDKM2gpEPJh9INSg8oN6E8hHIM5TuUM6h0oDKEygwqC6gsobKCyhEqJ6hcoBJB"
    "JYbKHSopVL5QrUC1DtUmVFtQ7UJ1CNUpVHdQNaBqQtWB6hWqT6iVoFaGWgVqNaipUGtCrQO1HtQGUJtAbQq1BdT2UNOh5kHtBLUb1FKoPaD2gtobah+oK1Dv"
    "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"
)
ARTIST_ALIASES = {
    "khalilfong": {"khalil fong", "方大同"},
    "jaychou": {"jay chou", "周杰伦"},
    "simpleplan": {"simple plan"},
    "celinedion": {"celine dion", "céline dion"},
    "easonchan": {"eason chan", "陈奕迅", "陳奕迅"},
    "eason": {"eason chan", "陈奕迅", "陳奕迅"},
    "chenyixun": {"eason chan", "陈奕迅", "陳奕迅"},
    "jackycheung": {"jacky cheung", "张学友", "張學友"},
    "zhangxueyou": {"jacky cheung", "张学友", "張學友"},
    "andy lau": {"andy lau", "刘德华"},
    "liudehua": {"andy lau", "刘德华", "劉德華"},
    "beyond": {"beyond", "BEYOND"},
    "wongka Kui": {"wong ka kui", "黄家驹"},
    "wongkakui": {"wong ka kui", "黄家驹"},
    "huangjiaju": {"wong ka kui", "黄家驹"},
    "leslieng": {"leslie cheung", "张国荣"},
    "lesliecheung": {"leslie cheung", "张国荣", "張國榮"},
    "zhangguorong": {"leslie cheung", "张国荣", "張國榮"},
    "alan tam": {"alan tam", "谭咏麟"},
    "tanyonglin": {"alan tam", "谭咏麟"},
    "priscilla chan": {"priscilla chan", "陈慧娴"},
    "chanwaihan": {"priscilla chan", "陈慧娴"},
    "sally yip": {"sally yip", "叶蒨文"},
    "yipsinman": {"sally yip", "叶蒨文"},
    "yipqingwen": {"sally yip", "叶蒨文"},
    "anita mui": {"anita mui", "梅艳芳"},
    "meiyanfang": {"anita mui", "梅艳芳"},
    "sammi cheng": {"sammi cheng", "郑秀文"},
    "zhengxiuwen": {"sammi cheng", "郑秀文"},
    "kay tse": {"kay tse", "谢安琪"},
    "xieanqi": {"kay tse", "谢安琪"},
    "joey yung": {"joey yung", "容祖儿"},
    "rongzuer": {"joey yung", "容祖儿"},
    "miriam yeung": {"miriam yeung", "杨千嬅"},
    "yeungchinwah": {"miriam yeung", "杨千嬅"},
    "yangqianhua": {"miriam yeung", "杨千嬅"},
    "leo ku": {"leo ku", "古巨基"},
    "gujuki": {"leo ku", "古巨基"},
    "hacken lee": {"hacken lee", "李克勤"},
    "likeqin": {"hacken lee", "李克勤"},
    "william so": {"william so", "苏永康"},
    "soyonghong": {"william so", "苏永康"},
    "alex fung": {"alex fung", "方力申"},
    "fungliksun": {"alex fung", "方力申"},
    "stephanie cheng": {"stephanie cheng", "郑融"},
    "zhengyung": {"stephanie cheng", "郑融"},
    "ivana wong": {"ivana wong", "王菀之"},
    "wongyuenchi": {"ivana wong", "王菀之"},
    "g.e.m.": {"g.e.m.", "邓紫棋"},
    "gem": {"g.e.m.", "邓紫棋"},
    "dengziqi": {"g.e.m.", "邓紫棋"},
    "jason chan": {"jason chan", "陈柏宇"},
    "chanpakyu": {"jason chan", "陈柏宇"},
    "juno mak": {"juno mak", "麦浚龙"},
    "makjuno": {"juno mak", "麦浚龙"},
    "khalil fong": {"khalil fong", "方大同"},
    "fongdaitong": {"khalil fong", "方大同"},
    "jay chou": {"jay chou", "周杰伦"},
    "zhoujielun": {"jay chou", "周杰伦", "周杰倫"},
    "wangfei": {"王菲", "王菲", "Faye Wong", "Wong Fei"},
    "fayewong": {"王菲", "Faye Wong", "Wong Fei"},
    "leoku": {"leo ku", "古巨基", "古巨基"},
    "vae": {"许嵩", "許嵩", "Vae", "Xu Song"},
    "xusong": {"许嵩", "許嵩", "Vae", "Xu Song"},
    "linyilian": {"林忆莲", "林憶蓮", "Sandy Lam", "Sandy Lam Yik-lin"},
    "sandy lam": {"林忆莲", "林憶蓮", "Sandy Lam", "Sandy Lam Yik-lin"},
    "sunyanzhi": {"孙燕姿", "孫燕姿", "Stefanie Sun"},
    "stefaniesun": {"孙燕姿", "孫燕姿", "Stefanie Sun"},
    "linyoujia": {"林宥嘉", "Yoga Lin"},
    "yogalin": {"林宥嘉", "Yoga Lin"},
    "lironghao": {"李荣浩", "李榮浩", "Li Ronghao", "Ronghao Li"},
    "li ronghao": {"李荣浩", "李榮浩", "Li Ronghao", "Ronghao Li"},
    "linjiaqian": {"林家谦", "林家謙", "Terence Lam", "Terence Lam Ka-him"},
    "林家谦": {"林家谦", "林家謙", "Terence Lam", "Terence Lam Ka-him"},
    "林家謙": {"林家谦", "林家謙", "Terence Lam", "Terence Lam Ka-him"},
    "terencelam": {"林家谦", "林家謙", "Terence Lam", "Terence Lam Ka-him"},
    "terence lam": {"林家谦", "林家謙", "Terence Lam", "Terence Lam Ka-him"},
}
KNOWN_CREDITS = {
    ("celinedion", "to love you more"): (
        "David Foster, Junior Miles",
        "David Foster, Junior Miles",
    ),
    ("easonchan", "任我行"): (
        "林夕",
        "Christopher Chak",
    ),
    ("easonchan", "let it out"): (
        "林若宁, Eric Kwok",
        "Eric Kwok",
    ),
    ("easonchan", "十年"): (
        "林夕",
        "陈小霞",
    ),
    ("easonchan", "富士山下"): (
        "林夕",
        "Christopher Chak",
    ),
    ("easonchan", "红玫瑰"): (
        "林夕",
        "周博贤",
    ),
    ("easonchan", "白玫瑰"): (
        "林夕",
        "周博贤",
    ),
    ("easonchan", "苦瓜"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "浮夸"): (
        "黄伟文",
        "Eric Kwok",
    ),
    ("easonchan", "裙下之臣"): (
        "林夕",
        "Eric Kwok",
    ),
    ("easonchan", "防不胜防"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "活着"): (
        "林夕",
        "Christopher Chak",
    ),
    ("easonchan", "孤勇者"): (
        "唐恬",
        "钱雷",
    ),
    ("easonchan", "我们"): (
        "林夕",
        "Eric Kwok",
    ),
    ("easonchan", "好久不见"): (
        "林夕",
        "陈小霞",
    ),
    ("easonchan", "岁月如歌"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "K歌之王"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "我的快乐时代"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "婚礼的祝福"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "不想放手"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "今天等我来"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "与我常在"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "爱是怀疑"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "夕阳无限好"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "不如不见"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "明年今日"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "落花流水"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "人来人往"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "爱情转移"): (
        "林夕",
        "Christopher Chak",
    ),
    ("easonchan", "沙龙"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "淘汰"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "葡萄成熟时"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "时代巨轮"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "陀飞轮"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "无人之境"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "是但求其爱"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "披风"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "重口味"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "不想让你失望"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "爱情转移"): (
        "林夕",
        "Christopher Chak",
    ),
    ("easonchan", "富士山下"): (
        "林夕",
        "Christopher Chak",
    ),
    ("easonchan", "红玫瑰"): (
        "林夕",
        "周博贤",
    ),
    ("easonchan", "白玫瑰"): (
        "林夕",
        "周博贤",
    ),
    ("easonchan", "苦瓜"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "浮夸"): (
        "黄伟文",
        "Eric Kwok",
    ),
    ("easonchan", "裙下之臣"): (
        "林夕",
        "Eric Kwok",
    ),
    ("easonchan", "防不胜防"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "活着"): (
        "林夕",
        "Christopher Chak",
    ),
    ("easonchan", "孤勇者"): (
        "唐恬",
        "钱雷",
    ),
    ("easonchan", "我们"): (
        "林夕",
        "Eric Kwok",
    ),
    ("easonchan", "好久不见"): (
        "林夕",
        "陈小霞",
    ),
    ("easonchan", "岁月如歌"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "K歌之王"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "我的快乐时代"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "婚礼的祝福"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "不想放手"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "今天等我来"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "与我常在"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "爱是怀疑"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "夕阳无限好"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "不如不见"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "明年今日"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "落花流水"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "人来人往"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "爱情转移"): (
        "林夕",
        "Christopher Chak",
    ),
    ("easonchan", "沙龙"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "淘汰"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "葡萄成熟时"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "时代巨轮"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "陀飞轮"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "无人之境"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "是但求其爱"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "披风"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "重口味"): (
        "林夕",
        "陈辉阳",
    ),
    ("easonchan", "不想让你失望"): (
        "林夕",
        "陈辉阳",
    ),
        ("jackycheung", "吻别"): (
            "何厚华",
            "劉志文",
    ),
        ("jackycheung", "一千个伤心的理由"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "等你等到我心痛"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "慢慢"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "李香兰"): (
            "林振强",
            "玉置浩二",
        ),
        ("jackycheung", "分手总要在雨天"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "忘记你我做不到"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "三天两夜"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "祝福"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "如果这都不算爱"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "她来听我的演唱会"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "每天爱你多一些"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "爱是永恒"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "只想一生跟你走"): (
            "林夕",
            "陈辉阳",
        ),
        ("jackycheung", "吻别"): (
            "何厚华",
            "劉志文",
        ),
        ("beyond", "海阔天空"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "光辉岁月"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "真的爱你"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "不再犹豫"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "喜欢你"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "大地"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "谁伴我闯荡"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "旧日的足迹"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "冷雨夜"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "遥远的梦"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "AMANI"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "长城"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "俾面派对"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "早班火车"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "农民"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "灰色轨迹"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "真的爱你"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "光辉岁月"): (
            "黄家驹",
            "黄家驹",
        ),
        ("beyond", "海阔天空"): (
            "黄家驹",
            "黄家驹",
        ),
        ("lesliecheung", "追"): (
            "林振强",
            "Dick Lee",
        ),
        ("lesliecheung", "风继续吹"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "有谁共鸣"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "Monica"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "为你钟情"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "共同度过"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "无心睡眠"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "当年情"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "侧面"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "热情的沙漠"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "谁令你心痴"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "沉默是金"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "追"): (
            "林振强",
            "Dick Lee",
        ),
        ("lesliecheung", "风继续吹"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "有谁共鸣"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "Monica"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "为你钟情"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "共同度过"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "无心睡眠"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "当年情"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "侧面"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "热情的沙漠"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "谁令你心痴"): (
            "林振强",
            "玉置浩二",
        ),
        ("lesliecheung", "沉默是金"): (
            "林振强",
            "玉置浩二",
        ),
        ("andylau", "忘情水"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "冰雨"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "练习"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "笨小孩"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "中国人"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "爱不完"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "谢谢你的爱"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "来生缘"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "暗里着迷"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "男人的爱"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "忘情水"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "冰雨"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "练习"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "笨小孩"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "中国人"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "爱不完"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "谢谢你的爱"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "来生缘"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "暗里着迷"): (
            "刘德华",
            "刘德华",
        ),
        ("andylau", "男人的爱"): (
            "刘德华",
            "刘德华",
        ),
        ("khalilfong", "love song"): (
            "方大同",
            "方大同",
        ),
    ("khalilfong", "手拖手"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "take me"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "好不容易"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "romeo"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "bb88"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "悟空"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "gf"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "tango"): (
        "方大同",
        "方大同",
    ),
    ("simpleplan", "astronaut"): (
        "Pierre Bouvier, Chuck Comeau, David Desrosiers, Sébastien Lefebvre, Jeff Stinco",
        "Pierre Bouvier, Chuck Comeau, David Desrosiers, Sébastien Lefebvre, Jeff Stinco",
    ),
    ("hermanosgutierrez", "esperanza"): (
        "",
        "Daniel Alejandro Hotz, Stephan Ricardo Hotz",
    ),
    ("linkinpark", "numb"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "in the end"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "what i've done"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "crawling"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "one step closer"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "breaking the habit"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "faint"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "shadow of the day"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "leave out all the rest"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "new divide"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("jaychou", "断了的弦"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "完美主义"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "反方向的钟"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "开不了口"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "安静"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "半岛铁盒"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "暗号"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "分裂"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "最后的战役"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "以父之名"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "晴天"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "三年二班"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "东风破"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "你听得到"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "她的睫毛"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "梯田"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "七里香"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "借口"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "外婆"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "搁浅"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "园游会"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "止战之殇"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "夜曲"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "发如雪"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "黑色毛衣"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "枫"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "浪漫手机"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "珊瑚海"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "漂移"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "一路向北"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "夜的第七章"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "听妈妈的话"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "退后"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "菊花台"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "牛仔很忙"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "彩虹"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "我不配"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "最长的电影"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "给我一首歌的时间"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "花海"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "说好的幸福呢"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "兰亭序"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "流浪诗人"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "时光机"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "稻香"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "说了再见"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "烟花易冷"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "我落泪情绪零碎"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "红尘客栈"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "哪里都是你"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "美人鱼"): (
        "方文山",
        "周杰伦",
    ),
    ("linjiaqian", "某种老朋友"): (
        "林夕",
        "Christopher Chak",
    ),
    ("linjiaqian", "一人之境"): (
        "林家谦",
        "林家谦",
    ),
    ("linjiaqian", "普渡众生"): (
        "林家谦",
        "林家谦",
    ),
    ("adele", "chasing pavements"): (
        "Adele",
        "Adele, Eg White",
    ),
    ("adele", "rolling in the deep"): (
        "Adele, Paul Epworth",
        "Adele, Paul Epworth",
    ),
    ("adele", "don't you remember"): (
        "Adele, Dan Wilson",
        "Adele, Dan Wilson",
    ),
    ("adele", "take it all"): (
        "Adele, Francis White",
        "Adele, Francis White",
    ),
    ("adele", "one and only"): (
        "Adele, Greg Wells, Dan Wilson",
        "Adele, Greg Wells, Dan Wilson",
    ),
    ("adele", "river lea"): (
        "Adele, Brian Burton",
        "Adele, Brian Burton",
    ),
    ("adele", "love in the dark"): (
        "Adele, Samuel Dixon",
        "Adele, Samuel Dixon",
    ),
    ("adele", "million years ago"): (
        "Adele, Greg Kurstin",
        "Adele, Greg Kurstin",
    ),
    ("adele", "all i ask"): (
        "Adele, Brody Brown, Philip Lawrence, Bruno Mars",
        "Adele, Brody Brown, Philip Lawrence, Bruno Mars",
    ),
    ("adele", "easy on me"): (
        "Adele, Greg Kurstin",
        "Adele, Greg Kurstin",
    ),
    ("adele", "i drink wine"): (
        "Adele, Greg Kurstin",
        "Adele, Greg Kurstin",
    ),
}

# Songs that the iTunes Search API fails to return (lookup-by-id still works).
# Key: (normalize_artist(artist), normalize(title)) -> iTunes trackId
KNOWN_ITUNES_IDS = {
    ("glassanimals", "the other side of paradise"): 1440840442,
}

LOOKUP_URL = "https://itunes.apple.com/lookup?id={}&entity=song&country={}"


def clean_title(value):
    return str(value or "").replace("\ufeff", "").replace("\u200b", "").strip()


def normalize(value):
    value = unicodedata.normalize("NFKC", clean_title(value))
    return " ".join(value.casefold().split())


def normalize_artist(value):
    value = unicodedata.normalize("NFKD", normalize(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def _has_cjk(value):
    return any("\u4e00" <= ch <= "\u9fff" for ch in (value or ""))


_CJK_HANS_TRANSLATE = None


def _get_cjk_hans_table():
    """Lazy-load a Traditional→Simplified translate table (zhconv or embedded)."""
    global _CJK_HANS_TRANSLATE
    if _CJK_HANS_TRANSLATE is not None:
        return _CJK_HANS_TRANSLATE
    try:
        import zhconv

        # Use zhconv via a thin wrapper object with .translate-like API
        class _ZhconvTable(object):
            def convert(self, text):
                return zhconv.convert(text, "zh-cn")

        _CJK_HANS_TRANSLATE = _ZhconvTable()
        return _CJK_HANS_TRANSLATE
    except Exception:
        pass
    # Embedded fallback map (single-char 繁→简); kept compressed to limit file size.
    try:
        import base64
        import zlib

        raw = zlib.decompress(base64.b64decode(_CJK_HANS_B64)).decode("utf-8")
        trad, simp = raw.split("\n", 1)
        _CJK_HANS_TRANSLATE = str.maketrans(trad, simp)
    except Exception:
        _CJK_HANS_TRANSLATE = {}
    return _CJK_HANS_TRANSLATE


def _cjk_to_hans(value):
    """Fold Traditional Chinese to Simplified Chinese."""
    text = value or ""
    if not text:
        return text
    table = _get_cjk_hans_table()
    if hasattr(table, "convert"):
        return table.convert(text)
    if table:
        return text.translate(table)
    return text


def to_simplified(value):
    """Convert text fields to Simplified Chinese for JSON storage."""
    if not value or not isinstance(value, str):
        return value
    return _cjk_to_hans(value)


def build_artist_alias_index():
    index = {}
    for canonical, aliases in ARTIST_ALIASES.items():
        group = {canonical, *aliases}
        normalized_group = {normalize_artist(name) for name in group if normalize_artist(name)}
        for name in normalized_group:
            index.setdefault(name, set()).update(normalized_group)
    return index


ARTIST_ALIAS_INDEX = build_artist_alias_index()


def artist_matches(actual, expected):
    actual_normalized = normalize_artist(actual)
    expected_normalized = normalize_artist(expected)
    if not actual_normalized or not expected_normalized:
        return False
    if actual_normalized == expected_normalized:
        return True

    # 简繁体折合后再比（林家谦 vs 林家謙）
    actual_hans = normalize_artist(_cjk_to_hans(actual))
    expected_hans = normalize_artist(_cjk_to_hans(expected))
    if actual_hans and actual_hans == expected_hans:
        return True

    actual_names = ARTIST_ALIAS_INDEX.get(actual_normalized, {actual_normalized})
    expected_names = ARTIST_ALIAS_INDEX.get(expected_normalized, {expected_normalized})
    # Also index under simplified forms so 林家谦 hits 林家謙 alias group
    if actual_hans:
        actual_names = actual_names | ARTIST_ALIAS_INDEX.get(actual_hans, set()) | {actual_hans}
    if expected_hans:
        expected_names = expected_names | ARTIST_ALIAS_INDEX.get(expected_hans, set()) | {expected_hans}

    return any(
        actual_name == expected_name
        or actual_name in expected_name
        or expected_name in actual_name
        for actual_name in actual_names
        for expected_name in expected_names
    )


def parse_song_reference(value):
    value = clean_title(value)
    if "|" in value:
        artist, title = value.split("|", 1)
        return clean_title(title), clean_title(artist)
    if " - " in value:
        artist, title = value.split(" - ", 1)
        return clean_title(title), clean_title(artist)
    return value, ""


def slug(title, artist):
    value = re.sub(
        r"[^\w\u4e00-\u9fff]+",
        "-",
        "{}-{}".format(artist, title).casefold(),
    ).strip("-")
    return value or "song"


def fetch_json(url):
    last_error = None
    for attempt in range(3):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT + " (contact: site-maintainer)",
                },
            )
            with urlopen(request, timeout=30) as response:
                content = response.read()
            return json.loads(content.decode("utf-8"))
        except (OSError, http.client.HTTPException, ValueError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(1)
    raise OSError("接口响应不完整或无效：{}".format(last_error))


def collect_credit_names(relationships, credit_type):
    names = []
    for relation in relationships:
        if relation.get("type") != credit_type:
            continue
        artist = relation.get("artist") or relation.get("target", {})
        name = artist.get("name") if isinstance(artist, dict) else ""
        if name and name not in names:
            names.append(name)
    return names


def collect_work_credits(relationships):
    writers = collect_credit_names(relationships, "writer")
    composers = collect_credit_names(relationships, "composer")
    lyricists = collect_credit_names(relationships, "lyricist")
    if writers:
        if not composers:
            composers = writers
        if not lyricists:
            lyricists = writers
    return lyricists, composers


def _credit_query_variants(title, artist):
    """Yield a small set of (title, artist) pairs for MusicBrainz (简繁 / 别名)."""
    seen = set()
    titles = [title]
    artists = [artist]
    try:
        import zhconv

        for t in (zhconv.convert(title, "zh-cn"), zhconv.convert(title, "zh-tw")):
            if t and t not in titles:
                titles.append(t)
        for a in (zhconv.convert(artist, "zh-cn"), zhconv.convert(artist, "zh-tw")):
            if a and a not in artists:
                artists.append(a)
    except Exception:
        pass
    # Prefer human-readable alias labels from ARTIST_ALIASES (not normalized keys).
    artist_key = normalize_artist(artist)
    for canonical, aliases in ARTIST_ALIASES.items():
        group = {canonical, *aliases}
        normalized_group = {normalize_artist(n) for n in group if n}
        if artist_key in normalized_group:
            for candidate in group:
                if candidate and candidate not in artists:
                    artists.append(candidate)
            break
    # Cap combinations to keep API usage reasonable (MusicBrainz rate-limits).
    pairs = []
    for t in titles:
        for a in artists:
            key = (normalize(t), normalize_artist(a))
            if key in seen or not t or not a:
                continue
            seen.add(key)
            pairs.append((t, a))
            if len(pairs) >= 6:
                return pairs
    return pairs


def _lookup_known_credits(title, artist):
    """Match KNOWN_CREDITS using artist aliases and 简繁 title variants."""
    title_keys = {normalize(title)}
    try:
        import zhconv

        title_keys.add(normalize(zhconv.convert(title, "zh-cn")))
        title_keys.add(normalize(zhconv.convert(title, "zh-tw")))
    except Exception:
        pass
    # Also fold via embedded table
    title_keys.add(normalize(_cjk_to_hans(title)))
    artist_keys = {normalize_artist(artist)}
    artist_keys.update(ARTIST_ALIAS_INDEX.get(normalize_artist(artist), set()))
    artist_keys.add(normalize_artist(_cjk_to_hans(artist)))
    artist_keys.update(
        ARTIST_ALIAS_INDEX.get(normalize_artist(_cjk_to_hans(artist)), set())
    )
    for ak in artist_keys:
        for tk in title_keys:
            known = KNOWN_CREDITS.get((ak, tk))
            if known:
                return known
    return None


def _parse_lrc_credits(lrc_text):
    """Extract 作词/作曲 from NetEase-style LRC header lines."""
    lyricist = ""
    composer = ""
    if not lrc_text:
        return lyricist, composer
    for raw_line in lrc_text.splitlines()[:25]:
        line = re.sub(r"^\[\d+:\d+[.\d]*\]", "", raw_line).strip()
        if not line:
            continue
        for pattern, target in (
            (r"^作词\s*[:：]\s*(.+)$", "lyricist"),
            (r"^作曲\s*[:：]\s*(.+)$", "composer"),
            (r"^词\s*[:：]\s*(.+)$", "lyricist"),
            (r"^曲\s*[:：]\s*(.+)$", "composer"),
            (r"^Lyricist\s*[:：]\s*(.+)$", "lyricist"),
            (r"^Composer\s*[:：]\s*(.+)$", "composer"),
        ):
            match = re.match(pattern, line, flags=re.IGNORECASE)
            if not match:
                continue
            name = match.group(1).strip()
            # Drop trailing junk like "/编曲: xxx" if present
            name = re.split(r"\s*[;/|]\s*", name)[0].strip()
            if target == "lyricist" and not lyricist and name:
                lyricist = name
            elif target == "composer" and not composer and name:
                composer = name
    return lyricist, composer


def _netease_search_songs(keyword, limit=8):
    """Search NetEase Cloud Music (no login). Returns list of song dicts."""
    url = (
        "https://music.163.com/api/search/get?"
        + "s={}&type=1&offset=0&limit={}".format(quote(keyword), limit)
    )
    last_error = None
    for attempt in range(3):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": "https://music.163.com/",
                    "Accept": "application/json",
                },
            )
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("unexpected response")
            return ((data.get("result") or {}).get("songs")) or []
        except (OSError, http.client.HTTPException, ValueError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(1)
    raise OSError("网易云搜索失败：{}".format(last_error))


def _netease_lyric(song_id):
    url = (
        "https://music.163.com/api/song/lyric?"
        + "id={}&lv=-1&kv=-1&tv=-1".format(song_id)
    )
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://music.163.com/",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        return ""
    return ((data.get("lrc") or {}).get("lyric")) or ""


def _credits_title_ok(candidate_title, requested_title):
    """Strict title gate for credit lookup — avoids 张冠李戴."""
    score = title_score(candidate_title, requested_title)
    if score >= 96:
        return True
    # Core equality after 简繁 fold (title_score may be 0 before fold in edge cases)
    a = normalize(_cjk_to_hans(title_core(candidate_title)))
    b = normalize(_cjk_to_hans(title_core(requested_title)))
    return bool(a and a == b)


def find_credits_netease(title, artist):
    """Look up lyricist/composer via NetEase lyric headers (strong for C-pop).

    Requires a tight title match AND artist match when artist is known, so we
    never take credits from a different song that merely shares a keyword.
    """
    if not title:
        return "", ""
    core = title_core(title) or title
    hans_core = _cjk_to_hans(core)
    hans_artist = _cjk_to_hans(artist) if artist else ""

    # Prefer short, clean queries (core title) — long iTunes titles with tribute
    # / 滚石40 / 原唱 noise break search and scoring.
    queries = []
    if artist:
        queries.append("{} {}".format(artist, core).strip())
        if hans_artist and hans_core:
            queries.append("{} {}".format(hans_artist, hans_core).strip())
    queries.append(core)
    if hans_core and hans_core != core:
        queries.append(hans_core)

    seen_q = set()
    seen_ids = set()
    for query in queries:
        qn = normalize(query)
        if not qn or qn in seen_q:
            continue
        seen_q.add(qn)
        try:
            time.sleep(0.35)
            songs = _netease_search_songs(query)
        except (OSError, ValueError, KeyError) as error:
            print(
                "网易云搜索失败：{} ({})".format(query, error),
                file=sys.stderr,
            )
            continue

        ranked = []
        for item in songs:
            if not isinstance(item, dict):
                continue
            track = item.get("name") or ""
            artists = [
                a.get("name", "")
                for a in (item.get("artists") or [])
                if isinstance(a, dict)
            ]
            if not _credits_title_ok(track, title) and not _credits_title_ok(
                track, core
            ):
                continue
            if artist:
                if not any(artist_matches(a, artist) for a in artists):
                    continue
            t_score = title_score(track, title) or title_score(track, core)
            # Prefer studio over live/cover-ish titles
            if is_variant_recording(track, core):
                t_score -= 20
            ranked.append((t_score, item, track))

        ranked.sort(key=lambda x: x[0], reverse=True)
        for _score, item, track in ranked[:3]:
            song_id = item.get("id")
            if not song_id or song_id in seen_ids:
                continue
            seen_ids.add(song_id)
            try:
                time.sleep(0.35)
                lrc = _netease_lyric(song_id)
            except (OSError, ValueError, KeyError, http.client.HTTPException):
                continue
            lyricist, composer = _parse_lrc_credits(lrc)
            if lyricist or composer:
                return lyricist, composer
    return "", ""


def find_credits(title, artist):
    if not artist:
        return "", ""
    lyricist = ""
    composer = ""

    known = _lookup_known_credits(title, artist)
    if known:
        lyricist, composer = known[0] or "", known[1] or ""
        if lyricist and composer:
            return lyricist, composer

    # NetEase for C-pop (LRC headers often include 作词/作曲).
    try:
        ne_l, ne_c = find_credits_netease(title, artist)
        lyricist = lyricist or ne_l
        composer = composer or ne_c
        if lyricist and composer:
            return lyricist, composer
    except (OSError, ValueError, KeyError) as error:
        print(
            "网易云词曲查询失败，将尝试 MusicBrainz：{} ({})".format(title, error),
            file=sys.stderr,
        )

    core = title_core(title) or title
    # Prefer core title for MB queries (same reason as NetEase)
    variants = _credit_query_variants(core, artist)
    if normalize(core) != normalize(title):
        variants = list(variants) + list(_credit_query_variants(title, artist))
    tried_works = set()
    tried_recordings = set()

    # MusicBrainz work search — lyricist/composer usually live on the work entity.
    for q_title, q_artist in variants:
        time.sleep(1)
        try:
            work_data = fetch_json(
                MUSICBRAINZ_WORK_SEARCH_URL.format(quote(q_title), quote(q_artist))
            )
        except (OSError, ValueError, KeyError) as error:
            print(
                "MusicBrainz work 搜索失败：{} — {} ({})".format(
                    q_artist, q_title, error
                ),
                file=sys.stderr,
            )
            continue
        for work in work_data.get("works", []):
            work_id = work.get("id")
            if not work_id or work_id in tried_works:
                continue
            work_title = work.get("title", "")
            # Strict: never take credits from a differently titled work
            if not _credits_title_ok(work_title, title) and not _credits_title_ok(
                work_title, core
            ):
                continue
            tried_works.add(work_id)
            time.sleep(1)
            try:
                details = fetch_json(MUSICBRAINZ_WORK_URL.format(work_id))
            except (OSError, ValueError, KeyError):
                continue
            lyricists, composers = collect_work_credits(details.get("relations", []))
            if lyricists or composers:
                lyricist = lyricist or ", ".join(lyricists)
                composer = composer or ", ".join(composers)
                if lyricist and composer:
                    return lyricist, composer

    # 2) Recording search → linked works (covers cases work search misses).
    for q_title, q_artist in variants:
        time.sleep(1)
        try:
            data = fetch_json(
                MUSICBRAINZ_SEARCH_URL.format(quote(q_title), quote(q_artist))
            )
        except (OSError, ValueError, KeyError) as error:
            print(
                "MusicBrainz recording 搜索失败：{} — {} ({})".format(
                    q_artist, q_title, error
                ),
                file=sys.stderr,
            )
            continue
        recordings = data.get("recordings", [])
        candidates = [
            item
            for item in recordings
            if (
                _credits_title_ok(item.get("title", ""), title)
                or _credits_title_ok(item.get("title", ""), core)
            )
            and any(
                artist_matches(credit.get("name", ""), artist)
                for credit in item.get("artist-credit", [])
                if isinstance(credit, dict)
            )
        ]
        # Never fall back to unmatched recordings — that caused 张冠李戴.
        for recording in candidates:
            recording_id = recording.get("id")
            if not recording_id or recording_id in tried_recordings:
                continue
            tried_recordings.add(recording_id)
            time.sleep(1)
            try:
                details = fetch_json(MUSICBRAINZ_LOOKUP_URL.format(recording_id))
            except (OSError, ValueError, KeyError):
                continue
            lyricists, composers = collect_work_credits(details.get("relations", []))
            for relation in details.get("relations", []):
                work_id = (relation.get("work") or {}).get("id")
                if not work_id or work_id in tried_works:
                    continue
                tried_works.add(work_id)
                time.sleep(1)
                try:
                    work = fetch_json(MUSICBRAINZ_WORK_URL.format(work_id))
                except (OSError, ValueError, KeyError):
                    continue
                work_lyricists, work_composers = collect_work_credits(
                    work.get("relations", [])
                )
                lyricists = work_lyricists or lyricists
                composers = work_composers or composers
            if lyricists or composers:
                lyricist = lyricist or ", ".join(lyricists)
                composer = composer or ", ".join(composers)
                if lyricist and composer:
                    return lyricist, composer

    return lyricist, composer


def enrich_missing_credits(songs, refresh=False):
    """Fill or refresh lyricist/composer; convert names to 简体.

    By default only fills empty fields. With refresh=True (or when the script
    is run with --refresh-credits), re-queries and overwrites existing values
    so previously 张冠李戴的 credits can be corrected.
    """
    changed = False
    targets = [
        song
        for song in songs
        if isinstance(song, dict)
        and (
            refresh
            or not (song.get("lyricist") and song.get("composer"))
        )
    ]
    if targets:
        print(
            "正在{}词曲信息（共 {} 首）…".format(
                "刷新" if refresh else "补全", len(targets)
            )
        )
    for song in targets:
        try:
            lyricist, composer = find_credits(
                song.get("title", ""),
                song.get("artist", ""),
            )
        except (OSError, ValueError, KeyError) as error:
            print(
                "词曲信息查询失败，将保留现有数据：{} ({})".format(
                    song.get("title", ""), error
                ),
                file=sys.stderr,
            )
            continue
        lyricist = to_simplified(lyricist) if lyricist else ""
        composer = to_simplified(composer) if composer else ""
        updated = False
        if lyricist and (refresh or not song.get("lyricist")):
            if song.get("lyricist") != lyricist:
                song["lyricist"] = lyricist
                changed = True
                updated = True
            elif not song.get("lyricist"):
                song["lyricist"] = lyricist
                changed = True
                updated = True
        if composer and (refresh or not song.get("composer")):
            if song.get("composer") != composer:
                song["composer"] = composer
                changed = True
                updated = True
            elif not song.get("composer"):
                song["composer"] = composer
                changed = True
                updated = True
        # Normalize residual fields to 简体
        for field in ("lyricist", "composer", "title", "artist", "album"):
            val = song.get(field)
            if val:
                simplified = to_simplified(val)
                if simplified != val:
                    song[field] = simplified
                    changed = True
        if updated:
            print(
                "已{}词曲：{} — 词：{}；曲：{}".format(
                    "更正" if refresh else "补充",
                    song.get("title", ""),
                    song.get("lyricist") or "未找到",
                    song.get("composer") or "未找到",
                )
            )
        elif not lyricist and not composer and not (
            song.get("lyricist") and song.get("composer")
        ):
            print(
                "未找到词曲：{} — {}".format(
                    song.get("title", ""), song.get("artist", "")
                ),
                file=sys.stderr,
            )
    return changed


def cache_cover(url, title, artist):
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    path = COVERS_DIR / "{}.jpg".format(slug(title, artist))
    last_error = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                content = response.read()
            if not content:
                raise OSError("封面内容为空")
            path.write_bytes(content)
            return "/music/assets/{}".format(quote(path.name))
        except (OSError, http.client.HTTPException) as error:
            last_error = error
            if attempt < 2:
                time.sleep(1)
    raise OSError("封面下载失败：{}".format(last_error))


def title_core(value):
    """Normalize a song title while ignoring version / tribute / live suffixes.

    Cuts at the first parenthesis so nested noise like
    「大雨 (滚石40 滚石撞乐队 40团拼经典 (原唱:娃娃))」→「大雨」.
    """
    value = normalize(value)
    # Drop featured-artist suffixes first
    value = re.sub(
        r"\s*[-–—]\s*(?:feat\.?|ft\.?|with)\s+.+$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    # Cut everything from the first opening bracket/parenthesis
    value = re.split(r"\s*[\(\[（【]", value, 1)[0].strip()
    # Trailing version tokens without parentheses
    value = re.sub(
        r"\s*[-–—_]?\s*(?:live|remix|remastered|remaster|karaoke|instrumental|"
        r"acoustic|demo|radio\s*edit|version|现场|現場|演唱会|演唱會|伴奏|重制|重製)\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip()


def _cjk_char_overlap(actual, expected):
    """Fraction of expected CJK chars found in actual (order-agnostic)."""
    exp_chars = [ch for ch in expected if "\u4e00" <= ch <= "\u9fff"]
    if not exp_chars:
        return 0.0
    act_set = set(ch for ch in actual if "\u4e00" <= ch <= "\u9fff")
    hits = sum(1 for ch in exp_chars if ch in act_set)
    return hits / len(exp_chars)


def title_matches(actual, expected):
    actual_norm = normalize(actual)
    expected_norm = normalize(expected)
    if not actual_norm or not expected_norm:
        return False
    if actual_norm == expected_norm:
        return True
    actual_core = title_core(actual)
    expected_core = title_core(expected)
    if actual_core == expected_core:
        return True
    # 简繁体折合后再比
    if _cjk_to_hans(actual_core) == _cjk_to_hans(expected_core) and expected_core:
        return True
    return expected_norm in actual_norm or expected_core in actual_core


def title_score(actual, expected):
    actual_norm = normalize(actual)
    expected_norm = normalize(expected)
    actual_core = title_core(actual)
    expected_core = title_core(expected)
    if actual_norm == expected_norm:
        return 120
    if actual_core == expected_core and actual_core:
        return 108
    if expected_norm and expected_norm in actual_norm:
        return 100
    if expected_core and expected_core in actual_core:
        return 96
    # 简繁体：折成简体后相等（有 zhconv 时最准；无库时退回原文）
    actual_hans = normalize(_cjk_to_hans(actual_core or actual_norm))
    expected_hans = normalize(_cjk_to_hans(expected_core or expected_norm))
    if actual_hans and actual_hans == expected_hans:
        return 110
    if expected_hans and expected_hans in actual_hans:
        return 98
    # 无 zhconv 时的兜底：CJK 字符重叠（海阔天空 vs 海闊天空 → 0.75）
    # Require equal core length so 2-char near-misses don't 张冠李戴.
    if _has_cjk(expected_norm) and _has_cjk(actual_norm):
        ac = actual_core or actual_norm
        ec = expected_core or expected_norm
        if len(ac) == len(ec) and len(ec) > 0:
            overlap = _cjk_char_overlap(ac, ec)
            if overlap >= 0.75:
                return 104
            # 吻别/吻別：一半字符相同且等长
            if overlap >= 0.5 and len(ec) <= 3:
                return 100
    return 0


def is_variant_recording(actual, requested):
    actual_norm = normalize(actual)
    requested_norm = normalize(requested)
    if actual_norm == requested_norm:
        return False
    return bool(re.search(
        r"\b(live|remix|remastered|remaster|karaoke|instrumental|acoustic|demo|edit|version|mix)\b|现场|現場|演唱会|演唱會|伴奏|重制|重製",
        actual_norm,
        flags=re.IGNORECASE,
    ))


def search_itunes(query, country, song_only=False):
    """Search one storefront. song_only limits matching to song title."""
    encoded_query = quote(query)
    url = SEARCH_URL.format(term=encoded_query, country=country)
    if song_only:
        url += "&attribute=songTerm"
    return fetch_json(url)


def candidate_score(item, title, artist_hint, country_rank, query_kind):
    track_name = item.get("trackName", "")
    artist_name = item.get("artistName", "")
    score = title_score(track_name, title)
    # Title must have some real overlap. Artist match alone must never rescue a
    # completely different song (e.g. Heat Waves for The Other Side of Paradise).
    if score == 0:
        return -10**9
    if artist_hint:
        if artist_matches(artist_name, artist_hint):
            score += 85
        else:
            return -10**9
    # Search-engine relevance is useful when the store uses Traditional Chinese
    # for the returned title and exact Unicode equality cannot represent the same title.
    if query_kind == "artist+title":
        score += 12
    else:
        score += 4
    # Prefer HK/TW/SG before US only as a deterministic tiebreaker.
    score -= country_rank
    # Prefer the requested/base studio track over versioned recordings.
    if is_variant_recording(track_name, title):
        score -= 18
    # Require a cover because the caller depends on it.
    if not item.get("artworkUrl100"):
        return -10**9
    return score


def collect_candidates(title, artist_hint, query, query_kind, country_rank):
    candidates = []
    for country in SEARCH_COUNTRIES:
        rank = country_rank + SEARCH_COUNTRIES.index(country)
        try:
            data = search_itunes(query, country, song_only=(query_kind == "title"))
        except (OSError, ValueError, KeyError, http.client.HTTPException) as error:
            print(
                "搜索失败 [{}] {}：{}".format(country, query, error),
                file=sys.stderr,
            )
            continue
        for position, item in enumerate(data.get("results", [])):
            if not isinstance(item, dict) or not item.get("trackName"):
                continue
            score = candidate_score(item, title, artist_hint, rank, query_kind)
            if score <= -10**8:
                continue
            # A small penalty keeps earlier API results ahead when all else is equal.
            score -= position * 0.01
            candidates.append((score, item, country, position))
        # A strong exact title + artist match is enough; don't hammer all storefronts.
        strong = [x for x in candidates if x[0] >= 190]
        if strong:
            break
    return candidates


def explain_match(actual_title, actual_artist, expected_title, expected_artist):
    """Return a human-readable explanation useful when debugging a new song."""
    return (
        "标题得分={}；歌手匹配={}；API艺人={!r}；API歌名={!r}".format(
            title_score(actual_title, expected_title),
            artist_matches(actual_artist, expected_artist) if expected_artist else True,
            actual_artist,
            actual_title,
        )
    )


def song_from_itunes_item(result, title, country="US"):
    """Build the song dict from an iTunes track result (search or lookup).

    Text fields are stored in Simplified Chinese when conversion is available.
    """
    raw_title = result.get("trackName") or title
    raw_artist = result.get("artistName", "")
    # Prefer a clean studio title: drop live/movie parentheticals when core matches request
    core_requested = title_core(title)
    core_actual = title_core(raw_title)
    if core_requested and (
        normalize(_cjk_to_hans(core_actual)) == normalize(_cjk_to_hans(core_requested))
        or title_score(raw_title, title) >= 96
    ):
        # Keep iTunes title if it has no extra suffix; otherwise use the core form
        if normalize(raw_title) != normalize(core_actual) and core_actual:
            display_title = core_actual
        else:
            display_title = raw_title
    else:
        display_title = raw_title

    artist = raw_artist
    lyricist = ""
    composer = ""
    try:
        lyricist, composer = find_credits(title, artist)
    except (OSError, ValueError, KeyError) as error:
        print(
            "词曲信息查询失败，将继续添加歌曲：{} ({})".format(title, error),
            file=sys.stderr,
        )
    cover_url = result["artworkUrl100"].replace("100x100", "600x600")

    # Normalize display fields to Simplified Chinese for JSON storage
    display_title = to_simplified(display_title)
    artist = to_simplified(artist)
    lyricist = to_simplified(lyricist) if lyricist else ""
    composer = to_simplified(composer) if composer else ""
    album = to_simplified(result.get("collectionName", "") or "")
    tags = []
    if result.get("primaryGenreName"):
        tags = [to_simplified(result["primaryGenreName"])]

    song = {
        "id": slug(display_title or title, artist or raw_artist),
        "title": display_title,
        "artist": artist,
        "lyricist": lyricist,
        "composer": composer,
        "cover": cover_url,
        "album": album,
        "year": (result.get("releaseDate") or "")[:4],
        "tags": tags,
        "url": result.get("trackViewUrl", ""),
    }
    try:
        song["cover"] = cache_cover(cover_url, song["title"], artist)
    except OSError as error:
        print(
            "封面无法缓存，将保留远程地址：{} ({})".format(title, error),
            file=sys.stderr,
        )
    return song


def lookup_itunes_track(track_id):
    """Fetch a track by iTunes ID across preferred storefronts."""
    last_error = None
    for country in SEARCH_COUNTRIES:
        try:
            data = fetch_json(LOOKUP_URL.format(track_id, country))
        except (OSError, ValueError, KeyError, http.client.HTTPException) as error:
            last_error = error
            continue
        for item in data.get("results", []):
            if (
                isinstance(item, dict)
                and item.get("wrapperType") == "track"
                and int(item.get("trackId") or 0) == int(track_id)
                and item.get("artworkUrl100")
            ):
                return item, country
    if last_error:
        raise OSError("lookup 失败：{}".format(last_error))
    return None, None


def find_song(title, artist_hint=""):
    """Find the best iTunes song match across multiple storefronts."""
    # Some tracks never appear in Search API results; use known IDs first.
    known_id = KNOWN_ITUNES_IDS.get(
        (normalize_artist(artist_hint), normalize(title))
    )
    if known_id is None and not artist_hint:
        known_id = KNOWN_ITUNES_IDS.get(("", normalize(title)))
    if known_id is not None:
        try:
            result, country = lookup_itunes_track(known_id)
        except (OSError, ValueError, KeyError) as error:
            print(
                "已知曲目 lookup 失败，将回退搜索：{} ({})".format(title, error),
                file=sys.stderr,
            )
            result = None
        if result:
            print(
                "使用已知 iTunes ID：{} — {} [{}] id={}".format(
                    result.get("artistName", ""),
                    result.get("trackName", ""),
                    country,
                    known_id,
                )
            )
            return song_from_itunes_item(result, title, country)

    # Pass 1: artist + title. This is the most precise query and should be tried first.
    candidates = collect_candidates(
        title,
        artist_hint,
        "{} {}".format(artist_hint, title).strip(),
        "artist+title",
        0,
    )

    # Pass 2: title-only. This is important for Traditional/Simplified script
    # differences because iTunes may return the same song under a different script.
    if not candidates:
        candidates = collect_candidates(
            title,
            artist_hint,
            title,
            "title",
            20,
        )

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, result, country, position = candidates[0]

    # Do not accept a merely artist-matched random result when the search itself
    # did not contain the title signal. In normal cases the API returns the target
    # song because the query contains its exact user-supplied title.
    if artist_hint and not artist_matches(result.get("artistName", ""), artist_hint):
        return None

    # Title must meaningfully match; artist match alone is not enough.
    if title_score(result.get("trackName", ""), title) == 0:
        return None

    if best_score < 90:
        return None

    if normalize(result.get("trackName", "")) != normalize(title):
        print(
            "使用近似标题匹配：{} — {} -> {} — {} [{}]".format(
                artist_hint or "",
                title,
                result.get("artistName", ""),
                result.get("trackName", ""),
                country,
            )
        )

    return song_from_itunes_item(result, title, country)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch-add songs from a UTF-8 text file."
    )
    parser.add_argument(
        "titles",
        nargs="*",
        help="Song titles; quote titles containing spaces.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Read one song title per line (default: music-list.txt).",
    )
    parser.add_argument(
        "--remove",
        nargs="+",
        metavar="SONG",
        help="Remove songs by title, or by 'artist | title'.",
    )
    parser.add_argument(
        "--remove-file",
        type=Path,
        help="Read songs to remove, one per line.",
    )
    parser.add_argument(
        "--refresh-credits",
        action="store_true",
        help="Re-query and overwrite lyricist/composer for all songs (fix 张冠李戴).",
    )
    return parser.parse_args()


def read_titles(args):
    titles = [clean_title(title) for title in args.titles if clean_title(title)]
    input_file = args.file or ROOT / "music-list.txt"
    if input_file:
        try:
            lines = input_file.read_text(encoding="utf-8-sig").splitlines()
        except OSError as error:
            print("无法读取 {}: {}".format(input_file, error), file=sys.stderr)
            return titles, False
        titles.extend(
            clean_title(line)
            for line in lines
            if clean_title(line) and not clean_title(line).lstrip().startswith("#")
        )
    return titles, True


def remove_references(args):
    references = [clean_title(value) for value in (args.remove or [])]
    if args.remove_file:
        try:
            lines = args.remove_file.read_text(encoding="utf-8-sig").splitlines()
        except OSError as error:
            print("无法读取 {}: {}".format(args.remove_file, error), file=sys.stderr)
            return references, False
        references.extend(
            clean_title(line)
            for line in lines
            if clean_title(line) and not clean_title(line).lstrip().startswith("#")
        )
    return references, True


def remove_songs(songs, references):
    """Remove songs matching references (supports 简繁 and core-title match)."""
    removed = []
    kept = []
    for song in songs:
        matched = False
        song_title = song.get("title") or ""
        song_artist = song.get("artist") or ""
        for reference in references:
            title, artist = parse_song_reference(reference)
            title_ok = (
                normalize(song_title) == normalize(title)
                or normalize(_cjk_to_hans(song_title))
                == normalize(_cjk_to_hans(title))
                or normalize(_cjk_to_hans(title_core(song_title)))
                == normalize(_cjk_to_hans(title_core(title)))
            )
            if not title_ok:
                continue
            if not artist or artist_matches(song_artist, artist):
                matched = True
                break
        if matched:
            removed.append(song)
        else:
            kept.append(song)
    return kept, removed


def remove_unused_covers(removed, remaining):
    used_covers = {
        normalize(song.get("cover"))
        for song in remaining
        if isinstance(song, dict)
    }
    for song in removed:
        cover = song.get("cover", "")
        if not cover.startswith("/music/assets/"):
            continue
        if normalize(cover) in used_covers:
            continue
        cover_path = ROOT / "static" / cover.lstrip("/")
        try:
            cover_path.unlink()
            print("已删除本地封面：{}".format(cover_path.name))
        except FileNotFoundError:
            pass
        except OSError as error:
            print("本地封面删除失败：{} ({})".format(cover_path, error), file=sys.stderr)


def optimize_cover_derivatives():
    """新增/删除歌曲后，自动补齐封面下载尺寸的 WebP 衍生图。

    复用 tools/optimize_music_covers.py（增量执行，只处理新封面，
    通常 1~2 秒）。这一步是幂等的，失败也只是一条警告 —— 不能因为
    图片优化出问题就影响加歌本身，所以整体 catch 住。
    """
    try:
        import importlib.util

        module_path = Path(__file__).resolve().parent / "optimize_music_covers.py"
        spec = importlib.util.spec_from_file_location("optimize_music_covers", module_path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        print()
        print("正在生成封面 WebP 衍生图 ...")
        result = module.optimize(verbose=False)
        if result.get("ok"):
            print("封面衍生图已就绪：生成 {} 个，跳过 {} 个，img 字段更新 {} 条。".format(
                result["generated"], result["skipped"], result["changed"]
            ))
        else:
            print("封面衍生图未全部生成，可手动运行 "
                  "python tools/optimize_music_covers.py 排查。", file=sys.stderr)
    except Exception as error:  # noqa: BLE001 - 图片优化不应影响加歌主流程
        print("封面衍生图生成失败（不影响本次加歌）：{}".format(error), file=sys.stderr)
        print("可手动运行 python tools/optimize_music_covers.py 重试。", file=sys.stderr)


def main():
    args = parse_args()
    remove_references_list, readable = remove_references(args)
    if not readable:
        return 1
    if remove_references_list and (args.titles or args.file):
        print("删除模式不能同时处理新增歌曲，请分开执行。", file=sys.stderr)
        return 2
    try:
        songs = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print("无法读取 {}: {}".format(DATA_FILE, error), file=sys.stderr)
        return 1
    if not isinstance(songs, list):
        print("songs.json 必须是数组", file=sys.stderr)
        return 1

    if remove_references_list:
        songs, removed = remove_songs(songs, remove_references_list)
        if not removed:
            print("没有找到要删除的歌曲。", file=sys.stderr)
            return 1
        DATA_FILE.write_text(
            json.dumps(songs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        remove_unused_covers(removed, songs)
        for song in removed:
            print("已删除：{} — {}".format(
                song.get("title", ""),
                song.get("artist", ""),
            ))
        print("完成：删除 {} 首，当前共 {} 首。".format(len(removed), len(songs)))
        optimize_cover_derivatives()
        return 0

    credits_changed = enrich_missing_credits(
        songs, refresh=bool(args.refresh_credits)
    )

    titles, readable = read_titles(args)
    if not readable:
        return 1
    if not titles:
        if credits_changed:
            DATA_FILE.write_text(
                json.dumps(songs, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print("完成：词曲已更新，当前共 {} 首。".format(len(songs)))
        else:
            print("没有可导入的歌曲。请把歌曲名逐行写入 music-list.txt。")
            print("提示：用 --refresh-credits 可强制重查全部词曲。")
        return 0

    existing = {
        (normalize(song.get("title")), normalize(song.get("artist")))
        for song in songs
        if isinstance(song, dict)
    }
    added = 0
    for reference in titles:
        title, artist_hint = parse_song_reference(reference)
        try:
            song = find_song(title, artist_hint)
        except (OSError, ValueError, KeyError, http.client.HTTPException) as error:
            print("查询失败：{} ({})".format(reference, error), file=sys.stderr)
            continue
        if not song or not song.get("cover"):
            print(
                "未找到匹配歌曲：{}{}".format(
                    artist_hint + " — " if artist_hint else "",
                    title,
                ),
                file=sys.stderr,
            )
            continue
        key = (normalize(song["title"]), normalize(song["artist"]))
        if key in existing:
            print("跳过（已存在）：{} — {}".format(
                song["title"], song["artist"]
            ))
            continue
        songs.append(song)
        existing.add(key)
        added += 1
        print("已添加：{} — {}".format(song["title"], song["artist"]))

    if added or credits_changed:
        DATA_FILE.write_text(
            json.dumps(songs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("完成：新增 {} 首，当前共 {} 首。".format(added, len(songs)))
    optimize_cover_derivatives()
    return 0


if __name__ == "__main__":
    sys.exit(main())
