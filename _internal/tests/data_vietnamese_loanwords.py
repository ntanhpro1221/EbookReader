"""Established Vietnamese renderings of English words, as a second evaluation set.

Only words Vietnamese took from ENGLISH, and recently enough that the English pronunciation
is what shaped them.

Left out on purpose - these came through French or scientific Latin and follow that
pronunciation, so they would pull an English rule set the wrong way: ga-ra (garage),
cà phê (café), vắc-xin (vaccin), xà phòng (savon), sâm banh (champagne), cà vạt (cravate),
xăng (essence), bơ (beurre), ga (gare), pin (pile), sếp (chef), xì gà (cigare),
vi-ta-min (vitamine), vi-rút (virus), vi-đi-ô (video), sa-lát (salade), me-nu (menu),
mo-đen (modèle), pi-da (pizza, Italian), lô-gô, com-bo, tua (tour), ba (bar).
"""

LOANS = {
    # computing and the internet, all taken from English directly
    "market": "mác-két",
    "internet": "in-tơ-nét",
    "laptop": "láp-tóp",
    "facebook": "phây-búc",
    "google": "gu-gồ",
    "email": "i-meo",
    "website": "goép-sai",
    "server": "xe-vờ",
    "download": "đao-lôt",
    "click": "cờ-líc",
    "clip": "cờ-líp",
    "scan": "sờ-can",
    "copy": "cóp-pi",
    "chat": "chát",
    "app": "áp",
    "online": "on-lai",
    "poster": "pốt-tơ",
    # sport and leisure
    "tennis": "ten-nít",
    "golf": "gôn",
    "shorts": "soóc",
    "game": "gêm",
    "show": "sâu",
    "fan": "phan",
    "team": "tim",
    "goal": "gôn",
    "match": "mát",
    "set": "xét",
    # food and shopping
    "sandwich": "xăng-uých",
    "hamburger": "hem-bơ-gơ",
    "shop": "sóp",
    "bill": "biu",
    "sale": "xeo",
    "ship": "síp",
    "size": "sai",
    "style": "sờ-tai",
    # objects and general
    "card": "cạc",
    "taxi": "tắc-xi",
    "test": "tét",
    "tip": "típ",
    "boss": "bốt",
    "box": "bóc",
}
