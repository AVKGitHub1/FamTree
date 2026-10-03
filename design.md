# FamTree Design Doc

## Purpose and scope

FamTree is a Docker-hosted website for viewing and editing a shared family tree. The core experience is a generation-based diagram, with code-based access, public and private information, relationship calculations, and image/PDF export.

The following choices are retained:

- Store persistent data on the host under `~/data/FamTree`, encrypted at rest.
- Print an admin password on first initialization; the admin can view and edit everything and manage access codes.
- Let guests view public information and let code holders act according to their code's permissions.
- Model people with names, extensible attributes, and mother/father, child, and spouse connections. Support multiple mothers, fathers, and spouses.
- Show rounded person cards, generation rows, and right-angle family connection lines.
- Provide the four generation controls, relation calculation, node menus, and configurable image/PDF export.
- Let users select several cards and show only the selected people.
- Keep daily snapshots of the tree that the admin can load or delete.

Framework, database, and graph-layout library selection are implementation decisions. They must support the behavior and privacy rules below.

## Docker and persistent data

### Hosting

- Use a configurable host port, with `18765` as the proposed default. No port can be guaranteed unused; if it is occupied, fail with a clear instruction to select another port.
- Mount the expanded host path `~/data/FamTree` into the container at `/data`. Container replacement or restart must preserve people, relationships, attribute definitions, credentials, and settings.
- Serve over a local port. DNS points the subdomain to the port via cloudfared.
- Provide a health check and graceful shutdown. A readiness check must fail if storage cannot be opened or decrypted.

### Encryption and recovery

- Encrypt the persistent database and any sensitive persistent files, temporary export files, and backups using a maintained encryption implementation. Encryption must cover names, attributes, relationships, codes, and authentication state; encrypting only selected private fields is insufficient.
- Supply the encryption key through a separately mounted secret. Do not embed it in the image or save it beside the encrypted data. Restrict host-directory and secret permissions to the service operator.
- Keep the encryption key across container replacement. If a populated data directory cannot be decrypted, fail clearly; never silently initialize a replacement tree.
- Store the admin password as a salted password hash. Store recoverable access-code values encrypted, because the admin must be able to view existing codes.
- Provide an operator procedure for backing up and restoring the data, preserving the key separately, and resetting a forgotten admin password with host access. A password reset must not replace the data-encryption key.
- Document that loss of the encryption key makes the encrypted data unrecoverable. At-rest encryption does not protect data from an operator who controls both the running server and its key.

### Snapshots

- Check for a due daily snapshot at startup and every hour, using UTC dates. If the latest daily snapshot was taken or renewed that day, further checks and restarts do nothing until the next UTC day. When due, compare the tree with the latest daily snapshot: save a new snapshot if the family data differs; otherwise renew the latest one, recording when it was first and last seen that way. Revisions and edit timestamps alone do not count as changes. Skip an empty tree and check again the next hour.
- A snapshot holds family data only: people, attribute values with their visibility, attribute definitions, relationships, and references to the pictures in use. A picture stays stored while any snapshot uses it. Credentials, access codes, sessions, and settings are not part of a snapshot.
- Store snapshots inside the encrypted database. Keep the latest 20, counting both kinds and ordered by when each was last taken; taking another deletes the oldest.
- The admin can list, delete, and load snapshots. Loading first saves the current tree as a snapshot, then replaces the tree in one transaction. Access codes, sessions, guest access, and the admin password are unchanged. Loaded records get revisions above any a record has had, including those deleted since, so an edit made from a page that still shows an earlier tree is rejected as stale, even for a person the load brings back.
- The snapshot saved before a load can contain an empty tree, so loading into an empty installation can also be undone. It counts toward the same 20-snapshot limit. Loading the oldest snapshot at that limit can remove its list entry; its family data becomes the current tree.
- A snapshot taken with a different database schema is listed but cannot be loaded.
- Snapshots supplement backups rather than replace them: they are lost with the database.

## Access and privacy

### First launch and admin access

