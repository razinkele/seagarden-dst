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
| Install | `pip install -e ".[app]"` — **editable**, landing in `~/.local/lib/python3.13/site-packages` | see §2 and §4 |
| Service | `seagarden-dst.service` → `/etc/systemd/system/`, `127.0.0.1:8140` | `~/seagarden/deploy/` |
| nginx | `laguna-seagarden-dst.location.conf`, included in the `nid4ocean` vhost | `~/seagarden/deploy/nginx/` |
| Portal card | `/var/www/html/services.json`, id `seagarden-dst` | **not version-controlled anywhere** |

`~/seagarden/deploy/README.md` §"SeaGarden DST on the laguna portal" explains *why* the app
runs under its own unit rather than shiny-server, and why no `--root-path` is needed. Read it
once before your first deploy; do not duplicate it here.

## 2. Two things about this host that will surprise you

**The restart needs a password, but only because nobody has added a rule.** `razinka` has full
sudo rights, and the host *does* carry passwordless entries — `sudo -l` lists
`(ALL) NOPASSWD: /usr/bin/systemctl restart shiny-server, /usr/bin/systemctl is-active shiny-server`
and `(root) NOPASSWD: /usr/bin/systemctl reload shiny-server`. There is simply no such entry for
`seagarden-dst`. So the restart in §4 needs a terminal you can type into today, and that is a
sudoers gap rather than a property of the host: one line matching the `shiny-server` rule already
present removes this constraint and, with it, the failure §5's restart assertion exists to catch.
An earlier version of this section said the host had no passwordless `systemctl` entry at all,
which would have told you the restart is unautomatable forever.

Until that line exists, a non-interactive `sudo` **fails loudly**, not silently:
`ssh host 'sudo systemctl restart seagarden-dst'` prints `sudo: a terminal is required to read
the password…` and exits non-zero (`sudo -n` prints `sudo: a password is required`). A deploy
script needs to check the exit status, not detect a silent partial failure — there is no such
failure to detect.

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

git fetch --tags origin         # FIRST: the next check is meaningless against a stale ref

git rev-parse --abbrev-ref HEAD # MUST be `main` — see below
git status --porcelain          # MUST be empty — uncommitted work in the serving tree
git log origin/main..HEAD       # MUST be empty — local commits not yet pushed
```

The fetch comes first deliberately. Run the other way round, `origin/main..HEAD` compares against
whatever `origin/main` pointed at the last time anybody fetched, so commits that were pushed from
a laptop a week ago are reported as unpushed local work and you stop for nothing.

The branch check matters because §4 fast-forwards **whatever branch is checked out**. This tree
has sat on a feature branch before; deploying from that state advances the feature branch to the
tag, leaves `main` untouched, and gives no signal, because everything in §5 still passes.

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
test "$(git rev-parse HEAD)" = "$(git rev-parse "$TAG^{commit}")" \
  || echo "NOT ON THE TAG: HEAD is $(git rev-parse --short HEAD) — STOP"
```

**The assertion is not belt-and-braces; without it this step can do nothing and say it
succeeded.** `git merge --ff-only` only refuses when the tree has *diverged*. When HEAD is a
*descendant* of the tag — the normal state of a checkout tracking `main`, which is usually several
commits past the last release — it prints `Already up to date.` and exits **0**, leaving HEAD
where it was. You have then deployed `main` tip rather than the tag, which is exactly what §3
forbids, and every check in §5 passes anyway. Compare the commits and stop if they differ.

If the merge genuinely refuses, HEAD is not an ancestor of the tag — the tree has diverged, and
§6 is where you go.

**Reinstall only if dependencies changed.** The install is editable, so the checkout *is* the
installed package: a pull updates the code and `__version__` together, and reinstalling is
normally unnecessary noise on a shared environment other apps use.

```bash
git diff ORIG_HEAD..HEAD -- pyproject.toml    # inspect the diff yourself
```

`ORIG_HEAD` is set by the merge itself. `HEAD@{1}` is a *reflog position*, which is only the
pre-deploy commit when the merge actually moved something — after a no-op merge it points at some
unrelated earlier checkout and shows you a diff from nowhere in particular.

If **anything but `version` alone** changed, reinstall. Dependencies are the obvious case, but not
the only one: `9ca82ac` rewrote `[tool.setuptools]` `package-dir`, `packages` and `package-data`
to map `params/` into the distribution as `seagarden_dst.paramdata`, with no dependency change at
all. An install predating it resolves `seagarden_dst.paramdata` not at all — harmless today only
because `DEFAULT_PARAM_ROOT` falls back to the checkout, and not harmless for the next packaging,
`[project.scripts]` or `requires-python` change. Then:

```bash
/opt/micromamba/envs/shiny/bin/python3 -m pip install -e ".[app]"
```

**Know where that writes.** The env's own `site-packages` is owned `shiny:micromamba` and is not
writable by `razinka`, so pip falls back to a `--user` install into
`~/.local/lib/python3.13/site-packages` — a directory that comes *before* the env's on `sys.path`
and already shadows it for at least `shiny`. The risk is therefore the opposite of "noise on a
shared environment": a reinstall that resolves a newer `shiny` or `pandas` changes the runtime for
every other Shiny app `razinka` runs on that env, silently and for all of them. Check what pip
says it did before moving on.

Restart. **This needs your sudo password** (§2), so run it in a terminal:

