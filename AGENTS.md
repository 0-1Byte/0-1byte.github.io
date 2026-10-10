# Repository Agent Guidelines

## Project environment

- This repository is a Hugo site. The project-root Hugo executable is `hugo.exe`.
- Important paths: `content/` and `data/` contain site content; `layouts/` contains Hugo templates; `assets/` and `static/` contain site resources; `themes/PaperMod/` is a Git submodule; `public/` is generated output.
- On Windows, run project commands from the repository root in the VS Code PowerShell 7 terminal. Check tools with:

  ```powershell
  Get-Location
  git rev-parse --show-toplevel
  git --version
  python --version
  node --version
  python -c "import PIL; print(PIL.__version__)"
  .\hugo.exe version
  ```
- The Pages workflow pins Python 3.11 and Pillow 10.4.0 because GitHub's current Ubuntu runner does not provide Python 3.7. Local Python 3.7/Pillow installations may still be used to check backward compatibility, but CI availability must be verified against the workflow's pinned versions.

## Before editing

- Confirm the current directory is this repository root and inspect `git status --short --branch`, `git branch -vv`, staged and unstaged diffs, untracked files, and relevant submodule status.
- Review existing implementation and project documentation before changing code. Keep each task narrowly scoped and do not mix unrelated visual redesign, performance work, and feature refactors.
- Protect user-maintained content (especially `data/quotes.yaml`), submodule changes, and generated files. Do not overwrite or discard changes whose ownership is unclear.
- Before branch integration or other risky worktree changes, back up staged/unstaged diffs and untracked files outside the repository and verify the backup.
- `.gitignore` does not untrack existing files. Inspect `git ls-files` and deployment dependencies before changing tracked generated output.

## Validation

- Identify the test or build that verifies each requested behavior, then actually run the applicable checks. Do not report unexecuted checks as passing; source edits without their applicable tests do not complete a task.
- For homepage backgrounds, run:

  ```powershell
  python tools/test_optimize_home_backgrounds.py
  python tools/optimize_home_backgrounds.py
  python tools/optimize_home_backgrounds.py
  ```

  Inspect the generator's summary and verify the second run reports cache reuse. The optimizer writes WebP variants under `static/home/backgrounds-optimized/` and cache metadata under `.cache/homepage-backgrounds/` (outside Hugo's published `static/` tree). Inspect those paths before running it.
- Check JavaScript and quote behavior with:

  ```powershell
  node --check tools/verify_quotes.js
  node tools/verify_quotes.js <path-to-built-index.html>
  ```

- Build production output outside the repository to avoid overwriting tracked `public/` files:

  ```powershell
  $build = Join-Path $env:TEMP "my-blog-hugo-build"
  .\hugo.exe --minify --cleanDestinationDir --destination $build
  node tools/verify_quotes.js (Join-Path $build "index.html")
  ```

  Check the generated HTML, responsive image URLs, fallback behavior, and that referenced build resources exist.
- If a command fails to launch (for example, `ENOENT`), report the actual executable and error. Check the available VS Code terminal/shell once; do not claim the whole system lacks a shell or repeatedly retry an unavailable executable without new evidence.
- Report failures with their cause, fix, and rerun result. Distinguish source changes, tests, production build, commit, push, and deployment as separate outcomes.

## GitHub Pages and delivery

- Inspect `.github/workflows/` before changing publish behavior. Confirm the order of dependency installation, asset generation, tests, Hugo build, artifact upload, and deployment.
- After changing Pages inputs, validate the built artifact and inspect the final Actions run. A valid workflow file or local build alone does not prove deployment succeeded.
- Before committing or pushing, review exact staged paths and diffs, preserve unrelated user changes, confirm branch and remote divergence, and run relevant validation. Never use destructive resets, `git clean`, force-push, or broad removal to simplify the worktree.
- Do not commit unrelated user content, submodule modifications, or generated output without explicit scope and review.
- Final reports must list modified files, actual commands and results, remaining issues, and commit/Actions/deployment links when those steps occurred. Never invent command results or describe a plan as completed work.