- On initialization of an empty data directory, generate a strong random admin password and print it to the container's local standard output once. Do not expose it through a web endpoint.
- Persist initialization state so restarts do not reset or reprint the password. Treat first-launch logs as sensitive and avoid forwarding the bootstrap password to routine application logging.
- The admin can change the password, view and edit all family data, manage access codes, and view, load, and delete snapshots of the tree.
- The admin can generate strong random codes, list and reveal existing codes, assign roles, and delete/revoke codes. Each code has an ID, optional label, role, creation time, and revocation state. Reveal full code values only in the authenticated admin interface.
- Revoking a code removes access for sessions issued from it on subsequent requests. Permission changes also apply to existing sessions.

### Code permissions and sessions

Use whole-tree roles; permissions are not scoped to individual people or attributes.

| Role | Read public data | Read private data | Edit family data and attribute definitions | Manage codes, snapshots, and admin settings |
| --- | --- | --- | --- | --- |
| Guest (no code) | Yes | No | No | No |
| Public viewer code | Yes | No | No | No |
| Private viewer code | Yes | Yes | No | No |
| Editor code | Yes | Yes | Yes | No |
| Admin password | Yes | Yes | Yes | Yes |

A public viewer code grants the same data access as a guest. Revoking a code removes its privileges; the holder can still access public information as a guest.

- A guest has read access only to public information. A valid code grants only its assigned permissions; the admin has all permissions.
- On first access, ask for an access code; admin sign-in is a separate button. The admin can turn guest access off, in which case guests can read nothing and must enter a code.
- Check authorization on the server for every read, search, mutation, relation calculation, and export. Hiding a button is not authorization.
- Exchange passwords and codes for sessions rather than including them in URLs. Protect session cookies from script access, require secure transport for internet use, protect mutations against cross-site requests, and rate-limit authentication attempts.
- Do not record passwords, full codes, private attributes, or exported family data in ordinary logs.

### Visibility rules

- Names are required and always public, so every person is identifiable in the public tree. Visibility for other attributes belongs to each value on each person; each relationship also has its own public/private setting. A custom attribute's definition does not make every person's value public.
- Every person must have at least one public parent, child, or spouse relationship, except when the tree contains only one person. Enforce this rule on creation, relationship edits, visibility changes, and deletion.
- A relationship has a single visibility setting shared by its two endpoints. Publishing one person's side of a connection necessarily reveals that connection at the other endpoint.
- Other attributes and extra relationships may be private. Newly entered optional attributes and relationships default to private; creation requires the editor to explicitly select the required public connection.
- Show editors the publication consequence before saving a public relationship. A public relationship necessarily reveals that both endpoint people exist.
- Build search suggestions, layouts, relation results, and exports from the caller's authorized data. Never send private values to a guest browser and rely on CSS to hide them.
- Public relationships need not form one connected diagram even when the full graph is connected. Render separate visible components without revealing the private links between them.

## Data model and editing

### People and attributes

- Give each person a stable ID independent of their name. Require a nonempty name, but allow duplicate names. When a new person's name, or a changed name, matches someone already in the tree (ignoring case, accents, and spacing), warn the editor and show what tells the existing people apart; do not block the save.
- Common optional attributes are birth date, location, profession, and a short description. Support a month-and-day birth date without a birth year; do not insert a fabricated year. An omitted date is distinct from a partially specified date.
- Store names and other text as plain text and escape them for display and export.
- Support reusable custom attribute definitions. Each definition has a stable ID, display label, and value type; editors can create a definition while editing a person, and it then becomes available for future people.
- Renaming a definition preserves existing values. Reject incompatible type changes while values exist. Individual values keep their own visibility setting.
- Record revisions for editable records so simultaneous edits cannot silently overwrite each other; a stale save asks the editor to reload and reconcile.

### Profile pictures

