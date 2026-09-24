# Annual refresh of the gridded forcing artifact

**Audience: somebody who is not the author.** This is the counterpart of
`docs/runbooks/deploy.md`: that runbook ships a new version of the app, this one rebuilds
the data the app reads. Both exist because a step only one person can reproduce does not
survive the SeaGarden Application Form's commitment to keep this tool online, on KU MRI
servers, to May 2034, with no maintenance budget. This runbook says what a failure looks
like, not only what to type.

---

## 1. What this does and when

Rebuilds `forcing.nc` and `manifest.json` for a year range, pulling the four Copernicus
Marine layers (`copernicus_phy`, `copernicus_bgc`, `copernicus_bgc_light`, `copernicus_wav`)
and the EMODnet bathymetry layer (`emodnet_bathy`), reducing all five onto the artifact
grid, and writing the pair together.

Run this **once a year**, or sooner if `.github/workflows/source-probe.yml` reports that a
source's catalogue metadata has drifted (a dataset id retired, a version bumped).

## 2. Prerequisites

- The `shiny` micromamba env on laguna, `/opt/micromamba/envs/shiny`, installed with the
  `spatial` extra (`pip install -e ".[spatial]"`). Without it, `copernicusmarine` and
  `rasterio` (used by the EMODnet fetch (`urllib` + `rasterio`)) are not importable and
  the refresh CLI exits before doing anything.
- The Copernicus Marine credential is **institutional, never personal** — it belongs to
  the project, not to whoever happens to run the refresh. It lives in
  `~/.copernicusmarine/.copernicusmarine-credentials` on laguna. Do not point a refresh at
  a personal Copernicus account: the credential must outlive whoever is currently running
  this.
- **No EMODnet credential is needed.** The WCS endpoint EMODnet bathymetry is fetched from
  is public.
- Free disk: the CLI refuses to start when the workdir has less than **2 GB** free (the
  wave stream peaks around ~1 GB, plus the ~530 MB EMODnet tile cache) or the target has
  less than **200 MB**, and sums the two when both sit on one filesystem (§8). Check by
  hand anyway before an unattended run, so the refusal never surprises you:

  ```bash
  df -h ~/seagarden-data
  ```
- Wall-clock: **hours**, not minutes. Do not run this and walk away assuming it finished;
  see §5 for how to check on it without watching it.

## 3. Where things go

- **Target:** `~/seagarden-data/forcing`. **Never** a path inside `~/seagarden-dst` — that
  checkout is the serving tree, and `docs/runbooks/deploy.md` §3's preflight fails a deploy
  against a dirty tree. Writing artifact output there is how a refresh silently blocks the
  next deploy.
- **Workdir:** `~/seagarden-data/work`. This is where EMODnet's tile cache survives between
  runs (§4) and where the wave stream's working files land.
- **How the service finds it:** the running app does not read `~/seagarden-dst/data/forcing`
  directly. It reads through the `SEAGARDEN_DATA_DIR` locator, wired into the service's
  environment (§10) as `SEAGARDEN_DATA_DIR=/home/razinka/seagarden-data/forcing` — the
  directory that holds `forcing.nc` and `manifest.json` together, the same directory
  `--target` writes to in §5. The committed manifest — a copy, not the artifact — lives
  at `data/forcing/manifest.json` inside the checkout (§9); the ~170 MB artifact itself
  never enters git.

## 4. Volumes and runtime

**~30.5 GB crosses the wire.** Broken down: ~0.59 GB of monthly fields, ~3.6 GB of daily
`zsd`, ~25.8 GB of hourly waves (waves dominate the runtime and the transfer), and ~0.5 GB
of EMODnet bathymetry tiles — the bathymetry cost is paid only once, because the tile cache
in `workdir` survives and a subsequent refresh over the same tiles reads from disk instead
of the network.

**On disk:** the artifact itself is **~170 MB**. Alongside it, the EMODnet tile cache adds
**~530 MB** to the scratch space in `workdir` — this is not part of the artifact and is not
committed anywhere.

Runtime is **hours**, driven by the hourly wave stream. A run that has been going for twenty
minutes is not stuck; a run that has been going for a day probably is — check the log (§5).
(The first real run on laguna, 2026-09-24, pulled one month of hourly waves in about five
seconds, so on that link the whole wave window may take minutes rather than hours; the figure
above is kept until a complete run has been timed.)

**Memory is the binding constraint on the serving host, not time.** Run 2 of the first real
refresh (2026-09-24) was OOM-killed at 30.7 GB resident on the 32 GB host that also serves
the app: the wave layer had rechunked the whole 25.9 GB hourly window into one array before
the quantile, and dask's default threaded scheduler would run one chunk per core (28 on
laguna). Since v0.11.2 the wave layer reduces month by month in latitude bands and the driver
pins dask to four worker threads (`driver.REFRESH_WORKERS`), so the refresh holds a few GB
however many cores the host has. Do not raise that bound to make a run faster on the serving
host; a refresh that kills the app is slower than any refresh.

