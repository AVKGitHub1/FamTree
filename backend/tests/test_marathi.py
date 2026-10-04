"""Marathi relationship names, checked against docs/marathi-relationship-reference.md."""

from builders import GraphBuilder, sample_family

from famtree.domain.marathi import marathi_names
from famtree.domain.relation import calculate_relation
from famtree.domain.visibility import Audience, authorize

ROLE = {"m": "father", "f": "mother"}


def names(graph, a, b):
    return [marathi_names(graph, r) for r in calculate_relation(graph, a, b).results]


def kin(a_line: str, b_line: str) -> list[str]:
    """Names for A relative to B, who both descend from one root.

    Each line gives genders from the root down to A or to B: "m", "f", or "?"
    for not recorded. A line of one letter means that person is the root.
    Genders are recorded as father/mother roles, so a known end person gets a child.
    """
    assert a_line[0] == b_line[0]
    g = GraphBuilder()
    root = g.person("Root")
    ends = []
    for side, line in (("a", a_line), ("b", b_line)):
        people = [root] + [g.person(f"{side}{i}") for i in range(1, len(line))]
        for parent, child, gender in zip(people, people[1:], line, strict=False):
            g.parent(parent, child, ROLE[gender])
        if len(line) > 1 and line[-1] != "?":
            g.parent(people[-1], g.person(f"{side} child"), ROLE[line[-1]])
        ends.append(people[-1])
    graph = g.build()
    (result,) = calculate_relation(graph, *ends).results
    return marathi_names(graph, result)


def test_parents_and_ancestors_name_the_side():
    assert kin("m", "m?") == ["वडील", "बाबा"]
    assert kin("f", "f?") == ["आई"]
    assert kin("m", "mf?") == ["आजोबा", "आईकडचे आजोबा"]
    assert kin("f", "fm?") == ["आजी", "वडिलांकडची आजी"]
    assert kin("m", "mmf?") == ["पणजोबा", "आईचे आजोबा"]
    assert kin("f", "fmm?") == ["पणजी", "वडिलांची आजी"]
    assert kin("m", "mmmm?") == ["खापरपणजोबा"]
    assert kin("m", "mmmmm?") == []


def test_descendants():
    assert kin("mf", "m") == ["मुलगी"]
    assert kin("m?", "m") == ["मुलगा/मुलगी"]
    assert kin("mmm", "m") == ["नातू", "मुलाचा मुलगा"]
    assert kin("mff", "m") == ["नात", "मुलीची मुलगी"]
    assert kin("mm?", "m") == ["नातू/नात", "मुलाचा मुलगा / मुलाची मुलगी"]
    assert kin("mfmf", "m") == ["पणती", "मुलीची नात"]
    assert kin("mmmmm", "m") == ["पणतवाचा मुलगा"]
    assert kin("mmmff", "m") == ["पणतीची मुलगी"]
    assert kin("mmmmmm", "m") == []


def test_siblings_and_spouses():
    assert kin("mm", "m?") == ["भाऊ"]
    assert kin("mf", "mm") == ["बहीण"]
    assert kin("m?", "mf") == ["भाऊ/बहीण"]
    graph = sample_family()
    assert names(graph, "me", "partner") == [["नवरा", "पती"]]
    assert names(graph, "partner", "me") == [["बायको", "पत्नी"]]
    g = GraphBuilder()
    x, y = g.people("X", "Y")
    g.spouse(x, y)
    assert names(g.build(), x, y) == [["नवरा/बायको", "पती/पत्नी"]]


def test_a_visible_gender_detail_settles_the_form():
    g = GraphBuilder()
    father = g.person("Father")
    sister = g.person("Sister", gender=("female", True))
    brother = g.person("Brother", gender=("male", False))  # private
    other = g.person("Other", gender=("other", True))
    for child in (sister, brother, other):
        g.parent(father, child)
    graph = g.build()
    assert names(graph, sister, other) == [["बहीण"]]
    assert names(graph, brother, other) == [["भाऊ"]]
    assert names(graph, other, sister) == [["भाऊ/बहीण"]]
    public = authorize(graph, Audience.PUBLIC)
    assert names(public, brother, sister) == [["भाऊ/बहीण"]]


