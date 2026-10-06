# GitHub Repos for Alfred

Fuzzy-open any GitHub repo you have access to from Alfred.

Type **`gh`** followed by a few letters. Every repo you own, collaborate on, or
can see through an org is searchable, and matching is fuzzy: `gh imsg agent`
finds `imessage-agent`, `gh mc2 opq` finds `mc2-project/opaque-sql`. An empty
query lists your most recently pushed repos. Repos you open often float up.

| Key | Action |
| --- | --- |
| ↩ | Open the repo |
| ⌘↩ | Open pull requests |
| ⌥↩ | Open issues |
| ⌃↩ | Open Actions |
| ⇧↩ | Copy the SSH clone URL |
| ⌘C | Copy the repo URL |
| ⇥ | Autocomplete the repo name |

Typing `owner/repo` that isn't in your list offers to open it directly, and a
"Search GitHub" item is always at the bottom. `gh >refresh` refreshes the repo
list now.

## Requirements

- macOS with `/usr/bin/python3` (installed with the Xcode Command Line Tools)
- [Alfred](https://www.alfredapp.com) 4 or 5 with the Powerpack
- The [GitHub CLI](https://cli.github.com), logged in with `gh auth login`.
  The workflow uses that session, so there's no token to configure. It finds
  `gh` in Homebrew, `/usr/local/bin` and Nix profile paths.

## Install

Download `GitHub-Repos.alfredworkflow` from the
[latest release](https://github.com/chester-leung/alfred-gh-repos/releases/latest)
and double-click it, or build from source:

```sh
./build.sh install
```

## How it works

`src/gh.py` is the whole workflow (Python standard library only):

- **Repo list:** `gh api --paginate user/repos?affiliation=owner,collaborator,organization_member`,
  cached in Alfred's workflow cache folder. Searches read the cache (~30ms) and
  kick off a background refresh when it's older than `cache_minutes`
  (workflow variable, default 60).
- **Matching:** fzf-style scoring. Every space-separated word must match as a
  substring or subsequence; contiguous runs, word starts and hits in the repo
  name (over the owner) score higher. Open counts (stored in Alfred's workflow
  data folder) and push recency break ties; archived repos rank lower.

If an org's repos are missing, that org probably restricts OAuth apps. Approve
the GitHub CLI for it under GitHub Settings → Applications, then `gh >refresh`.