- Provide one optional built-in **Profile Pic** attribute per person, with the same per-value visibility rule as other details. It starts private and appears on the card and in the details panel when the caller may see it. Custom attribute types remain short text, long text, date, number, and link; additional image attributes are not supported.
- Choosing a picture uploads it immediately; saving the person's details attaches it to that person. Canceling the edit does not change the saved picture. A pending upload must finish before the details can be saved.
- Where the browser can decode the selected image, resize it to at most 1600 pixels on its longest side and convert it to JPEG before upload. The server independently accepts JPEG, PNG, or WebP, limited to 15 MiB and 50 million pixels, and re-encodes it without camera metadata. Apply orientation and flatten transparency onto white. Do not preserve the original uploaded file.
- Store a JPEG up to 640 pixels on its longest side and a 128 × 128 square thumbnail inside the encrypted database. Cards use the thumbnail; the details panel uses the larger version. Serve pictures through an authorized person's endpoint with browser caching disabled.
- Export pictures only when **Profile Pic** is selected among the attributes. Use a square crop from the stored larger image; where no permitted picture is available, show initials derived from the public name. This does not distinguish a missing picture from a private one.

### Relationships

The family tree is a graph: multiple parents and spouses mean it is not necessarily a strict mathematical tree.

- Store a parent-child relationship once, with parent ID, child ID, a mother/father role, and visibility. Derive the child's parent list and the parent's child list from the same relationship.
- Treat all parent links equally. Do not distinguish biological, adoptive, step, or guardian relationships; every parent link counts in relation calculations.
- Allow multiple mother and father relationships for a child. Mother/father is a role on a particular relationship, not a limit on the number of parents or an inference from the person's name.
- Store a spouse relationship once as an unordered pair of person IDs plus visibility. Allow multiple spouses without requiring that they share children.
- Do not infer that two parents are spouses, that a parent's spouse is also a parent, or that spouses share every child. Draw each child from their explicitly recorded parent relationships.
- Reject self-parenting, self-spouse links, duplicate relationships, and parent-child cycles. Multiple paths to the same ancestor are valid and must not be rejected as cycles.
- Save person and relationship changes atomically, including cycle and required-public-connection validation.

### Add and edit workflow

1. A user with edit permission creates the first person with a name and no connection. This is the bootstrap exception; adding a second person requires a public connection between them.
2. For later additions, enter the new person's name and select a parent, child, or spouse connection. When adding from an existing card, preselect that person as the connection target.
3. Show a matching-name dropdown while typing a related person's name. Include only information the editor may view; use permitted contextual attributes to distinguish people with the same name. Selecting a result links its existing ID and never creates a duplicate implicitly.
4. If there is no appropriate match, offer an explicit action to create a new related person, with the duplicate-name warning if the name is already in the tree. Create the two people and their relationship in one transaction so neither is left invalid.
5. For parent/child connections, collect the parent's mother/father role. Clearly identify which person is the parent before saving.
6. The name is public. Choose public/private visibility for other attributes and relationships; at least one relationship for each newly created person must be public.
7. Validate and save, then show the updated cards and reciprocal connections.

Edits and deletions must preserve graph validity and required public connections. Before removing a person, show which incident relationships will be removed; reject the operation if it would leave a remaining person without a public relationship, unless only one person would remain.

## Family tree view

### Cards and layout

- Start with the full authorized tree visible and fit it to the viewport. Support pan and zoom so larger trees remain usable. With a mouse, dragging selects (see below), so pan with Space + drag, a middle-button drag, or the arrow keys; the wheel zooms. On touch screens, a drag pans and two fingers zoom.
- Use rectangles with rounded corners for people. Display the public name and a compact selection of permitted attributes; provide the remaining permitted details on selection.
- Place parents above children, with spouses and siblings on the same generation row whenever these constraints are compatible.
- Multiple parents and spouses can create conflicting generation constraints. Prioritize parent-above-child placement and clearly route exceptional connections when all same-row preferences cannot hold. Do not alter family data to simplify the drawing.
- Keep placement deterministic for the same graph and preserve the selected person and viewport when possible after an edit.
- Include empty, loading, error, and no-visible-results states. Guests seeing an empty tree cannot create its first person.
- Offer light, dark, and sepia themes, plus a default **System** choice that follows the device's light/dark preference. Remember the choice in that browser for the site's origin. Exports use a white background regardless of the interface theme.

