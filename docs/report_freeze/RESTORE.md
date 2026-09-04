# Restore and disaster recovery

Read this before you need it.

## The one thing that is genuinely unrecoverable

**`.report_freeze_salt` and `.id_map_*.csv`.** Every identifier in the shared files is
`FLW_xxxxxxxx`, a salted hash. Those two files are the only link back to a real Connect id, they
have no upstream, and they are gitignored on purpose because this repo is a public fork.

**If the machine holding them dies, every shared file becomes permanently un-linkable to a real
worker.** No re-pull fixes that. Run `build_dr_bundle.py` and copy the result to access-controlled
storage.

## Two halves, and what each is for

| | what it is | good for | not good for |
| --- | --- | --- | --- |
| `docs/report_freeze/` | re-keyed derived data, in git | defending a number in review, sharing outside Dimagi | rebuilding the pipeline |
| the DR bundle | the irreplaceable sources, with real ids, **never** in git | rebuilding, re-linking, comparing across dates | sharing with anyone |

The freeze folder alone cannot restore the pipeline. It is derived; you cannot regenerate the
sources from it.

## What can and cannot be re-pulled

**Re-pullable, so not bundled:**

- `hq_pull_full/` — 105 MB of append-only CommCare forms. `pull_hq_full_payloads.py` is resumable.
- `ocs_transcript_dump/` — 186 MB, re-derivable, and it holds FLW answers so it should not be
  copied around casually.

**Not re-pullable, so bundled:**

- `_ocs_state_cache.json` — session state including `interview_status`. OCS has no as-of query, so
  a historical status is gone the moment it changes.
- `_ocs_tags_cache.json` — review verdicts. These arrive weeks after completion and get revised.
  Today's verdict state is unrecoverable tomorrow.
- `_ocs_words_cache.json` — per-session word counts, derived from message content we do not keep.
- `connect_user_data_snapshot.csv` — point-in-time enrolment. Connect exposes current state only,
  so yesterday's funnel cannot be re-pulled.
- `_interview_schedule.json` — the CCHQ lookup, which changes when a cohort is reconfigured.
- `master_4src.csv` — the built master **with real ids**. The bridge back to the pipeline.
- `dashboard_data.json`, `_run_history.json` — the built payload and the regression-guard history.

## Taking a bundle

```bash
python build_dr_bundle.py                 # ../connect-labs-dr-backup/<date>/
python build_dr_bundle.py D:/backups      # or somewhere you choose
```

About 16 MB. Written outside the repo so it cannot be committed by accident. Copy it to
access-controlled storage; do not leave it as the only copy on one laptop.

**Cadence: on every change that moves a number.** A bundle cannot reconstruct a state older than
the oldest bundle, which is the whole argument against taking one and stopping.

## Verifying a backup

```bash
python verify_freeze.py                   # docs/report_freeze
python verify_freeze.py path/to/restored  # a restored copy
```

Eighteen checks in five groups: checksums against the manifest, no identifiers leaked back in, the
data still aggregates to the published figures, the derived figures still re-derive, and the
re-keying is still reversible. Exit code 0 means usable.

**A backup nobody has verified is a hope, not a backup.** Both layers are proven independently:
corrupting one byte fails the checksum check, and destroying seven completions *while updating the
manifest to match* still fails the aggregate check. Neither rides on the other.

## Restoring

1. `git clone` the repo and check out the commit named in `DR_MANIFEST.txt`
2. copy every loose file from the bundle into the repo root
3. copy `.id_map_*.csv` into `docs/report_freeze/`
4. `python verify_freeze.py` — expect **18 passed, 0 failed**
5. `python preflight.py` — expect all checks green

Verified end to end: a restore from a bundle into a clean directory passes 18/18.

**If step 4 fails on checksums**, the bundle is damaged. Use an older one.

**If it fails on the aggregate checks**, that is worse. The data is damaged in a way checksums
cannot see, the figures no longer reproduce, and nothing published from that set can be defended.

## Comparing across dates

Each bundle is a dated directory, so two bundles diff directly. To see which report figures moved
between two cuts:

```bash
python build_report_freeze.py <old-bundle>/report_freeze/payload_vNNN.json vNNN
# then diff the Figures sheets of the two workbooks
```

That yields a list of exactly which figures moved and why, rather than discovering it in review.

## Known limits, stated plainly

- **The Connect funnel reproduces 36 of 44 cells.** CI reassembles the snapshot at runtime from the
  `CONNECT_SNAP_1/2/3` secrets; the local snapshot a bundle captures is a separate artefact. Those
  secrets cannot be read locally, so the exact snapshot CI used cannot be pinned. See the data
  dictionary.
- **A bundle cannot recover what upstream has deleted.**
- **Reproducing the dashboard as an interface** additionally needs
  `docs/interviews_render_template.js`, which is in git at the commit the manifest names.