def test_same_person_has_no_name():
    assert names(sample_family(), "me", "me") == [[]]


def test_aunts_and_uncles_follow_the_connecting_parent():
    assert kin("mm", "mm?") == ["काका"]
    assert kin("mf", "mm?") == ["आत्या"]
    assert kin("mm", "mf?") == ["मामा"]
    assert kin("mf", "mf?") == ["मावशी"]
    assert kin("m?", "mf?") == ["मामा/मावशी"]


def test_great_aunts_and_uncles():
    assert kin("mf", "mff?") == ["आईची मावशी"]
    assert kin("mm", "mmm?") == ["वडिलांचे काका"]
    assert kin("mm", "mmfm?") == ["आजीचे काका", "वडिलांकडच्या आजीचे काका", "पणजोबांचा भाऊ"]
    assert kin("ff", "ffmf?") == ["आजोबांची मावशी", "आईकडच्या आजोबांची मावशी", "पणजीची बहीण"]
    assert kin("mm", "mmmmm?") == ["पणजोबांचे काका"]
    assert kin("mm", "mmmmmm?") == []


def test_nieces_and_nephews_depend_on_bs_gender_for_a_brothers_child():
    assert kin("mmm", "mm") == ["पुतण्या"]
    assert kin("mmf", "mm") == ["पुतणी"]
    assert kin("mmm", "mf") == ["भाचा"]
    assert kin("mfm", "mm") == ["भाचा"]
    assert kin("mff", "m?") == ["भाची"]
    assert kin("mf?", "m?") == ["भाचा/भाची"]
    assert kin("mm?", "m?") == ["पुतण्या/पुतणी/भाचा/भाची"]


def test_siblings_grandchildren():
    assert kin("mmfm", "mm") == ["भावाचा नातू", "पुतणीचा मुलगा"]
    assert kin("mfmf", "m?") == ["बहिणीची नात", "भाच्याची मुलगी"]
    assert kin("mmmmf", "mf") == ["भावाची पणती"]
    assert kin("mmmmmm", "mf") == []


def test_first_cousins_keep_the_branch():
    assert kin("mmm", "mm?") == ["चुलत भाऊ"]
    assert kin("mff", "mm?") == ["आत्ये बहीण"]
    assert kin("mmm", "mf?") == ["मामे भाऊ"]
    assert kin("mff", "mf?") == ["मावस बहीण"]
    assert kin("mm?", "mm?") == ["चुलत भाऊ/बहीण"]


def test_sample_family_cousins_follow_the_shown_path():
    graph = sample_family()
    assert names(graph, "cousin", "me") == [["आत्ये भाऊ/बहीण"]]
    assert names(graph, "me", "cousin") == [["मामे भाऊ"]]
    assert names(graph, "aunt", "me") == [["आत्या"]]
    assert names(graph, "me", "aunt") == [["भाचा"]]


def test_removed_and_more_distant_cousins():
    assert kin("mmm", "mmf?") == ["आईचा चुलत भाऊ"]
    assert kin("mm?", "mmm?") == ["वडिलांचा चुलत भाऊ / वडिलांची चुलत बहीण"]
    assert kin("mfmf", "mm?") == ["आत्ये भावाची मुलगी"]
    assert kin("mmmm", "mf?") == ["मामेभावाचा मुलगा"]
    assert kin("mmfm", "mmm?") == ["वडिलांच्या चुलत बहिणीचा मुलगा"]
    assert kin("mmf", "mfmm?") == ["आजोबांची मामे बहीण", "वडिलांकडच्या आजोबांची मामे बहीण"]
    assert kin("mmm", "mmmmm?") == ["पणजोबांचा चुलत भाऊ"]
    assert kin("mmmm", "mmmmm?") == ["पणजोबांच्या चुलत भावाचा मुलगा"]
    assert kin("mmmmm", "mfmm?") == [
        "आजोबांच्या मामेभावाचा नातू",
        "वडिलांकडच्या आजोबांच्या मामेभावाचा नातू",
    ]
    assert kin("mfmmmf", "mf?") == ["मावस भावाची पणती"]
    assert kin("mmm", "mmmmmm?") == []
    assert kin("mmmmmmm", "mmm?") == []
