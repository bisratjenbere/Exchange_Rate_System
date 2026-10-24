"""
scheduler/cli.py — Command-line interface for collection management.

Provides operational controls for manual intervention, testing, and monitoring:
- collect-one: Run collection for a single source
- health: Check system health
- test-adapter: Test an adapter without writing to database
- list-sources: List all configured sources
- pause/resume: Control collection execution
- status: Show current collection status

Usage:
    python3 -m scheduler.cli health
    python3 -m scheduler.cli collect-one 5
    python3 -m scheduler.cli test-adapter cbe_html --dry-run
    python3 -m scheduler.cli list-sources --enabled-only
"""
import os
import sys
import json
import time
from datetime import datetime, timezone

import click
import psycopg2

from scheduler.runner import Scheduler
from scheduler.health import health_check, format_health_report, quick_health_check
from scheduler.control import CollectionControl
from infrastructure.adapter_registry import default_registry
from infrastructure.rate_source_repository import RateSourceRepository
from infrastructure.config import Config


@click.group()
def cli():
    """Exchange rate collection management CLI."""
    pass


@cli.command()
@click.argument('source_id', type=int)
@click.option('--dry-run', is_flag=True, help='Test without committing to database')
def collect_one(source_id, dry_run):
    """
    Collect from a single source immediately.
    
    Example:
        scheduler/cli.py collect-one 5
        scheduler/cli.py collect-one 5 --dry-run
    """
    conn = _get_db_connection()
    
    try:
        scheduler = Scheduler(dry_run=dry_run)
        click.echo(f"Starting collection for source_id={source_id}...")
        
        start_time = time.time()
        result = scheduler.run_source(conn, source_id)
        duration = time.time() - start_time
        
        click.echo(json.dumps(result, indent=2))
        click.echo(f"\nDuration: {duration:.2f}s")
        
        if dry_run:
            click.echo("\n⚠ DRY RUN MODE - No changes committed to database")
        
        status = result.get("status")
        if status in ("success", "partial_success"):
            click.secho(f"✓ Collection {status}", fg='green')
            sys.exit(0)
        else:
            click.secho(f"✗ Collection {status}", fg='red')
            sys.exit(1)
    finally:
        conn.close()


@cli.command()
@click.option('--detailed/--quick', default=True, help='Detailed or quick health check')
@click.option('--json-output', is_flag=True, help='Output as JSON')
def health(detailed, json_output):
    """
    Check system health before collection.
    
    Example:
        scheduler/cli.py health
        scheduler/cli.py health --quick
        scheduler/cli.py health --json-output
    """
    conn = _get_db_connection()
    
    try:
        result = health_check(conn, detailed=detailed)
        
        if json_output:
            click.echo(json.dumps(result, indent=2))
        else:
            report = format_health_report(result)
            click.echo(report)
        
        sys.exit(0 if result["healthy"] else 1)
    finally:
        conn.close()


@cli.command()
@click.argument('adapter_key')
@click.option('--dry-run', is_flag=True, help='Parse without storing')
@click.option('--show-records', is_flag=True, help='Display parsed records')
def test_adapter(adapter_key, dry_run, show_records):
    """
    Test an adapter's fetch and parse without database writes.
    
    Example:
        scheduler/cli.py test-adapter cbe_html
        scheduler/cli.py test-adapter dashen_html --show-records
    """
    try:
        registry = default_registry
        adapter = registry.get(adapter_key)
        
        click.echo(f"Testing adapter: {adapter_key}")
        click.echo(f"Module: {adapter.__name__ if hasattr(adapter, '__name__') else type(adapter).__module__}")
        
        # Check if we can get source URL
        conn = _get_db_connection()
        try:
            repo = RateSourceRepository(conn)
            sources = [s for s in repo.get_all_sources() if s["adapter_key"] == adapter_key]
            
            if not sources:
                click.secho(f"✗ No source configured for adapter_key={adapter_key}", fg='yellow')
                sys.exit(1)
            
            source = sources[0]
            source_url = source["source_url"]
            ssl_verify = source["ssl_verify"]
            
            click.echo(f"Source URL: {source_url}")
            click.echo(f"SSL Verify: {ssl_verify}")
            click.echo("")
            
            # Fetch
            click.echo("Fetching...")
            config = Config()
            
            if hasattr(adapter, "fetch_raw"):
                raw_content, http_status = adapter.fetch_raw(
                    source_url, config.USER_AGENT, ssl_verify
                )
            else:
                from http_clients.http_client import RequestsHttpClient
                http_client = RequestsHttpClient()
                response = http_client.fetch(source_url, ssl_verify=ssl_verify)
                if not response.is_success():
                    click.secho(f"✗ HTTP fetch failed: {response.error}", fg='red')
                    sys.exit(1)
                raw_content = response.content
                http_status = response.status_code
            
            click.echo(f"✓ Fetched: {http_status} ({len(raw_content)} bytes)")
            
            # Parse
            click.echo("Parsing...")
            category = source.get("default_category", "UNKNOWN")
            
            import inspect
            sig = inspect.signature(adapter.parse)
            if "category" in sig.parameters:
                result = adapter.parse(raw_content, category=category)
            else:
                result = adapter.parse(raw_content)
            
            # Handle different result types
            from adapters.base import ParseResult
            if isinstance(result, ParseResult):
                records = result.records
                errors = result.errors
            elif isinstance(result, tuple):
                records, errors = result
            else:
                records = result
                errors = []
            
            click.echo(f"✓ Parsed: {len(records)} records, {len(errors)} errors")
            
            if show_records:
                click.echo("\nRecords:")
                for i, record in enumerate(records[:10], 1):  # Show first 10
                    click.echo(f"  {i}. {record}")
                if len(records) > 10:
                    click.echo(f"  ... and {len(records) - 10} more")
            
            if errors:
                click.echo("\nErrors:")
                for error in errors:
                    click.echo(f"  - {error}")
            
            # Schema fingerprint
            if hasattr(adapter, "schema_fingerprint"):
                fp = adapter.schema_fingerprint(raw_content)
                click.echo(f"\nSchema Fingerprint: {fp[:16]}...")
            
            click.secho(f"\n✓ Test passed", fg='green')
            sys.exit(0)
            
        finally:
            conn.close()
            
    except Exception as e:
        click.secho(f"✗ Test failed: {e}", fg='red')
        import traceback
        if os.environ.get("DEBUG"):
            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option('--enabled-only', is_flag=True, help='Show only enabled sources')
