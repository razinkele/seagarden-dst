# Deploying the DST to laguna.ku.lt

**Audience: somebody who is not the author.** The Application Form commits the Lead Partner
to keeping this tool online on KU MRI servers to **May 2034**, with no maintenance budget.
A deployment only one person can reproduce does not survive that, so this runbook states
what to check and what a failure looks like, not only what to type.

The live instance is **https://laguna.ku.lt/seagarden-dst/**.

---

## 1. What runs where

The hosting files live in a **different repository** — `razinkele/seagarden`, checked out at
`~/seagarden` on the server. That is correct: they configure the host, not this application.
This runbook is the only document that describes *shipping a new version*, and it lives here
because that is a property of the app.

| Piece | Where | Authority |
|---|---|---|
| Checkout | `/home/razinka/seagarden-dst` | this repo, branch `main` |
| Python env | `/opt/micromamba/envs/shiny` | shared with the host's other Shiny apps |
| Install | `pip install -e ".[app]"` — **editable** | see §3 for why that matters |
| Service | `seagarden-dst.service` → `/etc/systemd/system/`, `127.0.0.1:8140` | `~/seagarden/deploy/` |
| nginx | `laguna-seagarden-dst.location.conf`, included in the `nid4ocean` vhost | `~/seagarden/deploy/nginx/` |
| Portal card | `/var/www/html/services.json`, id `seagarden-dst` | **not version-controlled anywhere** |

`~/seagarden/deploy/README.md` §"SeaGarden DST on the laguna portal" explains *why* the app
runs under its own unit rather than shiny-server, and why no `--root-path` is needed. Read it
once before your first deploy; do not duplicate it here.

## 2. Two things about this host that will surprise you

**`sudo` requires a password.** `razinka` has full sudo rights but no passwordless entry for
`systemctl`, so the restart in §4 cannot be run from a non-interactive SSH command or a script.
It needs a terminal you can type into. Every other step in this runbook can be automated; that
one cannot, and a deploy script that assumes otherwise will fail silently in the middle.

**The deployment directory is also a development checkout.** On 2026-09-16 commits were
authored directly in `/home/razinka/seagarden-dst` and pushed from there. That means a deploy
is a `git pull` into a tree somebody may have been working in. §3's preflight exists for that
reason and is not a formality — skipping it is how you deploy a half-finished local commit, or
lose one.

## 3. Preflight

Stop if any of these is not true.

```bash
ssh razinka@laguna.ku.lt
cd ~/seagarden-dst

git status --porcelain          # MUST be empty — uncommitted work in the serving tree
git log origin/main..HEAD       # MUST be empty — local commits not yet pushed
git fetch --tags origin
```

If `git status` is dirty or there are local commits, **do not continue.** Find out whose they
are. Committing or stashing them to clear the check is how work gets lost; the tree is shared.

Pick the release and confirm it exists:

```bash
TAG=v0.2.0
git rev-parse --verify "refs/tags/$TAG"
```

**Deploy a tag, never a branch tip.** A tag is a version somebody can cite in a deliverable;
`main` is wherever development happened to be.

## 4. Deploy

```bash
git merge --ff-only "$TAG"      # refuses rather than creating a merge commit
```

If it refuses, HEAD is not an ancestor of the tag — the tree has diverged, and §6 is where you
go.

**Reinstall only if dependencies changed.** The install is editable, so the checkout *is* the
installed package: a pull updates the code and `__version__` together, and reinstalling is
normally unnecessary noise on a shared environment other apps use.

```bash
git diff HEAD@{1}..HEAD -- pyproject.toml     # inspect the diff yourself
```

If `dependencies` or `optional-dependencies` changed — not merely `version` — then:

```bash
/opt/micromamba/envs/shiny/bin/python3 -m pip install -e ".[app]"
```

Restart. **This needs your sudo password** (§2), so run it in a terminal:

```bash
sudo systemctl restart seagarden-dst
```

## 5. Verify

All four must pass. A deploy that serves 200 while running the previous version is the failure
this section exists to catch, and it is invisible from the outside.

```bash
systemctl is-active seagarden-dst                                    # active
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8140/      # 200
curl -s -o /dev/null -w '%{http_code}\n' https://laguna.ku.lt/seagarden-dst/   # 200

/opt/micromamba/envs/shiny/bin/python3 -c \
  'import seagarden_dst; print(seagarden_dst.__version__)'           # must equal $TAG without the v
```

**That version check alone does not prove the service restarted**, and the trap is worth stating
because the command looks like it does. The install is editable, so it spawns a *new* process
that reads the checkout as it is now — it reports the new version the moment the merge lands,
while the running service still holds the old module in memory. Assert the restart separately:

```bash
systemctl show -p ActiveEnterTimestamp --value seagarden-dst   # when the service started
git -C ~/seagarden-dst log -1 --format=%cd HEAD                # the commit it should be serving
```

**The service must have entered active state *after* the deploy moved the checkout.** If it did
not, the process is running code that is no longer on disk — and every other check here still
passes.

Together these are the deployment-level twin of `tests/test_version.py`, which guards the two
version literals against each other in CI. This pair guards the *running instance* against the
tag it claims to be. `app/shell.py` reads the same value into the About box, so a user can confirm
it without shell access — open the app and look.

**The websocket is the part that breaks when proxying Shiny**, and a 200 on the page does not
exercise it. It can be asserted without a browser — ask nginx for the upgrade directly and
require `101 Switching Protocols`:

```bash
curl -s -o /dev/null -w '%{http_code}
'   -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13'   -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ=='   https://laguna.ku.lt/seagarden-dst/websocket/
```

Anything other than `101` — typically `502`, or a `200` from nginx swallowing the upgrade —
means the proxy is serving the page but no session will ever start. The app looks fine and is
unusable.

Last, in a browser, and only this part needs one: load the app, run one assessment, and confirm
the About box reports the expected version. `app/shell.py` reads it from the package, so this is
how somebody without shell access checks what is deployed.

## 6. Rollback

A failed deploy is rolled back, not fixed forward under pressure.

```bash
cd ~/seagarden-dst
git merge --ff-only <previous-tag>   || git reset --hard <previous-tag>
sudo systemctl restart seagarden-dst
```

Then re-run §5 in full against the previous tag. `git reset --hard` is safe **only** because
§3 established the tree had nothing uncommitted in it — if you skipped the preflight, you do
not know that.

Before `v0.2.0` there were no tags. To roll back to something older than the first tag, use the
commit the reflog names: `git reflog` in the checkout shows each deploy as a `merge`, `pull` or
`checkout` entry with its date.

## 7. What is not covered

- **The portal card** (`/var/www/html/services.json`) is edited in place and version-controlled
  nowhere. A deploy does not touch it. It needs editing only when the app's name, description or
  URL changes — see `~/seagarden/deploy/README.md`.
- **No deploy script.** The sequence above has been run by hand once (v0.2.0). Automating it is
  worth doing after it has been followed a second time by somebody else, which is also the test
  of whether this document works.
- **`scripts/verify-deploy.sh`** in the `seagarden` repo checks the Hugo site, not this app. It
  has no DST coverage; §5 is the DST's verification.
