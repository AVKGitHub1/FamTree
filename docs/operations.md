# Operating FamTree

The commands below assume the default Compose setup (service `famtree`) and
are run from the repository directory.

## What lives where

| Item | Host location (default) | Notes |
| --- | --- | --- |
| Encrypted tree | `~/data/FamTree/famtree.db` (+ `-wal`, `-shm` while running) | mounted at `/data` |
| Backups | `~/data/FamTree/backups/` | encrypted with the same key |
| Snapshots | inside `famtree.db` | the latest 20 versions of the tree; **Admin → Snapshots** |
| Encryption key | `~/.config/famtree/encryption.key` | mounted as the secret `/run/secrets/famtree_key` |
| Settings | `docker-compose.yml` | copied from `docker-compose.yml.example`; gitignored |

The container runs as the compose file's `user` (your uid:gid), with a read-only root filesystem and all
capabilities dropped. Everything it writes is created with mode 600 inside a
700 directory.

## Encryption key

- The key is 64 hexadecimal characters (256 bits). `scripts/init-key.sh`
  creates it with mode 600 and refuses to overwrite an existing key.
- It is **not** in the image and **not** next to the data. Keep it that way.
- **Back it up separately** (for example in a password manager or on an
  offline USB stick). Data backups are useless without it.
- **If the key is lost, the encrypted data cannot be recovered.** There is no
  back door.
- Encryption at rest protects copies of the disk and backups. It does not
  protect against someone who controls both the running server and its key.
- If the data directory holds a database that the mounted key cannot decrypt,
  the server refuses to use it. It never initialises a replacement tree, and
  the file is left untouched. The site reports "unavailable", the health
  check fails, and the log states the reason.

## First launch and the admin password

When the data directory is empty, the server creates a new tree and prints
the admin password **once** to the container's standard output. It is not
available through any web endpoint, and it is never printed again on restart.

Read it with `docker logs famtree`. Treat that first-launch log as sensitive:
after noting the password, run `docker compose up -d --force-recreate` so the
running container no longer carries it in its log. Once signed in, change the password under
**Admin → Admin password**; this signs out other admin sessions.

### Resetting a forgotten admin password

You need host access:

```bash
docker compose exec famtree famtree-admin reset-admin-password
```

This prints a new password and signs out all admin sessions. The encryption
key and the family data are not changed. Access codes keep working.

## Access codes

The admin creates codes under **Admin → Access codes**, choosing a label and
a role (public viewer, family viewer or editor). Codes can be revealed later,
re-assigned to another role, revoked or deleted. Revoking or deleting a code
ends the sessions it started on their next request; the holder is then
treated as a guest. Codes and passwords are exchanged for an HttpOnly,
SameSite=Strict session cookie and never appear in URLs. Sign-in attempts are
rate-limited per client and globally.

Visitors who are not signed in first see an access-code screen, with a
separate **Admin sign in** button. Under **Admin → Guest access** the admin
chooses what they get without a code:

- **The public tree** (default): the screen also offers *Continue without a
  code*, and the browser remembers that choice until someone signs in there.
- **Nothing**: the server refuses every tree, search, relation and export
  request without a code, and the screen only asks for one. Hand out public
  viewer codes to people who should see just the public tree.

## Backups

A backup is a consistent, standalone, encrypted copy. It is safe to take
while FamTree is running:

```bash
docker compose exec famtree famtree-admin backup
# -> /data/backups/famtree-YYYYMMDDTHHMMSSZ.db  (host: ~/data/FamTree/backups/)
```

