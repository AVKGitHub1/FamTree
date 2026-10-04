import { request, requestRaw } from "./client";
import type {
  AccessCode,
  AdminSettings,
  AttributeDefinition,
  AttributeInput,
  ChangeSet,
  CodeRole,
  DeletionPreview,
  ExportPreview,
  ExportRequest,
  NewDefinition,
  ParentRole,
  RelationOutcome,
  SearchHit,
  Session,
  Snapshot,
  TreeData,
  UploadedPicture,
  ValueType,
} from "./types";

const q = encodeURIComponent;

// --- session -----------------------------------------------------------------
export const getSession = () => request<Session>("GET", "/api/session");
export const signIn = (kind: "code" | "admin", secret: string) =>
  request<Session>("POST", "/api/auth/login", { kind, secret });
export const signOut = () => request<Session>("POST", "/api/auth/logout");

// --- reading -------------------------------------------------------------------
export const getTree = () => request<TreeData>("GET", "/api/tree");

export function searchPeople(query: string, exclude: string[] = []) {
  const params = new URLSearchParams({ q: query, limit: "8" });
  exclude.forEach((id) => params.append("exclude", id));
  return request<{ results: SearchHit[] }>("GET", `/api/people/search?${params}`);
}

export const calculateRelation = (a: string, b: string) =>
  request<RelationOutcome>("POST", "/api/relation", { a, b });

// --- editing -------------------------------------------------------------------
export const applyChanges = (changes: ChangeSet) =>
  request<{ created: Record<string, string> }>("POST", "/api/changes", changes);

export const updatePerson = (
  id: string,
  body: {
    expected_revision: number;
    name: string;
    attributes: AttributeInput[];
    definitions: NewDefinition[];
  },
) => request<{ ok: true }>("PUT", `/api/people/${q(id)}`, body);

/** Children of the same parents, left to right; every one of them, each once. */
export const setSiblingOrder = (children: string[]) =>
  request<{ ok: true }>("PUT", "/api/sibling-order", { children });

export const getDeletionPreview = (id: string) =>
  request<DeletionPreview>("GET", `/api/people/${q(id)}/deletion`);

export const uploadPicture = (picture: Blob) => request<UploadedPicture>("POST", "/api/images", picture);

/** A person's profile picture; `imageId` changes the URL when the picture changes. */
export const pictureUrl = (personId: string, imageId: string, size: "thumb" | "full") =>
  `/api/people/${q(personId)}/picture?size=${size}&v=${q(imageId)}`;

/** `relationships` comes from the deletion preview the editor reviewed. */
export const deletePerson = (id: string, revision: number, relationships: string) =>
  request<{ ok: true }>(
    "DELETE",
    `/api/people/${q(id)}?expected_revision=${revision}&expected_relationships=${q(relationships)}`,
  );

export const updateParentLink = (
  id: string,
  body: { expected_revision: number; role?: ParentRole; is_public?: boolean },
) => request<{ ok: true }>("PATCH", `/api/relationships/parent/${q(id)}`, body);

export const updateSpouseLink = (id: string, body: { expected_revision: number; is_public: boolean }) =>
  request<{ ok: true }>("PATCH", `/api/relationships/spouse/${q(id)}`, body);

export const deleteRelationship = (kind: "parent" | "spouse", id: string, revision: number) =>
  request<{ ok: true }>("DELETE", `/api/relationships/${kind}/${q(id)}?expected_revision=${revision}`);

export const listDefinitions = () =>
  request<{ definitions: AttributeDefinition[] }>("GET", "/api/attributes");
export const createDefinition = (label: string, value_type: ValueType) =>
  request<{ id: string }>("POST", "/api/attributes", { label, value_type });
export const updateDefinition = (
  id: string,
  body: { expected_revision: number; label?: string; value_type?: ValueType },
) => request<{ ok: true }>("PATCH", `/api/attributes/${q(id)}`, body);
export const deleteDefinition = (id: string) =>
  request<{ ok: true }>("DELETE", `/api/attributes/${q(id)}`);

// --- export --------------------------------------------------------------------
export const previewExport = (body: ExportRequest) =>
  request<ExportPreview>("POST", "/api/export/preview", body);

export async function downloadExport(body: ExportRequest): Promise<{ blob: Blob; filename: string }> {
  const response = await requestRaw("POST", "/api/export", body);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `famtree.${body.format}`;
  return { blob: await response.blob(), filename };
}

// --- admin ---------------------------------------------------------------------
export const getSettings = () => request<AdminSettings>("GET", "/api/admin/settings");
export const updateSettings = (body: Partial<AdminSettings>) =>
  request<AdminSettings>("PATCH", "/api/admin/settings", body);
export const listCodes = () => request<{ codes: AccessCode[] }>("GET", "/api/admin/codes");
export const createCode = (label: string, role: CodeRole) =>
  request<{ code: AccessCode; value: string }>("POST", "/api/admin/codes", { label, role });
export const revealCode = (id: string) =>
  request<{ value: string }>("POST", `/api/admin/codes/${q(id)}/reveal`);
export const updateCode = (id: string, body: { label?: string; role?: CodeRole; revoked?: boolean }) =>
  request<{ ok: true }>("PATCH", `/api/admin/codes/${q(id)}`, body);
export const deleteCode = (id: string) => request<{ ok: true }>("DELETE", `/api/admin/codes/${q(id)}`);
/** Newest first; `keep` is how many are kept before the oldest is deleted. */
export const listSnapshots = () => request<{ snapshots: Snapshot[]; keep: number }>("GET", "/api/admin/snapshots");
/** Replace the tree with the snapshot's; the current tree is saved as a snapshot first. */
export const loadSnapshot = (id: string) =>
  request<{ saved: string }>("POST", `/api/admin/snapshots/${q(id)}/load`);
export const deleteSnapshot = (id: string) => request<{ ok: true }>("DELETE", `/api/admin/snapshots/${q(id)}`);
export const changePassword = (current_password: string, new_password: string) =>
  request<{ ok: true }>("POST", "/api/admin/password", { current_password, new_password });
