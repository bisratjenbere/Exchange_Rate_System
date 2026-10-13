# Git Quick Start - Ethiopian Bank Exchange Rate System

## 🚀 Fastest Path to Production-Ready Repository

```bash
# Execute atomic commit sequence (14 commits)
./execute_atomic_commits.sh

# That's it! Repository is initialized with proper history.
```

---

## 📋 What You Get

**14 atomic, production-ready commits:**

1. **chore(infra)**: Security & .gitignore
2. **docs(project)**: System overview & standards
3. **docs(adr)**: Architecture decisions
4. **feat(db)**: PostgreSQL schema
5. **feat(domain)**: Business entities
6. **feat(pipeline)**: Rate processing
7. **feat(registry)**: Bank sources & waves
8. **test(fixtures)**: Evidence & mappings
9. **feat(adapters)**: Wave 1-2 API adapters
10. **feat(adapters)**: Wave 3-4 HTML adapters
11. **feat(scheduler)**: Collection orchestration
12. **feat(api)**: REST API & trusted view
13. **test(suite)**: Full test coverage
14. **ops(scripts)**: Operational tooling

---

## 🎯 Why This Sequence?

### For Code Review
- Each commit is reviewable in 10-15 minutes
- Clear scope, single responsibility
- Bisectable for debugging

### For Production
- Any commit can be tagged as a release
- Rollback to any stable point
- Gradual feature enablement

### For Teams
- New engineers follow commit history as tutorial
- Parallel work on different adapters
- Clear ownership and decision trail

---

## 📊 Commit Message Format (Conventional Commits)

```
<type>(<scope>): <subject>

<body: what and why>

<footer: breaking changes, issues>
```

**Types used in this project:**
- `feat`: New feature or capability
- `fix`: Bug fix
- `docs`: Documentation only
- `test`: Test additions or changes
- `chore`: Infrastructure, tooling, dependencies
- `ops`: Operational scripts, deployment
- `refactor`: Code restructure (no behavior change)
- `perf`: Performance improvement

**Scopes used:**
- `infra`, `db`, `domain`, `pipeline`, `adapters`, `scheduler`, `api`, `suite`, `project`, `adr`, `registry`, `scripts`

---

## 🔍 Post-Commit Verification

```bash
# View commit history
git log --oneline --graph --all

# View detailed commit
git show <commit-hash>

# View files changed per commit
git log --stat

# Check what's tracked
git ls-files | head -20

# Verify .gitignore working
git status  # Should show only untracked: inspect_*.py, survey_*.py, logs/

# Security audit
git log -p | grep -iE "password|secret|api_key" || echo "✓ No secrets"

# Generate changelog
git log --format="- %s (%h)" --reverse > CHANGELOG.md
```

---

## 🌿 Branching Strategy for Production

```bash
# Set main as default branch
git branch -M main

# Create develop branch for ongoing work
git checkout -b develop

# Feature branches (for team collaboration)
git checkout -b feature/wave-5-browser-adapters
git checkout -b feature/correction-workflow
git checkout -b feature/monitoring-dashboard

# Release branches
git checkout -b release/v1.0.0

# Hotfix branches (from main)
git checkout -b hotfix/rate-validation-bug
```

**Branch Protection (recommended for GitHub/GitLab):**
- `main`: Require PR reviews, require CI pass, no direct commits
- `develop`: Require CI pass, allow direct commits
- `feature/*`: No restrictions

---

## 🔐 Security Checklist

**Before first push:**

```bash
# 1. Scan for secrets
git log -p | grep -iE "password|secret|token|api_key|BEGIN.*PRIVATE"

# 2. Check environment files
cat .env 2>/dev/null && echo "⚠️  .env exists!" || echo "✓ .env not tracked"

# 3. Verify .gitignore effective
echo "test_secret=abc123" > .env
git status | grep ".env" && echo "⚠️  .env not ignored!" || echo "✓ .env properly ignored"
rm .env

# 4. Add pre-commit hook (optional)
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
if git diff --cached | grep -qiE "password.*=|api_key.*="; then
    echo "❌ Potential secret detected!"
    exit 1
fi
EOF
chmod +x .git/hooks/pre-commit
```

---

## 🏃 Development Workflow

### Setup Development Environment

```bash
# 1. Clone repository (for team members)
git clone <repository-url>
cd exchange_rate_system

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# 3. Install dependencies (if requirements.txt exists)
pip install -r requirements.txt

# 4. Copy environment template
cp .env.example .env
# Edit .env with your database credentials

# 5. Setup database
createdb exchange_rates
psql exchange_rates < db/migrations/001_initial_schema.sql

# 6. Seed data
python seed_and_run.py

# 7. Run tests
pytest tests/ -v

# 8. Start API
python -m api.app
```

### Daily Development Cycle