```bash
sudo systemctl restart seagarden-dst
```

## 5. Verify

**All seven must pass** — four here, the restart assertion, the websocket, and the browser check.
The count is worth stating because the last three were each added after a deploy passed everything
before them. A deploy that serves 200 while running the previous version is the failure this
section exists to catch, and it is invisible from the outside.

```bash
systemctl is-active seagarden-dst                                    # active
curl -s -o /dev/null -w '%{http_code}\n' --retry 5 --retry-delay 1 \
     --retry-connrefused http://127.0.0.1:8140/                      # 200
curl -s -o /dev/null -w '%{http_code}\n' https://laguna.ku.lt/seagarden-dst/   # 200

git -C ~/seagarden-dst describe --tags --exact-match HEAD            # must print $TAG
```

The `--retry-connrefused` is not decoration. The unit is `Type=simple`, so `systemctl restart`
returns as soon as the process is *forked*, before uvicorn binds 8140 — the journal shows roughly
a second between `Started seagarden-dst.service` and `Uvicorn running on…`, and longer on a cold
import of scipy, pandas and shiny after a reboot. Without the retry you get `000`, silenced to
nothing by `-s -o /dev/null`, which is not one of the documented outcomes and looks identical to a
real failure.

**Check the tag with `git describe`, not with `__version__`.** `__version__` is a literal bumped
only at release, so it reads `0.2.0` on the tag *and* on every commit after it until the next
bump: on `main` today, six commits past `v0.2.0`, it prints `0.2.0` and the check passes. Paired
with a no-op merge (§4), a deploy that moved nothing verifies completely green.
`git describe --tags --exact-match` refuses unless HEAD *is* the tag, which is the invariant this
check was always meant to express.

**Neither of those proves the service restarted.** The install is editable, so any command you run
spawns a *new* process reading the checkout as it is now — it reports the new version the moment
the merge lands, while the running service still holds the old module in memory. Assert the
restart against **when the checkout moved**, not against the commit's own date:

```bash
svc=$(date -d "$(systemctl show -p ActiveEnterTimestamp --value seagarden-dst)" +%s)
head=$(stat -c %Y ~/seagarden-dst/.git/HEAD)
[ "$svc" -ge "$head" ] && echo "restart OK" || echo "STALE: service predates the deploy"
```

The commit's author date is the wrong anchor and reads as a pass when it should not: a release
commit authored upstream last week, on a service last restarted the day before yesterday, gives a
service timestamp *later* than the commit date while the restart never happened. What matters is
whether the service started after this checkout moved, and `.git/HEAD`'s mtime is when that was.

`.git/HEAD` moves on **any** checkout, not only a deploy — switching to a branch to read something
trips it. That is the safe direction: the serving tree did move, the process was not restarted,
and the honest answer is that you no longer know what is running. Restart, or switch back, and
re-check.

Together these are the deployment-level twin of `tests/test_version.py`, which guards the version
literals against each other in CI. `git describe` guards the *checkout* against the tag it claims
to be, and the timestamp pair guards the *running process* against the checkout. `app/shell.py` reads the same value into the About box, so a user can confirm
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
PREV=<previous-tag>
git reset --hard "$PREV"
test "$(git rev-parse HEAD)" = "$(git rev-parse "$PREV^{commit}")" || echo "DID NOT MOVE — STOP"
sudo systemctl restart seagarden-dst
```

**`reset --hard`, unconditionally.** An earlier version of this section read
`git merge --ff-only <previous-tag> || git reset --hard <previous-tag>`, and the fallback could
never run: rolling back always means moving to an *ancestor*, and `--ff-only` to an ancestor
prints `Already up to date.` and exits **0**. The `||` therefore never fired, the checkout never
moved, the restart brought the broken version straight back up, and §5 passed because
`__version__` had not changed. It was a no-op that reported success, in the one procedure where
that matters most.

Then re-run §5 in full against the previous tag. `git reset --hard` is safe **only** because
§3 established the tree had nothing uncommitted in it — if you skipped the preflight, you do
not know that.

Before `v0.2.0` there were no tags. To roll back to something older than the first tag, use the
commit the reflog names: `git reflog --date=iso` in the checkout shows each deploy as a `merge`,
`pull` or `checkout` entry. The `--date=iso` is required — plain `git reflog` prints the sha, the
index and the action and **no date at all**, which is useless for picking the last good deploy.

## 7. What is not covered

- **The portal card** (`/var/www/html/services.json`) is edited in place and version-controlled
  nowhere. A deploy does not touch it. It needs editing only when the app's name, description or
  URL changes — see `~/seagarden/deploy/README.md`.
- **No deploy script.** The sequence above has been run by hand once (v0.2.0). Automating it is
  worth doing after it has been followed a second time by somebody else, which is also the test
  of whether this document works.
- **`scripts/verify-deploy.sh`** in the `seagarden` repo checks the Hugo site, not this app. It
  has no DST coverage; §5 is the DST's verification.
- **One link is still missing, in the other repository.** This runbook is now linked from this
  repo's `README.md`. It should also be linked from `~/seagarden/deploy/README.md`
  §"SeaGarden DST on the laguna portal" — the document §1 sends you to, and where anybody
  investigating the live host starts. Without that pointer, the non-author this runbook is
  written for reads the hosting README, finds a table of every component, and never learns this
  file exists.
