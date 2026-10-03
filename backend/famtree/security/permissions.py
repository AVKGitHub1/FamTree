"""Whole-tree roles, capabilities and the action catalogue.

Roles are not scoped to people or attributes. Every server operation checks a
capability; hiding a control in the UI is never the authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    GUEST = "guest"
    PUBLIC_VIEWER = "public_viewer"
    PRIVATE_VIEWER = "private_viewer"
    EDITOR = "editor"
    ADMIN = "admin"


# Roles an access code can carry. Admin access comes only from the password.
CODE_ROLES = (Role.PUBLIC_VIEWER, Role.PRIVATE_VIEWER, Role.EDITOR)


class Capability(StrEnum):
    READ_PUBLIC = "read_public"
    READ_PRIVATE = "read_private"
    EDIT = "edit"
    ADMIN = "admin"


ROLE_CAPABILITIES: dict[Role, frozenset[Capability]] = {
    Role.GUEST: frozenset({Capability.READ_PUBLIC}),
    Role.PUBLIC_VIEWER: frozenset({Capability.READ_PUBLIC}),
    Role.PRIVATE_VIEWER: frozenset({Capability.READ_PUBLIC, Capability.READ_PRIVATE}),
    Role.EDITOR: frozenset({Capability.READ_PUBLIC, Capability.READ_PRIVATE, Capability.EDIT}),
    Role.ADMIN: frozenset(Capability),
}


class ActionVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


@dataclass(frozen=True)
class Action:
    name: str
    visibility: ActionVisibility
    capability: Capability


# Actions have an explicit classification plus a required capability. Reading
# private data does not imply any private *action* (e.g. editing).
ACTIONS: tuple[Action, ...] = (
    Action("calculate_relation", ActionVisibility.PUBLIC, Capability.READ_PUBLIC),
    Action("export", ActionVisibility.PUBLIC, Capability.READ_PUBLIC),
    Action("add_connection", ActionVisibility.PRIVATE, Capability.EDIT),
    Action("edit_person", ActionVisibility.PRIVATE, Capability.EDIT),
    Action("manage_attributes", ActionVisibility.PRIVATE, Capability.EDIT),
    Action("manage_access", ActionVisibility.PRIVATE, Capability.ADMIN),
)


@dataclass(frozen=True)
class Viewer:
    """The caller of one request, resolved fresh from its session every time."""

    role: Role
    session_digest: str | None = None
    code_id: str | None = None
    csrf_token: str | None = None
    # The admin can turn guest access off; a guest then may not read anything.
    guest_access: bool = True

    @property
    def capabilities(self) -> frozenset[Capability]:
        if self.role is Role.GUEST and not self.guest_access:
            return frozenset()
        return ROLE_CAPABILITIES[self.role]

    def can(self, capability: Capability) -> bool:
        return capability in self.capabilities

    @property
    def can_read_private(self) -> bool:
        return self.can(Capability.READ_PRIVATE)

    @property
    def can_edit(self) -> bool:
        return self.can(Capability.EDIT)

    def allowed_actions(self) -> list[str]:
        return [action.name for action in ACTIONS if self.can(action.capability)]


GUEST = Viewer(Role.GUEST)
