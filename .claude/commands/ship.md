# /ship — Check, review, commit, push, open PR, wait for CI, hand off for review

Automates the full ship workflow for the current git branch:
lint → local checks → review → commit → push → PR → CI check → ready for review.

**It never merges.** A green PR is left open for someone else to review and merge, even
when every check passes. Merge only when the user asks for it in so many words.

---

## Step 0 — Preflight

On Windows, refresh PATH so `gh` is available:
```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
```

Confirm we are NOT on `main` — abort if so and tell the user to switch to a feature branch
(main only takes version bumps).

Run `git status` to understand what has changed.

---

## Step 1 — Python interpreter

As CLAUDE.md says: the `rame-env` conda environment on Windows, `.venv/bin/python` on Linux.
```powershell
$python = "$env:USERPROFILE\anaconda3\envs\rame-env\python.exe"
```

---

## Step 2 — Lint

CI runs `ruff format --check .` on the whole repo, so a stray file fails it. Format what
this branch touched, then check everything:
```powershell
& $python -m ruff check . --fix
$changed = git diff --name-only main... -- '*.py'
if ($changed) { & $python -m ruff format $changed }
& $python -m ruff format --check .
```

- If errors remain after `--fix`, **stop and report** — do not commit.
- If ruff reformatted or fixed files, re-stage them before committing.

---

## Step 2b — Local checks

CI is the second look, not the first. Run what it runs before pushing:
```powershell
& $python -m mypy mento/
& $python -m pytest tests/
```

- If the branch touches `docs/source/` or a public docstring and `pandoc` is on PATH, also
  run `& $python -m sphinx -b html -W --keep-going docs/source docs/build/html`; without
  pandoc, say in the report that the docs build was left to CI.
- Any failure → **stop and report** — do not push.

---

## Step 2c — Review (mandatory)

Opus builds, Fable checks. Before committing, hand the change to the `revisor` agent
(`.claude/agents/revisor.md`, `model: fable`) with the Agent tool,
`subagent_type: "revisor"`. Give it the branch name and one or two lines on what the
change is meant to do — not your own verdict on it.

- **Never skip this step**, not even for a small change or when the user asks to go fast.
  If the agent cannot run, **stop and report** — do not commit.
- Each **confirmed** finding → fix it, rerun the Step 2b checks it touches, and send the
  fix back to the same agent (SendMessage) until it confirms nothing new.
- Each **plausible** finding → check it yourself; fix it, or say in the report why it does
  not hold.
- If a finding is a design question rather than a bug, **stop and ask** the user.
- List what the review found and what was done with each in the PR body (Step 5).

---

## Step 3 — Commit

- If the user supplied text after `/ship`, use it as the commit message verbatim, minus any
  `@login` (that is a reviewer, Step 7).
- Otherwise inspect `git diff --staged` and `git diff` to write a concise message focused
  on *why* (not just what).
- A user-visible change gets its line under `Unreleased` in `CHANGELOG.md`; tooling and
  tests do not.
- Stage modified tracked files by name (never `git add .` or `git add -A`).
- Commit with a PowerShell here-string. End the message with the `Co-Authored-By`
  attribution line the session provides — do not hardcode a model name:
  ```powershell
  git commit -m @'
  <message>

  <attribution line from the session>
  '@
  ```
- If a pre-commit hook reformats files and the commit fails, re-stage the reformatted
  files and commit again — at most once.

---

## Step 4 — Push

```powershell
git push origin <branch>
```

Print the remote URL on success.

---

## Step 5 — PR

Check if a PR already exists for this branch:
```powershell
gh pr list --head <branch> --json number,url,title
```

- If a PR exists → print its URL and use its number for the CI check.
- If no PR exists → create one:
  ```powershell
  gh pr create --title "<title>" --body "<body>" --base main
  ```
  Use the branch name and commit log to write the title and body, including the review
  from Step 2c. Print the new PR URL.

---

## Step 6 — Wait for CI

Wait for the checks of the PR (`gh pr checks <number> --json name,state,conclusion`)
until all are complete. Then evaluate:

- **`codecov/patch`** → non-blocking, treat as warning only.
- Any check with `conclusion = FAILURE` → print the failed check names and their
  `detailsUrl`, **stop**, ask the user whether to fix and retry.
- All required checks `SUCCESS` → go to Step 7.

---

## Step 7 — Hand off for review

Do **not** merge. For each `@login` in the text after `/ship`, request a review:
```powershell
gh pr edit <number> --add-reviewer <login>
```

Print the PR URL and one line saying it is green and waiting for review.

---

## Notes

- The snippets above are PowerShell; run them with the PowerShell tool and the `&` call
  operator. On Linux, use the Bash equivalents with `.venv/bin/python`.
- If `gh` auth fails, instruct the user to run `gh auth login` in a new terminal and retry.
- If there are no staged or unstaged changes, skip Steps 2–4 and go straight to Step 5
  (the branch may already be pushed with an open PR).