## 5. The commands

```bash
cd ~/seagarden-dst
P=/opt/micromamba/envs/shiny/bin/python3
$P scripts/refresh_layers.py --probe                       # every layer must report ok
mkdir -p ~/seagarden-data/forcing ~/seagarden-data/work
nohup $P scripts/refresh_layers.py --start-year 2016 --end-year 2025 \
   --target ~/seagarden-data/forcing --workdir ~/seagarden-data/work \
   > ~/seagarden-data/refresh-$(date +%F).log 2>&1 &
```

C§1 fixes the baseline at the decade **2016–2025**; only the wave layer takes its own
2023–2025 sub-window internally, so `--start-year`/`--end-year` here must span the whole
decade, not the wave layer's narrower internal window.

`--probe` first is not optional: it is a catalogue-only check (no bulk transfer) that
catches a retired or renamed dataset before you commit hours and 30 GB to a run that dies
partway through. If `--probe` reports a layer as unreachable, stop — do not proceed to the
full refresh, and see §8.

## 6. What success looks like

- The log ends by printing the artifact and manifest paths, not a traceback.
- `manifest.json`'s `artifact_sha256` matches `sha256sum ~/seagarden-data/forcing/forcing.nc`.
- Every layer in the manifest reports `archive.status: pending` — this is correct and
  expected for a first refresh (§9), not a bug.
- The artifact loads:

  ```bash
  SEAGARDEN_DATA_DIR=$HOME/seagarden-data/forcing $P -c "from seagarden_dst.gridded import GriddedForcing, artifact_directory; f = GriddedForcing.from_directory(artifact_directory()); print('loaded', artifact_directory())"
  ```

  A traceback here, especially an `artifact_schema_version` or checksum complaint, means
  something is wrong with the pair (§8) — do not deposit it.

- The provenance test passes against the freshly built pair:

  ```bash
  cd ~/seagarden-dst
  SEAGARDEN_DATA_DIR=$HOME/seagarden-data/forcing $P -m pytest tests/test_refresh_fixture.py -q -p no:cacheprovider
  ```

- The artifact's `year` coordinate carries ten values, the whole 2016–2025 decade:

  ```bash
  SEAGARDEN_DATA_DIR=$HOME/seagarden-data/forcing $P -c "import xarray as xr; print(len(xr.open_dataset('$HOME/seagarden-data/forcing/forcing.nc')['year']))"
  ```

## 7. The convention, confirmed on the first run (2026-09-24)

**What this section predicted happened, one step earlier than predicted.** The first real
refresh (v0.11.0, 2026-09-24) did not reach `check_grid`: it died four minutes in, at
`merge_layers`, with `xr.merge(join="exact")` refusing to align `latitude`. Opening the
products from the server showed why. For the Baltic extent every Copernicus product
returns the GridSpec's shape (390 × 630) and steps, but labels each cell by its **centre**:
latitude 53.50829 and longitude 9.51375 for the cell `GridSpec.lats()`/`lons()` label
53.5 / 9.5 (the **lower edges**), i.e. exactly half a step up. And the products are not
bit-identical to each other — the wave grid starts at 53.50827 where physics starts at
53.50829, and their longitude steps differ by a millionth of a degree — so the four
Copernicus layers would not exact-join even among themselves, while `emodnet_bathy` is
built on the edges and could never join any of them.

**The fix is the shared step this section asked for**, and it lives where it said:
`cmems.snap_to_grid`, called by `open_window` for every Copernicus layer (v0.11.1). It
checks the window has the GridSpec's size on both axes and that every coordinate sits
within a quarter step of either the edges or the centres, then relabels with the
GridSpec's own coordinates. That is a relabel of the same cells, not a shift of data: the
centre at 53.50829 is the middle of the cell whose southern edge is 53.5. Anything else — a
wrong size, a whole-step offset — raises `GridMismatch` naming the axis, so a product that
genuinely moves its grid stops the refresh rather than being quietly relabelled. The
bathymetry layer is untouched, as this section required.

If a future run fails in `snap_to_grid`, read the message: it prints the first source
coordinate against the first GridSpec edge, which is enough to tell a half-step convention
from a real change of grid. Do **not** loosen `_SNAP_TOLERANCE_STEPS` to clear it.

Separately, the bathymetry values themselves are referenced to **LAT** (lowest astronomical
tide), assumed to hold for the whole 2022 EMODnet release. Depth is `-elevation`; nobody
downstream should have to discover the sign or the datum by reading a bare number.

## 8. Failure modes

