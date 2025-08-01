"""CSV exporter for rankings"""
import csv
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from src.core.models import ConsensusRanking, Position
from config import OUTPUT_DIR
from .value_sheet import ValueSheetExporter


logger = logging.getLogger(__name__)


class CSVExporter:
    """Export rankings to CSV format"""
    
    def __init__(self):
        self.output_dir = OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a 'latest' directory for most recent exports
        self.latest_dir = self.output_dir / 'latest'
        self.latest_dir.mkdir(exist_ok=True)
        
        # Create an 'archive' directory for older exports
        self.archive_dir = self.output_dir / 'archive'
        self.archive_dir.mkdir(exist_ok=True)
    
    def _get_export_dir(self) -> Path:
        """Get directory for current export with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = self.archive_dir / timestamp
        export_dir.mkdir(exist_ok=True)
        return export_dir, timestamp
    
    def _copy_to_latest(self, source_file: Path, filename: str) -> None:
        """Copy file to latest directory"""
        dest_file = self.latest_dir / filename
        shutil.copy2(source_file, dest_file)
    
    def export_overall_rankings(self, rankings: List[ConsensusRanking], 
                              export_dir: Path, timestamp: str) -> Path:
        """Export overall rankings to CSV"""
        filename = f"overall_rankings_{timestamp}.csv"
        filepath = export_dir / filename
        
        with open(filepath, 'w', newline='') as csvfile:
            # Build fieldnames dynamically based on available data
            fieldnames = [
                'Rank', 'Tier', 'Player', 'Position', 'Team', 'Bye',
                'Pos Rank'
            ]
            
            # Add VORP if available
            if rankings and hasattr(rankings[0], 'vorp') and rankings[0].vorp is not None:
                fieldnames.append('VORP')
            
            # Add projected points if available  
            if rankings and rankings[0].projected_points is not None:
                fieldnames.append('Proj Pts')
                
            fieldnames.extend([
                'Avg Rank', 'Min Rank', 'Max Rank', 'Variance',
                'Sources', 'Notes'
            ])
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for i, ranking in enumerate(rankings, 1):
                # Format sources as string
                sources_str = ', '.join([
                    f"{source}:{rank}" 
                    for source, rank in sorted(ranking.sources.items())
                ])
                
                row = {
                    'Rank': i,
                    'Tier': ranking.tier,
                    'Player': ranking.player.name,
                    'Position': ranking.player.position.value,
                    'Team': ranking.player.team.value,
                    'Bye': ranking.player.bye_week,
                    'Pos Rank': f"{ranking.player.position.value}{ranking.position_rank}",
                }
                
                # Add VORP if available
                if hasattr(ranking, 'vorp') and ranking.vorp is not None:
                    row['VORP'] = f"{ranking.vorp:.1f}"
                
                # Add projected points if available
                if ranking.projected_points is not None:
                    row['Proj Pts'] = f"{ranking.projected_points:.0f}"
                
                row.update({
                    'Avg Rank': f"{ranking.consensus_rank:.1f}",
                    'Min Rank': ranking.min_rank or '',
                    'Max Rank': ranking.max_rank or '',
                    'Variance': ranking.rank_variance(),
                    'Sources': sources_str,
                    'Notes': ''  # For user to fill in
                })
                
                writer.writerow(row)
        
        # Copy to latest
        self._copy_to_latest(filepath, 'overall_rankings.csv')
        
        logger.info(f"Exported {len(rankings)} overall rankings")
        return filepath
    
    def export_position_rankings(self, rankings: List[ConsensusRanking],
                               export_dir: Path, timestamp: str) -> Dict[Position, Path]:
        """Export separate CSV files for each position"""
        # Group by position
        by_position = {}
        for ranking in rankings:
            pos = ranking.player.position
            if pos not in by_position:
                by_position[pos] = []
            by_position[pos].append(ranking)
        
        exported_files = {}
        
        for position, position_rankings in by_position.items():
            # Sort by consensus rank
            position_rankings.sort(key=lambda x: x.consensus_rank)
            
            filename = f"{position.value}_rankings_{timestamp}.csv"
            filepath = export_dir / filename
            
            with open(filepath, 'w', newline='') as csvfile:
                fieldnames = [
                    'Rank', 'Tier', 'Player', 'Team', 'Bye',
                    'Overall Rank', 'Avg Rank', 'Min Rank', 'Max Rank',
                    'Sources', 'Notes'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for i, ranking in enumerate(position_rankings, 1):
                    sources_str = ', '.join([
                        f"{source}:{rank}" 
                        for source, rank in sorted(ranking.sources.items())
                    ])
                    
                    # Find overall rank
                    overall_rank = next(
                        (j for j, r in enumerate(rankings, 1) if r == ranking),
                        None
                    )
                    
                    row = {
                        'Rank': i,
                        'Tier': ranking.tier,
                        'Player': ranking.player.name,
                        'Team': ranking.player.team.value,
                        'Bye': ranking.player.bye_week,
                        'Overall Rank': overall_rank,
                        'Avg Rank': f"{ranking.consensus_rank:.1f}",
                        'Min Rank': ranking.min_rank or '',
                        'Max Rank': ranking.max_rank or '',
                        'Sources': sources_str,
                        'Notes': ''
                    }
                    
                    writer.writerow(row)
            
            # Copy to latest
            self._copy_to_latest(filepath, f"{position.value}_rankings.csv")
            
            exported_files[position] = filepath
            logger.info(f"Exported {len(position_rankings)} {position.value} rankings")
        
        return exported_files
    
    def export_cheat_sheet(self, rankings: List[ConsensusRanking], 
                          export_dir: Path, timestamp: str,
                          max_players: int = 300) -> Path:
        """Export a condensed cheat sheet for draft day"""
        filename = f"cheat_sheet_{timestamp}.csv"
        filepath = export_dir / filename
        
        # Take top N players
        top_rankings = rankings[:max_players]
        
        with open(filepath, 'w', newline='') as csvfile:
            fieldnames = ['Rank', 'Player', 'Pos', 'Team', 'Bye', 'Tier']
            
            # Add VORP if available
            if top_rankings and hasattr(top_rankings[0], 'vorp') and top_rankings[0].vorp is not None:
                fieldnames.append('VORP')
                
            fieldnames.extend(['ADP', 'Drafted'])
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for i, ranking in enumerate(top_rankings, 1):
                row = {
                    'Rank': i,
                    'Player': ranking.player.name,
                    'Pos': ranking.player.position.value,
                    'Team': ranking.player.team.value,
                    'Bye': ranking.player.bye_week,
                    'Tier': ranking.tier,
                }
                
                # Add VORP if available
                if hasattr(ranking, 'vorp') and ranking.vorp is not None:
                    row['VORP'] = f"{ranking.vorp:.0f}"
                    
                row['ADP'] = f"{ranking.consensus_rank:.0f}"
                row['Drafted'] = ''  # Empty column for draft day marking
                
                writer.writerow(row)
        
        # Copy to latest
        self._copy_to_latest(filepath, 'cheat_sheet.csv')
        
        logger.info(f"Exported cheat sheet with {len(top_rankings)} players")
        return filepath
    
    def export_tier_rankings(self, rankings: List[ConsensusRanking],
                           export_dir: Path, timestamp: str) -> Path:
        """Export rankings grouped by tiers"""
        filename = f"tier_rankings_{timestamp}.csv"
        filepath = export_dir / filename
        
        with open(filepath, 'w', newline='') as csvfile:
            fieldnames = [
                'Position', 'Tier', 'Players'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # Group by position and tier
            tier_groups = {}
            for ranking in rankings:
                key = (ranking.player.position, ranking.tier)
                if key not in tier_groups:
                    tier_groups[key] = []
                tier_groups[key].append(ranking.player.name)
            
            # Sort and write
            for (position, tier), players in sorted(tier_groups.items(), key=lambda x: (x[0][0].value, x[0][1])):
                row = {
                    'Position': position.value,
                    'Tier': tier,
                    'Players': ', '.join(players[:10])  # Limit to 10 per row
                }
                writer.writerow(row)
                
                # If more than 10 players, write additional rows
                for i in range(10, len(players), 10):
                    row = {
                        'Position': '',
                        'Tier': '',
                        'Players': ', '.join(players[i:i+10])
                    }
                    writer.writerow(row)
        
        # Copy to latest
        self._copy_to_latest(filepath, 'tier_rankings.csv')
        
        logger.info(f"Exported tier rankings")
        return filepath
    
    def create_summary_file(self, export_dir: Path, timestamp: str,
                          exported_files: Dict[str, Path]) -> Path:
        """Create a summary file with export information"""
        summary_file = export_dir / 'export_summary.json'
        
        summary = {
            'timestamp': timestamp,
            'datetime': datetime.now().isoformat(),
            'files': {
                name: str(path.name) for name, path in exported_files.items()
            },
            'description': {
                'cheat_sheet': 'Quick reference for draft day (Top 300)',
                'value_sheet': 'Simplified value format with points above baseline',
                'overall': 'Detailed rankings with all stats',
                'tiers': 'Players grouped by position and tier',
                'position_files': 'Separate rankings for each position'
            }
        }
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Also copy to latest
        self._copy_to_latest(summary_file, 'export_summary.json')
        
        # Create a README in latest directory
        readme_path = self.latest_dir / 'README.txt'
        with open(readme_path, 'w') as f:
            f.write("Fantasy Football Draft Tools - Latest Rankings\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("FILES:\n")
            f.write("- cheat_sheet.csv: Quick reference for draft day (print this!)\n")
            f.write("- value_sheet.txt: Simplified value format with points above baseline\n")
            f.write("- overall_rankings.csv: Detailed rankings with variance\n")
            f.write("- tier_rankings.csv: Players grouped by tiers\n")
            f.write("- QB_rankings.csv: Quarterback rankings\n")
            f.write("- RB_rankings.csv: Running back rankings\n")
            f.write("- WR_rankings.csv: Wide receiver rankings\n")
            f.write("- TE_rankings.csv: Tight end rankings\n")
            f.write("- K_rankings.csv: Kicker rankings\n")
            f.write("- DST_rankings.csv: Defense rankings\n\n")
            f.write("For timestamped versions, check the archive folder.\n")
        
        return summary_file
    
    def cleanup_old_archives(self, keep_last: int = 5) -> None:
        """Clean up old archive directories, keeping only the most recent ones"""
        # Get all timestamp directories
        archive_dirs = [d for d in self.archive_dir.iterdir() if d.is_dir()]
        
        # Sort by name (timestamp)
        archive_dirs.sort(reverse=True)
        
        # Keep only the most recent ones
        for old_dir in archive_dirs[keep_last:]:
            try:
                shutil.rmtree(old_dir)
                logger.info(f"Removed old archive: {old_dir.name}")
            except Exception as e:
                logger.warning(f"Could not remove {old_dir}: {e}")
    
    def export_all(self, rankings: List[ConsensusRanking]) -> Dict[str, Path]:
        """Export all formats with organized structure"""
        # Create export directory
        export_dir, timestamp = self._get_export_dir()
        
        # Export all formats
        exported = {
            'overall': self.export_overall_rankings(rankings, export_dir, timestamp),
            'cheat_sheet': self.export_cheat_sheet(rankings, export_dir, timestamp),
            'tiers': self.export_tier_rankings(rankings, export_dir, timestamp)
        }
        
        # Add position files
        position_files = self.export_position_rankings(rankings, export_dir, timestamp)
        for pos, filepath in position_files.items():
            exported[f'position_{pos.value}'] = filepath
        
        # Export value sheet format
        value_exporter = ValueSheetExporter()
        value_sheet_path = value_exporter.export_value_sheet(rankings)
        exported['value_sheet'] = value_sheet_path
        
        # Create summary file
        self.create_summary_file(export_dir, timestamp, exported)
        
        # Clean up old archives
        self.cleanup_old_archives()
        
        # Log summary
        logger.info(f"All rankings exported to {export_dir}")
        logger.info(f"Latest rankings available in {self.latest_dir}")
        
        return exported