"""Marathi names for a calculated relationship ("A is B's …").

Terms and their compositions follow docs/marathi-relationship-reference.md.
The mother/father role on each link of the result's path gives the gender of
everyone between A and B. A's and B's own genders are known only if they are
recorded as someone's mother or father; when one matters and is not known, the
male and female forms are listed together, as in "मावस भाऊ/बहीण".

Longer names compose as "[B's ancestor's] [relative] [descendant]", e.g.
आजोबांच्या चुलत भावाचा नातू. Ancestor and descendant words go up to three
generations (पणजोबा, पणतू); a relationship that needs more has no name here.
"""

from __future__ import annotations

from itertools import product
from typing import Literal

from famtree.domain.model import FamilyGraph, ParentRole
from famtree.domain.relation import RelationKind, RelationResult

Gender = Literal["m", "f"]
_GENDER: dict[ParentRole, Gender] = {ParentRole.FATHER: "m", ParentRole.MOTHER: "f"}

# A phrase is (text, the genitive ending a possessor before it takes):
# वडिलांचा भाऊ, वडिलांची बहीण, वडिलांचे काका, वडिलांच्या चुलत भावाचा मुलगा.
Phrase = tuple[str, str]

_SIBLING: dict[Gender, Phrase] = {"m": ("भाऊ", "चा"), "f": ("बहीण", "ची")}
_SIBLING_OBLIQUE: dict[Gender, str] = {"m": "भावा", "f": "बहिणी"}
_CHILD_OBLIQUE: dict[Gender, str] = {"m": "मुला", "f": "मुली"}
_GREAT_GRANDCHILD_OBLIQUE: dict[Gender, str] = {"m": "पणतवा", "f": "पणती"}
# A as someone's descendant, by generation.
_DESCENDANT: dict[int, dict[Gender, str]] = {
    1: {"m": "मुलगा", "f": "मुलगी"},
    2: {"m": "नातू", "f": "नात"},
    3: {"m": "पणतू", "f": "पणती"},
}
# B's ancestor as a possessor (वडिलां|चा, आजी|ची), by generation.
_ANCESTOR_STEM: dict[int, dict[Gender, str]] = {
    1: {"m": "वडिलां", "f": "आई"},
    2: {"m": "आजोबां", "f": "आजी"},
    3: {"m": "पणजोबां", "f": "पणजी"},
}
_SIDE: dict[Gender, str] = {"m": "वडिलांकड", "f": "आईकड"}
# Keyed by (the connecting parent, the relative).
_AUNT_UNCLE: dict[tuple[Gender, Gender], Phrase] = {
    ("m", "m"): ("काका", "चे"),
    ("m", "f"): ("आत्या", "ची"),
    ("f", "m"): ("मामा", "चे"),
    ("f", "f"): ("मावशी", "ची"),
}
# First cousins, keyed by (B's connecting parent, the cousin's connecting parent).
_COUSIN_BRANCH: dict[tuple[Gender, Gender], str] = {
    ("m", "m"): "चुलत",
    ("m", "f"): "आत्ये",
    ("f", "m"): "मामे",
    ("f", "f"): "मावस",
}
# A sibling's child: पुतण्या/पुतणी for a man's brother's child, otherwise भाचा/भाची.
_NEPHEW: dict[bool, dict[Gender, str]] = {
    True: {"m": "पुतण्या", "f": "पुतणी"},
    False: {"m": "भाचा", "f": "भाची"},
}
_NEPHEW_OBLIQUE = {"पुतण्या": "पुतण्या", "पुतणी": "पुतणी", "भाचा": "भाच्या", "भाची": "भाची"}


def marathi_names(graph: FamilyGraph, result: RelationResult) -> list[str]:
    """Names for the result's path, most familiar first; [] if there is none."""
    if result.kind == RelationKind.SAME_PERSON:
        return []
    ids = [step.person_id for step in result.path]
    if result.kind == RelationKind.SPOUSE:
        up_ids, down_ids = ids[:1], ids[1:]
    else:
        da = result.distance_a or 0
        up_ids, down_ids = ids[: da + 1], ids[da:][::-1]
    path_links = {step.link_id for step in result.path}
    known = {
        link.parent_id: _GENDER[link.role] for link in graph.parent_links if link.id in path_links
    }
    a, b = ids[0], ids[-1]

    def options(person_id: str) -> list[Gender]:
        gender = known.get(person_id) or _recorded_gender(graph, person_id)
        return [gender] if gender else ["m", "f"]

    variants = []
    for gb, ga in product(options(b), options(a)):
        genders = known | {a: ga, b: gb}
        up = [genders[pid] for pid in up_ids]
        down = [genders[pid] for pid in down_ids]
        variants.append(_names(result.kind, up, down))
    return _combine(variants)


def _recorded_gender(graph: FamilyGraph, person_id: str) -> Gender | None:
    roles = {link.role for link in graph.child_links_of(person_id)}
    return _GENDER[roles.pop()] if len(roles) == 1 else None


