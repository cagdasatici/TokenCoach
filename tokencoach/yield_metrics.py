"""What a session's spend produced: commits tied to sessions, and how many held.

A repository the person opts in to (`tokencoach --yield-install`) gets a git
hook that tags commits made inside Claude Code with `Claude-Session: <id>`
(see trailer.py). This module reads those repositories' history into the
ledger and joins commits to the sessions that made them by that id.

A commit counts as *accepted* once it is a week old and has not, in that week,
been reverted or dropped from every branch. Estimates are labelled as such:
"dropped" is noticed by TokenCoach's own scans, so a commit rewritten and
gone before the first scan is never seen.
"""

import bisect
import datetime
import json
import logging
import re
import subprocess
import time

from tokencoach import ledger, trailer

log = logging.getLogger("tokencoach")

WINDOW_DAYS = 120            # history read from each repository
GIT_TIMEOUT = 60             # seconds for any one git call
SETTLE_DAYS = 7              # a change is judged a week after it was made
WEEKS_SHOWN = 12
# A "fix" is recognised by its subject: the person's own commit subjects are all we have.
FIX_SUBJECT = re.compile(r"\b(fix(es|ed|ing)?|bugfix|hotfix|regression|revert(s|ed)?)\b", re.I)

_TRAILER = re.compile(rf"^{trailer.TRAILER_KEY}:[ \t]*(\S+)[ \t]*$", re.M)
_REVERTS = re.compile(r"This reverts commit ([0-9a-f]{40})")


# ── repositories the person opted in ─────────────────────────────────────────

def register_repo(conn, path: str, now: float | None = None) -> str:
    """Start tracking a repository, reached from any of its worktrees, and return
    the path it is tracked under. A repository already tracked is not added twice."""
    now = time.time() if now is None else now
    where = trailer.locate(path)
    row = conn.execute("SELECT path FROM yield_repos WHERE git_dir = ? OR path = ?",
                       (where["git_dir"], where["repo"])).fetchone()
    if row:
        conn.execute("UPDATE yield_repos SET git_dir = COALESCE(git_dir, ?) WHERE path = ?",
                     (where["git_dir"], row["path"]))
        conn.commit()
        return row["path"]
    conn.execute("INSERT INTO yield_repos (path, git_dir, since) VALUES (?, ?, ?)",
                 (where["repo"], where["git_dir"], now))
    conn.commit()
    return where["repo"]


def unregister_repo(conn, path: str) -> None:
    try:
        where = trailer.locate(path)
        conn.execute("DELETE FROM yield_repos WHERE path = ? OR git_dir = ?", (where["repo"], where["git_dir"]))
    except (trailer.TrailerError, OSError, subprocess.SubprocessError):
        conn.execute("DELETE FROM yield_repos WHERE path = ?", (path,))
    conn.commit()


def registered(conn) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM yield_repos ORDER BY path"):
        # a repository registered before start times were kept counts from its first scan
        since = r["since"] if r["since"] is not None else (r["scanned"] or 0.0)
        out.append({"path": r["path"], "worktrees": json.loads(r["worktrees"]),
                    "scanned": r["scanned"], "since": since})
    return out


# ── reading git ──────────────────────────────────────────────────────────────

