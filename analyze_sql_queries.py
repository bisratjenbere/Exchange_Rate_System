#!/usr/bin/env python3
"""
Analyze SQL query distribution across the codebase.
Evidence-based assessment for repository pattern justification.
"""

import ast
import os
import re
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class SQLQuery:
    file: str
    line: int
    function: str
    statement_type: str
    target_table: Optional[str]
    sql_text: str
    normalized_sql: str

class SQLVisitor(ast.NodeVisitor):
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.queries = []
        self.current_function = None
        self.function_stack = []
    
    def visit_FunctionDef(self, node):
        self.function_stack.append(node.name)
        self.current_function = ".".join(self.function_stack)
        self.generic_visit(node)
        self.function_stack.pop()
        self.current_function = ".".join(self.function_stack) if self.function_stack else None
    
    def visit_Call(self, node):
        # Check for cursor.execute() or cur.execute() patterns
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == 'execute':
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id in ('cur', 'cursor'):
                        self._process_execute_call(node)
        
        self.generic_visit(node)
    
    def _process_execute_call(self, node):
        if not node.args:
            return
        
        sql_arg = node.args[0]
        sql_text = self._extract_sql_text(sql_arg)
        
        if sql_text:
            normalized = self._normalize_sql(sql_text)
            stmt_type = self._get_statement_type(normalized)
            table = self._extract_table(normalized, stmt_type)
            
            query = SQLQuery(
                file=self.filepath,
                line=node.lineno,
                function=self.current_function or "<module>",
                statement_type=stmt_type,
                target_table=table,
                sql_text=sql_text[:200],  # Truncate long queries
                normalized_sql=normalized
            )
            self.queries.append(query)
    
    def _extract_sql_text(self, node) -> Optional[str]:
        """Extract SQL text from various AST node types"""
        if isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Str):  # Python 3.7 compatibility
            return node.s
        elif isinstance(node, ast.JoinedStr):  # f-string
            # Can't reliably extract from f-strings
            return "[F-STRING]"
        return None
    
    def _normalize_sql(self, sql: str) -> str:
        """Normalize SQL for comparison"""
        # Remove comments
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        # Collapse whitespace
        sql = re.sub(r'\s+', ' ', sql)
        # Lowercase
        sql = sql.lower().strip()
        return sql
    
    def _get_statement_type(self, sql: str) -> str:
        """Identify SQL statement type"""
        sql = sql.strip().lower()
        
        if sql.startswith('select'):
            return 'SELECT'
        elif sql.startswith('insert'):
            return 'INSERT'
        elif sql.startswith('update'):
            return 'UPDATE'
        elif sql.startswith('delete'):
            return 'DELETE'
        elif sql.startswith(('create', 'alter', 'drop')):
            return 'DDL'
        elif sql.startswith('savepoint'):
            return 'SAVEPOINT'
        elif sql.startswith('release'):
            return 'RELEASE'
        elif sql.startswith('rollback'):
            return 'ROLLBACK'
        else:
            return 'OTHER'
    
    def _extract_table(self, sql: str, stmt_type: str) -> Optional[str]:
        """Extract primary table name from SQL"""
        sql = sql.strip().lower()
        
        if stmt_type == 'SELECT':
            match = re.search(r'\bfrom\s+(\w+)', sql)
            if match:
                return match.group(1)
        elif stmt_type == 'INSERT':
            match = re.search(r'\binto\s+(\w+)', sql)
            if match:
                return match.group(1)
        elif stmt_type in ('UPDATE', 'DELETE'):
            match = re.search(r'\b(?:update|delete\s+from)\s+(\w+)', sql)
            if match:
                return match.group(1)
        
        return None

def find_python_files(root_dir: str, exclude_dirs: List[str]) -> List[Path]:
    """Find all Python files excluding specified directories"""
    root = Path(root_dir)
    python_files = []
    
    for py_file in root.rglob("*.py"):
        # Check if file is in excluded directory
        if any(excluded in py_file.parts for excluded in exclude_dirs):
            continue
        python_files.append(py_file)
    
    return sorted(python_files)

def analyze_codebase(root_dir: str) -> List[SQLQuery]:
    """Parse all Python files and extract SQL queries"""
    exclude = ['tests', 'test', 'scratch', 'scripts', '.venv', 'venv', '__pycache__']
    files = find_python_files(root_dir, exclude)
    
    all_queries = []
    
    for filepath in files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source, filename=str(filepath))
            visitor = SQLVisitor(str(filepath.relative_to(root_dir)))
            visitor.visit(tree)
            all_queries.extend(visitor.queries)
            
        except SyntaxError as e:
            print(f"Syntax error in {filepath}: {e}")
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
    
    return all_queries

