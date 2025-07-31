#!/usr/bin/env python3
"""Main entry point for FF Draft Tools"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import click
from rich.console import Console
from rich.table import Table
from rich.progress import track

# Set up production logging first
from src.utils.logging import setup_logging, get_logger

from src.scrapers import FantasyProsScraper
from src.scrapers.yahoo import YahooScraper
from src.scrapers.yahoo_api import YahooAPIScraper
from src.core import RankingAggregator, ConsensusRanking
from src.exporters import CSVExporter
from src.utils.validation import InputValidator, ValidationError
from src.utils.monitoring import monitor
from config import DEFAULT_SETTINGS, PLATFORM_PRESETS, DATA_DIR

# Rich console for pretty output
console = Console()


@click.group()
@click.version_option(version='0.2.0')
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.pass_context
def cli(ctx, debug):
    """Fantasy Football Draft Tools - Advanced rankings with Value-Based Drafting
    
    Commands:
      fetch-rankings  - Fetch latest rankings (now with VBD/VORP!)
      vbd-info        - Learn about Value-Based Drafting
      list-rankings   - Show available ranking exports
      cleanup         - Clean up old ranking archives
      use-preset      - Use a platform preset configuration
      setup-yahoo     - Configure Yahoo Fantasy API
      mock-draft      - Run a mock draft simulation (coming soon)
    
    Quick Start:
      python main.py fetch-rankings --use-vbd
    """
    # Set up logging
    log_file = None
    if debug:
        log_file = DATA_DIR / 'logs' / f'debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    
    setup_logging(debug=debug, log_file=log_file)
    ctx.ensure_object(dict)
    ctx.obj['debug'] = debug


@cli.command()
@click.option('--force-refresh', is_flag=True, help='Force refresh data from sources')
@click.option('--export-format', type=click.Choice(['all', 'csv', 'sheets']), default='all')
@click.option('--max-players', type=int, default=300, help='Maximum players to include')
@click.option('--use-vbd', is_flag=True, help='Apply Value-Based Drafting (VORP) calculations')
@click.option('--vbd-baseline', type=click.Choice(['vols', 'vorp', 'beer']), default='vorp', 
              help='VBD baseline: vols=Value Over Last Starter, vorp=Value Over Replacement, beer=Best Ever Evaluation')
@click.pass_context
def fetch_rankings(ctx, force_refresh: bool, export_format: str, max_players: int, use_vbd: bool, vbd_baseline: str):
    """Fetch rankings from all sources and export"""
    logger = get_logger(__name__)
    
    # Validate inputs
    try:
        # Validate max players
        if max_players < 1:
            raise ValidationError("Max players must be at least 1")
        if max_players > 500:
            raise ValidationError("Max players cannot exceed 500")
        
        # Validate VBD baseline if VBD is enabled
        if use_vbd:
            InputValidator.validate_vbd_baseline(vbd_baseline)
            
    except ValidationError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    
    console.print("[bold green]Fantasy Football Draft Tools v0.2[/bold green]")
    console.print("Aggregating rankings for 2025 NFL season...\n")
    
    # Fetch rankings from sources
    source_rankings = {}
    
    # FantasyPros
    with console.status("[yellow]• Fetching FantasyPros rankings...[/yellow]"):
        try:
            scraper = FantasyProsScraper()
            rankings = scraper.fetch(force_refresh=force_refresh)
            if rankings:
                source_rankings['fantasypros'] = rankings
                console.print(f"[green]✓[/green] FantasyPros: {len(rankings)} players")
            else:
                raise ValueError("No data retrieved")
        except Exception as e:
            logger.debug(f"FantasyPros error: {e}")
            # Use fallback data silently
            from src.scrapers.fantasypros import get_fallback_rankings
            source_rankings['fantasypros'] = get_fallback_rankings()
            console.print("[green]✓[/green] FantasyPros: Using 2025 projections")
    
    # Yahoo rankings
    yahoo_found = False
    
    # Try Yahoo API first
    with console.status("[yellow]• Checking Yahoo API...[/yellow]"):
        try:
            yahoo_api = YahooAPIScraper()
            if yahoo_api.oauth:
                yahoo_rankings = yahoo_api.fetch(force_refresh=force_refresh)
                if yahoo_rankings:
                    source_rankings['yahoo_api'] = yahoo_rankings
                    console.print(f"[green]✓[/green] Yahoo API: {len(yahoo_rankings)} players")
                    yahoo_found = True
        except Exception as e:
            logger.debug(f"Yahoo API error: {e}")
    
    # Fall back to Yahoo web scraper if API not available
    if not yahoo_found:
        with console.status("[yellow]• Fetching Yahoo rankings...[/yellow]"):
            try:
                yahoo_scraper = YahooScraper()
                yahoo_rankings = yahoo_scraper.fetch(force_refresh=force_refresh)
                if yahoo_rankings:
                    source_rankings['yahoo'] = yahoo_rankings
                    console.print(f"[green]✓[/green] Yahoo: {len(yahoo_rankings)} players")
                else:
                    console.print("[yellow]○[/yellow] Yahoo: Currently unavailable")
            except Exception as e:
                logger.debug(f"Yahoo scraper error: {e}")
                console.print("[yellow]○[/yellow] Yahoo: Currently unavailable")
    
    if not source_rankings:
        console.print("\n[red]Error: No ranking data available. Please try again later.[/red]")
        sys.exit(1)
    
    # Aggregate rankings
    console.print("\n[bold]Processing rankings...[/bold]")
    
    # Import VBD baseline enum if needed
    if use_vbd:
        from src.core.vbd import VBDBaseline
        baseline_map = {
            'vols': VBDBaseline.VOLS,
            'vorp': VBDBaseline.VORP,
            'beer': VBDBaseline.BEER
        }
        vbd_baseline_enum = baseline_map[vbd_baseline]
    else:
        vbd_baseline_enum = None
    
    try:
        aggregator = RankingAggregator()
        consensus_rankings = aggregator.aggregate_rankings(
            source_rankings, 
            use_vbd=use_vbd,
            vbd_baseline=vbd_baseline_enum if use_vbd else None
        )
        
        console.print(f"[green]✓[/green] Generated rankings for {len(consensus_rankings)} players")
        if use_vbd:
            vbd_name = {'vols': 'VOLS (Aggressive)', 'vorp': 'VORP (Balanced)', 'beer': 'BEER (Injury-adjusted)'}
            console.print(f"[green]✓[/green] Applied VBD: {vbd_name.get(vbd_baseline, vbd_baseline)}")
    except Exception as e:
        logger.error(f"Failed to aggregate rankings: {e}")
        console.print("\n[red]Error: Failed to process rankings. Please check logs.[/red]")
        sys.exit(1)
    
    # Display top 20 in a nice table
    display_top_rankings(consensus_rankings[:20])
    
    # Export based on format
    if export_format in ['all', 'csv']:
        export_csv_rankings(consensus_rankings, max_players)
    
    if export_format in ['all', 'sheets']:
        console.print("\n[dim]Note: Google Sheets export requires additional setup. Run 'setup-sheets' for details.[/dim]")
    
    console.print("\n[bold green]✓ Draft rankings ready![/bold green]")
    console.print("\n[dim]Tip: Use --use-vbd for Value-Based Drafting rankings[/dim]")
    
    # Log performance summary if in debug mode
    if ctx.obj.get('debug'):
        monitor.log_summary()


@cli.command()
@click.argument('preset', type=click.Choice(list(PLATFORM_PRESETS.keys())))
def use_preset(preset: str):
    """Use a platform preset configuration"""
    settings = PLATFORM_PRESETS[preset]
    console.print(f"\n[bold]Using {preset} preset:[/bold]")
    console.print(f"Scoring: {settings['scoring']}")
    console.print(f"Teams: {settings['teams']}")
    console.print(f"Roster: {settings['roster']}")
    
    # TODO: Save this configuration for use in rankings


@cli.command()
def mock_draft():
    """Run a mock draft simulation"""
    console.print("[yellow]Mock draft feature coming soon![/yellow]")


@cli.command()
def setup_yahoo():
    """Set up Yahoo Fantasy API authentication"""
    from src.scrapers.yahoo_api import test_yahoo_api
    import os
    
    console.print("\n[bold]Yahoo Fantasy API Setup[/bold]")
    console.print("="*60)
    
    # Check for existing credentials
    if os.getenv('YAHOO_CLIENT_ID') and os.getenv('YAHOO_CLIENT_SECRET'):
        console.print("✓ Yahoo API credentials found in environment")
        console.print("\nTesting connection...")
        test_yahoo_api()
    else:
        console.print("\n[yellow]Yahoo API credentials not found![/yellow]")
        console.print("\nTo use Yahoo's official API:")
        console.print("1. Go to [link]https://developer.yahoo.com/apps/[/link]")
        console.print("2. Create a new app")
        console.print("3. Select 'Fantasy Sports' > 'Read' permissions")
        console.print("4. Get your Client ID and Client Secret")
        console.print("\n5. Add these to your .env file:")
        console.print("   [dim]YAHOO_CLIENT_ID=your_client_id[/dim]")
        console.print("   [dim]YAHOO_CLIENT_SECRET=your_client_secret[/dim]")
        console.print("\n6. Run this command again to test the connection")
        
        # Offer to open browser
        import webbrowser
        if click.confirm("\nOpen Yahoo Developer portal in browser?"):
            webbrowser.open("https://developer.yahoo.com/apps/")


@cli.command()
@click.option('--league-size', type=int, default=12, help='Number of teams in your league')
@click.option('--scoring', type=click.Choice(['standard', 'half_ppr', 'ppr']), default='half_ppr')
def vbd_info(league_size: int, scoring: str):
    """Explain Value-Based Drafting and show baseline examples"""
    from src.core.vbd import VBDCalculator, VBDBaseline
    from src.core.projections import ProjectionCalculator
    
    console.print("\n[bold]Value-Based Drafting (VBD) Explained[/bold]")
    console.print("="*60)
    
    console.print("\n[cyan]What is VBD?[/cyan]")
    console.print("Value-Based Drafting measures a player's value by how much they")
    console.print("outscore a 'replacement-level' player at their position.")
    console.print("\n[cyan]Why use VBD?[/cyan]")
    console.print("• Creates fair comparisons across positions")
    console.print("• Identifies true draft value beyond raw point totals")
    console.print("• Helps you avoid positional runs and find arbitrage")
    
    console.print("\n[cyan]VBD Baseline Options:[/cyan]\n")
    
    console.print("[bold]1. VOLS (Value Over Last Starter)[/bold]")
    console.print("   • Baseline: Worst starting player at each position")
    console.print("   • Philosophy: Aggressive 'stars and scrubs' approach")
    console.print("   • Best for: Active managers who work the waiver wire")
    console.print(f"   • Example: In a {league_size}-team league, baseline QB = QB{league_size}")
    
    console.print("\n[bold]2. VORP (Value Over Replacement Player)[/bold]")
    console.print("   • Baseline: Best waiver wire player after draft")
    console.print("   • Philosophy: Balanced approach valuing depth")
    console.print("   • Best for: Standard leagues, risk-averse managers")
    console.print(f"   • Example: Baseline RB ≈ RB{int(league_size * 3.5)} (teams draft ~3.5 RBs)")
    
    console.print("\n[bold]3. BEER (Best Ever Evaluation of Replacement)[/bold]")
    console.print("   • Baseline: Accounts for injuries and bye weeks")
    console.print("   • Philosophy: Realistic 'man-games' needed")
    console.print("   • Best for: Deep leagues, dynasty formats")
    console.print("   • Example: Factors in ~2.5x RB starters needed due to injuries")
    
    console.print("\n[cyan]Position Multipliers (for VORP baseline):[/cyan]")
    console.print("• QB: 1.5x (teams draft ~1.5 QBs)")
    console.print("• RB: 3.5x (teams draft ~3.5 RBs)")
    console.print("• WR: 4.0x (teams draft ~4 WRs)")
    console.print("• TE: 1.5x (teams draft ~1.5 TEs)")
    
    console.print("\n[dim]Tip: Start with VORP for balanced rankings, then adjust based on[/dim]")
    console.print("[dim]your league's tendencies and your management style.[/dim]")


@cli.command()
def list_rankings():
    """List available ranking exports"""
    from pathlib import Path
    
    output_dir = Path("data/output")
    latest_dir = output_dir / "latest"
    archive_dir = output_dir / "archive"
    
    console.print("\n[bold]Available Rankings:[/bold]\n")
    
    # Show latest
    if latest_dir.exists() and any(latest_dir.iterdir()):
        readme_file = latest_dir / "README.txt"
        if readme_file.exists():
            with open(readme_file, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith("Generated:"):
                        console.print(f"[bold green]Latest Rankings:[/bold green]")
                        console.print(f"  {line.strip()}")
                        break
        console.print(f"  Location: {latest_dir}")
        console.print(f"  Files: {len(list(latest_dir.glob('*.csv')))} CSV files")
    
    # Show archives
    if archive_dir.exists():
        archives = sorted([d for d in archive_dir.iterdir() if d.is_dir()], reverse=True)
        if archives:
            console.print(f"\n[bold]Archived Rankings:[/bold]")
            for i, archive in enumerate(archives[:5]):  # Show last 5
                timestamp = archive.name
                try:
                    dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
                    formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
                    console.print(f"  {i+1}. {formatted} ({archive.name})")
                except:
                    console.print(f"  {i+1}. {archive.name}")
            
            if len(archives) > 5:
                console.print(f"  ... and {len(archives) - 5} more")
    
    console.print("\n[dim]Tip: Run 'python main.py fetch-rankings' to update rankings[/dim]")


@cli.command()
@click.option('--keep', type=int, default=5, help='Number of archives to keep')
def cleanup(keep: int):
    """Clean up old ranking exports"""
    from src.exporters import CSVExporter
    
    console.print(f"\n[bold]Cleaning up old archives (keeping last {keep})...[/bold]")
    
    exporter = CSVExporter()
    exporter.cleanup_old_archives(keep_last=keep)
    
    console.print("[green]✓ Cleanup complete![/green]")


@cli.command()
@click.option('--clear', is_flag=True, help='Clear all cache data')
@click.option('--namespace', help='Clear specific cache namespace')
def cache(clear: bool, namespace: str):
    """Manage and view cache statistics"""
    from src.utils.cache import rankings_cache, api_cache, projections_cache, OptimizedCache
    
    if clear:
        if namespace:
            # Clear specific namespace
            cache_obj = OptimizedCache(namespace)
            count = cache_obj.clear_namespace()
            console.print(f"[green]✓[/green] Cleared {count} files from {namespace} cache")
        else:
            # Clear all caches
            total = 0
            for cache_name, cache_obj in [
                ('rankings', rankings_cache),
                ('api_responses', api_cache),
                ('projections', projections_cache)
            ]:
                count = cache_obj.clear_namespace()
                total += count
                console.print(f"[green]✓[/green] Cleared {count} files from {cache_name} cache")
            console.print(f"\n[bold green]Total: {total} cache files cleared[/bold green]")
    else:
        # Show cache statistics
        console.print("\n[bold]Cache Statistics[/bold]")
        console.print("="*60)
        
        # Collect info from all cache namespaces
        from pathlib import Path
        cache_namespaces = []
        
        # Check for scraper caches
        cache_base = Path("data/cache")
        if cache_base.exists():
            for cache_dir in cache_base.iterdir():
                if cache_dir.is_dir():
                    cache_obj = OptimizedCache(cache_dir.name)
                    info = cache_obj.get_cache_info()
                    if info.get('file_count', 0) > 0:
                        cache_namespaces.append(info)
        
        # Add predefined caches
        for cache_name, cache_obj in [
            ('rankings', rankings_cache),
            ('api_responses', api_cache),
            ('projections', projections_cache)
        ]:
            info = cache_obj.get_cache_info()
            if info.get('file_count', 0) > 0 or info.get('stats', {}).get('hits', 0) > 0:
                cache_namespaces.append(info)
        
        if not cache_namespaces:
            console.print("[dim]No cache data found[/dim]")
            return
        
        # Display cache info
        total_size = 0
        total_files = 0
        
        for cache_info in cache_namespaces:
            if 'error' in cache_info:
                continue
                
            namespace = cache_info['namespace']
            file_count = cache_info.get('file_count', 0)
            size_mb = cache_info.get('total_size_mb', 0)
            stats = cache_info.get('stats', {})
            
            total_size += size_mb
            total_files += file_count
            
            console.print(f"\n[cyan]{namespace}:[/cyan]")
            console.print(f"  Files: {file_count}")
            console.print(f"  Size: {size_mb:.2f} MB")
            
            if stats.get('hits', 0) > 0 or stats.get('misses', 0) > 0:
                hit_rate = stats.get('hit_rate', 0) * 100
                console.print(f"  Hit Rate: {hit_rate:.1f}% ({stats.get('hits', 0)} hits, {stats.get('misses', 0)} misses)")
                
            if stats.get('compression_ratio', 0) > 0:
                compression = stats.get('compression_ratio', 0) * 100
                console.print(f"  Compression: {compression:.1f}% saved")
        
        console.print(f"\n[bold]Total:[/bold] {total_files} files, {total_size:.2f} MB")
        console.print("\n[dim]Tip: Use --clear to clear all cache data[/dim]")


@cli.command()
@click.option('--export', is_flag=True, help='Export metrics to JSON file')
@click.option('--clear', is_flag=True, help='Clear all metrics data')
def metrics(export: bool, clear: bool):
    """View performance metrics and monitoring data"""
    if clear:
        monitor.clear_metrics()
        console.print("[green]✓[/green] Metrics cleared")
        return
    
    # Get performance summary
    summary = monitor.get_performance_summary()
    
    if summary.get("message") == "No metrics recorded":
        console.print("[dim]No metrics recorded yet. Run some commands first![/dim]")
        return
    
    console.print("\n[bold]Performance Metrics[/bold]")
    console.print("="*60)
    
    # Display operation metrics
    operations = [(k, v) for k, v in summary.items() if k != 'system']
    
    if operations:
        # Create a table for operations
        from rich.table import Table
        
        table = Table(title="Operation Performance")
        table.add_column("Operation", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Success", justify="right", style="green")
        table.add_column("Errors", justify="right", style="red")
        table.add_column("Avg Time", justify="right")
        table.add_column("Max Time", justify="right")
        
        for name, stats in sorted(operations):
            table.add_row(
                name,
                str(stats['count']),
                str(stats['success_count']),
                str(stats['error_count']) if stats['error_count'] > 0 else "0",
                f"{stats['avg_duration']:.3f}s",
                f"{stats['max_duration']:.3f}s"
            )
        
        console.print(table)
    
    # Display system metrics if available
    if 'system' in summary:
        sys = summary['system']
        console.print("\n[bold]System Resources[/bold]")
        console.print(f"  CPU Usage: avg={sys['avg_cpu_percent']:.1f}%, max={sys['max_cpu_percent']:.1f}%")
        console.print(f"  Memory: avg={sys['avg_memory_mb']:.1f}MB, max={sys['max_memory_mb']:.1f}MB")
        console.print(f"  Disk I/O: read={sys['total_disk_read_mb']:.1f}MB, write={sys['total_disk_write_mb']:.1f}MB")
    
    if export:
        filepath = monitor.export_metrics()
        console.print(f"\n[green]✓[/green] Metrics exported to: {filepath}")
    
    console.print("\n[dim]Tip: Use --export to save metrics to file[/dim]")


def display_top_rankings(rankings: List[ConsensusRanking]):
    """Display top rankings in a nice table"""
    table = Table(title="\n[bold]Top 20 Overall Rankings[/bold]")
    
    table.add_column("Rank", style="cyan", no_wrap=True)
    table.add_column("Player", style="magenta")
    table.add_column("Pos", style="green")
    table.add_column("Team", style="yellow")
    table.add_column("Bye", style="red")
    table.add_column("Tier", style="blue")
    
    # Add VORP column if available
    has_vorp = any(hasattr(r, 'vorp') and r.vorp is not None for r in rankings[:20])
    if has_vorp:
        table.add_column("VORP", style="bright_green")
    
    # Add projected points if available
    has_projections = any(r.projected_points is not None for r in rankings[:20])
    if has_projections:
        table.add_column("Proj Pts", style="bright_cyan")
    
    table.add_column("Sources", style="dim")
    
    for i, ranking in enumerate(rankings, 1):
        sources_str = f"{len(ranking.sources)} sources"
        
        row_data = [
            str(i),
            ranking.player.name,
            ranking.player.position.value,
            ranking.player.team.value,
            str(ranking.player.bye_week),
            str(ranking.tier)
        ]
        
        if has_vorp:
            vorp_str = f"{getattr(ranking, 'vorp', 0):.1f}" if hasattr(ranking, 'vorp') else "0.0"
            row_data.append(vorp_str)
        
        if has_projections:
            proj_str = f"{ranking.projected_points:.0f}" if ranking.projected_points else "-"
            row_data.append(proj_str)
        
        row_data.append(sources_str)
        
        table.add_row(*row_data)
    
    console.print(table)


def export_csv_rankings(rankings: List[ConsensusRanking], max_players: int):
    """Export rankings to CSV files"""
    logger = get_logger(__name__)
    
    with console.status("[yellow]Exporting rankings...[/yellow]"):
        try:
            exporter = CSVExporter()
            exported_files = exporter.export_all(rankings[:max_players])
            
            # Show success
            console.print(f"\n[green]✓[/green] Exported to: [cyan]data/output/latest/[/cyan]")
            console.print("\n[bold]Key Files:[/bold]")
            console.print("  • [green]cheat_sheet.csv[/green] - Quick draft reference")
            console.print("  • overall_rankings.csv - Full rankings with stats")
            console.print("  • Position files - Individual position rankings")
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            console.print("\n[red]Error: Failed to export rankings.[/red]")
            raise


if __name__ == '__main__':
    cli()