def _run(repo: str, *args: str, stdin: str | None = None) -> str | None:
    """Output of a git command, or None when it failed (never raises)."""
    try:
        r = subprocess.run(["git", "-C", repo, "-c", "core.quotepath=off", *args], input=stdin,
                           capture_output=True, text=True, errors="replace", timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        log.debug("yield: git %s failed in %s", args[:1], repo, exc_info=True)
        return None
    return r.stdout if r.returncode == 0 else None


def _worktrees(repo: str) -> list[str]:
    out = _run(repo, "worktree", "list", "--porcelain")
    paths = [line[len("worktree "):] for line in (out or "").splitlines() if line.startswith("worktree ")]
    return paths or [repo]


def _refs(repo: str) -> list[str]:
    """What counts as 'kept': branches, remote branches, tags and the checked-out
    commit. Not stashes, and not the reflog."""
    refs = ["--branches", "--remotes", "--tags"]
    if _run(repo, "rev-parse", "--verify", "-q", "HEAD") is not None:
        refs.append("HEAD")
    return refs


def _read_log(repo: str, since: float) -> list[dict] | None:
    out = _run(repo, "log", *_refs(repo), "--no-merges", f"--since={int(since)}", "--name-only",
               "--format=%x1e%H%x1f%ct%x1f%s%x1f%B%x1f")
    if out is None:
        return None
    commits = []
    for record in out.split("\x1e")[1:]:
        parts = record.split("\x1f")
        if len(parts) < 5:
            continue
        sha, ts, subject, body, files = parts[0], parts[1], parts[2], parts[3], parts[4]
        sessions = _TRAILER.findall(body)
        commits.append({
            "sha": sha, "ts": float(ts), "subject": subject,
            "session_id": sessions[-1] if sessions else None,
            "files": [f for f in files.splitlines() if f.strip()],
            "reverts": _REVERTS.findall(body),
        })
    return commits


def _patch_ids(repo: str, revs: list[str], *, walk: bool) -> dict[str, list[str]]:
    """patch-id -> commit shas, for `revs` (or everything reachable from them)."""
    args = ["log", "-p", "--no-merges"] + ([] if walk else ["--no-walk=unsorted"]) + revs
    diff = _run(repo, *args)
    if not diff:
        return {}
    out = _run(repo, "patch-id", "--stable", stdin=diff) or ""
    ids: dict[str, list[str]] = {}
    for line in out.splitlines():
        pid, _, sha = line.partition(" ")
        if pid and sha:
            ids.setdefault(pid, []).append(sha)
    return ids


# ── scanning ─────────────────────────────────────────────────────────────────

def scan_repo(conn, path: str, now: float | None = None) -> dict:
    """Bring the commits table up to date for one repository."""
    now = time.time() if now is None else now
    where = trailer.locate(path)
    repo = where["repo"]
    since = now - WINDOW_DAYS * 86400
    commits = _read_log(repo, since)
    if commits is None:                      # git failed: leave what we know untouched
        return {"repo": repo, "new": 0, "ok": False}
    reachable = {c["sha"] for c in commits}
    known = {r["sha"]: r["gone_ts"] for r in conn.execute(
        "SELECT sha, gone_ts FROM commits WHERE repo = ? AND ts >= ?", (repo, since))}
    new = 0
    for c in commits:
        if c["sha"] not in known:
            new += 1
            conn.execute(
                "INSERT INTO commits (repo, sha, session_id, ts, subject, files, first_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (repo, c["sha"], c["session_id"], c["ts"], c["subject"], json.dumps(c["files"]), now))
        elif known[c["sha"]] is not None:    # it came back
            conn.execute("UPDATE commits SET gone_ts = NULL, superseded = 0 WHERE repo = ? AND sha = ?",
                         (repo, c["sha"]))
    for c in commits:
        for target in c["reverts"]:
            conn.execute("UPDATE commits SET reverted_ts = ? WHERE repo = ? AND sha = ? "
                         "AND (reverted_ts IS NULL OR reverted_ts > ?)", (c["ts"], repo, target, c["ts"]))
    if reachable:                            # an empty answer more likely means a broken repo
        _mark_gone(conn, repo, [s for s, g in known.items() if g is None and s not in reachable], now)
    conn.execute("UPDATE yield_repos SET worktrees = ?, scanned = ?, git_dir = COALESCE(git_dir, ?) "
                 "WHERE path = ?", (json.dumps(_worktrees(repo)), now, where["git_dir"], repo))
    conn.commit()
    return {"repo": repo, "new": new, "ok": True}


def _mark_gone(conn, repo: str, gone: list[str], now: float) -> None:
    """Record commits that left every branch. A commit whose patch still exists
    elsewhere was rebased, cherry-picked or only re-worded: replaced, not lost."""
    if not gone:
        return
    kept = _patch_ids(repo, _refs(repo), walk=True)
    lost = _patch_ids(repo, gone, walk=False)
    replaced = {sha for pid, shas in lost.items() if pid in kept for sha in shas}
    for sha in gone:
        conn.execute("UPDATE commits SET gone_ts = ?, superseded = ? WHERE repo = ? AND sha = ?",
                     (now, int(sha in replaced), repo, sha))


def scan_all(conn, now: float | None = None) -> list[dict]:
    """Scan every registered repository; one that can't be read is skipped."""
    results = []
    for r in registered(conn):
        try:
            results.append(scan_repo(conn, r["path"], now=now))
        except Exception:
            log.debug("yield: scan of %s failed", r["path"], exc_info=True)
    return results


def refresh(conn, now: float | None = None, min_interval: float = 600) -> bool:
    """scan_all, unless it ran within `min_interval` seconds (the app calls this
    on every ledger pass). Returns whether it scanned."""
    now = time.time() if now is None else now
    if not registered(conn):
        return False
    last = ledger._meta_get(conn, "yield_scanned")
    if min_interval and last is not None and now - float(last) < min_interval:
        return False
    scan_all(conn, now=now)
    ledger._meta_set(conn, "yield_scanned", now)
    conn.commit()
    return True


def remove_hooks(conn, strict=False) -> list[str]:
    """Take our git hook out of every tracked repository (for uninstalling).
    History and the list of repositories stay. Returns the repositories changed."""
    removed = []
    for r in registered(conn):
        try:
            if trailer.uninstall_repo(r["path"]):
                removed.append(r["path"])
        except (trailer.TrailerError, OSError, subprocess.SubprocessError):
            if strict and os.path.exists(r["path"]):
                raise RuntimeError("A tracked repository hook could not be removed. Check access and retry cleanup.")
            log.debug("yield: could not remove the hook from %s", r["path"], exc_info=True)
    return removed


# ── metrics ──────────────────────────────────────────────────────────────────

def _load_sessions(conn, repos: list[dict], tagged: set[str], since: float) -> dict[str, dict]:
    """Claude Code sessions that worked in a tracked repository (by folder) after
    tracking began, or whose commits carry their id, with cost, prompts and the
    model that cost most. Earlier sessions could never have been tagged, so
    judging them would only make the cost per change look worse."""
    sessions = {r["session_id"]: {"first": r["first"], "last": r["last"], "cost": r["cost"] or 0.0}
                for r in conn.execute(
                    "SELECT session_id, MIN(ts) first, MAX(ts) last, SUM(cost_usd) cost FROM calls "
                    "WHERE source = 'claude_code' GROUP BY session_id HAVING MAX(ts) >= ?", (since,))}
    rules = [(set(r["worktrees"]) | {r["path"]}, r["since"]) for r in repos]
    in_repo = set(tagged)
    for r in conn.execute("SELECT DISTINCT session_id, cwd FROM prompts "
                          "WHERE source = 'claude_code' AND cwd IS NOT NULL"):
        s = sessions.get(r["session_id"])
        if s and any(s["first"] >= began and any(trailer._inside(r["cwd"], w) for w in folders)
                     for folders, began in rules):
            in_repo.add(r["session_id"])
    sessions = {sid: s for sid, s in sessions.items() if sid in in_repo}
    for sid, s in sessions.items():
        s["prompts"], s["model"], s["model_cost"] = 0, None, -1.0
    for r in conn.execute("SELECT session_id, COUNT(*) n FROM prompts WHERE source = 'claude_code' "
                          "GROUP BY session_id"):
        if r["session_id"] in sessions:
            sessions[r["session_id"]]["prompts"] = r["n"]
    for r in conn.execute("SELECT session_id, model, SUM(cost_usd) cost FROM calls "
                          "WHERE source = 'claude_code' GROUP BY session_id, model"):
        s = sessions.get(r["session_id"])
        if s and (r["cost"] or 0.0) > s["model_cost"]:
            s["model"], s["model_cost"] = r["model"], r["cost"] or 0.0
    return sessions


def _week_of(ts: float) -> str:
    d = datetime.date.fromtimestamp(ts)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def _group_metrics(sessions: list[dict], commits_of, verdict) -> dict:
    """Metrics for a set of settled sessions. `commits_of(session)` lists their
    commits; `verdict(commit)` says what became of each."""
    out = {"sessions": len(sessions), "cost": 0.0, "prompts": 0, "commits": 0, "accepted": 0,
           "reverted": 0, "rewritten": 0, "reworked": 0, "idle_sessions": 0, "idle_cost": 0.0}
    for s in sessions:
        out["cost"] += s["cost"]
        out["prompts"] += s["prompts"]
        commits = commits_of(s)
        if not commits:
            out["idle_sessions"] += 1
            out["idle_cost"] += s["cost"]
        for c in commits:
            v = verdict(c)
            out["commits"] += 1
            out["accepted"] += v["accepted"]
            out["reverted"] += v["reverted"]
            out["rewritten"] += v["rewritten"]
            out["reworked"] += v["reworked"]
    acc = out["accepted"]
    out["cost_per_accepted"] = out["cost"] / acc if acc else None
    out["prompts_per_accepted"] = out["prompts"] / acc if acc else None
    out["accepted_rate"] = acc / out["commits"] if out["commits"] else None
    out["rework_rate"] = out["reworked"] / out["commits"] if out["commits"] else None
    return out


def snapshot(conn, now: float | None = None) -> dict | None:
    """Yield metrics for the dashboard; None until a repository is registered.

    Only settled sessions are measured (everything a session did, including its
    commits, is at least SETTLE_DAYS old), so no change is judged before its
    week is up; younger work is counted as pending."""
    repos = registered(conn)
    if not repos:
        return None
    now = time.time() if now is None else now
    settle = SETTLE_DAYS * 86400
    since = now - WINDOW_DAYS * 86400
    paths = [r["path"] for r in repos]
    marks = ",".join("?" * len(paths))
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM commits WHERE repo IN ({marks}) AND superseded = 0 ORDER BY ts", paths)]
    for c in rows:
        c["files"] = set(json.loads(c["files"]))
    by_session: dict[str, list[dict]] = {}
    for c in rows:
        if c["session_id"]:
            by_session.setdefault(c["session_id"], []).append(c)
    by_repo: dict[str, tuple[list[float], list[dict]]] = {}
    for p in paths:
        cs = [c for c in rows if c["repo"] == p]
        by_repo[p] = ([c["ts"] for c in cs], cs)

    def reworked(c) -> bool:
        stamps, cs = by_repo[c["repo"]]
        lo = bisect.bisect_right(stamps, c["ts"])
        hi = bisect.bisect_right(stamps, c["ts"] + settle)
        return any(f["gone_ts"] is None and FIX_SUBJECT.search(f["subject"]) and f["files"] & c["files"]
                   for f in cs[lo:hi])

    def verdict(c) -> dict:
        rev = c["reverted_ts"] is not None and c["reverted_ts"] - c["ts"] <= settle
        gone = c["gone_ts"] is not None and c["gone_ts"] - c["ts"] <= settle
        return {"accepted": int(not rev and not gone), "reverted": int(rev), "rewritten": int(gone),
                "reworked": int(reworked(c))}

    sessions = _load_sessions(conn, repos, set(by_session), since)
    settled, pending = [], {"sessions": 0, "commits": 0}
    for sid, s in sessions.items():
        s["id"] = sid
        s["commits"] = by_session.get(sid, [])
        done_at = max([s["last"]] + [c["ts"] for c in s["commits"]])
        if done_at <= now - settle:
            settled.append(s)
        else:
            pending["sessions"] += 1
            pending["commits"] += len(s["commits"])

    def measure(group):
        return _group_metrics(group, lambda s: s["commits"], verdict)

    def cut(key_of, keep=None):
        groups: dict[str, list[dict]] = {}
        for s in settled:
            groups.setdefault(key_of(s), []).append(s)
        rows_ = [{"key": k, **measure(g)} for k, g in groups.items()]
        return rows_ if keep is None else keep(rows_)

    tagged = [c for c in rows if c["session_id"]]
    return {
        "generated": round(now), "settle_days": SETTLE_DAYS,
        "repos": [{"path": r["path"], "scanned": r["scanned"]} for r in repos],
        "tracking_since": min(r["since"] for r in repos),
        "overall": measure(settled),
        "by_week": cut(lambda s: _week_of(s["first"]),
                       lambda r: sorted(r, key=lambda x: x["key"])[-WEEKS_SHOWN:]),
        "by_model": cut(lambda s: s["model"] or "unknown", lambda r: sorted(r, key=lambda x: -x["cost"])),
        "pending": pending,
        "coverage": {"commits": len(rows), "tagged": len(tagged)},
    }


# ── text report ──────────────────────────────────────────────────────────────

def _n(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def format_report(snap: dict | None) -> str:
    """The metrics as plain text, for `tokencoach --yield`."""
    if snap is None:
        return ("Not tracking any repository yet. Start with:\n"
                "  tokencoach --yield-install /path/to/repo")
    o, cov, pend = snap["overall"], snap["coverage"], snap["pending"]
    money = lambda v: ledger.fmt_usd(v)
    ratio = lambda v: "—" if v is None else f"{v:.1f}"
    share = lambda v: "—" if v is None else f"{round(v * 100)}%"
    lines = ["What your Claude Code sessions produced (judged a week after each change)", ""]
    n_repos = len(snap["repos"])
    lines += [f"Tracking {n_repos} {'repository' if n_repos == 1 else 'repositories'}:"]
    lines += [f"  {r['path']}" for r in snap["repos"]]
    began = time.strftime("%Y-%m-%d", time.localtime(snap["tracking_since"]))
    lines += [f"Judging sessions from {began} on. {cov['tagged']} of {_n(cov['commits'], 'commit')} "
              "carry a session tag (commits you make by hand don't).", ""]
    if not o["sessions"]:
        lines.append("Nothing to judge yet: the first numbers appear a week after the first tagged commit.")
    else:
        lines += [
            f"Judged: {_n(o['sessions'], 'session')}, {money(o['cost'])} API-equivalent, "
            f"{_n(o['commits'], 'commit')}",
            f"  accepted   {o['accepted']} of {o['commits']} ({share(o['accepted_rate'])}); "
            f"{o['reverted']} reverted, {o['rewritten']} dropped",
            f"  cost per accepted change       {money(o['cost_per_accepted'])}",
            f"  prompts per accepted change    {ratio(o['prompts_per_accepted'])}",
            f"  rework rate                    {share(o['rework_rate'])} "
            f"({_n(o['reworked'], 'commit')} fixed within {snap['settle_days']} days)",
        ]
        if o["idle_sessions"]:
            lines.append(f"  {_n(o['idle_sessions'], 'session')} ({money(o['idle_cost'])}) made no commit; "
                         "their cost is included above")
    if pend["sessions"]:
        lines += ["", f"Not judged yet (under a week old): {_n(pend['sessions'], 'session')}, "
                      f"{_n(pend['commits'], 'commit')}"]
    return "\n".join(lines)
