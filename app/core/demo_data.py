"""app/core/demo_data.py — syntetyczne pozycje do selftestów, screenshotów i dev-mode.

Zero sieci, zero zapisu do bazy: wyłącznie obiekty domenowe w pamięci.
"""

from __future__ import annotations

from typing import List

from app.domain.models import Donghua, MediaType, Status

_TITLES = [
    ("Doupo Cangqiong", 2017, 12),
    ("Doupo Cangqiong 2nd Season", 2018, 12),
    ("Doupo Cangqiong 3rd Season", 2019, 12),
    ("Doupo Cangqiong: Yuanqi", 2023, 12),
    ("Fanren Xiu Xian Zhuan", 2020, 17),
    ("Fanren Xiu Xian Zhuan 2nd Season", 2022, 46),
    ("Ling Long", 2019, 12),
    ("Wu Dong Qian Kun", 2019, 12),
    ("Wu Dong Qian Kun 2nd Season", 2020, 12),
    ("Xian Ni", 2023, 26),
    ("Shen Yin Wang Zuo", 2022, 26),
    ("Yao Shen Ji", 2017, 40),
    ("Yao Shen Ji 2nd Season", 2018, 40),
    ("Yao Shen Ji 3rd Season", 2019, 40),
    ("Yao Shen Ji 4th Season", 2020, 52),
    ("Quan Zhi Gao Shou", 2017, 12),
    ("Mo Dao Zu Shi", 2018, 15),
    ("Mo Dao Zu Shi 2nd Season", 2019, 15),
    ("Tian Bao Fuyao Lu", 2020, 13),
    ("Ding Hai Fusheng Lu", 2021, 12),
    ("Lie Huo Jiao Chou", 2019, 12),
    ("Can Ci Pin", 2021, 16),
    ("Shi Yi Chang An", 2019, 12),
    ("Feng Ying Zhi Ge", 2021, 12),
]

# Tytuły alternatywne (jak z MAL/AniList) — demo pokazuje drugą linię karty (r11).
# Brak wpisu = baza nie zwróciła alta (linia w karcie jest wtedy zwinięta).
_ALTS = {
    "Doupo Cangqiong": "Battle Through the Heavens",
    "Fanren Xiu Xian Zhuan": "A Record of a Mortal's Journey to Immortality",
    "Ling Long": "Ling Cage: Incarnation",
    "Wu Dong Qian Kun": "Martial Universe",
    "Xian Ni": "Renegade Immortal",
    "Shen Yin Wang Zuo": "Throne of Seal",
    "Yao Shen Ji": "Tales of Demons and Gods",
    "Quan Zhi Gao Shou": "The King's Avatar",
    "Mo Dao Zu Shi": "Grandmaster of Demonic Cultivation",
    "Tian Bao Fuyao Lu": "The Legend of Tianbao",
}

_DEMO_NOTE = "Numeracja na CDA: 52 + nr odcinka tego sezonu"


def demo_rows(count: int = 300) -> List[Donghua]:
    """Deterministyczna biblioteka demo (statusy/postępy rozłożone jak w realu)."""
    rows: List[Donghua] = []
    for i in range(count):
        title, year, total = _TITLES[i % len(_TITLES)]
        suffix = "" if i < len(_TITLES) else " (%d)" % (i // len(_TITLES) + 1)
        mod = i % 7
        if mod in (0, 1, 2):
            status = Status.WATCHING
            cur = (i * 3) % max(1, total)
        elif mod in (3, 4):
            status = Status.COMPLETED
            cur = total
        elif mod == 5:
            status = Status.PLANNED
            cur = 0
        else:
            status = Status.DROPPED
            cur = (i * 2) % max(1, total)
        rows.append(
            Donghua(
                id=i + 1,
                mal_id=30000 + i,
                provider="mal",
                title=title + suffix,
                title_alt=_ALTS.get(title),  # r11: alt tylko gdy baza go ma
                note=_DEMO_NOTE if i % 23 == 0 else None,
                total_episodes=total,
                current_episode=cur,
                status=status,
                media_type=MediaType.ONA if i % 3 else MediaType.TV,
                start_year=year,
                added_at="2026-01-01T00:00:00.000Z",
                updated_at="2026-09-01T00:00:00.000Z",
            )
        )
    return rows
