---
name: git-workflow
description: Hướng dẫn sử dụng Git an toàn, quy trình branch, commit, và PR.
tags: [git, version-control, workflow]
version: 1.0
---

# Git Workflow Skill

Bạn là một chuyên gia Git. Hãy giúp người dùng quản lý version control hiệu quả và an toàn.

## 🚫 The Golden Rules

1. **NEVER** commit directly to `main` or `master`
2. **ALWAYS** create a branch for new work
3. **ALWAYS** create a PR before merging
4. **ALWAYS** delete branches after merge

## 🌿 Branch Naming Convention

```
<type>/<scope>/<description>

feat/auth/add-social-login
fix/api/handle-empty-response
docs/readme/add-setup-guide
refactor/core/simplify-payment-logic
test/utils/add-date-parser-tests
chore/deps/update-dependencies
```

### Type
- `feat` – New feature
- `fix` – Bug fix
- `docs` – Documentation
- `refactor` – Code refactoring (no behavior change)
- `test` – Add/update tests
- `chore` – Dependencies, build configs
- `style` – Formatting (spaces, semicolons)
- `perf` – Performance improvements

### Scope (optional)
- Module/component being changed
- `api`, `auth`, `db`, `ui`, `core`, etc.

### Description
- Use lowercase, hyphen-separated
- Clear and concise
- What is the change, not why

## 📝 Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Subject Line (50 chars max)
```
✅ feat(auth): add login endpoint
✅ fix(api): handle null response
❌ feat: add stuff
❌ feat(auth): added login endpoint that allows users to authenticate (way too long)
```

### Body (Wrap at 72 chars)
```
Explain WHAT and WHY, not HOW

- Why was this change needed?
- What problem does it solve?
- What are the side effects?

Use bullet points for clarity
```

### Footer
```
Closes #123
Fixes #456
Breaking change: description
Reviewed-by: reviewer@example.com
```

### Full Example
```
feat(payment): add stripe integration

Add Stripe API integration for payment processing.
This allows users to pay with credit/debit cards.

- Integrate Stripe SDK
- Add payment form component
- Add webhook handler for events
- Add error handling for failed charges

Closes #789
Reviewed-by: john@example.com
```

## 🔄 Git Workflow (Standard)

### 1. Start New Feature

```bash
# Update local main
git checkout main
git pull origin main

# Create feature branch
git checkout -b feat/awesome-feature

# Verify you're on correct branch
git branch
# Output: * feat/awesome-feature
#           main
```

### 2. Make Changes & Commit

```bash
# Check status
git status

# Stage changes (selective staging is better)
git add src/feature.js
# or stage all
git add .

# Verify what you're committing
git diff --cached

# Commit with good message
git commit -m "feat(feature): add awesome functionality"

# Make another commit
git add src/test.js
git commit -m "test(feature): add unit tests"

# View your commits
git log --oneline origin/main..HEAD
```

### 3. Keep Branch Updated

```bash
# If main has new commits while you work
git fetch origin
git rebase origin/main

# or merge (creates merge commit)
git merge origin/main

# Push your branch
git push origin feat/awesome-feature
```

### 4. Create Pull Request

```bash
# Push branch first
git push -u origin feat/awesome-feature

# Then create PR on GitHub/GitLab
# Set title, description, link issues
# Set reviewers
```

### 5. Address Review Comments

```bash
# Make requested changes
git add .
git commit -m "refactor(feature): address review comments"

# Push to same branch (auto-updates PR)
git push origin feat/awesome-feature
```

### 6. Merge PR

```bash
# When approved, merge via UI or CLI
# Prefer "Squash and merge" for feature branches

git checkout main
git pull origin main
git merge feat/awesome-feature --squash
git commit -m "feat(feature): add awesome functionality"
git push origin main
```

### 7. Clean Up

```bash
# Delete local branch
git branch -d feat/awesome-feature

# Delete remote branch (via GitHub UI or:)
git push origin --delete feat/awesome-feature

# List branches to verify cleanup
git branch -a
```

## 🆘 Common Git Scenarios

### Undo Last Commit (not pushed)
```bash
# Undo commit, keep changes
git reset --soft HEAD~1

# Undo commit, discard changes
git reset --hard HEAD~1
```

### Undo Changes in Working Directory
```bash
# Restore file to last commit
git restore src/file.js

# Restore all files
git restore .
```

### Stash Changes Temporarily
```bash
# Save changes without committing
git stash

# Switch branch
git checkout main

# Come back and restore changes
git checkout feat/your-feature
git stash pop
```

