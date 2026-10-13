# Git Setup - Quick Reference Card

## 🚀 ONE COMMAND TO RULE THEM ALL

```bash
./execute_atomic_commits.sh
```

**That's it!** Your repository is now production-ready with 14 atomic commits.

---

## 📁 What Was Created

| File | Purpose | Read This If... |
|------|---------|-----------------|
| **execute_atomic_commits.sh** | Executable script | You want to initialize repo NOW |
| **GIT_QUICK_START.md** | Quick start guide | You're new to the project |
| **ATOMIC_COMMIT_PLAN.md** | Detailed commit strategy | You want to understand the approach |
| **SENIOR_ENGINEER_SUMMARY.md** | Executive summary | You're reviewing for production |
| **COMMIT_VISUAL_MAP.md** | Visual architecture | You prefer diagrams |
| **.gitignore** | Security & cleanliness | You want to see what's ignored |
| **.env.example** | Configuration template | You're setting up environment |

---

## ⚡ Quick Commands

```bash
# Initialize repository with atomic commits
./execute_atomic_commits.sh

# Check status
git status
git log --oneline

# Setup remote
git remote add origin <your-repo-url>
git push -u origin main

# Create development branch
git checkout -b develop

# Start working on a feature
git checkout -b feature/your-feature-name

# Make atomic commit
git add <files>
git commit -m "feat(scope): clear description

Why this change was needed
What it enables

WHY: Business reason
TESTING: How it was verified"

# Push and create PR
git push -u origin feature/your-feature-name
```

---

## 📊 Commit Types Reference

| Type | When to Use | Example |
|------|-------------|---------|
| **feat** | New feature/capability | `feat(adapters): add NewBank HTML scraper` |
| **fix** | Bug fix | `fix(pipeline): handle null buying_rate` |
| **docs** | Documentation only | `docs(adr): document SSL bypass decision` |
| **test** | Tests only | `test(fixtures): add edge case for zero rates` |
| **chore** | Infrastructure/tooling | `chore(deps): upgrade requests to 2.31.0` |
| **ops** | Operational scripts | `ops(backup): add automated daily backups` |
| **refactor** | Code restructure | `refactor(pipeline): extract validation rules` |
| **perf** | Performance | `perf(db): add index on source_id` |

---

## 🎯 Scopes Reference

| Scope | What It Covers |
|-------|---------------|
| **infra** | Repository infrastructure (.gitignore, CI/CD) |
| **db** | Database schema, migrations |
| **domain** | Business entities, enums |
| **pipeline** | Rate processing logic |
| **adapters** | Bank-specific adapters |
| **scheduler** | Collection orchestration |
| **api** | REST API, endpoints |
| **review** | Correction workflow |
| **suite** | Test infrastructure |
| **scripts** | Operational scripts |
| **project** | Project-level docs |
| **adr** | Architecture decisions |
| **registry** | Source registry, configuration |

---

## ✅ Commit Message Template

```bash
# Save as .gitmessage (optional)
git config commit.template .gitmessage

# Template content:
type(scope): subject (max 70 chars)

Body:
- What changed
- Why it changed
- What it enables

WHY: Business/technical reason
TESTING: How verified (command + result)
REFS: #issue-number (if applicable)
```

---

## 🔒 Security Checklist

```bash
# Before first push
git log -p | grep -iE "password|secret|api_key"  # Should be empty
ls -la .env  # Should not exist (or git check-ignore .env shows it's ignored)

# Setup pre-commit hook (recommended)
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
if git diff --cached | grep -qiE "password.*=|api_key.*="; then
    echo "❌ Secret detected!"
    exit 1
fi
EOF
chmod +x .git/hooks/pre-commit
```

---

## 🌿 Branch Strategy

```
main (production)
  └─ develop (integration)
       ├─ feature/add-new-bank
       ├─ feature/correction-ui
       ├─ feature/monitoring-dashboard
       └─ hotfix/critical-bug  (also from main)
```