def _names(kind: RelationKind, up: list[Gender], down: list[Gender]) -> list[str]:
    """`up` runs from A to the common ancestor, `down` from B to it."""
    a = up[0]
    match kind:
        case RelationKind.SPOUSE:
            return [{"m": "नवरा", "f": "बायको"}[a], {"m": "पती", "f": "पत्नी"}[a]]
        case RelationKind.ANCESTOR:
            return _ancestor(down)
        case RelationKind.DESCENDANT:
            return _descendant(up)
        case RelationKind.SIBLING:
            return [_SIBLING[a][0]]
        case RelationKind.AUNT_UNCLE:
            return _aunt_uncle(a, down)
        case RelationKind.NIECE_NEPHEW:
            return _niece_nephew(up, down[0])
        case RelationKind.COUSIN:
            return _cousin(up, down)
    return []


def _ancestor(down: list[Gender]) -> list[str]:
    generations, a = len(down) - 1, down[-1]
    if generations == 1:
        return ["वडील", "बाबा"] if a == "m" else ["आई"]
    grandparent = {"m": "चे आजोबा", "f": "ची आजी"}[a]
    if generations == 2:
        return [{"m": "आजोबा", "f": "आजी"}[a], _SIDE[down[1]] + grandparent]
    if generations == 3:
        return [{"m": "पणजोबा", "f": "पणजी"}[a], _ANCESTOR_STEM[1][down[1]] + grandparent]
    if generations == 4:
        return [{"m": "खापरपणजोबा", "f": "खापरपणजी"}[a]]
    return []


def _descendant(up: list[Gender]) -> list[str]:
    generations, a = len(up) - 1, up[0]
    if generations == 1:
        return [_DESCENDANT[1][a]]
    if generations == 2:
        return [_DESCENDANT[2][a], _descended(_CHILD_OBLIQUE[up[1]], 1, a)[0]]
    if generations == 3:
        return [_DESCENDANT[3][a], _descended(_CHILD_OBLIQUE[up[2]], 2, a)[0]]
    if generations == 4:
        return [_descended(_GREAT_GRANDCHILD_OBLIQUE[up[1]], 1, a)[0]]
    return []


def _aunt_uncle(a: Gender, down: list[Gender]) -> list[str]:
    """A is the sibling of B's ancestor down[-2]."""
    anchor = len(down) - 3  # whose aunt or uncle A is
    if anchor > 3:
        return []
    names = _anchored(_AUNT_UNCLE[down[anchor + 1], a], anchor, down)
    if anchor == 2:  # also the great-grandparent's sibling: पणजोबांचा भाऊ
        names += _anchored(_SIBLING[a], 3, down)
    return names


def _niece_nephew(up: list[Gender], b: Gender) -> list[str]:
    """A descends from B's sibling up[-2]."""
    generations, a, sibling = len(up) - 2, up[0], up[-2]
    nephew = _NEPHEW[sibling == "m" and b == "m"]
    if generations == 1:
        return [nephew[a]]
    if generations > 3:
        return []
    names = [_descended(_SIBLING_OBLIQUE[sibling], generations, a)[0]]
    if generations == 2:  # also the nephew's or niece's child: भाच्याचा मुलगा
        names.append(_descended(_NEPHEW_OBLIQUE[nephew[up[1]]], 1, a)[0])
    return names


def _cousin(up: list[Gender], down: list[Gender]) -> list[str]:
    """A descends from a first cousin of B or of B's ancestor."""
    generations, anchor = len(up) - 3, len(down) - 3
    if generations > 3 or anchor > 3:
        return []
    branch = _COUSIN_BRANCH[down[anchor + 1], up[generations + 1]]
    cousin = up[generations]
    if generations == 0:
        word, ending = _SIBLING[cousin]
        phrase = (f"{branch} {word}", ending)
    else:
        joiner = "" if branch == "मामे" else " "  # मामेभावाचा, but चुलत भावाचा
        oblique = f"{branch}{joiner}{_SIBLING_OBLIQUE[cousin]}"
        phrase = _descended(oblique, generations, up[0])
    return _anchored(phrase, anchor, down)


def _descended(oblique: str, generations: int, a: Gender) -> Phrase:
    """A as a descendant of someone: भावाचा नातू, बहिणीची मुलगी."""
    ending = "चा" if a == "m" else "ची"
    return f"{oblique}{ending} {_DESCENDANT[generations][a]}", "च्या"


def _anchored(phrase: Phrase, anchor: int, down: list[Gender]) -> list[str]:
    """The phrase as said of B's ancestor `anchor` generations up (0 is B)."""
    text, ending = phrase
    if anchor == 0:
        return [text]
    named = f"{_ANCESTOR_STEM[anchor][down[anchor]]}{ending} {text}"
    if anchor == 2:  # also with the grandparent's side: वडिलांकडच्या आजोबांचे काका
        return [named, f"{_SIDE[down[1]]}च्या {named}"]
    return [named]


def _combine(variants: list[list[str]]) -> list[str]:
    """Merge the names for each guess at unknown genders, position by position."""
    names: list[str] = []
    for forms in zip(*variants, strict=True):  # only A's and B's genders vary
        name = _merge(list(dict.fromkeys(forms)))
        if name not in names:
            names.append(name)
    return names


def _merge(forms: list[str]) -> str:
    """'चुलत भाऊ', 'चुलत बहीण' -> 'चुलत भाऊ/बहीण'."""
    words = [form.split(" ") for form in forms]
    shared = 0
    while all(len(w) > shared + 1 for w in words) and len({w[shared] for w in words}) == 1:
        shared += 1
    rest = [" ".join(w[shared:]) for w in words]
    separator = " / " if any(" " in part for part in rest) else "/"
    return " ".join([*words[0][:shared], separator.join(rest)])
