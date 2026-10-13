#!/bin/bash
# Pre-deployment validation script
# Run this before pushing to production

set -e  # Exit on any error

echo "======================================"
echo "  Pre-Deployment Validation Script"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

# Check 1: Required files exist
echo "📁 Check 1: Required files..."
REQUIRED_FILES=(
    "render.yaml"
    "requirements.txt"
    "gunicorn.conf.py"
    "Procfile"
    "runtime.txt"
    "api/app.py"
    "scheduler/run_job.py"
    "scripts/init_database.py"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}   ❌ Missing: $file${NC}"
        FAILED=1
    else
        echo -e "${GREEN}   ✓${NC} $file"
    fi
done
echo ""

# Check 2: Python syntax
echo "🐍 Check 2: Python syntax validation..."
PYTHON_FILES=(
    "api/app.py"
    "scheduler/run_job.py"
    "seed_and_run.py"
)

for file in "${PYTHON_FILES[@]}"; do
    if python3 -m py_compile "$file" 2>/dev/null; then
        echo -e "${GREEN}   ✓${NC} $file"
    else
        echo -e "${RED}   ❌ Syntax error in $file${NC}"
        FAILED=1
    fi
done
echo ""

# Check 3: Run tests
echo "🧪 Check 3: Running test suite..."
if python3 -m pytest tests/ -q --tb=no 2>/dev/null; then
    echo -e "${GREEN}   ✓ All tests passed${NC}"
else
    echo -e "${RED}   ❌ Tests failed${NC}"
    echo -e "${YELLOW}   ⚠️  Run 'pytest tests/ -v' to see details${NC}"
    FAILED=1
fi
echo ""

# Check 4: Check .gitignore
echo "🔒 Check 4: Security - .gitignore validation..."
IGNORE_PATTERNS=(
    "\.env"
    "\.pem"
    "__pycache__"
    "*.pyc"
)

for pattern in "${IGNORE_PATTERNS[@]}"; do
    if grep -q "$pattern" .gitignore 2>/dev/null; then
        echo -e "${GREEN}   ✓${NC} $pattern ignored"
    else
        echo -e "${YELLOW}   ⚠️  $pattern not in .gitignore${NC}"
    fi
done
echo ""

# Check 5: No secrets in code
echo "🔐 Check 5: Scanning for hardcoded secrets..."
SECRET_PATTERNS=(
    "password.*=.*['\"]"
    "api_key.*=.*['\"]"
    "secret.*=.*['\"]"
    "token.*=.*['\"]"
)

SECRET_FOUND=0
for pattern in "${SECRET_PATTERNS[@]}"; do
    if grep -r -E "$pattern" --include="*.py" --exclude-dir=".git" --exclude-dir="tests" . 2>/dev/null | grep -v "PASSWORD_HERE\|SECRET_HERE\|API_KEY_HERE" > /dev/null; then
        echo -e "${RED}   ⚠️  Possible hardcoded secret found: $pattern${NC}"
        SECRET_FOUND=1
    fi
done

if [ $SECRET_FOUND -eq 0 ]; then
    echo -e "${GREEN}   ✓ No obvious secrets detected${NC}"
fi
echo ""

# Check 6: Database migration syntax
echo "🗄️  Check 6: Database migration validation..."
if [ -f "db/migrations/001_initial_schema.sql" ]; then
    # Check for basic SQL syntax issues
    if grep -i "CREATE TABLE" db/migrations/001_initial_schema.sql > /dev/null; then
        echo -e "${GREEN}   ✓ Migration file looks valid${NC}"
    else
        echo -e "${RED}   ❌ Migration file may be corrupted${NC}"
        FAILED=1
    fi
else
    echo -e "${RED}   ❌ Migration file missing${NC}"
    FAILED=1
fi
echo ""

# Check 7: Dependencies installable
echo "📦 Check 7: Dependencies validation..."
if pip3 install -r requirements.txt --dry-run --quiet 2>/dev/null; then
    echo -e "${GREEN}   ✓ All dependencies installable${NC}"
else
    echo -e "${RED}   ❌ Dependency issues detected${NC}"
    FAILED=1
fi
echo ""

# Check 8: Git status
echo "📋 Check 8: Git status..."
if [ -d ".git" ]; then
    UNCOMMITTED=$(git status --porcelain | wc -l)
    if [ $UNCOMMITTED -eq 0 ]; then
        echo -e "${GREEN}   ✓ No uncommitted changes${NC}"
    else
        echo -e "${YELLOW}   ⚠️  $UNCOMMITTED uncommitted files${NC}"
        echo -e "${YELLOW}      Run 'git status' to review${NC}"
    fi
    
    # Check if on main/master branch
    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    if [ "$BRANCH" == "main" ] || [ "$BRANCH" == "master" ]; then
        echo -e "${GREEN}   ✓ On deployment branch ($BRANCH)${NC}"
    else
        echo -e "${YELLOW}   ⚠️  On branch '$BRANCH' (not main/master)${NC}"
    fi
else
    echo -e "${YELLOW}   ⚠️  Not a git repository${NC}"
fi
echo ""

# Summary
echo "======================================"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. git add ."
    echo "2. git commit -m 'feat(deploy): production deployment'"
    echo "3. git push origin main"
    echo "4. Follow DEPLOYMENT_CHECKLIST.md"
else
    echo -e "${RED}❌ Some checks failed!${NC}"
    echo ""
    echo "Please fix the issues above before deploying."
    exit 1
fi
echo "======================================"
