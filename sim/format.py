"""表示用フォーマットのユーティリティ。"""
from __future__ import annotations


def humanize_seconds(sec: float) -> str | None:
    """秒数を「X分Y秒」「X時間Y分」の読みやすい表記にする。

    60秒未満は併記不要のため None を返す。
    """
    if sec < 60:
        return None
    if sec < 3600:
        m = int(sec // 60)
        s = int(round(sec % 60))
        if s == 60:
            m += 1
            s = 0
        if m == 60:
            return "1時間0分"
        return f"{m}分{s}秒"
    h = int(sec // 3600)
    m = int(round((sec % 3600) / 60))
    if m == 60:
        h += 1
        m = 0
    return f"{h}時間{m}分"
