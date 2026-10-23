# GitHub setup (manual steps for C1)

These steps need a repository owner, so C1 does them by hand once. Commands are for **PowerShell on Windows**. Each step also has the web click path.

Prerequisites: [Git for Windows](https://git-scm.com/download/win) and [GitHub CLI](https://cli.github.com/) (`winget install --id GitHub.cli`), then sign in once with `gh auth login`.

> **Private repo note.** On a free personal account, branch protection on a *private* repo is not enforced. Either claim GitHub Pro through the [Student Developer Pack](https://education.github.com/pack) (free for students), create the repo under a free GitHub organization on GitHub Team for education, or make the repo public. The team must never commit dataset records or secrets, whichever you choose.

## 1. Create the repository and push the starter code

From the `icd-platform` folder:

```powershell
git init -b main
git add .
git commit -m "chore(c1): initial monorepo, CI and Docker Compose"
gh repo create icd-platform --private --source . --remote origin --push
```

Web alternative: **github.com → + (top right) → New repository →** name `icd-platform`, Private, do **not** add a README/.gitignore/licence → **Create repository**, then run the `git remote add origin ...` and `git push -u origin main` lines GitHub shows.

## 2. Add the five other members

Replace the usernames with your teammates' GitHub usernames:

```powershell
$repo = "$(gh api user --jq .login)/icd-platform"
$members = @("c2-username", "c3-username", "c4-username", "c5-username", "ai1-username")
foreach ($m in $members) {
  gh api -X PUT "repos/$repo/collaborators/$m" -f permission=push
}
```

`push` is GitHub's **Write** role: members can push branches and open PRs, but cannot change settings. Each member must accept the email invitation.

Web alternative: **Repo → Settings → Collaborators → Add people →** username → role **Write**.

## 3. Protect `main`

Run this only after the first push, so that `main` exists. Save the JSON to a file first, because PowerShell quoting breaks inline JSON:

```powershell
@'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["lint", "test", "secret-scan", "compose-smoke"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true
  },
  "required_conversation_resolution": true,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
'@ | Set-Content -Encoding utf8 protection.json

gh api -X PUT "repos/$repo/branches/main/protection" --input protection.json
Remove-Item protection.json
```

What this enforces: no direct pushes to `main`, a PR with one approval for every change, stale approvals are dismissed when new commits are pushed, all four CI jobs must pass on an up-to-date branch, review conversations must be resolved, and no force pushes or branch deletion. It applies to you (the admin) too.

Web alternative: **Repo → Settings → Branches → Add classic branch protection rule →** branch name pattern `main` → tick:
- Require a pull request before merging → Require approvals: **1** → Dismiss stale pull request approvals when new commits are pushed
- Require status checks to pass before merging → Require branches to be up to date → search and add `lint`, `test`, `secret-scan`, `compose-smoke` (they appear in the search only after CI has run once, e.g. on your first PR)
- Require conversation resolution before merging
- Do not allow bypassing the above settings
- → **Create**

Also set **Settings → General → Pull Requests**: allow only **squash merging**, and tick **Automatically delete head branches**.

## 4. Check it worked

```powershell
gh api "repos/$repo/branches/main/protection" --jq "{reviews: .required_pull_request_reviews.required_approving_review_count, checks: .required_status_checks.contexts, admins: .enforce_admins.enabled}"
gh api "repos/$repo/collaborators" --jq ".[].login"
```

Expected: `reviews` is `1`, `checks` lists the four jobs, `admins` is `true`, and the collaborator list shows you plus every member who has accepted the invite.

Final test: try `git push origin main` with a small change. It must be rejected with `protected branch hook declined`.