def group_by_table(queries: List[SQLQuery]) -> dict:
    """Group queries by target table"""
    by_table = defaultdict(lambda: {'files': set(), 'functions': set(), 'queries': []})
    
    for query in queries:
        if query.target_table:
            by_table[query.target_table]['files'].add(query.file)
            by_table[query.target_table]['functions'].add(f"{query.file}:{query.function}")
            by_table[query.target_table]['queries'].append(query)
    
    return by_table

def find_duplicates(queries: List[SQLQuery]) -> dict:
    """Find duplicate SQL statements"""
    sql_map = defaultdict(list)
    
    for query in queries:
        # Only compare substantial queries (not savepoints, etc.)
        if query.statement_type in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
            sql_map[query.normalized_sql].append(query)
    
    # Keep only duplicates
    duplicates = {sql: queries for sql, queries in sql_map.items() if len(queries) > 1}
    return duplicates

def find_is_current_writes(queries: List[SQLQuery]) -> List[SQLQuery]:
    """Find all queries that write to rate_observation.is_current"""
    is_current_writes = []
    
    for query in queries:
        if query.target_table == 'rate_observation':
            if 'is_current' in query.normalized_sql:
                if query.statement_type in ('UPDATE', 'INSERT'):
                    is_current_writes.append(query)
    
    return is_current_writes

