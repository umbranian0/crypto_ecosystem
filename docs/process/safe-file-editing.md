# Safe file editing on this machine (OneDrive-sync workaround)

This repo's working copy sits inside a OneDrive-synced folder. OneDrive occasionally locks a file mid-sync, which makes the normal `Write`/`Edit` tools (and plain `mkdir`/file writes via Bash) fail with `ENOENT: no such file or directory, open '...tmp.<pid>.<hash>'` even though the target path is completely valid. This is a filesystem-sync quirk, not a permissions or sandbox restriction — PowerShell's file APIs are unaffected by it, which is why the workaround below always uses PowerShell as the actual write mechanism.

**Do not** repeatedly retry the same failing `Write`/`Edit` call, and do not try to "fix" it with `git reset`/`git checkout --`/`git clean` — the file is fine, the write mechanism is the problem, not repo state.

## The workaround

1. Write (or edit) the file content to the session scratchpad directory instead — a path outside the OneDrive-synced tree, e.g. `C:\Users\...\AppData\Local\Temp\claude\...\scratchpad\<name>`. `Write`/`Edit` work normally there.
2. Copy the scratchpad file into its real destination in the repo using PowerShell's `[System.IO.File]` APIs directly, with **explicit UTF-8, no-BOM encoding on both the read and the write**:

   ```powershell
   $src = "C:\...\scratchpad\<name>"
   $dst = "c:\Users\...\crypto_ecosystem\<real\path>"
   $content = [System.IO.File]::ReadAllText($src)
   [System.IO.File]::WriteAllText($dst, $content, [System.Text.UTF8Encoding]::new($false))
   ```

## The failure mode this prevents — read this before using any other method

**Never** use PowerShell `Get-Content -Raw` (without `-Encoding UTF8`) to read a file back, and never use `Set-Content`/`Add-Content` (without `-Encoding utf8`) to write one. PowerShell 5.1's default encoding for these cmdlets is the system codepage (e.g. Windows-1252), not UTF-8. Round-tripping a UTF-8 file (which this repo's Markdown/Python/HTML files all are — they use real em-dashes `—`, en-dashes `–`, and arrows `→`) through the wrong codepage silently corrupts every multi-byte character into mojibake (`â€"` and similar) across the **entire file**, not just the lines you meant to touch, and can also inject a stray BOM at the top.

This is not a hypothetical — it recurred **four separate times** during Sprint 21 (2026-09-02), each time from a dev agent using an encoding-unsafe PowerShell round-trip to make what was intended as a small, targeted addition. Every instance was caught before landing by diffing the actual file (`git diff --stat` should show a small, targeted change — if it shows the whole file as modified, stop and investigate before reporting done) and reversing the corruption from `git show HEAD:<path>` (never `git checkout`/`git reset` — reconstruct the clean content by hand from the last-known-good `git show` output, then re-apply only the intended change with the safe method above).

## Self-check before reporting a file edit done

1. `git diff --stat <path>` — the insertion/deletion count should roughly match the size of the change you actually intended. A whole-file rewrite where you meant to add two lines is a red flag, not a success.
2. If the file contains em-dashes, en-dashes, or arrows, grep for the corruption signature directly: `grep -c "â€"` (or similar mojibake patterns) should return `0`.
3. Only use `[System.IO.File]::ReadAllText`/`WriteAllText` with explicit `UTF8Encoding` for anything in this workaround — never `Get-Content`/`Set-Content`/`Add-Content` without an explicit `-Encoding utf8` (and even then, prefer the `[System.IO.File]` APIs — they're the only method verified clean across every ticket this sprint once adopted).