### Connection lines

- Draw a spouse line between spouse cards. For children shared by that pair, extend a line from the center of the spouse line and branch at right angles to their children.
- For a child with one visible parent, extend horizontally from that parent's center, turn downward at a right angle, and branch toward the child or children.
- For two parents without a spouse relationship, or more than two parents, use a labeled parent junction that connects the recorded parents to their shared child or child group without implying a marriage. Group children only when their visible parent sets match.
- Route crossings so an intersection cannot be mistaken for a family junction. Use a legend or labels where line meanings differ; do not rely only on color.
- Render lines from the authorized graph. A private parent relationship must not be disclosed by a dangling connector, reserved card space, or an explanatory tooltip.

### Generation controls

- Keep four buttons beside the tree: `^+`, `^-`, `⌄+`, and `⌄-`.
- Require a selected person before enabling these controls. The selected person's generation is the reference point and remains visible.
- Filter generation rows across the whole authorized tree, rather than only the selected person's ancestor/descendant branches. For selected row `g`, show rows from `g - A` through `g + D`, where `A` and `D` are the visible generation counts above and below the selection.
- `^+` increases `A` by one; `^-` decreases it by one. `⌄+` increases `D` by one; `⌄-` decreases it by one. Neither count can fall below zero or exceed the available rows in that direction. Initially both counts include all available rows.
- Show all people in the included rows, including spouses and siblings placed there. Draw complete relationship lines only between visible endpoints and mark filtered continuations without revealing unauthorized relationships.
- Add accessible labels: show one more generation above, hide one generation above, show one more generation below, and hide one generation below.
- Disable controls at their limits and provide a reset to the full authorized tree. Selecting a different person resets the generation limits so earlier hidden rows do not create a misleading starting view.

### Selection and View Only Selected

- Dragging over the tree with a mouse or pen draws a selection rectangle; every card it touches is selected. Ctrl/⌘ + click adds or removes one card, and Ctrl/⌘ + drag adds to the selection. A plain click selects only that card and opens its details; clicking empty space clears the selection. From the keyboard, Ctrl/⌘ + Enter adds or removes the focused card.
- A top-level **View Only Selected** button, showing how many people are selected, shows only those people and fits them to the screen. It shows the selection as it was when pressed; later changes to the selection take effect when it is pressed again. Cards keep their positions in the full layout.
- Draw lines between shown people. A family line keeps the branches to its shown parents and the drops to its shown children, with its horizontal line shortened to match; a couple's line to their children needs both partners shown. Continuation marks show people whose relatives are not shown.
- The generation controls still apply within the selected view. The person in focus stays visible: if they are not selected, View Only Selected lets go of them; someone chosen from the details panel or just added joins the view.
- A top-level **Default View** button shows the full tree again: it ends View Only Selected, resets the generation controls, and fits the tree to the screen. The selection is kept.

### Available actions

Selecting a card exposes its vertical `⋮` menu:

- **Add connection** is a private action requiring edit permission. It opens the add workflow with that person preselected.
- **Calculate relation with another card** is public for visible cards. It starts relation calculation with the current person already selected as the first person.
- Users with edit permission can also edit the selected person's attributes and relationships through its details view.

Actions have an explicit public/private classification plus a required capability. A private viewer cannot perform a private editing action merely because they can read private data. Admin controls remain restricted to the admin.

All controls, person selection, and relation selection must work with keyboard navigation as well as pointer input. On smaller screens, keep controls usable without obscuring the selected card.

## Calculate Relation

