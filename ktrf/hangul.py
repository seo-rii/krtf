"""Hangul jamo decomposition/composition and dubeolsik keyboard channel.

Supports:
- syllable <-> (choseong, jungseong, jongseong) decomposition (§17.2)
- compat jamo run composition for the canonical stream (T-08, §14.7)
- jamo sequence representation for fuzzy matching (§17.2)
- dubeolsik key mapping for the keyboard channel (§17.4), e.g. 한전 <-> gkswjs
"""

from __future__ import annotations

SBASE = 0xAC00
LCOUNT, VCOUNT, TCOUNT = 19, 21, 28

CHOSEONG = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
JUNGSEONG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
JONGSEONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")

_CHO_INDEX = {c: i for i, c in enumerate(CHOSEONG)}
_JUNG_INDEX = {c: i for i, c in enumerate(JUNGSEONG)}
_JONG_INDEX = {c: i for i, c in enumerate(JONGSEONG) if c}

# compound jungseong built from two simple vowels
JUNG_COMPOSE = {
    ("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ",
    ("ㅜ", "ㅓ"): "ㅝ", ("ㅜ", "ㅔ"): "ㅞ", ("ㅜ", "ㅣ"): "ㅟ",
    ("ㅡ", "ㅣ"): "ㅢ",
}
JUNG_DECOMPOSE = {v: k for k, v in JUNG_COMPOSE.items()}

# compound jongseong built from two simple consonants
JONG_COMPOSE = {
    ("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ",
    ("ㄹ", "ㄱ"): "ㄺ", ("ㄹ", "ㅁ"): "ㄻ", ("ㄹ", "ㅂ"): "ㄼ",
    ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ", ("ㄹ", "ㅍ"): "ㄿ",
    ("ㄹ", "ㅎ"): "ㅀ", ("ㅂ", "ㅅ"): "ㅄ",
}
JONG_DECOMPOSE = {v: k for k, v in JONG_COMPOSE.items()}

_COMPAT_CONSONANTS = set(CHOSEONG) | set(c for c in JONGSEONG if c)
_COMPAT_VOWELS = set(JUNGSEONG)


def is_syllable(ch: str) -> bool:
    return SBASE <= ord(ch) < SBASE + LCOUNT * VCOUNT * TCOUNT


def is_compat_jamo(ch: str) -> bool:
    return 0x3131 <= ord(ch) <= 0x318E


def is_hangul(ch: str) -> bool:
    return is_syllable(ch) or is_compat_jamo(ch)


def decompose_syllable(ch: str) -> tuple[str, str, str] | None:
    """Return (cho, jung, jong) compat jamo, jong may be ''."""
    if not is_syllable(ch):
        return None
    s = ord(ch) - SBASE
    l, rem = divmod(s, VCOUNT * TCOUNT)
    v, t = divmod(rem, TCOUNT)
    return CHOSEONG[l], JUNGSEONG[v], JONGSEONG[t]


def compose_syllable(cho: str, jung: str, jong: str = "") -> str | None:
    l = _CHO_INDEX.get(cho)
    v = _JUNG_INDEX.get(jung)
    t = 0 if not jong else _JONG_INDEX.get(jong)
    if l is None or v is None or t is None:
        return None
    return chr(SBASE + (l * VCOUNT + v) * TCOUNT + t)


def has_batchim(ch: str) -> bool | None:
    """True/False for a Hangul syllable, None for anything else."""
    d = decompose_syllable(ch)
    if d is None:
        return None
    return d[2] != ""


def last_jongseong(ch: str) -> str | None:
    d = decompose_syllable(ch)
    return d[2] if d else None


def to_jamo_seq(s: str) -> str:
    """Flatten text to a jamo sequence for fuzzy matching (§17.2).

    Syllables expand to 2-3 simple jamo (compound jong/jung further split);
    other characters pass through unchanged.
    """
    out: list[str] = []
    for ch in s:
        d = decompose_syllable(ch)
        if d is None:
            out.append(ch)
            continue
        cho, jung, jong = d
        out.append(cho)
        out.extend(JUNG_DECOMPOSE.get(jung, (jung,)))
        if jong:
            out.extend(JONG_DECOMPOSE.get(jong, (jong,)))
    return "".join(out)


def compose_jamo_run(jamos: str) -> str:
    """Compose a jamo sequence into syllables using typing (automaton) rules.

    Used both for T-08 (compat jamo runs in the canonical stream) and the
    keyboard channel. Incomplete jamo are preserved as-is (spec T-08:
    "합성 불가 잔여 자모는 보존").
    """
    out: list[str] = []
    cho = jung = jong = ""
    n = len(jamos)

    def flush():
        nonlocal cho, jung, jong
        if cho and jung:
            out.append(compose_syllable(cho, jung, jong) or (cho + jung + jong))
        else:
            if cho:
                out.append(cho)
            if jung:
                out.append(jung)
            if jong:
                out.append(jong)
        cho = jung = jong = ""

    i = 0
    while i < n:
        ch = jamos[i]
        nxt = jamos[i + 1] if i + 1 < n else ""
        if ch in _COMPAT_CONSONANTS:
            if not cho and not jung:
                cho = ch
            elif cho and not jung:
                flush()
                cho = ch
            elif cho and jung and not jong:
                # candidate jongseong unless the next jamo is a vowel
                if nxt in _COMPAT_VOWELS or ch not in _JONG_INDEX:
                    flush()
                    cho = ch
                else:
                    jong = ch
            elif cho and jung and jong:
                combined = JONG_COMPOSE.get((jong, ch))
                if combined and nxt not in _COMPAT_VOWELS:
                    jong = combined
                else:
                    flush()
                    cho = ch
            else:  # jung without cho (shouldn't normally happen)
                flush()
                cho = ch
        elif ch in _COMPAT_VOWELS:
            if cho and jung and jong:
                # dokkaebi: last jong consonant moves to the next syllable
                pair = JONG_DECOMPOSE.get(jong)
                if pair:
                    keep, move = pair
                else:
                    keep, move = "", jong
                saved = move
                jong = keep
                flush()
                cho = saved
                jung = ch
            elif cho and jung:
                combined = JUNG_COMPOSE.get((jung, ch))
                if combined:
                    jung = combined
                else:
                    flush()
                    jung = ch
            elif cho:
                jung = ch
            else:
                if jung:
                    combined = JUNG_COMPOSE.get((jung, ch))
                    if combined:
                        jung = combined
                        i += 1
                        continue
                    flush()
                jung = ch
        else:
            flush()
            out.append(ch)
        i += 1
    flush()
    return "".join(out)


# ---------------------------------------------------------------------------
# Dubeolsik keyboard channel (§17.4)
# ---------------------------------------------------------------------------

KEY_TO_JAMO = {
    "q": "ㅂ", "w": "ㅈ", "e": "ㄷ", "r": "ㄱ", "t": "ㅅ",
    "y": "ㅛ", "u": "ㅕ", "i": "ㅑ", "o": "ㅐ", "p": "ㅔ",
    "a": "ㅁ", "s": "ㄴ", "d": "ㅇ", "f": "ㄹ", "g": "ㅎ",
    "h": "ㅗ", "j": "ㅓ", "k": "ㅏ", "l": "ㅣ",
    "z": "ㅋ", "x": "ㅌ", "c": "ㅊ", "v": "ㅍ", "b": "ㅠ",
    "n": "ㅜ", "m": "ㅡ",
    "Q": "ㅃ", "W": "ㅉ", "E": "ㄸ", "R": "ㄲ", "T": "ㅆ",
    "O": "ㅒ", "P": "ㅖ",
}
JAMO_TO_KEY = {}
for k, j in KEY_TO_JAMO.items():
    JAMO_TO_KEY.setdefault(j, k)

# QWERTY physical adjacency (subset used for adjacent-key cost)
_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
KEY_ADJACENT: dict[str, set[str]] = {}
for ri, row in enumerate(_ROWS):
    for ci, k in enumerate(row):
        adj = set()
        for dr in (-1, 0, 1):
            r2 = ri + dr
            if 0 <= r2 < len(_ROWS):
                for dc in (-1, 0, 1):
                    c2 = ci + dc
                    if (dr, dc) != (0, 0) and 0 <= c2 < len(_ROWS[r2]):
                        adj.add(_ROWS[r2][c2])
        KEY_ADJACENT[k] = adj


def keys_adjacent(a: str, b: str) -> bool:
    return b.lower() in KEY_ADJACENT.get(a.lower(), set())


def jamo_keys_adjacent(a: str, b: str) -> bool:
    """Adjacency of two jamo on the dubeolsik layout."""
    ka, kb = JAMO_TO_KEY.get(a), JAMO_TO_KEY.get(b)
    if ka is None or kb is None:
        return False
    return keys_adjacent(ka, kb)


def hangul_to_keys(s: str) -> str:
    """한전 -> gkswjs. Non-Hangul characters pass through."""
    return "".join(JAMO_TO_KEY.get(j, j) for j in to_jamo_seq(s))


def keys_to_hangul(s: str) -> str:
    """gkswjs -> 한전 (English-input-mode recovery)."""
    jamos = "".join(KEY_TO_JAMO.get(ch, ch) for ch in s)
    return compose_jamo_run(jamos)
