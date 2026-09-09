# StreamSieve reconciliation and migration plan

Reviewed 2026-09-09 against local revision `a8ed449` (v1.5.2).
This document records the reviewed roadmap. The v1.6.0 implementation status and operational limits are documented in README.md; later roadmap phases are not implied to be complete.

## Objective and boundary

Keep the proposed architecture: Dispatcharr owns the catalog, StreamSieve materializes selected media, and Jellyfin consumes normal Movies/TV libraries. Series migration comes first; movies subsequently use the same reconciliation engine. Live TV stays outside this work.

Define “complete replacement” as replacement of the VOD ingestion behavior actually used in this installation. Do not imply parity with every Xtream Library feature. No Jellyfin version number is a dependency or acceptance criterion. Verify playback and metadata on the installed and intended target versions.

The central safety rule is: reconcile owned files against a validated catalog snapshot for an explicitly selected scope. An absent, unavailable, unselected, or unprocessed item is not automatically a deleted item.

## Findings in the current implementation

| Finding | Evidence | Required response |
| --- | --- | --- |
| Cleanup does not establish file ownership. Movie cleanup recognizes extensions and deletes entire folders; series cleanup deletes whole folders matched by whitelist-derived names. | `plugin.py`, `_cleanup_movies`, `_cleanup_series` | Replace both recursive cleanup paths with indexed, individual-file operations. A matching title or `.strm` extension is insufficient proof of ownership. |
| STRMs remain stale, while show metadata is rewritten on every run. | `_generate_movies`, `_process_single_series` | Compare content before atomically replacing every managed output, including NFOs. |
| Movie NFO repair is skipped when its STRM exists. | Early `continue` in `_generate_movies` | Plan STRM and NFO changes independently. |
| Batching does not ensure eventual coverage. Movies inspect only the first `3 × batch` relations; series always select the first whitelisted batch. | `_generate_movies`, `_select_series_relations` | Use deterministic pagination and persistent progress for a complete cycle. Never interpret a batch as the whole catalog. |
| Series relation selection does not solve duplicate episode selection. The episode query filters by account and series, without a relation-ID tie-break for equal episode numbers. | `_process_single_series` | Select one eligible source per logical episode; distinguish language/edition constraints from interchangeable backups. |
| Names are recomputed from mutable title/year/episode title, and sanitization can collapse distinct names to the same path. | Naming helpers and generation loops | Persist identity-to-path assignments and detect collisions before writing. |
| Series/episode NFOs lack external identity fields. | `_generate_tvshow_nfo`, `_generate_episode_nfo` | Preserve adopted metadata; add validated identifiers where available and supported. Never invent IDs. |
| Tests encode legacy behavior. One explicitly preserves arbitrary existing STRM contents; cleanup tests do not put unrelated files inside a selected folder. | `tests/test_plugin.py` | Retain coverage of unmanaged-file preservation, but separately test updates to owned files and mixed-content folders. |

Baseline: all six existing unit tests pass. They use mocked Dispatcharr models and do not establish runtime compatibility or safe reconciliation.

