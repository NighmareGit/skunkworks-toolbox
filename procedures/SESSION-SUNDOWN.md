# SESSION SUNDOWN — the end-of-session commit/push/backup protocol

> **Reusable procedure.** First executed 2026-08-04 (the logout sweep). The campaign's memory
> is only as durable as its last sundown: the LEDGER, the reports, the harnesses, and the
> `/tmp` artifacts must be in at least TWO durable places before the session ends.
> **Rule of thumb:** if a report cites a file that lives in `/tmp`, archive it at sundown —
> a reboot is a silent data loss.

---

## 0. When to run

At session end (user says "log off" / "pause" / "cy tomorrow"), or before any compaction that
may drop the working context. ~10 minutes. Run the steps in order; each is idempotent.

---

## 1. Commit the workspace sweep

```bash
cd /home/hunter/scratch/prototype-auto
git add -A
# ⚠️ GITLINK GUARD (learned the hard way, 2026-08-04): `git add -A` records embedded git
#    repos (the fork + worktrees) as gitlinks. Check and undo:
git ls-files -s | grep -c '^160000'   # if > 0:
git rm --cached -q atomic-llama-cpp-turboquant worktrees/ bug-002a-worktree gdn-graph-reuse-worktree t4-pipeline-optimization
# (worktrees/ + the embedded repos are already in .gitignore — re-add only if missing)
git commit -q -m "chore: sundown sweep — <session summary through LEDGER #N>"
```

Note: tracked `__pycache__/*.pyc` files ride along (they are tracked state; harmless).

---

## 2. Push the repo manifest (all repos, all branches)

| Repo | Location | Push targets |
|------|----------|--------------|
| prototype-auto (workspace) | `/home/hunter/scratch/prototype-auto` | gitea `hunter/prototype-auto` |
| fork | `atomic-llama-cpp-turboquant/` | github `NighmareGit` **and** gitea (good-prototype + any active branches: `proto/*`, `fix/*`) |
| south-star-sibling | `/home/hunter/scratch/south-star-sibling` | gitea |
| south-star-reflection | `/home/hunter/scratch/south-star-reflection` | gitea |
| dispatcher-engine (+ -campaign) | `/home/hunter/scratch/dispatcher-engine*` | gitea |
| skunkworks-toolbox | `/home/hunter/scratch/skunkworks-toolbox` | gitea |
| grok-build | **gitea-only** (no local clone) | branches: `main`, `harness-needs`, `remote-server-client` |

```bash
# per repo with a local clone:
git -C <repo> status --short && git -C <repo> push        # commit anything pending first
# fork branch sweep (unpushed vs gitea):
git log --oneline gitea/<branch>..<branch> | wc -l        # push any non-zero
# grok-build: verify via gitea API (no local clone):
curl -s "http://192.168.8.108:3005/api/v1/repos/hunter/grok-build/branches" -H 'Authorization: token <helm-write>'
```

---

## 3. Archive `/tmp` — two tiers (BOTH before logout)

`/tmp` is volatile. Anything a report cites must survive in two places.

**Tier 1 — git archive (load-bearing subset, pushed):**

```bash
cd /home/hunter/scratch/prototype-auto
mkdir -p .scratch/archives/tmp-$(date +%F)
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude 'venv' --exclude 'logs' \
  /tmp/<harness-or-corpus-dirs>/ .scratch/archives/tmp-$(date +%F)/<name>/
git add .scratch/archives/ && git commit -q -m "chore(archive): /tmp artifacts <date>" && git push gitea master
```

**Tier 2 — HDD full dump (everything, incl. venvs + big files):**

```bash
DEST=/mnt/toshiba_a/campaign-tmp-archive-$(date +%F)
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
sync && sync -f /mnt/toshiba_a/campaign-tmp-archive-$(date +%F)
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
ls /mnt/toshiba_a/campaign-tmp-archive-<date>/          # the full dump
tar -xzf .../atomizer-pilot.tar.gz -C /tmp/              # e.g. the sealed corpus + harness
# Verify the git archive is in sync: git log --oneline -1 (prototype-auto) shows the sundown commit.
```

---

## Lessons encoded (why each step exists)

1. **`git add -A` records embedded repos as gitlinks** — the fork + worktrees silently became
   gitlinks in the 2026-08-04 sweep (fixed: `rm --cached` + `.gitignore`). Check `git ls-files -s | grep 160000` every sweep.
2. **HDD writes are cached** — `sync` is mandatory after any HDD copy, or a power loss eats the backup.
3. **Small files kill HDD IOPS** — the VA venv (98M, thousands of files) took minutes; its
   archive (30M) takes seconds. Archive before any transfer.
4. **Reports cite `/tmp` paths** (e.g. `/tmp/redteam-atomizer-design-v2.md` in the atomizer
   design) — those citations are only safe if the file is archived at sundown.
5. **Grok-build has no local clone** — its state is gitea-only; verify branches via the API, not `git status`.
