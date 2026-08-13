# SESSION SUNDOWN — the end-of-session commit/push/backup protocol

> **Reusable procedure.** First executed 2026-08-04 (the logout sweep). A campaign's memory
> is only as durable as its last sundown: the ledger, the reports, the harnesses, and the
> `/tmp` artifacts must be in at least TWO durable places before the session ends.
> **Rule of thumb:** if a report cites a file that lives in `/tmp`, archive it at sundown —
> a reboot is a silent data loss.
> **Placeholders:** replace `<WORKSPACE>`, `<ARCHIVE_MOUNT>`, `<GITEA_HOST>`, `<USER>`,
> `<GITEA_TOKEN>` with your environment. The real values live in the originating project,
> never here.

---

## 0. When to run

At session end (user says "log off" / "pause" / "cy tomorrow"), or before any compaction that
may drop the working context. ~10 minutes. Run the steps in order; each is idempotent.

---

## 1. Commit the workspace sweep

```bash
cd <WORKSPACE>
git add -A
# ⚠️ GITLINK GUARD (learned the hard way, 2026-08-04): `git add -A` records embedded git
#    repos (the fork + worktrees) as gitlinks. Check and undo:
git ls-files -s | grep -c '^160000'   # if > 0:
git rm --cached -q <fork> <worktrees>  # list the embedded repos here (already in .gitignore)
git commit -q -m "chore: sundown sweep — <session summary through ledger entry #N>"
```

Note: tracked `__pycache__/*.pyc` files ride along (they are tracked state; harmless).

---

## 2. Push the repo manifest (all repos, all branches)

| Repo | Location | Push targets |
|------|----------|--------------|
| workspace (project repo) | `<WORKSPACE>` | gitea `<USER>/<repo>` |
| fork | `<WORKSPACE>/<fork>/` | github (public) **and** gitea (any active branches) |
| sibling | `<WORKSPACE>/<sibling>` | gitea |
| reflection machine | `<WORKSPACE>/<reflection>` | gitea |
| dispatcher engine (+ campaign) | `<WORKSPACE>/<dispatcher>*` | gitea |
| skunkworks-toolbox | `<WORKSPACE>/<toolbox>` | gitea |
| harness repo | **gitea-only** (no local clone) | branches: `<branch-a>`, `<branch-b>` |

```bash
# per repo with a local clone:
git -C <repo> status --short && git -C <repo> push        # commit anything pending first
# fork branch sweep (unpushed vs gitea):
git log --oneline gitea/<branch>..<branch> | wc -l        # push any non-zero
# gitea-only repo: verify via gitea API (no local clone):
curl -s "http://<GITEA_HOST>/api/v1/repos/<USER>/<harness-repo>/branches" -H 'Authorization: token <GITEA_TOKEN>'
```

---

## 3. Archive `/tmp` — two tiers (BOTH before logout)

`/tmp` is volatile. Anything a report cites must survive in two places.

**Tier 1 — git archive (load-bearing subset, pushed):**

```bash
cd <WORKSPACE>
mkdir -p .scratch/archives/tmp-$(date +%F)
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude 'venv' --exclude 'logs' \
  /tmp/<harness-or-corpus-dirs>/ .scratch/archives/tmp-$(date +%F)/<name>/
git add .scratch/archives/ && git commit -q -m "chore(archive): /tmp artifacts <date>" && git push gitea master
```

**Tier 2 — HDD full dump (everything, incl. venvs + big files):**

```bash
DEST=<ARCHIVE_MOUNT>/campaign-tmp-archive-$(date +%F)
mkdir -p "$DEST"
rsync -a /tmp/<all-campaign-dirs-and-files> "$DEST/"        # full fidelity, no exclusions
```

**IOPS rule (HDD):** pack every project folder into a single archive — thousands of tiny files
make HDD copies crawl. After the rsync:

```bash
cd "$DEST"
for d in <project-dirs>; do tar -czf "$d.tar.gz" "$d"; done
for a in *.tar.gz; do tar -tzf "$a" | wc -l >/dev/null && echo "OK $a"; done   # verify, 0 bad
```

Keep both the unpacked dirs (browsing) and the archives (transfer).

---

## 4. Flush the HDD to platter

A spinning disk caches writes in RAM — `cp`/`rsync` "done" does NOT mean on-platter:

```bash
sync && sync -f <ARCHIVE_MOUNT>/campaign-tmp-archive-$(date +%F)
```

---

## 5. Update the File & Folder Map (AGENTS.md)

The map lives in `AGENTS.md` → `## File & Folder Map`. Update the `/tmp` archive row: size,
new content, and the archive-date. Push. A fresh or resumed session reads this in its first
file — the map is the single source of "where is everything."

---

## 6. Resume checklist (next session, after a reboot)

```bash
# If /tmp was cleared, re-materialize what's needed FROM THE ARCHIVES (never from memory):
ls <ARCHIVE_MOUNT>/campaign-tmp-archive-<date>/          # the full dump
tar -xzf .../<name>.tar.gz -C /tmp/                      # e.g. a sealed corpus + harness
# Verify the git archive is in sync: git log --oneline -1 (<WORKSPACE>) shows the sundown commit.
```

---

## Lessons encoded (why each step exists)

1. **`git add -A` records embedded repos as gitlinks** — the fork + worktrees silently became
   gitlinks in the 2026-08-04 sweep (fixed: `rm --cached` + `.gitignore`). Check `git ls-files -s | grep 160000` every sweep.
2. **HDD writes are cached** — `sync` is mandatory after any HDD copy, or a power loss eats the backup.
3. **Small files kill HDD IOPS** — the VA venv (98M, thousands of files) took minutes; its
   archive (30M) takes seconds. Archive before any transfer.
4. **Reports cite `/tmp` paths** (e.g. `/tmp/<report>.md` in a design doc) — those citations
   are only safe if the file is archived at sundown.
5. **A gitea-only repo has no local clone** — its state is gitea-only; verify branches via
   the API, not `git status`.
