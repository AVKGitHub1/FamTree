# FamTree

A self-hosted family tree you can share. It shows a generation-based
diagram with right-angle connection lines, separates public from private
information, calculates relationships ("A is B's first cousin twice
removed") and exports to PNG or PDF. All data is encrypted at rest. The
interface has light, dark and sepia themes; exports are always on white paper
for printing.

The full specification is in [design.md](design.md). Running and maintaining
an installation is covered in [docs/operations.md](docs/operations.md).

## Quick start

Requirements: Docker with Compose v2. Builds work on arm64 (Raspberry Pi) and amd64.

Copy the template (the real file is gitignored, so local tweaks never land in
commits), create the data folder and the encryption key once, and start:

```bash
cp docker-compose.yml.example docker-compose.yml
mkdir -p ~/data/FamTree
scripts/init-key.sh          # ~/.config/famtree/encryption.key, mode 600
docker compose up -d --build
```

On first start the container prints the **admin password once**:
`docker logs famtree`. Treat that log as sensitive; after noting the password,
`docker compose up -d --force-recreate` starts a fresh container without it.

The port, 8765, is published on all interfaces, as in the dashboard project.
Point your Cloudflare tunnel at `http://localhost:8765` (see
[operations](docs/operations.md#cloudflare-tunnel)); tailnet devices can use
`http://<tailscale-name>:8765`. The site opens on an access-code screen; use
**Admin sign in** there, then create access codes under **Admin → Access codes**.

**Back up the key file separately from the data.** Without it the tree cannot be recovered.

## Who sees what

| Access | Public data | Private data | Edit people & details | Manage codes |
| --- | --- | --- | --- | --- |
| Guest (no code)¹ / Public viewer code | ✓ | | | |
| Family viewer code (`private_viewer`) | ✓ | ✓ | | |
| Editor code | ✓ | ✓ | ✓ | |
| Admin password | ✓ | ✓ | ✓ | ✓ |

¹ Unless the admin sets **Admin → Guest access** to *Nothing*; visitors then
need a code (a public viewer code is enough) to see anything.

Names are always public. Every other detail and every relationship has its
own public/private setting, and new ones start private. Each person needs at
least one public relationship, so the public tree always shows who someone is
connected to. The server filters every response (tree, search, relation
results, exports) for the caller. The browser never receives data it may not
show.

## Configuration

Everything is set in `docker-compose.yml`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `ports` | `"8765:8080"` | Host port (left), published on all interfaces. If it is taken, Compose reports "port is already allocated": change the left-hand number. |
| `volumes` | `~/data/FamTree:/data` | Encrypted database, WAL and backups |
| `secrets.famtree_key.file` | `~/.config/famtree/encryption.key` | 64-hex-character key, mounted separately from the data |
| `user` | `"1000:1000"` | Owner of the data folder and key (`id -u` / `id -g`) |

Optional `environment` entries: `FAMTREE_COOKIE_SECURE` (`auto` by default;
`true` always requires HTTPS for sessions), `FAMTREE_LOG_LEVEL`,
`FAMTREE_SESSION_TTL_HOURS`, `FAMTREE_ADMIN_SESSION_TTL_HOURS` and
`FAMTREE_TRUSTED_PROXIES`. They are documented in
[backend/famtree/config.py](backend/famtree/config.py).

## Project layout

```text
backend/                Python 3.13, FastAPI
  famtree/
    storage/            SQLCipher database, key file, first launch, migrations, backup
    security/           permissions, sessions, access codes, passwords, rate limits
    domain/             people/relationship model, validation, edits, search, relations
    layout/             generation rows, ordering, x positions, orthogonal routing
    export/             export scene + cairo/Pango rendering to PNG/PDF (in memory)
    api/                HTTP routes, request schemas, response shaping
    app.py, server.py   app factory and process entry point (python -m famtree)
    cli.py              operator commands (famtree-admin)
  tests/                pytest suite (unit + API + storage + export)
frontend/               React 19 + TypeScript + Vite
  src/api/              typed API client
  src/state/            session, tree data, UI reducer, toasts
  src/lib/              pure logic: generations, dates, viewport maths, drafts
  src/components/       tree view, panels, dialogs
  test/                 vitest unit tests
scripts/                init-key.sh (encryption key), check.sh (all tests)
docs/operations.md      backup/restore, key handling, password reset, troubleshooting
Dockerfile              SPA build, Python runtime, test stage
```

## Implementation choices

These settle the "Decisions to resolve" in the design doc:

- **Framework:** FastAPI backend serving a React/TypeScript SPA from one container.
- **Storage and encryption:** SQLCipher 4 (whole-database AES-256, including
  the WAL and backups) with a raw 256-bit key from a mounted secret. Temp
  tables are kept in memory. The admin password is hashed with Argon2id.
  Access codes are stored inside the encrypted database so they can be
  revealed, and looked up by digest.
- **Layout:** a custom engine (`backend/famtree/layout`). It ranks
  generations as a constrained optimisation, keeping every parent above their
  children and merging spouses into the same row when that stays acyclic. It
  then reduces crossings with barycentric sweeps, positions cards with
  isotonic regression, and routes lines on separate tracks. Real branch points
  get dots; crossings get gaps. The same layout drives the browser view and the
  exports.
- **Export:** rendered on the server with cairo and Pango, so names in
  Devanagari, Arabic, Tamil and similar scripts are shaped correctly with
  Noto fonts. Files are produced in memory and streamed back, never written
  to disk.
- **Size target:** up to about 500 people. On a Raspberry Pi 5 the layout of
  a 500-person tree takes about 0.1 s, and a PNG export of a small tree about
  0.1 s.

## Development

Backend (uses the system's PyGObject/pycairo for export rendering):

```bash
cd backend
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest            # export tests skip if python3-gi-cairo is missing
.venv/bin/ruff check . && .venv/bin/ruff format --check .

# Run locally against a scratch directory:
mkdir -p /tmp/ft-data && ../scripts/init-key.sh /tmp/ft.key
FAMTREE_DATA_DIR=/tmp/ft-data FAMTREE_KEY_FILE=/tmp/ft.key .venv/bin/python -m famtree
```

Frontend (Node 22; no local install needed):

```bash
cd frontend
docker run --rm -it -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/app -w /app \
  -p 5173:5173 node:22-alpine npx vite --host   # proxies /api to 127.0.0.1:8080
```

Everything at once, in containers: `scripts/check.sh`. It runs ruff and
pytest in the Docker `test` stage, plus tsc, eslint and vitest.
