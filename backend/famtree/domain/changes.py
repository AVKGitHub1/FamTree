"""Editing operations. Each runs inside one write transaction and validates
the resulting graph before commit, so a rejected change leaves nothing behind."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from famtree.domain import repository as repo
from famtree.domain.attributes import (
    ValueType,
    custom_type_problem,
    normalize_label,
    normalize_name,
    normalize_value,
    type_change_problem,
)
from famtree.domain.errors import Conflict, InvalidInput, NotFound, StaleRevision
from famtree.domain.model import (
    AttributeValue,
    FamilyGraph,
    ParentLink,
    ParentRole,
    SpouseLink,
)
from famtree.domain.validation import people_without_public_connection, validate_graph
from famtree.storage.database import Connection

MAX_BATCH = 50


@dataclass(frozen=True)
class Ref:
    """Points at an existing record (`id`) or one created in the same request (`ref`)."""

    id: str | None = None
    ref: str | None = None

    def __post_init__(self) -> None:
        if (self.id is None) == (self.ref is None):
            raise InvalidInput("Each reference needs exactly one of 'id' or 'ref'.")


@dataclass(frozen=True)
class AttributeInput:
    definition: Ref
    value: Any
    is_public: bool = False


@dataclass(frozen=True)
class NewDefinition:
    ref: str
    label: str
    value_type: ValueType


@dataclass(frozen=True)
class NewPerson:
    ref: str
    name: str
    attributes: list[AttributeInput] = field(default_factory=list)


@dataclass(frozen=True)
class NewParentLink:
    parent: Ref
    child: Ref
    role: ParentRole
    is_public: bool = False


@dataclass(frozen=True)
class NewSpouseLink:
    a: Ref
    b: Ref
    is_public: bool = False


@dataclass(frozen=True)
class ChangeSet:
    definitions: list[NewDefinition] = field(default_factory=list)
    people: list[NewPerson] = field(default_factory=list)
    parent_links: list[NewParentLink] = field(default_factory=list)
    spouse_links: list[NewSpouseLink] = field(default_factory=list)


@dataclass
class _Resolver:
    """Maps request-local refs to the IDs created for them."""

    people: dict[str, str] = field(default_factory=dict)
    definitions: dict[str, str] = field(default_factory=dict)

    def person(self, conn: Connection, ref: Ref) -> str:
        if ref.ref is not None:
            if ref.ref not in self.people:
                raise InvalidInput(f"Unknown new-person reference {ref.ref!r}.")
            return self.people[ref.ref]
        if repo.person_revision(conn, ref.id) is None:
            raise NotFound("That person no longer exists. Reload and try again.")
        return ref.id

    def definition(self, ref: Ref) -> str:
        if ref.ref is not None:
            if ref.ref not in self.definitions:
                raise InvalidInput(f"Unknown new-attribute reference {ref.ref!r}.")
            return self.definitions[ref.ref]
        return ref.id


# --- attribute definitions ---------------------------------------------------


def _create_definitions(conn: Connection, items: list[NewDefinition], resolver: _Resolver) -> None:
    for item in items:
        if item.ref in resolver.definitions:
            raise InvalidInput(f"Duplicate attribute reference {item.ref!r}.")
        label = normalize_label(item.label)
        if problem := custom_type_problem(item.value_type):
            raise InvalidInput(problem)
        if repo.label_in_use(conn, label):
            raise Conflict(f"An attribute named “{label}” already exists; choose it instead.")
        resolver.definitions[item.ref] = repo.insert_definition(conn, label, item.value_type)


def create_definition(conn: Connection, label: str, value_type: ValueType) -> str:
    resolver = _Resolver()
    _create_definitions(conn, [NewDefinition("new", label, value_type)], resolver)
    return resolver.definitions["new"]


def update_definition(
    conn: Connection,
    definition_id: str,
    expected_revision: int,
    label: str | None,
    value_type: ValueType | None,
) -> None:
    definitions = repo.load_definitions(conn)
    current = definitions.get(definition_id)
    if current is None:
        raise NotFound("That attribute no longer exists.")
    if current.revision != expected_revision:
        raise StaleRevision(
            "This attribute was changed by someone else. Reload and try again.",
            current_revision=current.revision,
        )
    new_label = current.label if label is None else normalize_label(label)
    if repo.label_in_use(conn, new_label, except_id=definition_id):
        raise Conflict(f"An attribute named “{new_label}” already exists.")
    new_type = current.value_type if value_type is None else value_type
    if new_type != current.value_type:
        if current.builtin:
            raise InvalidInput("The type of a built-in attribute cannot be changed.")
        if problem := custom_type_problem(new_type):
            raise InvalidInput(problem)
        problem = type_change_problem(
            current.value_type, new_type, repo.values_for_definition(conn, definition_id)
        )
        if problem:
            raise Conflict(problem)
    repo.update_definition(conn, definition_id, new_label, new_type)


def delete_definition(conn: Connection, definition_id: str) -> None:
    current = repo.load_definitions(conn).get(definition_id)
    if current is None:
        raise NotFound("That attribute no longer exists.")
    if current.builtin:
        raise InvalidInput("Built-in attributes cannot be deleted.")
    in_use = repo.value_counts(conn).get(definition_id, 0)
    if in_use:
        raise Conflict(
            f"{in_use} person/people still have a value for this attribute. "
            "Remove those values before deleting it."
        )
    repo.delete_definition(conn, definition_id)


# --- people ------------------------------------------------------------------


def _attribute_values(
    conn: Connection, items: list[AttributeInput], resolver: _Resolver
) -> list[AttributeValue]:
    definitions = repo.load_definitions(conn)
    values: list[AttributeValue] = []
    seen: set[str] = set()
    for item in items:
        definition_id = resolver.definition(item.definition)
        definition = definitions.get(definition_id)
        if definition is None:
            raise NotFound("An attribute used here no longer exists. Reload and try again.")
        if definition_id in seen:
            raise InvalidInput(f"“{definition.label}” is listed more than once.")
        seen.add(definition_id)
        try:
            value = normalize_value(definition.value_type, item.value)
        except InvalidInput as exc:
            raise InvalidInput(f"{definition.label}: {exc.message}") from None
        if definition.value_type is ValueType.IMAGE and not repo.image_exists(conn, value["id"]):
            raise InvalidInput(
                f"{definition.label}: that picture is no longer available. Upload it again."
            )
        values.append(AttributeValue(definition_id, value, bool(item.is_public)))
    return values


def apply_changes(conn: Connection, changes: ChangeSet) -> dict[str, str]:
    """Create people, definitions and relationships atomically.

    Returns a map from each new person's request ref to its stored ID.
    """
    total = (
        len(changes.definitions)
        + len(changes.people)
        + len(changes.parent_links)
        + len(changes.spouse_links)
    )
    if total == 0:
        raise InvalidInput("Nothing to save.")
    if total > MAX_BATCH:
        raise InvalidInput(f"Save at most {MAX_BATCH} changes at once.")

    resolver = _Resolver()
    _create_definitions(conn, changes.definitions, resolver)

    for person in changes.people:
        if person.ref in resolver.people:
            raise InvalidInput(f"Duplicate person reference {person.ref!r}.")
        person_id = repo.insert_person(conn, normalize_name(person.name))
        resolver.people[person.ref] = person_id
        repo.replace_attribute_values(
            conn, person_id, _attribute_values(conn, person.attributes, resolver)
        )

    for link in changes.parent_links:
        parent = resolver.person(conn, link.parent)
        child = resolver.person(conn, link.child)
        _add_parent_link(conn, parent, child, link.role, link.is_public)
    for link in changes.spouse_links:
        a = resolver.person(conn, link.a)
        b = resolver.person(conn, link.b)
        _add_spouse_link(conn, a, b, link.is_public)

    validate_graph(repo.load_graph(conn))
    repo.delete_unused_images(conn)
    return resolver.people


def _add_parent_link(
    conn: Connection, parent: str, child: str, role: ParentRole, is_public: bool
) -> None:
    if parent == child:
        raise InvalidInput("A person cannot be their own parent.")
    if repo.find_parent_link(conn, parent, child) is not None:
        raise Conflict("That parent-child relationship already exists.")
    if repo.find_parent_link(conn, child, parent) is not None:
        raise Conflict("Those two people are already recorded as parent and child the other way.")
    repo.insert_parent_link(conn, parent, child, role, is_public)


def _add_spouse_link(conn: Connection, a: str, b: str, is_public: bool) -> None:
    if a == b:
        raise InvalidInput("A person cannot be their own spouse.")
    if repo.find_spouse_link(conn, a, b) is not None:
        raise Conflict("Those two people are already recorded as spouses.")
    repo.insert_spouse_link(conn, a, b, is_public)


def _check_person_revision(conn: Connection, person_id: str, expected: int) -> None:
    current = repo.person_revision(conn, person_id)
    if current is None:
        raise NotFound("That person no longer exists.")
    if current != expected:
        raise StaleRevision(
            "Someone else saved changes to this person. Reload to see them, then re-apply yours.",
            current_revision=current,
        )


def update_person(
    conn: Connection,
    person_id: str,
    expected_revision: int,
    name: str,
    attributes: list[AttributeInput],
    new_definitions: list[NewDefinition] | None = None,
) -> None:
    """Rename a person and replace their full set of attribute values."""
    _check_person_revision(conn, person_id, expected_revision)
    resolver = _Resolver()
    _create_definitions(conn, new_definitions or [], resolver)
    values = _attribute_values(conn, attributes, resolver)
    repo.touch_person(conn, person_id, normalize_name(name))
    repo.replace_attribute_values(conn, person_id, values)
    repo.delete_unused_images(conn)


@dataclass(frozen=True)
class DeletionPreview:
    parent_links: list[ParentLink]
    spouse_links: list[SpouseLink]
    blocked_people: list[str]
    # Identifies exactly the relationships listed, for `delete_person`.
    relationships: str

    @property
    def allowed(self) -> bool:
        return not self.blocked_people


def relationships_token(graph: FamilyGraph, person_id: str) -> str:
    """Fingerprint of a person's relationships (which ones, at which revision).
    A person's own revision does not change when a relationship is added, so
    deletion is also bound to this: it removes only what the preview listed."""
    parent_links = graph.parent_links_of(person_id) + graph.child_links_of(person_id)
    parts = sorted(
        [f"p:{link.id}:{link.revision}" for link in parent_links]
        + [f"s:{link.id}:{link.revision}" for link in graph.spouse_links_of(person_id)]
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def preview_person_deletion(graph: FamilyGraph, person_id: str) -> DeletionPreview:
    if person_id not in graph.people:
        raise NotFound("That person no longer exists.")
    remaining = FamilyGraph(
        people={k: v for k, v in graph.people.items() if k != person_id},
        parent_links=[
            link for link in graph.parent_links if person_id not in (link.parent_id, link.child_id)
        ],
        spouse_links=[
            link for link in graph.spouse_links if person_id not in (link.person_a, link.person_b)
        ],
        definitions=graph.definitions,
    )
    return DeletionPreview(
        parent_links=graph.parent_links_of(person_id) + graph.child_links_of(person_id),
        spouse_links=graph.spouse_links_of(person_id),
        blocked_people=people_without_public_connection(remaining),
        relationships=relationships_token(graph, person_id),
    )


def delete_person(
    conn: Connection, person_id: str, expected_revision: int, expected_relationships: str
) -> None:
    _check_person_revision(conn, person_id, expected_revision)
    if relationships_token(repo.load_graph(conn), person_id) != expected_relationships:
        raise StaleRevision(
            "This person's relationships changed after the deletion was checked. "
            "Review the updated list, then delete again."
        )
    repo.delete_person(conn, person_id)
    validate_graph(repo.load_graph(conn))
    repo.delete_unused_images(conn)


def set_sibling_order(conn: Connection, children: list[str]) -> None:
    """Arrange a family's children left to right as listed. `children` must be
    everyone with exactly the same parents, each once; a list that no longer
    matches the stored tree is refused as stale, so a reload cannot be undone
    by an order chosen on an older tree."""
    if len(children) < 2:
        raise InvalidInput("List at least two children to put in order.")
    if len(set(children)) != len(children):
        raise InvalidInput("Each child can be listed only once.")
    graph = repo.load_graph(conn)
    for child in children:
        if child not in graph.people:
            raise NotFound("That person no longer exists. Reload and try again.")
    if not graph.parents_of(children[0]):
        raise InvalidInput("Only children with recorded parents can be put in order.")
    if sorted(graph.siblings_by_parents(children[0])) != sorted(children):
        raise StaleRevision("These children or their parents have changed. Reload and try again.")
    repo.set_sibling_order(conn, children)


# --- relationships -----------------------------------------------------------


def _check_link_revision(link: ParentLink | SpouseLink | None, expected: int) -> None:
    if link is None:
        raise NotFound("That relationship no longer exists.")
    if link.revision != expected:
        raise StaleRevision(
            "This relationship was changed by someone else. Reload and try again.",
            current_revision=link.revision,
        )


def update_parent_link(
    conn: Connection,
    link_id: str,
    expected_revision: int,
    role: ParentRole | None,
    is_public: bool | None,
) -> None:
    link = repo.get_parent_link(conn, link_id)
    _check_link_revision(link, expected_revision)
    repo.update_parent_link(
        conn,
        link_id,
        link.role if role is None else role,
        link.is_public if is_public is None else is_public,
    )
    validate_graph(repo.load_graph(conn))


def update_spouse_link(
    conn: Connection, link_id: str, expected_revision: int, is_public: bool
) -> None:
    link = repo.get_spouse_link(conn, link_id)
    _check_link_revision(link, expected_revision)
    repo.update_spouse_link(conn, link_id, is_public)
    validate_graph(repo.load_graph(conn))


def delete_parent_link(conn: Connection, link_id: str, expected_revision: int) -> None:
    link = repo.get_parent_link(conn, link_id)
    _check_link_revision(link, expected_revision)
    repo.delete_parent_link(conn, link_id)
    validate_graph(repo.load_graph(conn))


def delete_spouse_link(conn: Connection, link_id: str, expected_revision: int) -> None:
    link = repo.get_spouse_link(conn, link_id)
    _check_link_revision(link, expected_revision)
    repo.delete_spouse_link(conn, link_id)
    validate_graph(repo.load_graph(conn))
