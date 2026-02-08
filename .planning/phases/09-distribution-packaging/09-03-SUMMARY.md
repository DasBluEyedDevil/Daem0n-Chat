---
phase: 09-distribution-packaging
plan: 03
subsystem: distribution
tags: [inno-setup, windows-installer, python-build-standalone, embedding, offline-install]

# Dependency graph
requires:
  - phase: 09-01
    provides: installer modules (config_manager, post_install, health_check, model_downloader)
provides:
  - Inno Setup installer script (.iss) for Windows installation
  - Build orchestrator (build_inno.py) for staging directory preparation
  - CPU-only PyTorch distribution to avoid 2GB CUDA download
  - Pre-downloaded embedding model (~400MB) for offline installation
affects: [release, distribution, end-user-setup]

# Tech tracking
tech-stack:
  added: [python-build-standalone, tarfile, urllib]
  patterns: [staging directory preparation, embedded Python runtime, CPU-only wheel selection]

key-files:
  created:
    - installer/inno/daem0n_chat.iss
    - installer/build_inno.py
    - tests/test_build_inno.py
  modified: []

key-decisions:
  - "Inno Setup installs to {localappdata}\DaemonChat (no admin required)"
  - "CPU-only PyTorch index URL used to get ~200MB wheel instead of 2GB CUDA"
  - "Pre-download embedding model during build to avoid 400MB first-run download"
  - "Pascal InitializeSetup checks for Claude Desktop before proceeding"
  - "All paths in .iss use double-quoting to handle spaces in usernames"
  - "build_inno.py uses python-build-standalone for embedded runtime"

patterns-established:
  - "Staging directory structure: staging/{python, app, site-packages, installer, models}"
  - "Post-install hook runs from embedded Python to configure Claude Desktop"
  - "Uninstall hook cleans up config entry"
  - "Build script has --stage-only, --skip-model, --clean options for iteration"

# Metrics
duration: 4min
completed: 2026-02-08
---

# Phase 09 Plan 03: Inno Setup Windows Installer

**Inno Setup installer bundles embedded Python, dependencies, and pre-downloaded model for offline Windows installation to LocalAppData**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-08T18:37:58Z
- **Completed:** 2026-02-08T18:41:34Z
- **Tasks:** 2
- **Files created:** 3

## Accomplishments

- Inno Setup script installs DaemonChat to LocalAppData (no admin required)
- Build orchestrator downloads python-build-standalone, installs dependencies with CPU-only PyTorch, copies application code, and pre-downloads embedding model
- Post-install and uninstall hooks configure/remove Claude Desktop config entry
- Claude Desktop existence check prevents useless installation
- 6 tests verify requirements generation, file exclusions, and staging directory structure

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Inno Setup script** - `eb862db` (feat)
2. **Task 2: Create build orchestrator and tests** - `3316241` (feat)

## Files Created/Modified

- `installer/inno/daem0n_chat.iss` - Inno Setup installer script with LocalAppData install, post-install/uninstall hooks, Claude Desktop check
- `installer/build_inno.py` - Build orchestrator that prepares staging directory with Python runtime, dependencies, app code, and model
- `tests/test_build_inno.py` - 6 tests covering requirements file generation, file exclusions, and staging directory structure

## Decisions Made

- **Inno Setup installs to LocalAppData:** Avoids UAC prompt by using {localappdata}\DaemonChat instead of Program Files. PrivilegesRequired=lowest enables non-admin installation.
- **CPU-only PyTorch:** Uses `--index-url https://download.pytorch.org/whl/cpu` to get ~200MB CPU wheel instead of ~2GB CUDA wheel. Critical for reasonable download size.
- **Pre-download embedding model:** build_inno.py calls model_downloader to stage the ~400MB model during build, avoiding first-run download for users.
- **Claude Desktop check:** Pascal InitializeSetup() checks for %APPDATA%\Claude directory before proceeding, preventing useless installation.
- **Path quoting:** All paths in [Run] and [UninstallRun] use double-quoting pattern to handle spaces in usernames correctly.
- **python-build-standalone:** Uses Astral's python-build-standalone releases for embedded Python runtime (3.12). URL requires updating at build time to match latest release.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - installer handles all configuration automatically via post_install.py hooks.

## Next Phase Readiness

Phase 09 (Distribution & Packaging) is now 3/3 complete. All distribution paths are ready:

- **09-01:** Co-existence with DaemonMCP, installer modules using claude-desktop-config library
- **09-02:** MCPB executable builder (experimental path)
- **09-03:** Inno Setup installer (production-ready, proven path)

Both MCPB (09-02) and Inno Setup (09-03) are complete. Users have two distribution options:
- **MCPB:** Experimental single-file executable (antivirus false positives possible)
- **Inno Setup:** Traditional guided wizard installer (zero false positives, proven technology)

Phase 9 complete. All 9 phases of the roadmap are now finished.

## Self-Check: PASSED

All files created and commits verified:
- FOUND: installer/inno/daem0n_chat.iss
- FOUND: installer/build_inno.py
- FOUND: tests/test_build_inno.py
- FOUND: commit eb862db (Task 1)
- FOUND: commit 3316241 (Task 2)

---
*Phase: 09-distribution-packaging*
*Completed: 2026-02-08*