| Condition | What it looks like | What to do |
|---|---|---|
| Any layer fails | The refresh exits non-zero; no partial artifact is written. The whole refresh fails together — a missing variable is never silently defaulted. | Read the log for which layer and why (often a `--probe`-catchable cause). Fix the cause, re-run the whole refresh. |
| Refresh interrupted before step 5 | Process killed, log stops mid-layer. | Nothing live was touched; the previous artifact/manifest pair is still valid. Just re-run. |
| Interrupted between 5 and 6 | The next time the app reads the artifact, it refuses with a sha mismatch and falls back to `PlaceholderForcing` with a banner. | Re-run the refresh; this repairs it. Do not hand-edit the manifest. |
| `artifact_sha256` mismatch | The app refuses to load the artifact and says why, rather than serving numbers from a file that does not match its own manifest. | Re-run the refresh cleanly. Never patch the manifest's checksum to make it match. |
| Unrecognised `artifact_schema_version` | The app refuses and falls back, same banner as above. | Usually means an old artifact against a newer app, or vice versa. Re-run the refresh with the current code. |
| Insufficient free disk | The CLI refuses **before** starting and exits 1 with one line on stderr beginning `refresh refused: insufficient free disk`, naming the directory, what it needs and what it has (C§6.1). Nothing is downloaded and nothing is created. The check runs against the filesystem the directories will land on, so it works before `mkdir`. If the disk fills *during* the run instead (another process wrote to it), the log ends in `OSError: No space left on device` partway through the 30.5 GB transfer. | Free the space the message names (§2's figures) and re-run. The EMODnet tile cache resumes from where it stopped; the Copernicus streams restart from zero. |
| Layer built but not yet deposited | Every layer's manifest entry reads `archive.status: pending` with a `source_url`. This is not an error — it is the state of every layer immediately after a build, before §9's deposit step. | Proceed to §9. If it is still `pending` long after a deposit, the DOI was never recorded back — do that. |
| A layer marked `forbidden` that is in fact redistributable | Not automatically detectable — the validator cannot tell a correctly `forbidden` layer from a mis-marked one. This is exactly why `pending` exists as a distinct state: mis-marking a layer `forbidden` is the path of least resistance to clear a check that would otherwise block you. | Check the layer's actual licence by hand before marking it anything other than `pending`. |
| OOM-killed | The log stops with no traceback; `dmesg` (or `journalctl -k`) shows `Out of memory: Killed process <pid> (python3)`; a stale `tmp*` directory may be left under the target, which the next run ignores. Seen on run 2, 2026-09-24, at 30.7 GB. | Confirm the checkout is at v0.11.2 or later (the bounded wave reduction and `REFRESH_WORKERS`). If it recurs, read the `anon-rss` figure in the kernel line and `LATITUDE_BAND_ROWS` in `wav.py`; halve the band before touching the worker count. Never run the refresh on the serving host with the bound removed. |
| `TileFetchFailed` (EMODnet) | `emodnet_bathy` dies partway through the WCS tile loop. | Re-run the refresh: the tile cache in `workdir` resumes from where it left off rather than re-fetching completed tiles. If the failure recurs on the same tile, the cached file for it may be poisoned — delete `~/seagarden-data/work/emodnet/<lat0>_<lon0>.tif` (e.g. `~/seagarden-data/work/emodnet/55.0_20.0.tif`) and re-run. |

## 9. Deposit and record the DOI

The **deposited manifest and the committed manifest differ**, and that is intentional, not
a bug to reconcile away. The sequence:

1. Build (every layer's `archive.status` reads `pending`, as in §8).
2. Deposit the artifact and the manifest to **Zenodo**.
3. Record the DOI Zenodo returns back into the **committed** manifest, flipping those
   layers' `archive.status` from `pending` to `deposited`.

The committed manifest — the one in this repo — is authoritative for provenance; the
manifest actually deposited to Zenodo is a snapshot taken **before** the DOI existed, so it
necessarily still says `pending` and always will. `artifact_sha256` does not change between
the two: it covers the artifact, which the DOI-recording step does not touch.

Finally, copy the committed manifest into the repo **without the artifact**:

```bash
cp ~/seagarden-data/forcing/manifest.json ~/seagarden-dst/data/forcing/manifest.json
cd ~/seagarden-dst
git add data/forcing/manifest.json
git commit -m "data: forcing manifest for the <year range> refresh, deposited to Zenodo (DOI ...)"
```

The ~170 MB artifact itself is never committed.

## 10. Wire the service

If this is the first time `SEAGARDEN_DATA_DIR` has been set, or the target directory moved,
add to `seagarden-dst.service` in the `seagarden` repo's `deploy/`:

```
Environment=SEAGARDEN_DATA_DIR=/home/razinka/seagarden-data/forcing
```

Restart per `docs/runbooks/deploy.md` §4 and verify per its §5. Then confirm in the browser
that the app's Site panel banner reads "gridded forcing artifact" rather than the
placeholder-conditions banner — that is the visible sign the app is reading the artifact
you just built rather than falling back.

## 11. Who to contact

The app's top bar carries a **Feedback** action; its modal renders the `CONTACT_EMAIL`
constant defined in `app/shell.py`. That is the address a user without shell access sees,
and it should always resolve to whoever can run this runbook. Both the About and Feedback
modals also carry a link to the project's GitHub issues, for anyone who prefers to file a
report there instead.
