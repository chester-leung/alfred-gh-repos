#!/usr/bin/python3
"""Alfred workflow: fuzzy-open any GitHub repo you can access.

  gh.py search <query>   Script Filter (prints Alfred JSON)
  gh.py refresh          fetch repo list via `gh api` into the cache
  gh.py open <url>       record usage of $repo, then open the URL
"""
import json
import os
import re
import subprocess
import sys
import time

BUNDLE = "io.chester.alfred.gh-repos"
CACHE_DIR = os.environ.get("alfred_workflow_cache") or os.path.expanduser(
    "~/Library/Caches/com.runningwithcrayons.Alfred/Workflow Data/" + BUNDLE)
DATA_DIR = os.environ.get("alfred_workflow_data") or os.path.expanduser(
    "~/Library/Application Support/Alfred/Workflow Data/" + BUNDLE)
REPOS = os.path.join(CACHE_DIR, "repos.json")
LOCK = os.path.join(CACHE_DIR, "refresh.lock")
ERROR = os.path.join(CACHE_DIR, "error.txt")
USAGE = os.path.join(DATA_DIR, "usage.json")
MAX_AGE = int(os.environ.get("cache_minutes") or 60) * 60
MAX_RESULTS = 40

GH_CANDIDATES = [
    "/opt/homebrew/bin/gh", "/usr/local/bin/gh",
    os.path.expanduser("~/.nix-profile/bin/gh"),
    "/etc/profiles/per-user/%s/bin/gh" % os.environ.get("USER", ""),
    "/run/current-system/sw/bin/gh", "/nix/var/nix/profiles/default/bin/gh",
]


def gh_bin():
    for p in GH_CANDIDATES:
        if os.access(p, os.X_OK):
            return p
    return "gh"


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


# ---------------------------------------------------------------- refresh

def refresh():
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        if time.time() - os.path.getmtime(LOCK) < 120:
            return  # another refresh is running
    except OSError:
        pass
    open(LOCK, "w").close()
    try:
        jq = ("[.[] | .[] | {n: .full_name, d: .description, u: .html_url, "
              "p: .private, f: .fork, a: .archived, s: .stargazers_count, "
              "l: .language, t: .pushed_at}]")
        out = subprocess.run(
            [gh_bin(), "api", "--paginate", "--slurp",
             "user/repos?per_page=100&sort=pushed"
             "&affiliation=owner,collaborator,organization_member",
             "--jq", jq],
            capture_output=True, text=True, timeout=180)
        if out.returncode != 0:
            # older gh without --slurp: fall back to per-page parsing
            out = subprocess.run(
                [gh_bin(), "api", "--paginate",
                 "user/repos?per_page=100&sort=pushed"
                 "&affiliation=owner,collaborator,organization_member",
                 "--jq", jq.replace("[.[] | .[] |", "[.[] |")],
                capture_output=True, text=True, timeout=180)
        if out.returncode != 0:
            with open(ERROR, "w") as f:
                f.write(out.stderr.strip() or "gh api failed")
            return
        repos = []
        for line in out.stdout.splitlines():
            if line.strip():
                repos.extend(json.loads(line))
        seen, uniq = set(), []
        for r in repos:
            if r["n"] not in seen:
                seen.add(r["n"])
                uniq.append(r)
        save(REPOS, {"fetched": time.time(), "repos": uniq})
        if os.path.exists(ERROR):
            os.remove(ERROR)
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


def refresh_in_background():
    try:
        if time.time() - os.path.getmtime(LOCK) < 120:
            return
    except OSError:
        pass
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "refresh"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


# ---------------------------------------------------------------- fuzzy

SEP = set("/-_. ")


def fuzzy(needle, hay):
    """fzf-style score for subsequence `needle` in `hay` (both lowercase).
    Returns None when it doesn't match. Higher is better."""
    if not needle:
        return 0
    idx = hay.find(needle)
    if idx >= 0:  # contiguous substring: strong match
        score = 100 + 4 * len(needle)
        if idx == 0 or hay[idx - 1] in SEP:
            score += 40
        if idx + len(needle) == len(hay) or hay[idx + len(needle)] in SEP:
            score += 15
        return score - idx * 0.5
    # subsequence match: greedy from the right-most best start
    best = None
    start = hay.find(needle[0])
    while start >= 0:
        score, prev, pos = 0, -2, start
        ok = True
        for i, ch in enumerate(needle):
            pos = hay.find(ch, pos if i else start)
            if pos < 0:
                ok = False
                break
            if pos == prev + 1:
                score += 8          # consecutive
            elif pos == 0 or hay[pos - 1] in SEP:
                score += 6          # start of a word
            else:
                score -= min(pos - prev, 6)  # gap penalty
            prev, pos = pos, pos + 1
        if not ok:
            break
        score -= start * 0.3
        if best is None or score > best:
            best = score
        start = hay.find(needle[0], start + 1)
    return best


