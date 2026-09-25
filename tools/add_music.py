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
MUSICBRAINZ_SEARCH_URL = (
    "https://musicbrainz.org/ws/2/recording/?query=recording:%22{}%22"
    "%20AND%20artist:%22{}%22&fmt=json&limit=5"
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
    "https://musicbrainz.org/ws/2/work/?query=work:%22{}%22"
    "%20AND%20artist:%22{}%22&fmt=json&limit=5"
)
USER_AGENT = "0-1byte.github.io music importer/1.0"
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


def clean_title(value):
    return str(value or "").replace("\ufeff", "").replace("\u200b", "").strip()


def normalize(value):
    value = unicodedata.normalize("NFKC", clean_title(value))
    return " ".join(value.casefold().split())


def normalize_artist(value):
    value = unicodedata.normalize("NFKD", normalize(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


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

    actual_names = ARTIST_ALIAS_INDEX.get(actual_normalized, {actual_normalized})
    expected_names = ARTIST_ALIAS_INDEX.get(expected_normalized, {expected_normalized})

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


def find_credits(title, artist):
    if not artist:
        return "", ""
    known = KNOWN_CREDITS.get((normalize_artist(artist), normalize(title)))
    if known:
        return known
    time.sleep(1)
    search_url = MUSICBRAINZ_SEARCH_URL.format(quote(title), quote(artist))
    data = fetch_json(search_url)
    recordings = data.get("recordings", [])
    wanted_title = normalize(title)
    wanted_artist = normalize_artist(artist)
    candidates = [
        item for item in recordings
        if (
            normalize(item.get("title")) == wanted_title
            or wanted_title in normalize(item.get("title"))
        )
        and any(
            wanted_artist == normalize_artist(credit.get("name", ""))
            or wanted_artist in normalize_artist(credit.get("name", ""))
            for credit in item.get("artist-credit", [])
            if isinstance(credit, dict)
        )
    ]
    for recording in candidates or recordings:
        recording_id = recording.get("id")
        if not recording_id:
            continue
        details = fetch_json(MUSICBRAINZ_LOOKUP_URL.format(recording_id))
        lyricists, composers = collect_work_credits(details.get("relations", []))
        work_ids = [
            relation.get("work", {}).get("id")
            for relation in details.get("relations", [])
            if relation.get("work", {}).get("id")
        ]
        for work_id in work_ids:
            time.sleep(1)
            work = fetch_json(MUSICBRAINZ_WORK_URL.format(work_id))
            work_lyricists, work_composers = collect_work_credits(
                work.get("relations", [])
            )
            lyricists = work_lyricists or lyricists
            composers = work_composers or composers
        if lyricists or composers:
            return ", ".join(lyricists), ", ".join(composers)
    work_data = fetch_json(
        MUSICBRAINZ_WORK_SEARCH_URL.format(quote(title), quote(artist))
    )
    for work in work_data.get("works", []):
        work_id = work.get("id")
        if not work_id:
            continue
        time.sleep(1)
        details = fetch_json(MUSICBRAINZ_WORK_URL.format(work_id))
        lyricists, composers = collect_work_credits(
            details.get("relations", [])
        )
        if lyricists or composers:
            return ", ".join(lyricists), ", ".join(composers)
    return "", ""


def enrich_missing_credits(songs):
    changed = False
    for song in songs:
        if not isinstance(song, dict) or (
            song.get("lyricist") and song.get("composer")
        ):
            continue
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
        if lyricist and not song.get("lyricist"):
            song["lyricist"] = lyricist
            changed = True
        if composer and not song.get("composer"):
            song["composer"] = composer
            changed = True
        if lyricist or composer:
            print(
                "已补充词曲：{} — 词：{}；曲：{}".format(
                    song.get("title", ""),
                    lyricist or "未找到",
                    composer or "未找到",
                )
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
    """Normalize a song title while ignoring common version suffixes."""
    value = normalize(value)
    # Keep the base title, but ignore common release/version decorations.
    value = re.sub(
        r"\s*[\(\[（【][^\)\]）】]*(?:live|live in|remix|remastered|remaster|karaoke|instrumental|acoustic|demo|edit|version|mix|现场|現場|演唱会|演唱會|伴奏|重制|重製)[^\)\]）】]*[\)\]）】]$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value


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


def find_song(title, artist_hint=""):
    """Find the best iTunes song match across multiple storefronts."""
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

    if title_score(result.get("trackName", ""), title) == 0 and best_score < 95:
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

    artist = result.get("artistName", "")
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
    song = {
        "id": slug(result.get("trackName") or title, artist),
        "title": result.get("trackName") or title,
        "artist": artist,
        "lyricist": lyricist,
        "composer": composer,
        "cover": cover_url,
        "album": result.get("collectionName", ""),
        "year": (result.get("releaseDate") or "")[:4],
        "tags": [result["primaryGenreName"]] if result.get("primaryGenreName") else [],
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
    removed = []
    kept = []
    for song in songs:
        matched = False
        song_title = normalize(song.get("title"))
        song_artist = normalize(song.get("artist"))
        for reference in references:
            title, artist = parse_song_reference(reference)
            if song_title == normalize(title) and (
                not artist
                or song_artist == normalize(artist)
                or normalize(artist) in song_artist
            ):
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
        return 0

    credits_changed = enrich_missing_credits(songs)

    titles, readable = read_titles(args)
    if not readable:
        return 1
    if not titles:
        print("没有可导入的歌曲。请把歌曲名逐行写入 music-list.txt。")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
