# StreamSieve v1.6.0

StreamSieve generates and reconciles Movies/Series STRM and NFO libraries from Dispatcharr. Jellyfin consumes the folders as normal libraries; no Jellyfin Xtream plugin is needed for generation. Live TV is unaffected.

## Install or update

Add this repository manifest in Dispatcharr's Plugin Hub:

```text
https://raw.githubusercontent.com/NicholasBoulanger/StreamSieve/main/manifest.json
```

Alternatively import the `StreamSieve-v1.6.0.zip` release asset. The archive includes a top-level `streamsieve` folder containing `plugin.py`, `plugin.json`, `reconciliation.py`, and `sync.py`. Do not install only `plugin.py`.

**Upgrade change:** generation now requires explicit library initialization. Existing files are unmanaged until adopted. Existing NFOs are preserved; they are not overwritten during adoption.

## First run and migration

1. Mount a persistent parent directory, for example a host media folder at `/VODS`. Pre-create `/VODS/Series` and `/VODS/Movies`. Dispatcharr needs write access to the roots and their parent. Configure Jellyfin to scan the individual media roots, not `/VODS` itself.
2. Set the Dispatcharr URL to an HTTP(S) address reachable from Jellyfin. Set the series whitelist to Dispatcharr Series database IDs, e.g. `12,34`. Blank means process no series. Movie generation includes all eligible movies.
3. Back up existing library files and Jellyfin data. Stop the previous generator's writes and cleanup before adopting its files.
4. Run **Initialize** for the desired media type. This writes an ownership index in the sibling `Series.streamsieve-state` or `Movies.streamsieve-state` directory and a `.streamsieve-root` marker inside the media root. Keep both on persistent storage and include both in backups.
5. For an existing library, run **Preview adoption**, inspect the returned paths/logs, then **Adopt matching legacy STRMs**. Matching requires a unique existing Dispatcharr proxy UUID and the configured URL authority/base path. Arbitrary legacy filenames are retained. Ambiguous mappings are errors. Raw provider URLs, changed UUIDs, different proxy hosts, and layouts without show/season hierarchy require manual migration; they are not guessed from titles. Adoption covers the selected catalog without a batch limit, does not refresh providers, and does not generate missing files.
6. Run **Preview**, then **Synchronize**. Preview reads the existing catalog without provider refresh. A subsequent synchronization refreshes selected series, so newly discovered episodes may differ from preview. Start with a small batch. Repeated runs rotate through all selected items; `all` handles the whole selection.
7. Scan Jellyfin and verify identity, artwork, watched/resume state, playback, seeking, and new episodes. Preserved paths reduce churn but cannot guarantee preserved Jellyfin item IDs. Disable/uninstall the old plugin only after verifying the migration. Upgrade Jellyfin separately.

Initialization requires real, non-symlink root paths. Missing/mismatched markers, corrupt state, overlapping media roots, and another active writer stop the action. Restore missing state from backup rather than deleting the marker and reinitializing.

## Synchronization behavior

- Missing files are created; changed **owned** STRMs/NFOs are atomically replaced. Unchanged media retains its modification time.
- Persisted path assignments survive title/year and stream URL changes. New filenames are byte-bounded, sanitized, and disambiguated when assigned names collide.
- Existing unmanaged files are preserved. Externally edited owned files are reported as conflicts, including during cleanup. Resolve a conflict by restoring the indexed version from your backup or intentionally retaining your edits; this release has no force-overwrite switch.
- NFO generation is independent of STRM creation. Missing owned NFOs are repaired. Disabling NFO generation preserves existing metadata. Series and episode NFOs include available external IDs.
- Inactive accounts are excluded. Optional **Account priority** lists Dispatcharr account IDs in preference order. Current sources are retained within an equal priority tier; relation ID breaks remaining ties. One stream is chosen per episode. Where present, the provider-series relation is respected.
- Source preference does not implement playback-time failover or prove stream health. Different editions/languages should be selected deliberately at the catalog/provider level.
- Failures and conflicts return error status. Action results include change counts and up to 100 change details; logs contain individual operations. Changes already completed before a later error remain valid and are reconciled on the next run.

There is **no automatic orphan deletion in v1.6.0**. Missing whitelist IDs, disabled accounts, removed episodes, and deselected series preserve existing files. Dispatcharr's episode refresh does not expose a reliable completeness/success contract for safe automated pruning. A returned refresh call is not treated as evidence that missing media should disappear.

## Retirement and recovery

**Preview retirement** counts only indexed, unmodified files. **Retire owned files** copies those files to the sibling state directory's `recovery/` tree, verifies the source, and removes individual files from the scanned library. Series retirement is restricted to the current whitelist; movie retirement covers all owned movies. Unmanaged artwork, subtitles, NFOs, and media survive; only empty directories are removed.

**Restore retired files** restores verified recovery copies when the destination is absent, preserving conflicts. Recovery copies are retained until you remove them manually. A normal sync can also recreate selected retired content, so stop scheduling or deselect a series before retiring it permanently. Retirement is an explicit cleanup operation, not an orphan detector.

Writes use a recovery journal and an exclusive POSIX file lock. Restarting an action reconciles an interrupted write before proceeding. Atomicity is per file, not per whole library. Use one Dispatcharr writer and storage supporting POSIX locks and atomic replacement; validate these semantics on your actual network filesystem. Do not run an external generator against the same files.

## Automatic runs

The included `sync.py` uses the same engine and locks as manual actions. Run it inside Dispatcharr's Python environment with its normal database/environment configuration. It does not start background threads when Dispatcharr imports the plugin.

Create a persistent JSON settings file, for example:

```json
{
  "series_root_folder": "/VODS/Series",
  "root_folder": "/VODS/Movies",
  "dispatcharr_url": "http://dispatcharr:9191",
  "series_whitelist": "12,34",
  "series_batch_size": "10",
  "batch_size": "100",
  "generate_series_nfo": true,
  "generate_nfo": true,
  "account_priority": ""
}
```

From Dispatcharr's application environment, with the application directory on `PYTHONPATH`:

```sh
python /path/to/streamsieve/sync.py --settings /path/to/settings.json --kind series --preview
python /path/to/streamsieve/sync.py --settings /path/to/settings.json --kind series
python /path/to/streamsieve/sync.py --settings /path/to/settings.json --kind both --interval 3600
```

Replace paths for your deployment. The settings file is separate from the plugin UI settings; keep it in sync. Use `--django-settings` if the deployment uses a different Django settings module. The first command previews; the second runs once and returns nonzero on error; the third repeats after each run finishes. Use a process supervisor to restart periodic runs, or call the one-shot command from your existing scheduler. Initialization/adoption remain manual. No Jellyfin API scan is triggered; use normal library scanning.

## Development and release

```sh
python3 -m unittest discover -s tests -v
python3 build_release.py
```

Tests cover filesystem recovery and mocked Dispatcharr model interactions. Live playback, mounted filesystem semantics, installed Dispatcharr compatibility, and actual Xtream Library migration must be verified in the deployment. The broader roadmap is in `RECONCILIATION_PLAN.md`; v1.6.0 delivers the safe create/update foundation, migration helpers, explicit retirement/recovery, and an external scheduling runner. Completeness-aware automatic pruning, native refresh events, health probing, and Jellyfin scan integration remain future work.