def score_repo(tokens, repo):
    full = repo["n"].lower()
    name = full.split("/", 1)[1]
    total = 0
    for tok in tokens:
        if "/" in tok:
            s = fuzzy(tok, full)
        else:
            s_name = fuzzy(tok, name)
            s_full = fuzzy(tok, full)
            s = None
            if s_name is not None:
                s = s_name + 10  # prefer hits in repo name over owner
            if s_full is not None and (s is None or s_full > s):
                s = s_full
        if s is None:
            return None
        total += s
    if len(tokens) == 1 and tokens[0] in (name, full):
        total += 200
    return total


# ---------------------------------------------------------------- output

def item_for(repo, uses):
    name, url = repo["n"], repo["u"]
    bits = []
    if repo.get("p"):
        bits.append("🔒 private")
    if repo.get("a"):
        bits.append("archived")
    if repo.get("f"):
        bits.append("fork")
    if repo.get("l"):
        bits.append(repo["l"])
    if repo.get("s"):
        bits.append("★ %d" % repo["s"])
    if repo.get("d"):
        bits.append(repo["d"])
    sub = "  ·  ".join(bits) or url
    return {
        "uid": name,
        "title": name,
        "subtitle": sub,
        "arg": url,
        "autocomplete": name,
        "match": name,
        "quicklookurl": url,
        "text": {"copy": url, "largetype": name},
        "variables": {"repo": name},
        "mods": {
            "cmd": {"arg": url + "/pulls", "subtitle": "Open pull requests",
                    "variables": {"repo": name}},
            "alt": {"arg": url + "/issues", "subtitle": "Open issues",
                    "variables": {"repo": name}},
            "ctrl": {"arg": url + "/actions", "subtitle": "Open Actions",
                     "variables": {"repo": name}},
            "shift": {"arg": "copy:git@github.com:%s.git" % name,
                      "subtitle": "Copy SSH clone URL",
                      "variables": {"repo": name}},
        },
    }


def search(query):
    query = query.strip()
    items, rerun = [], None
    if query in (">refresh", "> refresh", ":refresh"):
        refresh_in_background()
        return emit([{"title": "Refreshing repo list…",
                      "subtitle": "Runs in the background", "valid": False}])

    cache = load(REPOS, None)
    if cache is None or time.time() - cache.get("fetched", 0) > MAX_AGE:
        refresh_in_background()
    err = None
    if os.path.exists(ERROR):
        with open(ERROR) as f:
            err = f.read().strip()

    if cache is None:
        if err:
            return emit([{
                "title": "Couldn't load repos — is `gh` logged in?",
                "subtitle": "↩ run `gh auth login` in Terminal  ·  " + err[:120],
                "arg": "auth", "variables": {"repo": ""}}])
        return emit([{"title": "Loading your repos…",
                      "subtitle": "Fetching via gh api (first run only)",
                      "valid": False}], rerun=0.5)

    usage = load(USAGE, {})
    repos = cache["repos"]
    tokens = query.lower().split()
    scored = []
    for i, r in enumerate(repos):
        s = score_repo(tokens, r)
        if s is None:
            continue
        u = usage.get(r["n"], 0)
        # frecency boost (bounded) + recency of push (list is sorted by pushed)
        boost = min(u, 20) * (3 if tokens else 10) - i * 0.01
        if r.get("a"):
            boost -= 15
        scored.append((s + boost, r))
    scored.sort(key=lambda x: -x[0])
    items = [item_for(r, usage) for _, r in scored[:MAX_RESULTS]]

    if query:
        if re.fullmatch(r"[\w.-]+/[\w.-]+", query) and not any(
                i["title"].lower() == query.lower() for i in items):
            url = "https://github.com/" + query
            items.append({"title": "Open github.com/" + query,
                          "subtitle": url, "arg": url,
                          "variables": {"repo": query}})
        from urllib.parse import quote
        url = "https://github.com/search?type=repositories&q=" + quote(query)
        items.append({"title": "Search GitHub for “%s”" % query,
                      "subtitle": url, "arg": url,
                      "variables": {"repo": ""}})
    if err:
        items.append({"title": "Last refresh failed", "subtitle": err[:200],
                      "valid": False})
    return emit(items, rerun)


def emit(items, rerun=None):
    out = {"items": items}
    if rerun:
        out["rerun"] = rerun
    sys.stdout.write(json.dumps(out))


def open_url(url):
    repo = os.environ.get("repo", "")
    if repo:
        usage = load(USAGE, {})
        usage[repo] = usage.get(repo, 0) + 1
        save(USAGE, usage)
    if url == "auth":
        subprocess.run(["osascript", "-e",
                        'tell application "Terminal" to do script "%s auth login"'
                        % gh_bin(), "-e", 'tell application "Terminal" to activate'])
    elif url.startswith("copy:"):
        subprocess.run(["pbcopy"], input=url[5:], text=True)
        sys.stdout.write(url[5:])
    else:
        subprocess.run(["open", url])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "search"
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    if cmd == "search":
        search(arg)
    elif cmd == "refresh":
        refresh()
    elif cmd == "open":
        open_url(arg)