**Rules:**
- **main**: Protected, requires PR + review + CI pass
- **develop**: Integration branch, relatively stable
- **feature/**: Short-lived, merge to develop when done
- **hotfix/**: From main, merge to main AND develop

---

## 🚨 Common Operations

### Undo Last Commit (Not Pushed)
```bash
git reset --soft HEAD~1  # Keeps changes staged
git reset --mixed HEAD~1 # Keeps changes unstaged
git reset --hard HEAD~1  # Discards changes (DANGEROUS)
```

### Amend Last Commit (Not Pushed)
```bash
git add <forgotten-file>
git commit --amend --no-edit
```

### Revert Commit (After Push)
```bash
git revert <commit-hash>  # Creates new commit that undoes it
git push origin main
```

### Find Which Commit Broke Tests
```bash
git bisect start
git bisect bad HEAD
git bisect good <last-known-good>
# Test at each step: pytest tests/
git bisect good  # or: git bisect bad
# Repeat until found
git bisect reset
```

### Cherry-Pick Commit from Another Branch
```bash
git cherry-pick <commit-hash>
```

---

## 📈 Health Check Commands

```bash
# Commit frequency (last week)
git log --since="1 week ago" --oneline | wc -l

# Contributors
git shortlog -sn

# Most changed files (hotspots)
git log --format=format: --name-only | sort | uniq -c | sort -rn | head -10

# Average commit size
git log --shortstat --since="1 month ago" | \
  awk '/files? changed/ {files+=$1; ins+=$4; del+=$6} END {print "Avg: " files/NR " files, " ins/NR " insertions, " del/NR " deletions"}'

# Check for secrets (should be empty)
git log -p | grep -iE "password|secret" || echo "✓ Clean"
```

---

## 🎓 For New Team Members

**Day 1:**
```bash
# 1. Clone repo
git clone <repo-url>
cd exchange_rate_system

# 2. Read documentation
cat README.md
cat CLAUDE.md
cat GIT_QUICK_START.md

# 3. Walk through commit history
git log --oneline --reverse
git show <first-commit>
# Read each commit message + changes
```

**Day 2:**
```bash
# 1. Setup dev environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Copy environment
cp .env.example .env
# Edit .env with your database credentials

# 3. Run tests
pytest tests/ -v

# 4. Make first commit (small change)
# Example: Fix typo in docs
git checkout -b fix/docs-typo
# Make change
git commit -m "docs(readme): fix typo in setup instructions"
git push -u origin fix/docs-typo
```

---

## 🎯 Code Review Checklist

When reviewing a PR:
- [ ] Each commit is atomic (one logical change)
- [ ] Commit messages follow format (type(scope): subject)
- [ ] Tests pass (check CI)
- [ ] No secrets committed
- [ ] No unnecessary files (logs, __pycache__, etc.)
- [ ] Documentation updated if needed
- [ ] Each commit can stand alone (no "fix previous commit")

---

## 📞 Help & Resources

| Question | Command/File |
|----------|--------------|
| How do I start? | `./execute_atomic_commits.sh` |
| I'm new, where to begin? | Read `GIT_QUICK_START.md` |
| I need details | Read `ATOMIC_COMMIT_PLAN.md` |
| I prefer visuals | Read `COMMIT_VISUAL_MAP.md` |
| Executive overview | Read `SENIOR_ENGINEER_SUMMARY.md` |
| What's ignored? | Check `.gitignore` |
| How do I configure? | Copy `.env.example` to `.env` |
| I broke something | `git reflog` shows all operations |

---

## 💡 Pro Tips

1. **Small commits are better**: 50-200 lines per commit is ideal
2. **Commit often**: Don't wait until end of day
3. **Write WHY, not WHAT**: Code shows what changed, message explains why
4. **Test before commit**: `pytest tests/` should pass
5. **Use branches**: Never commit directly to main
6. **Review your own commits**: `git log -p` before pushing
7. **Keep history clean**: Squash "fix typo" commits before PR

---

## 🎉 Success Indicators

You're doing it right when:
- ✅ You can describe each commit in one sentence
- ✅ Code reviews take <30 minutes
- ✅ You can rollback any commit safely
- ✅ `git bisect` finds bugs quickly
- ✅ New engineers understand history by reading commits
- ✅ You deploy multiple times per week
- ✅ Merge conflicts are rare

---

## 🚀 Execute Now

```bash
# One command, production-ready repository
./execute_atomic_commits.sh

# Then push to remote
git remote add origin <your-repo-url>
git push -u origin main

# Start developing
git checkout -b develop
git push -u origin develop

# Done! ✨
```

---

**Questions?** Check the detailed docs:
- GIT_QUICK_START.md
- ATOMIC_COMMIT_PLAN.md  
- SENIOR_ENGINEER_SUMMARY.md

**Ready to scale? Let's go!** 🚀
