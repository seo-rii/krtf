"""Sentence cues that a registered name is being used for its namesake.

Korean sports writing names a team by its owner: `대한항공 7연승`,
`프로배구 한국전력 KB손보 꺾고`, `kt 박세진 2⅔이닝 5실점`. The string is
exactly the registered company, so the exact channel commits the company,
and nothing about the surface can say otherwise. Across the six cached
corpora that was every one of these occurrences.

Which entities have a namesake is the glossary's to declare
(``metadata.namesakes``), not this module's: a tenant knows that its own
product shares a name with a river or a film, and a built-in list of
companies would be a gazetteer pretending to be a rule. This module only
says what a *kind* of namesake looks like in a sentence.

The cues are the ones that do not occur outside the domain. `경기`, `시즌`,
`선수`, `승리`, `우승`, `리그`, `감독` are left out on purpose: in a first
measurement they fired on `경기 침체`, `실적 시즌`, `윗선수사` and
`금융감독원`, which is the finance news the companies themselves appear in.
"""

from __future__ import annotations

import re

_SPORTS_TEAM = re.compile(
    "|".join((
        # leagues and disciplines
        r"프로(?:야구|배구|농구|축구)", r"(?:남자|여자)(?:프로)?(?:배구|농구)",
        r"KBO", r"KBL", r"WKBL", r"V-?리그", r"K-?리그",
        r"(?:야구|배구|농구|축구)단",
        # results vocabulary
        r"\d*연승", r"\d+연패", r"역전승", r"역전패", r"완승", r"완패",
        r"탈꼴찌", r"선두\s?탈환", r"플레이오프", r"포스트시즌",
        r"챔(?:피언결정전|프전)", r"정규리그",
        # in-game vocabulary. `이닝` needs a count or a word start: bare, it
        # matched inside `홈트레이닝`. `강판` is left out — in these corpora
        # it is steel sheet far more often than a pitcher leaving the game.
        r"(?:\d+[⅓⅔]?|[⅓⅔])이닝", r"(?<![가-힣])이닝", r"홈런", r"\d*타점",
        r"\d+안타", r"선발\s?(?:출전|투수|등판)", r"세트\s?스코어",
        r"\d+득점", r"\d+실점", r"3점포", r"결승타", r"사이클링\s?히트",
        r"세터", r"풀세트", r"셧아웃",
        # results verbs news uses for games and not for companies. `꺾고` and
        # `잡고` are not here: market share is "꺾고" too, and `잡고` sits
        # inside `손잡고` in every partnership story.
        r"완파", r"격파", r"제압", r"대파", r"진땀승", r"대승",
        r"첫\s?승(?![인계격])", r"\d+승째", r"시즌\s?\d+승", r"연패\s?탈출",
        r"통합\s?우승", r"컵대회",
        # esports leagues, where the same companies field teams
        r"프로리그", r"\bLCK\b",
    )),
    re.IGNORECASE)

# A team nickname says something only when it is attached to the name —
# `kt wiz`, `KT 위즈`, `대한항공 점보스`. Anywhere in the sentence it matched
# `수원KT위즈파크` in a story about the company wiring the stadium, and
# `위즈스틱`, a product.
_TEAM_NICKNAME = re.compile(
    r"\s?(?:"
    r"(?:위즈|wiz|점보스|jumbos|빅스톰|vixtorm|롤스터|rolster)"
    # a particle may follow (`KT 위즈가`); a longer word may not
    r"(?:(?:가|는|를|의|와|에|에서|도|로|전|와의|에게)?(?![가-힣A-Za-z]))"
    # or a team staff title, optionally after the person's name:
    # `한국전력 장병철 감독`, `kt 감독`. A company's people are 상무 and
    # 본부장, not 감독 and 코치.
    r"|(?:[가-힣]{2,4}\s)?(?:감독|코치|수석코치|단장)"
    r"(?:은|는|이|가|을|를|의|에게|도|과|와)?(?![가-힣])"
    r")",
    re.IGNORECASE)

FOLLOWERS = {"sports_team": _TEAM_NICKNAME}

CUES = {"sports_team": _SPORTS_TEAM}

# Sentence boundary for the window the cues are read in. A cue elsewhere in a
# long document says nothing about this mention.
_SENTENCE_END = re.compile(r"[.!?。…]\s|\n")
MAX_WINDOW = 160


def sentence_window(text: str, span: tuple[int, int]) -> str:
    """The sentence containing ``span``, capped at ``MAX_WINDOW`` each side."""
    lo = max(0, span[0] - MAX_WINDOW)
    hi = min(len(text), span[1] + MAX_WINDOW)
    start = lo
    for m in _SENTENCE_END.finditer(text, lo, span[0]):
        start = m.end()
    m = _SENTENCE_END.search(text, span[1], hi)
    end = m.start() + 1 if m else hi
    return text[start:end]


def namesake_cue(text: str, span: tuple[int, int],
                 namesakes) -> str | None:
    """The first declared namesake kind whose cues appear in the sentence."""
    if not namesakes:
        return None
    window = None
    for kind in namesakes:
        follower = FOLLOWERS.get(kind)
        if follower is not None and follower.match(text, span[1]):
            return kind
        pattern = CUES.get(kind)
        if pattern is None:
            continue
        if window is None:
            window = sentence_window(text, span)
        if pattern.search(window):
            return kind
    return None