@click.option('--show-failures', is_flag=True, help='Show failure information')
def list_sources(enabled_only, show_failures):
    """
    List all configured sources.
    
    Example:
        scheduler/cli.py list-sources
        scheduler/cli.py list-sources --enabled-only
        scheduler/cli.py list-sources --show-failures
    """
    conn = _get_db_connection()
    
    try:
        repo = RateSourceRepository(conn)
        
        if enabled_only:
            sources = repo.get_enabled_sources()
        else:
            sources = repo.get_all_sources()
        
        # Header
        click.echo(f"{'ID':<4} {'Enabled':<8} {'Adapter Key':<25} {'Failures':<10} {'Last Success':<20}")
        click.echo("-" * 90)
        
        for source in sources:
            enabled = "✓" if source.get("is_enabled", True) else "✗"
            failures = source.get("consecutive_failures", 0)
            last_success = source.get("last_success_at")
            
            if last_success:
                last_success_str = last_success.strftime("%Y-%m-%d %H:%M") if hasattr(last_success, 'strftime') else str(last_success)[:16]
            else:
                last_success_str = "Never"
            
            failure_str = f"{failures}" if failures > 0 else "-"
            
            # Color code failures
            if failures >= 3:
                failure_str = click.style(failure_str, fg='red')
            elif failures > 0:
                failure_str = click.style(failure_str, fg='yellow')
            
            click.echo(f"{source['id']:<4} {enabled:<8} {source['adapter_key']:<25} {failure_str:<10} {last_success_str:<20}")
            
            if show_failures and failures > 0:
                last_error = source.get("last_failure_code", "unknown")
                click.echo(f"     └─ Last error: {last_error}")
        
        click.echo(f"\nTotal: {len(sources)} sources")
        
    finally:
        conn.close()


@cli.command()
@click.argument('reason')
@click.option('--paused-by', default=os.environ.get('USER', 'cli'), help='Who is pausing')
def pause(reason, paused_by):
    """
    Pause collection execution.
    
    Example:
        scheduler/cli.py pause "Maintenance window"
        scheduler/cli.py pause "Testing changes" --paused-by alice
    """
    conn = _get_db_connection()
    
    try:
        control = CollectionControl(conn)
        control.pause(reason, paused_by)
        
        click.secho(f"✓ Collection paused by {paused_by}", fg='yellow')
        click.echo(f"  Reason: {reason}")
    finally:
        conn.close()


@cli.command()
def resume():
    """
    Resume collection execution.
    
    Example:
        scheduler/cli.py resume
    """
    conn = _get_db_connection()
    
    try:
        control = CollectionControl(conn)
        control.resume()
        
        click.secho("✓ Collection resumed", fg='green')
    finally:
        conn.close()


@cli.command()
def status():
    """
    Show current collection status.
    
    Example:
        scheduler/cli.py status
    """
    conn = _get_db_connection()
    
    try:
        control = CollectionControl(conn)
        
        if control.is_paused():
            pause_info = control.get_pause_info()
            click.secho("⚠ Collection is PAUSED", fg='yellow')
            if pause_info:
                click.echo(f"  Paused by: {pause_info.get('paused_by', 'unknown')}")
                click.echo(f"  Paused at: {pause_info.get('paused_at', 'unknown')}")
                click.echo(f"  Reason: {pause_info.get('reason', 'No reason provided')}")
        else:
            click.secho("✓ Collection is RUNNING", fg='green')
        
        # Show recent activity
        click.echo("\nRecent Activity (last 10 runs):")
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cr.started_at, rs.adapter_key, cr.status, 
                       cr.records_accepted, cr.duration_ms
                FROM collection_run cr
                JOIN rate_source rs ON rs.id = cr.source_id
                ORDER BY cr.started_at DESC
                LIMIT 10
            """)
            
            for row in cur.fetchall():
                started, adapter_key, status, accepted, duration = row
                status_symbol = "✓" if status in ("success", "partial_success") else "✗"
                duration_str = f"{duration}ms" if duration else "-"
                click.echo(f"  {status_symbol} {started.strftime('%H:%M:%S')} {adapter_key:<25} {status:<15} {accepted or 0} records  {duration_str}")
        
    finally:
        conn.close()


def _get_db_connection():
    """Get database connection from environment."""
    dsn = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
    try:
        return psycopg2.connect(dsn)
    except Exception as e:
        click.secho(f"✗ Database connection failed: {e}", fg='red')
        sys.exit(1)


if __name__ == "__main__":
    cli()
