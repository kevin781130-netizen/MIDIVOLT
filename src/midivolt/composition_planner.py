"""Deterministic, zero-network natural-language MIDI orchestration planner.

This module describes requested instrument tracks; it does not call models,
choose unrequested instruments, produce notes, or apply edits to the source.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Role:
    name: str
    label: str
    aliases: tuple[str, ...]
    gm_hint: int | None = None
    drum: bool = False
    family: str = ""


ROLES = (
    Role("drums", "Drum kit", ("drum kit", "drums", "drum", "鼓組", "鼓组", "鼓點", "鼓点", "爵士鼓", "鼓"), drum=True),
    Role("bass", "Bass", ("bass guitar", "electric bass", "bass", "貝斯", "贝斯", "電貝斯", "电贝斯", "低音吉他")),
    Role("piano", "Piano", ("grand piano", "piano", "鋼琴", "钢琴"), gm_hint=0),
    Role("guitar", "Guitar", ("electric guitar", "acoustic guitar", "guitar", "電吉他", "电吉他", "木吉他", "吉他")),
    Role("keys", "Keyboard / synth", ("synthesizer", "synth", "keyboard", "keyboards", "keys", "鍵盤", "键盘", "合成器")),
    Role("strings", "String ensemble", ("string ensemble", "strings", "弦樂", "弦乐"), gm_hint=48, family="strings"),
    Role("violin", "Violin", ("violin", "violins", "小提琴"), gm_hint=40, family="strings"),
    Role("viola", "Viola", ("viola", "violas", "中提琴"), gm_hint=41, family="strings"),
    Role("cello", "Cello", ("cello", "cellos", "violoncello", "大提琴"), gm_hint=42, family="strings"),
    Role("woodwinds", "Woodwind ensemble", ("woodwinds", "woodwind", "木管樂", "木管乐", "木管"), family="woodwinds"),
    Role("flute", "Flute", ("flute", "flutes", "長笛", "长笛"), gm_hint=73, family="woodwinds"),
    Role("oboe", "Oboe", ("oboe", "oboes", "雙簧管", "双簧管"), gm_hint=68, family="woodwinds"),
    Role("clarinet", "Clarinet", ("clarinet", "clarinets", "單簧管", "单簧管"), gm_hint=71, family="woodwinds"),
    Role("bassoon", "Bassoon", ("bassoon", "bassoons", "巴松管", "低音管"), gm_hint=70, family="woodwinds"),
)
_ROLE_BY_NAME = {role.name: role for role in ROLES}
# Every English token is bounded to avoid false matches such as "embassy".
_ALIASES = sorted(
    ((alias, role.name) for role in ROLES for alias in role.aliases),
    key=lambda item: len(item[0]), reverse=True,
)
_PATTERNS = [
    (re.compile(
        (r"(?<![A-Za-z])" if alias.isascii() else "") +
        re.escape(alias) +
        (r"(?![A-Za-z])" if alias.isascii() else ""),
        re.IGNORECASE,
    ), name) for alias, name in _ALIASES
]
_EN_NEG = re.compile(
    r"(?:\b(?:no|without|exclude|omit|avoid|not|don't|do\s+not)\b"
    r"(?:\s+(?:any|the|add|include|use|want|play|generate|more|new)){0,4}\s*)$",
    re.IGNORECASE,
)
_ZH_NEG = re.compile(r"(?:不要|不需要|不加|不加入|不使用|排除|移除|沒有|没有|無|无|別加|别加)\s*(?:加|加入|任何)?\s*$")
_NEG_JOIN = re.compile(r"\s*(?:(?:,|，|、|及|和|與|与|&|\bor\b|\band\b)\s*)+", re.IGNORECASE)


def _matches(prompt: str) -> list[tuple[int, int, str]]:
    found = []
    for pattern, name in _PATTERNS:
        for m in pattern.finditer(prompt):
            found.append((m.start(), m.end(), name))
    # Longest matching alias wins when two phrases overlap.
    found.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    selected = []
    for item in found:
        if not selected or item[0] >= selected[-1][1]:
            selected.append(item)
    return selected


def make_composition_plan(
    prompt: str,
    *,
    source_track_count: int,
    locked_tracks: tuple[int, ...],
) -> dict:
    """Extract only explicit parts and exclusions; fail closed on ambiguity.

    A generic family request is replaced by named members if both are present,
    preventing duplicate ensemble + individual part instructions. GM hints are
    0-based, advisory and never silently assigned to an ambiguous instrument.
    """
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2048:
        raise ValueError("Prompt must contain 1..2048 non-whitespace characters.")
    if type(source_track_count) is not int or not 1 <= source_track_count <= 1024:
        raise ValueError("Source must contain 1..1024 tracks.")
    if not isinstance(locked_tracks, tuple) or not locked_tracks:
        raise ValueError("Explicit source track locks are mandatory.")
    if len(set(locked_tracks)) != len(locked_tracks) or any(
        type(i) is not int or i < 0 or i >= source_track_count
        for i in locked_tracks
    ):
        raise ValueError("Locked track indices must be unique and in range.")

    hits = _matches(prompt)
    yes, no = set(), set()
    prev_end, prev_negative = 0, False
    for start, end, name in hits:
        prefix = prompt[max(0, start - 80):start]
        immediate_negative = bool(_EN_NEG.search(prefix) or _ZH_NEG.search(prefix))
        # "without bass and drums" / "不要鼓和貝斯": both members excluded.
        inherited_negative = (
            prev_negative and bool(_NEG_JOIN.fullmatch(prompt[prev_end:start]))
        )
        negative = immediate_negative or inherited_negative
        (no if negative else yes).add(name)
        prev_end, prev_negative = end, negative

    if yes & no:
        raise ValueError("Contradictory requested and excluded instrument: " +
                         ", ".join(sorted(yes & no)))
    if not yes:
        raise ValueError("No explicitly requested instruments found; specify tracks.")
    # Excluding a whole family conflicts with requesting one of its members.
    for family in ("strings", "woodwinds"):
        if family in no and any(
            r.family == family and r.name != family and r.name in yes for r in ROLES
        ):
            raise ValueError("Cannot request a part from an excluded instrument family.")
        named = [r.name for r in ROLES if r.family == family and r.name != family]
        if family in yes and any(n in yes for n in named):
            yes.remove(family)

    parts = []
    for role in ROLES:
        if role.name not in yes:
            continue
        parts.append({
            "role": role.name,
            "label": role.label,
            "is_drum": role.drum,
            "gm_program_hint": role.gm_hint,
            "requires_program_selection": not role.drum and role.gm_hint is None,
            "instruction": (
                f"Create ONLY one separate {role.label} MIDI part. "
                f"Respect the original user request: {prompt.strip()}. "
                "Do not change the source melody, tempo map, or locked tracks."
            ),
        })
    return {
        "schema_version": 1,
        "type": "midivolt_composition_plan",
        "original_prompt": prompt.strip(),
        "original_track_count": source_track_count,
        "locked_tracks": list(locked_tracks),
        "parts": parts,
        "excluded_roles": [r.name for r in ROLES if r.name in no],
        "needs_program_selection": [p["role"] for p in parts if p["requires_program_selection"]],
        "requires_human_approval": True,
        "generated_midi": False,
    }
