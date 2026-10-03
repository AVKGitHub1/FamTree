// Shapes of the JSON exchanged with the FamTree API. Fields marked optional
// are only sent to callers allowed to use them (visibility flags to private
// readers, revisions to editors).

export type Role = "guest" | "public_viewer" | "private_viewer" | "editor" | "admin";
export type CodeRole = "public_viewer" | "private_viewer" | "editor";
export type Action =
  | "calculate_relation"
  | "export"
  | "add_connection"
  | "edit_person"
  | "manage_attributes"
  | "manage_access";

export interface Session {
  role: Role;
  authenticated: boolean;
  capabilities: string[];
  actions: Action[];
  csrf_token: string;
}

/** "image" is used only by the built-in Profile Pic. */
export type ValueType = "text" | "long_text" | "date" | "number" | "url" | "image";

export interface PartialDate {
  year: number | null;
  month: number | null;
  day: number | null;
}

/** A stored picture; fetch it with `pictureUrl`. */
export interface ImageValue {
  id: string;
}

export type AttributeValue = string | number | PartialDate | ImageValue;

export interface PersonAttribute {
  definition_id: string;
  value: AttributeValue;
  is_public?: boolean;
}

export interface Person {
  id: string;
  name: string;
  attributes: PersonAttribute[];
  revision?: number;
}

export type ParentRole = "mother" | "father";

export interface ParentLink {
  id: string;
  parent_id: string;
  child_id: string;
  role: ParentRole;
  is_public?: boolean;
  revision?: number;
}

export interface SpouseLink {
  id: string;
  a: string;
  b: string;
  is_public?: boolean;
  revision?: number;
}

export interface AttributeDefinition {
  id: string;
  label: string;
  value_type: ValueType;
  builtin: boolean;
  revision?: number;
  usage?: number;
}

export type Point = [number, number];

export interface LayoutNode {
  x: number;
  y: number;
  width: number;
  height: number;
  row: number;
}

export interface Connector {
  id: string;
  type: "spouse" | "family";
  people: string[];
  links: string[];
  paths: Point[][];
  dots: Point[];
  junction: { x: number; y: number; width: number; height: number } | null;
  /** Junction families: parent id -> index of that parent's own path to the junction. */
  branches: Record<string, number>;
  /** Families whose children hang from a bus: indices of the bus and of the trunk meeting it. */
  bus: number | null;
  trunk: number | null;
  /** child id -> index of that child's own drop from the bus. */
  drops: Record<string, number>;
}

export interface Crossing {
  x: number;
  y: number;
  over: string;
  under: string;
  /** The parent whose branch each crossing segment is on, if any. */
  over_branch: string | null;
  under_branch: string | null;
}

export interface Layout {
  width: number;
  height: number;
  rows: { index: number; top: number; bottom: number }[];
  nodes: Record<string, LayoutNode>;
  connectors: Connector[];
  crossings: Crossing[];
}

export interface TreeData {
  people: Person[];
  parent_links: ParentLink[];
  spouse_links: SpouseLink[];
  definitions: AttributeDefinition[];
  layout: Layout;
}

export interface SearchHit {
  id: string;
  name: string;
  context: string[];
}

export interface PathStep {
  person_id: string;
  name: string;
  step: "start" | "parent" | "child" | "spouse";
  link_id: string | null;
}

export interface RelationResult {
  kind: string;
  label: string;
  statement: string;
  distance_a: number | null;
  distance_b: number | null;
  cousin_degree: number | null;
  removed: number | null;
  common_ancestors: { id: string; name: string }[];
  path: PathStep[];
}

export interface RelationOutcome {
  a: string;
  b: string;
  results: RelationResult[];
  message: string | null;
}

export interface PersonRef {
  id: string;
  name: string;
}

export interface UploadedPicture {
  id: string;
  width: number;
  height: number;
  /** The card-sized version, as a data URL, to show before saving. */
  preview: string;
}

export interface DeletionPreview {
  allowed: boolean;
  /** Stands for exactly the relationships listed; deletion is refused if they change. */
  relationships: string;
  parent_links: { id: string; parent: PersonRef; child: PersonRef; role: ParentRole }[];
  spouse_links: { id: string; spouse: PersonRef }[];
  blocked_people: PersonRef[];
}

export interface AccessCode {
  id: string;
  label: string;
  role: CodeRole;
  created_at: string;
  revoked_at: string | null;
  revoked: boolean;
}

export type SnapshotKind = "daily" | "before_load";

export interface Snapshot {
  id: string;
  kind: SnapshotKind;
  /** When the tree was first seen like this; a daily snapshot is renewed while the tree stays the same. */
  first_taken: string;
  taken_at: string;
  people: number;
  relationships: number;
  /** Bytes stored. */
  size: number;
  /** False if taken by a FamTree release with a different database layout. */
  loadable: boolean;
}

export interface AdminSettings {
  /** Whether visitors without a code may read the public tree. */
  guest_access: boolean;
}

// --- requests ------------------------------------------------------------------

export type Ref = { id: string } | { ref: string };

export interface AttributeInput {
  definition: Ref;
  value: AttributeValue;
  is_public: boolean;
}

export interface NewDefinition {
  ref: string;
  label: string;
  value_type: ValueType;
}

export interface ChangeSet {
  definitions?: NewDefinition[];
  people?: { ref: string; name: string; attributes?: AttributeInput[] }[];
  parent_links?: { parent: Ref; child: Ref; role: ParentRole; is_public: boolean }[];
  spouse_links?: { a: Ref; b: Ref; is_public: boolean }[];
}

export type ExportFormat = "png" | "pdf";
export type ExportScope = "full" | "view";
export type Orientation = "auto" | "portrait" | "landscape";

export interface ExportRequest {
  format: ExportFormat;
  scope: ExportScope;
  window: { selected_id: string; above: number; below: number } | null;
  /** View Only Selected: with the "view" scope, only these people. */
  people: string[] | null;
  attributes: string[];
  include_parent_links: boolean;
  include_spouse_links: boolean;
  include_legend: boolean;
  png_width: number;
  page_size: string;
  orientation: Orientation;
}

export interface ExportPreview {
  image: string;
  people: number;
  /** Cards on which a name or value is cut short to fit. */
  shortened: number;
  warnings: string[];
  output: { width: number; height: number; unit: "px" | "pt" };
  text_size: { value: number; unit: "px" | "pt" };
  legible: boolean;
}