Copy backups **off the host**; a backup on the same disk does not protect you
from disk failure. Profile pictures and [snapshots](#snapshots) are inside the
database, so they are in every backup too (typically well under 100 KB per
picture, about 1 KB per snapshot of a small tree). Check a backup at any time with:

```bash
docker compose exec famtree famtree-admin verify /data/backups/famtree-….db
```

Example nightly backup that keeps 30 days (`crontab -e` on the host):

```
30 3 * * * cd /home/USER/code/FamTree && docker compose exec -T famtree famtree-admin backup >/dev/null && find /home/USER/data/FamTree/backups -name 'famtree-*.db' -mtime +30 -delete
```

## Profile pictures

Editors add or replace a picture through the built-in **Profile Pic** detail.
Choosing a file uploads it immediately, but it becomes the person's picture
only when their details are saved. Removing the detail and saving removes it
from the current tree. New picture values start private.

The browser tries to resize a chosen image to at most 1600 pixels on its
longest side and upload a JPEG. If it cannot decode the file, the original
file is sent for server validation. The server accepts JPEG, PNG and WebP,
up to **15 MiB and 50 million pixels**, applies orientation, removes metadata
and puts transparency on white. It keeps a JPEG up to 640 pixels on its
longest side and a 128 × 128 square thumbnail, not the original photo. Keep
original photos separately if you need their full resolution.

Pictures are encrypted inside the database and included in backups. An
unattached upload has a one-hour grace period for saving the person's
details. After that it is eligible for deletion when a later cleanup runs;
this is not an hourly deletion timer. Cleanup runs during uploads, person
saves/deletions and relevant snapshot operations. A picture still referenced
by the tree or any snapshot is retained. Old pictures in snapshots are not
served through the current person's picture endpoint unless restored to the
current tree.

## Restoring a backup

```bash
docker compose stop famtree
docker compose run --rm famtree famtree-admin restore /data/backups/famtree-….db --yes
docker compose start famtree
```

The restore checks that the backup decrypts with the mounted key, passes an
integrity check and is not from a newer FamTree release before replacing
anything. It then copies the backup next to the live database and syncs it
to disk; only after that is the live database moved aside, so a failed copy
(a full disk, say) leaves the live tree as it was. The previous database is
kept as `famtree.db.replaced-<timestamp>`. If the service is still running,
the restore refuses to proceed.

A restore rolls back access as well as family data: **everyone is signed
out**, and access codes, guest access, the admin password and the list of
snapshots become what they were when the backup was taken. A code revoked
since then works again until you revoke it again, so review **Admin → Access
codes** and **Admin → Guest access** after restoring. If the admin password is
unknown, reset it (see above).

To go back to an earlier version of the tree without rolling back access or
stopping the service, load a [snapshot](#snapshots) instead.

If a restore is interrupted (power loss, for example) and `famtree.db` is
missing afterwards, the server reports `populated_without_database` and does
not create a new tree. Put the previous database back under its own name,
with any `-wal` and `-shm` files beside it, then start the service:

```bash
cd ~/data/FamTree
ls famtree.db.replaced-*                      # pick the newest timestamp
mv famtree.db.replaced-<timestamp> famtree.db
# only if they exist:
mv famtree.db.replaced-<timestamp>-wal famtree.db-wal
mv famtree.db.replaced-<timestamp>-shm famtree.db-shm
rm -f famtree.db.restoring
```

To restore a backup copied in from elsewhere, put it in the data directory
first (for example `~/data/FamTree/backups/`).

### Moving to a new host

1. On the new host, install Docker and clone the repository.
2. Copy the key to `~/.config/famtree/encryption.key` (mode 600), or point
   `secrets.famtree_key.file` in `docker-compose.yml` at it.
3. Copy the latest backup to `~/data/FamTree/backups/` on the new host.
4. `cp docker-compose.yml.example docker-compose.yml` (adjust it if needed),
   then `docker compose build`.
5. Restore: `docker compose run --rm famtree famtree-admin restore /data/backups/famtree-….db --yes`.
6. Start with `docker compose up -d`. The tree already exists, so no new
   admin password is created; the old one still works.

## Snapshots

Snapshots are earlier versions of the tree that the admin can load from the
web page (**Admin → Snapshots**), without stopping the service. They are not a
replacement for backups: they live inside the database, so they are lost
with it.

- At start-up and every hour, the server checks whether a daily snapshot is
  due. If the latest daily snapshot was taken or renewed for the current UTC
  date, even a restart does not capture further edits that day. On the next
  due check, the tree is compared with the latest daily snapshot. If it changed, a new
  snapshot is kept; if not, the latest one is renewed, so the list shows when
  the tree was last seen like that ("unchanged since …"). An empty tree is
  skipped and checked again the next hour. Revisions and edit timestamps
  alone do not count as changes. The log says `Daily snapshot created` or
  `renewed`. There is no snapshot of every edit or of days the server was off;
  use an operator backup when you need an immediate recovery point.
- A snapshot holds people, their details and pictures, relationships and
  attribute definitions. Pictures are not copied: a picture is kept for as
  long as the tree or any snapshot uses it.
- Loading a snapshot first saves the current tree as a snapshot ("Saved
  before a load"), so a load can always be undone by loading that one.
  Access codes, guest access, the admin password and sign-ins are not part
  of snapshots and stay as they are. Attribute and relationship visibility
  does return to the snapshot's values along with the family data. Anyone
  editing from a page that still shows the replaced tree is told it changed
  and to reload, also for a person deleted since and brought back by the load.
- The tree saved before a load may be empty; loading that saved snapshot
  returns to the empty tree. If loading the oldest snapshot when 20 are
  already kept, saving the current tree can remove that oldest list entry;
  the loaded family data still becomes the current tree.
- The latest 20 snapshots are kept, counting both kinds and ranked by when
  each was last taken; taking another deletes the oldest. The admin can also
  delete any of them. Each is compressed: a tree of a dozen people and their
  relationships takes about 1 KB.
- Deleting the latest daily snapshot does not pause the job. If no daily
  snapshot for today remains, the next check can create or renew one again.
- A snapshot taken by a FamTree release with a different database layout is
  listed but cannot be loaded.

## Ports

The host port is the left-hand number of `ports` in `docker-compose.yml`
(default `8765`). No port can be guaranteed free. If it is taken, `docker
compose up` fails with "port is already allocated": change the number and run
it again. Inside the container the server listens on 8080; if that port were
somehow taken, the server would exit with the same instruction.

The port is published on every interface, IPv4 and IPv6, as in the dashboard
project. That means it is reachable at `localhost` (cloudflared), on the
tailnet, and on the LAN, all over plain HTTP. To keep it off the LAN, limit
the port with your firewall or Tailscale ACLs, or prefix the mapping in
`docker-compose.yml` with a specific address.

## Cloudflare tunnel

cloudflared runs on the host and forwards the subdomain to the local port.
For a locally managed tunnel, the ingress rule looks like this:

```yaml
ingress:
  - hostname: tree.example.com
    service: http://localhost:8765
  - service: http_status:404
```

For a dashboard-managed (token) tunnel, add a public hostname with service
`HTTP` and URL `localhost:8765`.

cloudflared sends `X-Forwarded-Proto: https` and `CF-Connecting-IP`. FamTree
trusts these headers only from `FAMTREE_TRUSTED_PROXIES` (by default loopback
and the Docker bridge range). It then marks session cookies `Secure` and
rate-limits sign-ins by the real client address.

Set `FAMTREE_COOKIE_SECURE=true` to allow sessions only over HTTPS. Every
session cookie is then marked `Secure`; a sign-in that does not arrive over
HTTPS (as reported by a trusted proxy) is refused with "Sign in over HTTPS",
and session cookies sent over plain HTTP are ignored, so such requests are
treated as a guest's. Guests can still read the public tree over HTTP. This
includes the Tailscale route below: with `true`, use the tunnel to sign in.
The setting does not stop plain-HTTP connections to the port; to keep
devices off it, use the firewall, Tailscale ACLs or the `ports` mapping (see
[Ports](#ports)).

## Tailscale

Devices on your tailnet can open `http://<tailscale-name>:8765`, for example
`http://raspberrypi.tail1234.ts.net:8765`, or use the Tailscale IP. The traffic is
encrypted by WireGuard, so plain HTTP is fine here. Session cookies are not
marked `Secure` on this route, and sign-in works unless
`FAMTREE_COOKIE_SECURE` is `true`. Tailnet addresses are
not trusted proxies, so a tailnet device cannot spoof `X-Forwarded-*` headers.

The tunnel's hostname and the Tailscale name are separate sites to the
browser, so sign in separately on each.

## Health checks and shutdown

- `GET /api/health/live`: the process is up.
- `GET /api/health/ready`: storage is open and decrypted. The Docker health
  check uses this, so `docker ps` shows `unhealthy` when storage is
  unavailable.
- `docker compose stop` sends SIGTERM. In-flight requests get up to 15 s to
  finish, then the WAL is checkpointed and the database closed. Compose
  waits 20 s (`stop_grace_period` in the compose file) before it kills the
  container, which leaves time for that. Without the setting Docker waits
  only 10 s.

## Troubleshooting

`docker compose logs famtree` shows `STORAGE UNAVAILABLE (<reason>)`:

| Reason | Meaning and fix |
| --- | --- |
| `key_unavailable` | The key file is missing or malformed. Check `secrets.famtree_key.file` in `docker-compose.yml` and that it holds 64 hex characters. |
| `decrypt_failed` | The database exists but this key does not open it. Mount the original key; the data was not modified. |
| `populated_without_database` | The data directory has files but no `famtree.db`. FamTree will not create a new tree over them. Restore a backup or empty the directory. |
| `data_dir_not_mounted` | `/data` is not a mounted volume, so data would be lost with the container. Check the `volumes:` entry. |
| `data_dir_not_writable` | Ownership mismatch. Set `user` in `docker-compose.yml` to the owner of the data directory (`id -u`:`id -g`). |
| `locked` | Another FamTree process is using the directory. |

`The daily snapshot failed; it is tried again in an hour` in the log comes
with the error that caused it. The tree itself is not affected; the next
hourly check tries again.

`famtree-admin status` confirms the key opens the database and shows the
number of people, without displaying any names.

## Upgrading

```bash
git pull
docker compose exec famtree famtree-admin backup
docker compose up -d --build    # rebuilds and restarts; schema migrations run on start
```

Migrations only move forward. A newer database is refused by an older
release, so you never silently lose data by downgrading.

An upgrade that changes how the tree itself is stored leaves earlier
[snapshots](#snapshots) listed but no longer loadable, because they were taken
with the old layout; keep the backup taken before upgrading to go back that
far. The first upgrade to a release with snapshots creates the snapshot
storage and takes the first snapshot as it starts.
