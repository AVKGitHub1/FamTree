"""Name search over the caller's authorized graph, with disambiguating context."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from famtree.domain.attributes import BIRTH_DATE, LOCATION, PROFESSION, display_text
from famtree.domain.model import FamilyGraph, Person

MAX_LIMIT = 20


@dataclass(frozen=True)
class SearchHit:
    person_id: str
    name: str
    context: list[str]


def fold(text: str) -> str:
    """Case- and accent-insensitive comparison form."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def _score(folded_name: str, folded_query: str, tokens: list[str]) -> int | None:
    if not all(token in folded_name for token in tokens):
        return None
    if folded_name == folded_query:
        return 0
    if folded_name.startswith(folded_query):
        return 1
    words = folded_name.split()
    if all(any(word.startswith(token) for word in words) for token in tokens):
        return 2
    return 3


def context_for(graph: FamilyGraph, person: Person) -> list[str]:
    """Short, permitted facts that tell same-named people apart."""
    facts: list[str] = []
    for definition_id, prefix in ((BIRTH_DATE, "born "), (LOCATION, ""), (PROFESSION, "")):
        value = person.attributes.get(definition_id)
        definition = graph.definitions.get(definition_id)
        if value is not None and definition is not None:
            facts.append(prefix + display_text(definition.value_type, value.value))
    parents = [graph.people[p].name for p in graph.parents_of(person.id)]
    if parents:
        facts.append("child of " + " & ".join(parents[:3]))
    spouses = [graph.people[s].name for s in graph.spouses_of(person.id)]
    if spouses:
        facts.append("spouse of " + ", ".join(spouses[:2]))
    if not parents and not spouses:
        children = [graph.people[c].name for c in graph.children_of(person.id)]
        if children:
            facts.append("parent of " + ", ".join(children[:2]))
    return facts


def search_people(
    graph: FamilyGraph, query: str, limit: int = 8, exclude: frozenset[str] = frozenset()
) -> list[SearchHit]:
    folded_query = " ".join(fold(query).split())
    if not folded_query:
        return []
    tokens = folded_query.split()
    ranked = []
    for person in graph.people.values():
        if person.id in exclude:
            continue
        folded_name = fold(person.name)
        score = _score(folded_name, folded_query, tokens)
        if score is not None:
            ranked.append((score, folded_name, person.seq, person))
    ranked.sort(key=lambda item: item[:3])
    return [
        SearchHit(person.id, person.name, context_for(graph, person))
        for *_, person in ranked[: min(limit, MAX_LIMIT)]
    ]