```bash
# Morning: Sync with team
git checkout develop
git pull origin develop

# Create feature branch
git checkout -b feature/add-new-bank

# Work on feature...
# ... make changes ...

# Test locally
pytest tests/test_my_feature.py -v

# Commit atomically (one logical change)
git add adapters/new_bank/
git commit -m "feat(adapters): add NewBank adapter with API parsing

- Implement fetch() for NewBank JSON API
- Parse rates with category mapping
- Add fixtures for normal and edge cases
- Add unit tests with 95% coverage

WHY: NewBank is Wave 5 priority, requested by stakeholders
TESTING: All tests pass, verified against live API capture"

# Push and create PR
git push -u origin feature/add-new-bank

# Create PR via GitHub/GitLab web interface or CLI:
# gh pr create --title "feat(adapters): add NewBank adapter"
```

---

## 🎓 For New Team Members

**Day 1: Understanding the System**
```bash
# 1. Read system overview
cat README.md
cat CLAUDE.md

# 2. Study commit history (the tutorial)
git log --oneline --reverse
git show <first-commit>  # Start from beginning
git show <next-commit>   # Progress chronologically

# 3. Explore architecture decisions
ls docs/decisions/
cat docs/decisions/ADR-index.md

# 4. Review execution plan
cat docs/plan/execution-order.md
cat docs/plan/STATUS.md
```

**Day 2-3: Hands-on Learning**
```bash
# 1. Setup dev environment (see above)

# 2. Run existing tests to understand behavior
pytest tests/test_m3_pipeline.py -v
pytest tests/test_m4_adib_adapter.py -v

# 3. Pick a simple task
# Example: Add fixture for edge case, fix typo in docs

# 4. Make your first commit (follow format)
git commit -m "test(fixtures): add zero-rate rejection test

- Add fixture with buying_rate=0.0
- Verify pipeline rejects with INVALID_RATE_VALUE
- Update test_m3_pipeline.py with new case

WHY: Found production edge case, adding regression test"
```

---

## 🚨 Troubleshooting

### "I committed a secret!"

```bash
# If not pushed yet:
git reset --soft HEAD~1  # Undo commit, keep changes
# Remove secret, commit again

# If already pushed (CRITICAL):
# DO NOT try to hide it - assume compromised
# 1. Rotate the secret immediately
# 2. Use git-filter-repo to rewrite history (contact senior engineer)
```

### "My commit is too big"

```bash
# Split into multiple commits using interactive staging:
git add -p  # Stage hunks interactively
git commit -m "First logical change"
git add -p  # Stage more hunks
git commit -m "Second logical change"
```

### "I need to update the last commit"

```bash
# If not pushed yet:
git add <forgotten-file>
git commit --amend --no-edit

# If already pushed to your branch (not main):
git push --force-with-lease origin feature/my-branch
```

### "How do I find which commit introduced a bug?"

```bash
# Binary search through commit history
git bisect start
git bisect bad           # Current commit is broken
git bisect good <hash>   # Known good commit
# Git checks out middle commit
# Test it: pytest tests/
git bisect good   # or: git bisect bad
# Repeat until culprit found
git bisect reset
```

---

## 📈 Scaling to Production

### CI/CD Integration

```bash
# Example: GitHub Actions workflow
mkdir -p .github/workflows
cat > .github/workflows/ci.yml << 'EOF'
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: exchange_rates_test
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v --cov
      - run: flake8 . --max-line-length=100
EOF
```

### Release Process

```bash
# 1. Ensure develop is stable
git checkout develop
pytest tests/ -v
# All tests pass

# 2. Create release branch
git checkout -b release/v1.0.0

# 3. Update version files, changelog
echo "1.0.0" > VERSION
git log --format="- %s (%h)" v0.9.0..HEAD > CHANGELOG-1.0.0.md

# 4. Commit release prep
git commit -am "chore(release): prepare v1.0.0"

# 5. Merge to main
git checkout main
git merge --no-ff release/v1.0.0
git tag -a v1.0.0 -m "Release v1.0.0 - Initial production release"

# 6. Push main and tags
git push origin main --tags

# 7. Merge back to develop
git checkout develop
git merge main
git push origin develop
```

### Monitoring Repository Health

```bash
# Commit frequency
git log --since="1 month ago" --oneline | wc -l

# Contributors
git shortlog -sn

# Code churn (files changed most often)
git log --format=format: --name-only | sort | uniq -c | sort -rn | head -20

# Average commit message length (should be detailed)
git log --format=%s | awk '{print length}' | awk '{s+=$1; c++} END {print s/c}'
```

---

## 📚 Additional Resources

- **Conventional Commits**: https://www.conventionalcommits.org/
- **Git Best Practices**: https://git-scm.com/book/en/v2
- **Code Review Guide**: (link to team's internal guide)
- **Deployment Runbook**: ops/README.md (if exists)

---

## 🎯 Summary: Atomic Commits for Scale

**What we achieved:**
- ✅ 14 atomic, reviewable commits
- ✅ Clear separation of concerns
- ✅ Production-ready from commit 1
- ✅ Rollback to any point safely
- ✅ Team can parallelize work
- ✅ Self-documenting history
- ✅ Security built-in from start

**Run this one command:**
```bash
./execute_atomic_commits.sh
```

**Result:**
A production-ready repository that scales with your team, with proper history, security, and documentation from day one.