Upstream integration hazard: the inspected [Dispatcharr task source](https://raw.githubusercontent.com/Dispatcharr/Dispatcharr/main/apps/vod/tasks.py), `refresh_series_episodes`, catches/logs exceptions and provides no explicit success result. Empty episode data also returns without processing in the batch helper. A normal return or refresh timestamp alone is not authoritative evidence for deletion. This observation concerns upstream main, not a verified installed version.

## Design decisions

### 1. Separate reading, planning, and applying

Extract a small Dispatcharr adapter, source selector, deterministic renderer, and filesystem reconciler behind the existing plugin entry point. Reuse suitable existing naming and metadata helpers. Keep the first implementation synchronous and straightforward; do not create a general orchestration framework.

The adapter returns a bounded snapshot with item identities, candidates, selected scope, and completeness/error information. Keep network refresh outside long database transactions. Detect catalog refresh overlap or invalidate destructive plans when the input generation changes. If the installed Dispatcharr version cannot establish completeness, allow additions/updates but report pruning as blocked.

The planner produces create/update/unchanged/conflict/retire operations with reasons and expected old hashes. Dry-run performs no filesystem changes and does not refresh the provider catalog; an explicit refresh is a separate operation. Applying a saved plan revalidates its configuration, inputs, and file preconditions.

### 2. Use a persistent ownership index

Start with a versioned JSON index and recoverable operation journal under a dedicated state directory on persistent storage outside Jellyfin's scanned library. Use a single writer; revisit SQLite only if measured scale warrants it.

Record a library-instance identifier, root identity marker, catalog identity, assigned relative path, output kind, last written content hash, selected relation, and retirement state. Keep sync status/progress separately so no-op runs do not rewrite media or the ownership index unnecessarily.

Ownership is per file. An index entry does not authorize overwriting a file whose bytes have since changed externally: report a conflict and preserve it. Never infer ownership from folder names, file extensions, or a URL host alone. Missing/corrupt state requires recovery or explicit adoption, not automatic reconstruction with deletion rights.

Require a validated root marker before automated writes. A missing mount must not become a newly created local library. Reject overlapping Movies/Series roots, unsafe relative paths, and symlinked output components; verify containment and preconditions at mutation time. Never recursively remove library directories. Remove only recorded, empty directories with `rmdir`.

### 3. Preserve identity and paths

Key normal operation by Dispatcharr media identity scoped to the library/catalog instance, not provider stream ID or display name. Store provider references and external metadata IDs as supporting identity evidence. Do not assume database IDs or UUIDs survive a Dispatcharr rebuild; rebuilds require an explicit remapping/adoption preview.

Once assigned or adopted, keep a media path when titles, years, stream IDs, or preferred sources change. Update metadata and URL contents in place. Naming changes are a separate migration operation. For genuinely new paths, handle case-insensitive and Unicode-equivalent collisions, reserved names, and filesystem byte limits; use a stable identity suffix only where required. Reject ambiguous episode numbering rather than silently merging unrelated items into episode zero; support valid season-zero specials.

### 4. Make source selection deterministic and conservative

Keep Dispatcharr proxy URLs. Verify URL routing, authentication, and the meaning of `stream_id` against the installed version before changing URL construction. Do not presume a pinned URL provides automatic playback failover.

Initially rank eligible candidates using configured account preference, retain the current candidate within the same priority tier, and use relation ID as the final tie-breaker. Disabled or incompatible candidates are ineligible. Unknown health is not known failure. Select episode candidates within the intended provider-series relation when the installed schema supports it; do not pool unrelated editions just because they share account and series IDs.

Loss of every eligible candidate marks existing output unavailable and preserves it pending the removal policy. Defer active probing, cross-provider episode filling, and playback-time failover until actual Dispatcharr capabilities and equivalence rules are verified. Avoid probes that consume provider playback slots.

### 5. Establish removal policy before adding deletion

Default pruning to off for the first release and migration. Later offer retirement to a recoverable quarantine outside scanned roots, followed by explicit or retention-based permanent deletion of owned, unmodified files.

Automatic retirement requires complete observations for the affected scope, no applicable refresh/query/write failures, and absence in at least two distinct successful catalog refresh generations separated by a configurable grace period. Repeating a sync against the same database snapshot is not a second observation. Add configurable absolute and percentage removal limits; exceeding either holds retirement and reports the proposed changes.

Blank whitelist retains its current meaning: process no series. Removing an ID from the whitelist stops management updates but preserves existing output by default. Provide an explicit “retire deselected media” operation. Missing whitelisted IDs, disabled accounts, and source failures are reported separately from confirmed catalog removal. Batch exclusions cannot produce orphans. Disabling NFO generation stops NFO writes and preserves existing NFOs.

### 6. Be precise about crash safety

Use temporary files in each destination directory, flush/fsync as supported, and atomic replacement. Atomic replacement protects individual files, not a whole show or library transaction.

Persist operation intent before mutation, serialize filesystem/index commits, and recover interrupted operations using expected old/new hashes. Apply all planned additions/updates for a scope before retirement; a failed scope performs no retirement. On restart, finish or reconcile journaled work without claiming unrelated files. Quarantine moves on another filesystem require a verified copy before source removal.

Use a lock shared by manual actions and scheduled runs. Start with one active process per library and reject unsupported concurrent writers. Choose lock storage and semantics for the actual mounted filesystem; test them there. Return partial/failure status when work fails, not an unconditional success message with an error counter.

### 7. Automate only after manual reconciliation is reliable

First deliver manual Preview and Sync actions using the same engine. Then verify the installed Dispatcharr plugin/task lifecycle and choose its supported scheduler, or a documented external scheduled invocation if necessary. Avoid import-time background threads, duplicate schedulers across workers, and undocumented event assumptions.

Persist deterministic cycle progress so every selected item is eventually visited. Schedule catalog refresh less frequently than inexpensive filesystem reconciliation where appropriate; bound provider concurrency, retry with backoff, and coalesce overlapping triggers. Report last successful complete cycle, coverage, errors, conflicts, and changes held from retirement.

Optional Jellyfin scanning comes last, after a successful cycle with media changes. A scan failure must not roll back library files. Scanning should be disabled during migration application and coalesced afterward.

## Migration procedure

1. Inventory the installed Dispatcharr/Jellyfin/Xtream Library versions, actual generated paths and NFOs, mount layout, selection rules, and desired variants. These are not present in the reviewed workspace. Collect representative specials, duplicate titles, Unicode names, and multi-provider shows. Do not assume a particular Xtream Library repository or naming algorithm.
2. Back up generated files and Jellyfin configuration/database using the deployment's supported procedure. Capture representative Jellyfin item identities, metadata IDs, watched status, and resume positions for comparison.
3. Produce a read-only adoption report mapping existing relative paths to Dispatcharr identities. Match with strong corroborating evidence from NFO IDs, episode numbering, and URLs; title alone cannot authorize adoption. Leave ambiguous/unmatched files untouched.
4. Exercise generation and recovery in a separate staging root that Jellyfin does not scan. Do not add duplicate staged media to the production Jellyfin library.
5. Stop the old generator's writes and cleanup. Explicitly adopt verified existing STRM paths; preserve richer existing NFOs by default and leave artwork/subtitles unmanaged. Apply an update-only production sync at the existing mounted paths with pruning disabled, then scan once.
6. Verify unchanged paths, identity, watched/resume state, artwork, episode numbering, playback start, seek, and resume. Same paths reduce churn but do not guarantee Jellyfin database identity preservation. Check the media server's ability to reach proxy URLs.
7. Disable/uninstall Xtream Library after verification. Keep the prior configuration and file backup for rollback. Enable scheduling after repeat no-op syncs; enable retirement separately after completeness evidence is verified. Upgrade Jellyfin as a separate change.

## Delivery order and acceptance gates

1. **Safety foundation:** replace unsafe cleanup behavior; introduce ownership, path validation, locking, and dry-run. Gate: mixed-content folders and unowned files survive every action.
2. **Series create/update reconciliation:** stable paths, source selection, NFO policy, atomic writes, journal recovery, and complete batching. Gate: URL changes update in place; unchanged runs preserve media hashes and mtimes; every selected series receives coverage.
3. **Adoption and migration:** fixtures from actual legacy output, adoption report, update-only pilot, documented rollback. Gate: representative existing series retain paths and verified Jellyfin behavior. This is the first useful migration release; it need not wait for automatic deletion.
4. **Retirement:** completeness contract, grace period, removal limits, quarantine, restore, and empty-directory cleanup. Gate: partial refreshes, empty responses, failed batches, missing mounts, and configuration changes cannot accidentally retire the library.
5. **Scheduling:** supported invocation, restart recovery, overlap handling, progress/status. Gate: scheduled cycles converge without starving later items or exceeding provider limits.
6. **Movies:** reuse the engine, deduplicate logical movies, preserve intentional editions, and adopt existing paths. Gate: the same ownership, convergence, migration, and recovery checks pass.

Tests must cover collisions, external modifications, duplicate episode relations, missing/invalid state, root changes, symlinks, disk-full/permission errors, interruption between file and index commits, recovery during retirement, whitelist changes, and concurrent manual/scheduled calls. Add integration tests against the supported Dispatcharr schema and manual playback/migration checks in the real deployment. Keep the original six tests as a baseline, adapting assertions only where the intended behavior changes.

Production-specific discovery is a prerequisite for adoption and destructive synchronization, not for implementing the safe create/update foundation. The original review made no production changes. See README.md for the subsequent v1.6.0 implementation.
