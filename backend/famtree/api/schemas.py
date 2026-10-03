"""Request bodies. Unknown fields are rejected; the domain layer does the
semantic validation and converts these into its own types."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from famtree.domain import changes
from famtree.domain.attributes import ValueType
from famtree.domain.model import ParentRole
from famtree.export.options import (
    PAGE_SIZES_MM,
    ExportFormat,
    ExportOptions,
    ExportScope,
    GenerationWindow,
    Orientation,
)

Id = Field(min_length=1, max_length=64)
CodeRole = Literal["public_viewer", "private_viewer", "editor"]
PageSize = Literal[tuple(PAGE_SIZES_MM)]  # type: ignore[valid-type]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- auth & admin ----------------------------------------------------------------


class LoginRequest(Strict):
    kind: Literal["code", "admin"]
    secret: str = Field(max_length=256)


class SettingsUpdate(Strict):
    guest_access: bool | None = None


class PasswordChange(Strict):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class CodeCreate(Strict):
    label: str = Field("", max_length=200)
    role: CodeRole


class CodeUpdate(Strict):
    label: str | None = Field(None, max_length=200)
    role: CodeRole | None = None
    revoked: bool | None = None


# --- family data -------------------------------------------------------------------


class RefIn(Strict):
    id: str | None = Field(None, max_length=64)
    ref: str | None = Field(None, max_length=64)

    def to_domain(self) -> changes.Ref:
        return changes.Ref(id=self.id, ref=self.ref)


class AttributeIn(Strict):
    definition: RefIn
    value: Any
    is_public: bool = False

    def to_domain(self) -> changes.AttributeInput:
        return changes.AttributeInput(self.definition.to_domain(), self.value, self.is_public)


class DefinitionIn(Strict):
    ref: str = Id
    label: str = Field(max_length=200)
    value_type: ValueType

    def to_domain(self) -> changes.NewDefinition:
        return changes.NewDefinition(self.ref, self.label, self.value_type)


class PersonIn(Strict):
    ref: str = Id
    name: str = Field(max_length=500)
    attributes: list[AttributeIn] = Field(default_factory=list, max_length=100)


class ParentLinkIn(Strict):
    parent: RefIn
    child: RefIn
    role: ParentRole
    is_public: bool = False


class SpouseLinkIn(Strict):
    a: RefIn
    b: RefIn
    is_public: bool = False


class ChangeSetIn(Strict):
    definitions: list[DefinitionIn] = Field(default_factory=list, max_length=20)
    people: list[PersonIn] = Field(default_factory=list, max_length=20)
    parent_links: list[ParentLinkIn] = Field(default_factory=list, max_length=40)
    spouse_links: list[SpouseLinkIn] = Field(default_factory=list, max_length=40)

    def to_domain(self) -> changes.ChangeSet:
        return changes.ChangeSet(
            definitions=[d.to_domain() for d in self.definitions],
            people=[
                changes.NewPerson(p.ref, p.name, [a.to_domain() for a in p.attributes])
                for p in self.people
            ],
            parent_links=[
                changes.NewParentLink(
                    link.parent.to_domain(), link.child.to_domain(), link.role, link.is_public
                )
                for link in self.parent_links
            ],
            spouse_links=[
                changes.NewSpouseLink(link.a.to_domain(), link.b.to_domain(), link.is_public)
                for link in self.spouse_links
            ],
        )


class PersonUpdate(Strict):
    expected_revision: int
    name: str = Field(max_length=500)
    attributes: list[AttributeIn] = Field(default_factory=list, max_length=100)
    definitions: list[DefinitionIn] = Field(default_factory=list, max_length=20)


class ParentLinkUpdate(Strict):
    expected_revision: int
    role: ParentRole | None = None
    is_public: bool | None = None


class SpouseLinkUpdate(Strict):
    expected_revision: int
    is_public: bool


class DefinitionCreate(Strict):
    label: str = Field(max_length=200)
    value_type: ValueType


class DefinitionUpdate(Strict):
    expected_revision: int
    label: str | None = Field(None, max_length=200)
    value_type: ValueType | None = None


# --- relation & export -----------------------------------------------------------


class RelationRequest(Strict):
    a: str = Id
    b: str = Id


class WindowIn(Strict):
    selected_id: str = Id
    above: int = Field(ge=0, le=10_000)
    below: int = Field(ge=0, le=10_000)


class ExportRequest(Strict):
    format: ExportFormat
    scope: ExportScope = ExportScope.FULL
    window: WindowIn | None = None
    people: list[Annotated[str, Id]] | None = Field(None, max_length=20_000)
    attributes: list[str] = Field(default_factory=list, max_length=100)
    include_parent_links: bool = True
    include_spouse_links: bool = True
    include_legend: bool = True
    png_width: int = Field(3200, ge=1, le=100_000)
    page_size: PageSize = "a3"
    orientation: Orientation = Orientation.AUTO

    def to_domain(self) -> ExportOptions:
        window = None
        if self.window is not None:
            window = GenerationWindow(self.window.selected_id, self.window.above, self.window.below)
        return ExportOptions(
            format=self.format,
            scope=self.scope,
            window=window,
            people=None if self.people is None else frozenset(self.people),
            attributes=list(self.attributes),
            include_parent_links=self.include_parent_links,
            include_spouse_links=self.include_spouse_links,
            include_legend=self.include_legend,
            png_width=self.png_width,
            page_size=self.page_size,
            orientation=self.orientation,
        )