def generate_report(queries: List[SQLQuery], output_file: str):
    """Generate markdown report"""
    
    with open(output_file, 'w') as f:
        f.write("# Persistence Layer Analysis\n\n")
        f.write("**Mode:** Evidence-based assessment (read-only)\n\n")
        f.write("**Goal:** Test the claim that SQL is scattered and duplicated enough to justify a repository layer.\n\n")
        f.write("---\n\n")
        
        # Section 1: All cursor.execute calls
        f.write("## 1. All cursor.execute() Calls\n\n")
        f.write(f"**Total queries found:** {len(queries)}\n\n")
        
        # Group by statement type
        by_type = defaultdict(list)
        for q in queries:
            by_type[q.statement_type].append(q)
        
        f.write("**By statement type:**\n\n")
        for stmt_type in sorted(by_type.keys()):
            f.write(f"- {stmt_type}: {len(by_type[stmt_type])}\n")
        
        f.write("\n### Detailed Query List\n\n")
        f.write("| File | Line | Function | Type | Table | SQL Preview |\n")
        f.write("|------|------|----------|------|-------|-------------|\n")
        
        for q in sorted(queries, key=lambda x: (x.file, x.line)):
            sql_preview = q.sql_text.replace('\n', ' ')[:80]
            f.write(f"| {q.file} | {q.line} | {q.function} | {q.statement_type} | {q.target_table or '-'} | {sql_preview}... |\n")
        
        f.write("\n---\n\n")
        
        # Section 2: Group by table
        f.write("## 2. Queries Grouped by Table\n\n")
        
        by_table = group_by_table(queries)
        
        f.write(f"**Tables accessed:** {len(by_table)}\n\n")
        
        for table in sorted(by_table.keys()):
            data = by_table[table]
            f.write(f"### Table: `{table}`\n\n")
            f.write(f"- **Files touching this table:** {len(data['files'])}\n")
            f.write(f"- **Functions touching this table:** {len(data['functions'])}\n")
            f.write(f"- **Total queries:** {len(data['queries'])}\n\n")
            
            f.write("**Files:**\n")
            for file in sorted(data['files']):
                file_queries = [q for q in data['queries'] if q.file == file]
                f.write(f"- `{file}` ({len(file_queries)} queries)\n")
            f.write("\n")
        
        f.write("---\n\n")
        
        # Section 3: Duplicates
        f.write("## 3. Duplicate SQL Statements\n\n")
        
        duplicates = find_duplicates(queries)
        
        f.write(f"**Duplicate statement patterns found:** {len(duplicates)}\n\n")
        
        if duplicates:
            for i, (sql, dup_queries) in enumerate(sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True), 1):
                f.write(f"### Duplicate #{i} (appears {len(dup_queries)} times)\n\n")
                f.write("**Normalized SQL:**\n```sql\n")
                f.write(sql[:300])
                f.write("\n```\n\n")
                f.write("**Locations:**\n")
                for q in dup_queries:
                    f.write(f"- `{q.file}:{q.line}` in `{q.function}`\n")
                f.write("\n")
        else:
            f.write("No exact duplicates found (after normalization).\n\n")
        
        f.write("---\n\n")
        
        # Section 4: is_current writes
        f.write("## 4. Writes to `rate_observation.is_current`\n\n")
        
        is_current_writes = find_is_current_writes(queries)
        
        f.write(f"**Total writes to is_current:** {len(is_current_writes)}\n\n")
        
        if is_current_writes:
            f.write("| File | Line | Function | Type | SQL Preview |\n")
            f.write("|------|------|----------|------|-------------|\n")
            
            for q in is_current_writes:
                sql_preview = q.sql_text.replace('\n', ' ')[:100]
                f.write(f"| {q.file} | {q.line} | {q.function} | {q.statement_type} | {sql_preview}... |\n")
            
            f.write("\n**Transaction safety:** Needs confirmation (requires runtime analysis)\n\n")
        
        f.write("---\n\n")
        
        # Section 5: Git history placeholder
        f.write("## 5. Schema Change Frequency\n\n")
        f.write("**Command:** `git log --since=\"12 months ago\" --name-only --pretty=format: -- db/migrations pipeline/persist.py`\n\n")
        f.write("See git analysis section below.\n\n")
        f.write("---\n\n")
        
        # Section 6: Verdict (to be filled in after analysis)
        f.write("## 6. Verdict\n\n")
        f.write("### Key Metrics\n\n")
        
        # Calculate key metrics
        rate_obs_data = by_table.get('rate_observation', {'files': set(), 'functions': set(), 'queries': []})
        
        f.write(f"- **Total SQL queries in codebase:** {len(queries)}\n")
        f.write(f"- **Tables accessed:** {len(by_table)}\n")
        f.write(f"- **Files with SQL queries:** {len(set(q.file for q in queries))}\n")
        f.write(f"- **Duplicate patterns:** {len(duplicates)}\n")
        f.write(f"- **`rate_observation` queries:** {len(rate_obs_data['queries'])}\n")
        f.write(f"- **Files touching `rate_observation`:** {len(rate_obs_data['files'])}\n")
        f.write(f"- **Functions touching `rate_observation`:** {len(rate_obs_data['functions'])}\n")
        f.write(f"- **`is_current` writes:** {len(is_current_writes)}\n\n")
        
        f.write("### Analysis\n\n")
        f.write("**(a) Is a repository layer justified?**\n\n")
        
        if len(rate_obs_data['files']) > 3:
            f.write(f"**YES** - `rate_observation` is accessed from {len(rate_obs_data['files'])} files and {len(rate_obs_data['functions'])} functions. ")
            f.write("This level of dispersion indicates scattered data access logic.\n\n")
        else:
            f.write("**MARGINAL** - Data access is relatively concentrated.\n\n")
        
        f.write("**(b) Would a smaller change give most of the benefit?**\n\n")
        f.write("Analyzing alternatives:\n\n")
        
        insert_queries = [q for q in rate_obs_data['queries'] if q.statement_type == 'INSERT']
        f.write(f"- **INSERT standardization:** {len(insert_queries)} INSERT statements into `rate_observation`. ")
        
        if len(set(q.normalized_sql for q in insert_queries)) == 1:
            f.write("All appear identical - could extract to single function.\n")
        else:
            f.write("Multiple patterns exist - requires more than a constant.\n")
        
        f.write(f"- **`is_current` ownership:** {len(is_current_writes)} write sites across {len(set(q.file for q in is_current_writes))} files. ")
        
        if len(set(q.file for q in is_current_writes)) <= 2:
            f.write("Could centralize ownership in 1-2 modules.\n")
        else:
            f.write("Dispersed ownership - harder to centralize without repository.\n")
        
        f.write("\n**(c) Proof of concept cost**\n\n")
        f.write(f"- **Files to touch:** Minimum {len(rate_obs_data['files'])} files for `rate_observation` alone\n")
        f.write(f"- **Functions to refactor:** ~{len(rate_obs_data['functions'])} functions\n")
        f.write("- **Estimated effort:** 2-3 weeks for full migration, 3-5 days for POC with one repository\n\n")
        
        f.write("---\n\n")
        f.write("**Report generated by:** analyze_sql_queries.py\n")

if __name__ == '__main__':
    root = '/home/bisru/Exchange_Rate_System'
    output = os.path.join(root, 'docs/persistence-assessment.md')
    
    print("Analyzing SQL queries in codebase...")
    queries = analyze_codebase(root)
    
    print(f"Found {len(queries)} SQL queries")
    print(f"Generating report: {output}")
    
    generate_report(queries, output)
    
    print("Analysis complete!")
