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

Run `git status` to understand what has changed, and `git fetch origin main`: local `main`
only moves when someone pulls it, so every comparison below is against `origin/main`.

---

## Step 1 — Python interpreter

As CLAUDE.md says: the `rame-env` conda environment on Windows, `.venv/bin/python` on Linux.
```powershell
$python = "$env:USERPROFILE\anaconda3\envs\rame-env\python.exe"
```

---

## Step 2 — Lint

CI runs `ruff format --check .` on the whole repo, so a stray file fails it. Format what
this branch touched — committed, uncommitted and new, deleted files left out — then check
everything:
```powershell
& $python -m ruff check . --fix
$changed = @(git diff --name-only --diff-filter=d $(git merge-base origin/main HEAD) -- '*.py') + @(git ls-files -o --exclude-standard -- '*.py') | Sort-Object -Unique
if ($changed) { & $python -m ruff format $changed }
& $python -m ruff format --check .
```

- If errors remain after `--fix`, **stop and report** — do not commit.
- If ruff reformatted or fixed files, re-stage them before committing.

---

## Step 2b — Local checks

CI is the second look, not the first. Run what it runs before pushing. The suite takes
a quarter of an hour in one process, so spread it over the cores with `pytest-xdist`
(installed in `rame-env`):
```powershell
& $python -m mypy mento/
& $python -m pytest tests/ -n auto
```

- If the branch touches nothing under `mento/`, `tests/` or `pyproject.toml` (tooling or
  prose only), skip mypy and pytest: they cannot fail on it. Say so in the PR body.

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
- Each **confirmed** finding → fix it, rerun Step 2 and the Step 2b checks it touches, and launch
  `revisor` again with its previous findings and what was fixed, until it confirms nothing
  new. (Its run ends when it reports, so there is no agent left to message.)
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
- Stage the modified and new files of the change by name (never `git add .` or
  `git add -A`), so CI tests the same tree Step 2b ran.
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
git push -u origin <branch>
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

Wait for the checks of the PR (`gh pr checks <number> --json name,state,bucket,link`)
until all five checks below are listed and none has `bucket = pending`. Right after
`gh pr create` it reports "no checks reported" (exit 1): that means not started yet, keep
waiting. The repo marks no check as required, so judge them all
(`tests 3.12 / windows-latest`, `tests 3.13 / windows-latest`, `lint and type check`,
`docs build`, `codecov/patch`):

- **`codecov/patch`** → non-blocking, treat as warning only.
- Any other check with `bucket = fail` (or `cancel`) → print its name and `link`, **stop**,
  ask the user whether to fix and retry.
- The four non-codecov checks all `bucket = pass` → go to Step 7.

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
- If the tree is still clean after Step 2c (work already committed, and neither ruff nor
  a review fix changed anything), skip only Step 3: the checks and the
  review still run on the branch against `origin/main`, and Step 4 pushes whatever
  `origin` does not have yet.