- Provide a top-level **Calculate Relation** button. Clicking it starts a two-person selection flow with clear first/second prompts, selected-card highlighting, and cancellation.
- The card-menu shortcut enters the same flow with its first person already selected.
- Compute from the caller's authorized graph. Generation filters affect drawing only, not which authorized relationships are available to this calculation.
- Treat the order explicitly: report “A is B's …” so ancestor, descendant, aunt/uncle, and niece/nephew results are unambiguous.
- Handle the same person, direct ancestors/descendants, siblings, aunt/uncle and niece/nephew relationships, and direct spouses as named cases. Do not force these into cousin notation. A recorded shared parent is enough to identify siblings; missing parent data must not be interpreted as evidence of a half-sibling relationship.
- For a shared ancestor at parent-link distances `a` and `b`, where both are at least 2, cousin degree is `min(a, b) - 1` and removals are `abs(a - b)`. For example, `(2, 2)` means first cousins and `(2, 4)` means first cousins twice removed.
- Multiple ancestry paths are possible. Deduplicate equivalent results and show multiple distinct closest ancestry results instead of silently choosing an arbitrary path. Define “closest” by the lowest total number of parent links through a common ancestor, with ties retained. A spouse result can coexist with an ancestry result.
- Explain the selected result using a visible relationship path. If there is no eligible path, say “No relationship found in the available data,” without asserting that the people are unrelated or disclosing hidden connections.

## Export

- Export the authorized tree view as an image or PDF. Offer **current view** (respecting generation filters and View Only Selected) and **full authorized tree**, with a preview of the selected scope. Draw lines in the current view by the same rule as on screen.
- Ask which attributes to include across the exported cards. An attribute selection includes a value only when the caller may view that value; mixed public/private values of the same attribute do not bypass privacy.
- Require selection of at least one relationship category—parent/child or spouse—for placement; a one-person tree is exempt. Draw only selected, authorized relationships between included people. A filtered export may contain isolated cards even though each person has a public connection in the stored tree; retain those cards and their positions without inventing connections.
- Preserve the generation layout and orthogonal connection style. Include public names on exported cards so people remain identifiable.
- Let the user select image resolution and PDF page size/orientation. Fit the selected tree to the chosen output and show legibility in the preview rather than silently clipping it.
- Produce a clean diagram without interactive controls. Avoid exposing hidden attributes, private metadata, authentication codes, or private relationship counts in the file.
- Recheck authorization when generating and delivering a server-side export. Do not make export artifacts publicly addressable; promptly remove sensitive temporary files after use.

## Acceptance criteria

- A fresh data directory produces one admin password; a restart preserves data, permissions, and the existing password without reprinting it.
- Missing or incorrect encryption keys prevent opening existing data and never cause a fresh tree to overwrite it. A documented restore recovers the same tree using the backup and separately preserved key.
- A guest cannot retrieve private data through page responses, search suggestions, relation results, or exports. An authenticated caller cannot exceed its code permissions; revocation affects its next request.
- Creating a person linked to an existing person updates both displayed endpoints. Duplicate names remain separate people, while duplicate links and parent-child cycles are rejected without partial saves.
- Multiple mothers, fathers, and spouses render without inventing marriages or parentage. Conflicting generation constraints remain understandable.
- A birthday without a year round-trips without adding a year. A new custom attribute is available on another person and each value retains its chosen visibility.
- Generation controls expand and collapse one level at a time, preserve the selected person, and reset to the full authorized tree.
- Dragging over cards selects them and Ctrl/⌘ + click toggles one. View Only Selected shows only those people, with the lines between them; Default View returns to the full tree.
- Adding or renaming a person to a name already in the tree warns the editor without preventing the save.
- A daily snapshot is saved when the tree changed and renewed when it did not; only the latest 20 are kept. Loading one saves the current tree first and leaves access unchanged.
- Relation examples include first cousins, first cousins twice removed, ancestors, siblings, multiple ancestry paths, spouses, and no visible relationship.
- Image and PDF exports respect selected scope (including View Only Selected), attributes, required connections, and current permissions, including public names and private parent links.

## Decisions to resolve before implementation

- Choose the framework, persistent store/encryption implementation, and layout/export libraries.
- Agree on an expected tree size and measurable render, search, calculation, and export targets before selecting graph algorithms and output limits.
