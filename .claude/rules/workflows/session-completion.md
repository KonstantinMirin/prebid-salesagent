# Session Completion Checklist

## Before Saying "Done" or "Complete"

Run through this checklist in order:

### Step 1: Check Incomplete Work
```bash
bd ready          # what is workable now
bd show <id>      # detail on anything you touched
```
Review any tasks still in progress. Either complete them or file follow-up issues.

**Do NOT use `bd list` in this repo.** See the warning in
[beads-workflow.md](beads-workflow.md#never-use-bd-list-here) — on a tracker this
size it can balloon the bd process to tens of GB. `bd ready` / `bd show` answer
the same questions safely.

### Step 2: File Issues for Remaining Work
For anything discovered but not completed:
```bash
bd create --title="..." --type=task --priority=2
```
Include enough context for the next session to pick up the work.

### Step 3: Run Quality Gates
```bash
make quality
```
All checks must pass. If they fail, fix the issues before committing.

### Step 4: Close Completed Tasks
```bash
bd close <id1> <id2> ...
```
Close all beads tasks that were fully completed this session.

### Step 5: Commit
```bash
git add <specific-files>
git commit -m "feat/fix/refactor: description"
```

There is no beads step here. Do NOT run `bd sync` in any form — the subcommand
does not exist in bd 1.1.2 and errors; JSONL export is automatic, and the tracker
replicates on its own (see [beads-workflow.md](beads-workflow.md)).

**Important**: This is an ephemeral branch. No `git push`. Code is merged to main locally.

### Step 6: Verify Clean State
```bash
git status
bd ready
```
Confirm:
- Working tree is clean (or only has expected untracked files)
- All completed tasks are closed
- Any remaining open tasks have clear descriptions

## Ephemeral Branch Workflow

This project uses ephemeral branches:
- Work happens on feature branches
- Branches are merged to main **locally** (not pushed)
- Nothing needs to be done for beads at commit time — one shared tracker, automatic
  export, automatic replication
- No upstream tracking — don't run `git push`