### Fix Wrong Branch
```bash
# Oops, made changes on main instead of branch
git log --oneline -5  # Note the commit hashes

# Create new branch from current state
git checkout -b feat/correct-branch

# Go back to main and undo
git checkout main
git reset --hard origin/main
```

### Interactive Rebase (Squash Commits)
```bash
# Last 3 commits
git rebase -i HEAD~3

# Mark commits to squash
pick abc123 First commit
squash def456 Second commit  # <- 's' to squash
squash ghi789 Third commit

# Save, edit message, done!
```

### Merge Conflict Resolution
```bash
# Merge fails due to conflicts
git merge feat/another-branch
# CONFLICT in src/file.js

# Option 1: Manual resolution
# 1. Open src/file.js
# 2. Find conflict markers (<<<<<<, ======, >>>>>>)
# 3. Edit to desired state
# 4. Save and commit

# Option 2: Keep one version
git checkout --ours src/file.js   # Keep current branch version
git checkout --theirs src/file.js # Keep incoming version

# Complete merge
git add .
git commit -m "merge: resolve conflicts"
git push
```

## 📋 Git Workflow Checklist

Before Pushing:
- [ ] Checked out correct branch
- [ ] All changes staged
- [ ] Commit message clear
- [ ] Code is formatted
- [ ] Tests pass locally
- [ ] No debug code/console.log

Before Creating PR:
- [ ] Branch is up-to-date with main
- [ ] Commits squashed if needed
- [ ] PR title is descriptive
- [ ] PR description explains changes
- [ ] Links related issues
- [ ] Screenshots if UI change

Before Merging:
- [ ] PR approved
- [ ] All CI checks pass
- [ ] Tests pass
- [ ] No merge conflicts
- [ ] Code reviewed

## 🔍 Code Review Workflow

### For Reviewers
```bash
# Check out PR branch locally
git fetch origin
git checkout origin/feat/awesome-feature

# Review code, run locally
npm test

# Go back to main
git checkout main
```

### Comment on PR
```
# Suggest changes
- [ ] Need to add error handling here
- [ ] Consider extracting this function

# Approve when ready
LGTM! 👍
```

## 🚀 Advanced Git

### View Commit History
```bash
# Pretty log
git log --oneline --graph --all

# Show commits by author
git log --author="John"

# Show what changed in last 5 commits
git log -p -5

# Blame - who changed this line?
git blame src/file.js
```

### Find Bugs (Bisect)
```bash
# Binary search to find which commit broke things
git bisect start
git bisect bad          # Current state is broken
git bisect good v1.0    # v1.0 worked fine

# Git will checkout commits between
# Test each one, mark as good/bad
git bisect good/bad

# When done
git bisect reset
```

### Cherry-pick
```bash
# Apply specific commit from another branch
git cherry-pick abc123

# Useful for hotfixes
```

### Tag Releases
```bash
# Create annotated tag
git tag -a v1.0.0 -m "Release version 1.0.0"

# Push tags
git push origin v1.0.0
# or all tags
git push origin --tags
```

## 📊 Merge Strategies

### Merge (Default)
```bash
git merge feat/branch
```
**Pros:** Preserves full history
**Cons:** Creates merge commits, history gets cluttered

### Squash & Merge
```bash
git merge --squash feat/branch
```
**Pros:** Clean history, one commit per feature
**Cons:** Loses intermediate commit history

### Rebase & Merge
```bash
git rebase origin/main
git merge --ff-only feat/branch
```
**Pros:** Linear history, clean
**Cons:** Rewrites history (don't use with shared branches)

**Recommendation:** Use **Squash & Merge** for feature branches

## 🛡️ Git Best Practices

✅ **DO:**
- Create branches for everything
- Write descriptive messages
- Review before merge
- Delete branches after merge
- Keep commits atomic
- Use .gitignore effectively
- Backup important branches

❌ **DON'T:**
- Force push to shared branches
- Commit directly to main
- Write vague commit messages
- Mix unrelated changes
- Commit secrets/API keys
- Ignore conflicts
- Use git if you don't understand it

## 🔐 Security

### Prevent Accidents
```bash
# Require code review before merge (GitHub settings)
# Require all checks to pass
# Require branches to be up-to-date
# Require status checks
```

### Clean Up History
```bash
# Remove sensitive data
git filter-branch --tree-filter 'rm -f secret.txt' HEAD

# Or use git-filter-repo (recommended)
git filter-repo --path secret.txt --invert-paths
```

## 📚 Git Resources

- `git help <command>` – Built-in help
- GitHub Docs: https://docs.github.com/en/get-started
- GitLab Docs: https://docs.gitlab.com/
- Atlassian Git Tutorial: https://www.atlassian.com/git/
