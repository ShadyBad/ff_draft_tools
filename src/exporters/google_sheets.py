"""Google Sheets exporter for Fantasy Football rankings"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import time

import gspread
from google.oauth2 import service_account
from google.auth.exceptions import GoogleAuthError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.core.models import ConsensusRanking
from config import GOOGLE_SHEETS_SCOPES, SERVICE_ACCOUNT_FILE, DEFAULT_SETTINGS


logger = logging.getLogger(__name__)


class GoogleSheetsExporter:
    """Export rankings to Google Sheets with live updates"""
    
    def __init__(self):
        self.client = None
        self.drive_service = None
        self.sheets_service = None
        self.authenticated = False
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Sheets API"""
        try:
            # Try service account first
            if os.path.exists(SERVICE_ACCOUNT_FILE):
                logger.info("Authenticating with service account")
                creds = service_account.Credentials.from_service_account_file(
                    SERVICE_ACCOUNT_FILE,
                    scopes=GOOGLE_SHEETS_SCOPES
                )
                self.authenticated = True
            else:
                # Try from environment variable
                service_account_info = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
                if service_account_info:
                    logger.info("Authenticating with environment variable")
                    account_info = json.loads(service_account_info)
                    creds = service_account.Credentials.from_service_account_info(
                        account_info,
                        scopes=GOOGLE_SHEETS_SCOPES
                    )
                    self.authenticated = True
                else:
                    logger.warning("No Google Sheets authentication found")
                    return
            
            # Initialize clients
            self.client = gspread.authorize(creds)
            self.drive_service = build('drive', 'v3', credentials=creds)
            self.sheets_service = build('sheets', 'v4', credentials=creds)
            
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Sheets: {e}")
            self.authenticated = False
    
    def is_authenticated(self) -> bool:
        """Check if authenticated with Google"""
        return self.authenticated
    
    def create_draft_sheet(self, title: str = None, folder_id: str = None) -> Optional[str]:
        """Create a new draft sheet with formatting"""
        if not self.authenticated:
            logger.error("Not authenticated with Google Sheets")
            return None
        
        try:
            # Generate title with timestamp
            if not title:
                title = f"FF Draft Rankings - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # Create spreadsheet
            spreadsheet = self.client.create(title)
            sheet_id = spreadsheet.id
            
            # Move to folder if specified
            if folder_id:
                self._move_to_folder(sheet_id, folder_id)
            
            # Set up sheets structure
            self._setup_sheet_structure(spreadsheet)
            
            # Make it accessible by link
            self._set_sharing_permissions(sheet_id)
            
            logger.info(f"Created Google Sheet: {title} (ID: {sheet_id})")
            return sheet_id
            
        except Exception as e:
            logger.error(f"Failed to create Google Sheet: {e}")
            return None
    
    def update_rankings(self, sheet_id: str, rankings: List[ConsensusRanking], 
                       sheet_name: str = "Overall Rankings") -> bool:
        """Update rankings in Google Sheet"""
        if not self.authenticated:
            logger.error("Not authenticated with Google Sheets")
            return False
        
        try:
            # Open spreadsheet
            spreadsheet = self.client.open_by_key(sheet_id)
            
            # Get or create worksheet
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                worksheet.clear()
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(sheet_name, rows=len(rankings)+10, cols=20)
            
            # Prepare data
            headers = self._get_headers(rankings)
            rows = self._prepare_ranking_rows(rankings)
            
            # Update in batch
            all_data = [headers] + rows
            worksheet.update('A1', all_data)
            
            # Apply formatting
            self._format_worksheet(spreadsheet, worksheet, len(rankings))
            
            logger.info(f"Updated {len(rankings)} rankings in sheet {sheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update rankings: {e}")
            return False
    
    def update_by_position(self, sheet_id: str, rankings: List[ConsensusRanking]) -> bool:
        """Create/update separate sheets for each position"""
        if not self.authenticated:
            return False
        
        try:
            # Group by position
            by_position = {}
            for ranking in rankings:
                pos = ranking.player.position.value
                if pos not in by_position:
                    by_position[pos] = []
                by_position[pos].append(ranking)
            
            # Update each position sheet
            for position, position_rankings in by_position.items():
                self.update_rankings(sheet_id, position_rankings, f"{position} Rankings")
                time.sleep(0.5)  # Rate limiting
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update position sheets: {e}")
            return False
    
    def create_cheat_sheet(self, sheet_id: str, rankings: List[ConsensusRanking]) -> bool:
        """Create a printable cheat sheet"""
        if not self.authenticated:
            return False
        
        try:
            spreadsheet = self.client.open_by_key(sheet_id)
            
            # Create or update cheat sheet
            try:
                worksheet = spreadsheet.worksheet("Cheat Sheet")
                worksheet.clear()
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet("Cheat Sheet", rows=300, cols=10)
            
            # Prepare cheat sheet data
            headers = ["Rank", "Player", "Pos", "Team", "Bye", "Tier", "ADP", "Drafted"]
            rows = []
            
            for i, ranking in enumerate(rankings[:250], 1):  # Top 250
                row = [
                    i,
                    ranking.player.name,
                    ranking.player.position.value,
                    ranking.player.team.value,
                    ranking.player.bye_week or "",
                    ranking.tier,
                    getattr(ranking, 'adp', i),
                    ""  # Drafted column for manual marking
                ]
                rows.append(row)
            
            # Update sheet
            all_data = [headers] + rows
            worksheet.update('A1', all_data)
            
            # Format for printing
            self._format_cheat_sheet(spreadsheet, worksheet, len(rows))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create cheat sheet: {e}")
            return False
    
    def enable_live_draft_mode(self, sheet_id: str) -> bool:
        """Enable features for live draft tracking"""
        if not self.authenticated:
            return False
        
        try:
            spreadsheet = self.client.open_by_key(sheet_id)
            
            # Add draft board sheet
            try:
                draft_board = spreadsheet.worksheet("Draft Board")
            except gspread.WorksheetNotFound:
                draft_board = spreadsheet.add_worksheet("Draft Board", rows=300, cols=20)
            
            # Set up draft board structure
            headers = ["Pick", "Round", "Team", "Player", "Position", "ADP vs Pick"]
            draft_board.update('A1:F1', [headers])
            
            # Add conditional formatting for value picks
            self._add_draft_board_formatting(spreadsheet, draft_board)
            
            # Add instructions sheet
            self._add_instructions_sheet(spreadsheet)
            
            logger.info("Enabled live draft mode")
            return True
            
        except Exception as e:
            logger.error(f"Failed to enable live draft mode: {e}")
            return False
    
    def _get_headers(self, rankings: List[ConsensusRanking]) -> List[str]:
        """Get headers based on available data"""
        headers = ["Rank", "Player", "Position", "Team", "Bye", "Tier"]
        
        # Check for additional fields
        if rankings and len(rankings) > 0:
            sample = rankings[0]
            if hasattr(sample, 'vorp') and sample.vorp is not None:
                headers.append("VORP")
            if sample.projected_points is not None:
                headers.append("Proj Pts")
            if hasattr(sample, 'adp'):
                headers.append("ADP")
            headers.extend(["Avg Rank", "Sources", "Notes"])
        
        return headers
    
    def _prepare_ranking_rows(self, rankings: List[ConsensusRanking]) -> List[List[Any]]:
        """Prepare ranking data for sheets"""
        rows = []
        
        for i, ranking in enumerate(rankings, 1):
            row = [
                i,
                ranking.player.name,
                ranking.player.position.value,
                ranking.player.team.value,
                ranking.player.bye_week or "",
                ranking.tier
            ]
            
            # Add optional fields
            if hasattr(ranking, 'vorp') and ranking.vorp is not None:
                row.append(round(ranking.vorp, 1))
                
            if ranking.projected_points is not None:
                row.append(round(ranking.projected_points, 1))
                
            if hasattr(ranking, 'adp'):
                row.append(round(getattr(ranking, 'adp', i), 1))
            
            # Add standard fields
            row.extend([
                round(ranking.avg_rank, 1),
                len(ranking.sources),
                ranking.notes or ""
            ])
            
            rows.append(row)
        
        return rows
    
    def _format_worksheet(self, spreadsheet, worksheet, num_rows: int):
        """Apply formatting to worksheet"""
        try:
            requests = []
            sheet_id = worksheet.id
            
            # Header formatting
            requests.append({
                'repeatCell': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 0,
                        'endRowIndex': 1
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': {'red': 0.2, 'green': 0.3, 'blue': 0.5},
                            'textFormat': {
                                'foregroundColor': {'red': 1, 'green': 1, 'blue': 1},
                                'bold': True
                            }
                        }
                    },
                    'fields': 'userEnteredFormat'
                }
            })
            
            # Freeze header row
            requests.append({
                'updateSheetProperties': {
                    'properties': {
                        'sheetId': sheet_id,
                        'gridProperties': {
                            'frozenRowCount': 1
                        }
                    },
                    'fields': 'gridProperties.frozenRowCount'
                }
            })
            
            # Tier-based coloring (alternating colors)
            tier_colors = [
                {'red': 0.85, 'green': 0.92, 'blue': 0.83},  # Light green
                {'red': 0.95, 'green': 0.95, 'blue': 0.80},  # Light yellow
                {'red': 1.0, 'green': 0.90, 'blue': 0.80},   # Light orange
                {'red': 1.0, 'green': 0.85, 'blue': 0.85},   # Light red
                {'red': 0.90, 'green': 0.90, 'blue': 0.90}   # Light gray
            ]
            
            # Apply tier coloring
            current_tier = 1
            start_row = 1
            
            for i in range(1, num_rows + 1):
                # Check if tier changed (would need tier data)
                # For now, apply alternating colors every 10 rows
                if i % 10 == 0:
                    color_idx = min(current_tier - 1, len(tier_colors) - 1)
                    requests.append({
                        'repeatCell': {
                            'range': {
                                'sheetId': sheet_id,
                                'startRowIndex': start_row,
                                'endRowIndex': i + 1,
                                'startColumnIndex': 0,
                                'endColumnIndex': 1
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'backgroundColor': tier_colors[color_idx]
                                }
                            },
                            'fields': 'userEnteredFormat.backgroundColor'
                        }
                    })
                    current_tier += 1
                    start_row = i + 1
            
            # Column widths
            requests.append({
                'autoResizeDimensions': {
                    'dimensions': {
                        'sheetId': sheet_id,
                        'dimension': 'COLUMNS',
                        'startIndex': 0,
                        'endIndex': 15
                    }
                }
            })
            
            # Execute formatting
            if requests:
                body = {'requests': requests}
                self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet.id,
                    body=body
                ).execute()
                
        except Exception as e:
            logger.warning(f"Failed to apply formatting: {e}")
    
    def _format_cheat_sheet(self, spreadsheet, worksheet, num_rows: int):
        """Format cheat sheet for printing"""
        try:
            sheet_id = worksheet.id
            requests = []
            
            # Compact formatting for printing
            requests.append({
                'updateSheetProperties': {
                    'properties': {
                        'sheetId': sheet_id,
                        'gridProperties': {
                            'rowCount': num_rows + 5,
                            'columnCount': 8
                        }
                    },
                    'fields': 'gridProperties'
                }
            })
            
            # Set print settings
            requests.append({
                'updateSheetProperties': {
                    'properties': {
                        'sheetId': sheet_id,
                        'pageBreakPreview': True
                    },
                    'fields': 'pageBreakPreview'
                }
            })
            
            # Apply requests
            if requests:
                body = {'requests': requests}
                self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet.id,
                    body=body
                ).execute()
                
        except Exception as e:
            logger.warning(f"Failed to format cheat sheet: {e}")
    
    def _add_draft_board_formatting(self, spreadsheet, worksheet):
        """Add conditional formatting to draft board"""
        try:
            sheet_id = worksheet.id
            
            # Conditional formatting for value picks (ADP vs actual pick)
            request = {
                'addConditionalFormatRule': {
                    'rule': {
                        'ranges': [{
                            'sheetId': sheet_id,
                            'startRowIndex': 1,
                            'startColumnIndex': 5,
                            'endColumnIndex': 6
                        }],
                        'gradientRule': {
                            'minpoint': {
                                'color': {'red': 0.8, 'green': 0.2, 'blue': 0.2},
                                'type': 'MIN'
                            },
                            'maxpoint': {
                                'color': {'red': 0.2, 'green': 0.8, 'blue': 0.2},
                                'type': 'MAX'
                            }
                        }
                    }
                }
            }
            
            self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet.id,
                body={'requests': [request]}
            ).execute()
            
        except Exception as e:
            logger.warning(f"Failed to add draft board formatting: {e}")
    
    def _add_instructions_sheet(self, spreadsheet):
        """Add instructions for using the draft sheet"""
        try:
            worksheet = spreadsheet.add_worksheet("Instructions", rows=20, cols=5)
            
            instructions = [
                ["Fantasy Football Draft Sheet Instructions"],
                [""],
                ["Sheets Overview:"],
                ["- Overall Rankings: All players ranked by consensus"],
                ["- Position Rankings: Separate sheets for each position"],
                ["- Cheat Sheet: Printable format with draft tracking"],
                ["- Draft Board: Track picks during your draft"],
                [""],
                ["How to Use:"],
                ["1. During draft, mark players as 'Drafted' in Cheat Sheet"],
                ["2. Use Draft Board to track actual picks vs ADP"],
                ["3. Green = value pick, Red = reach"],
                ["4. Sheets auto-save all changes"],
                [""],
                ["Tips:"],
                ["- Sort by VORP to see cross-positional value"],
                ["- Check bye weeks to avoid conflicts"],
                ["- Monitor tiers to avoid positional runs"],
                [""],
                ["Created by FF Draft Tools"]
            ]
            
            # Update with instructions
            worksheet.update('A1', instructions)
            
            # Format
            worksheet.format('A1', {
                'textFormat': {'bold': True, 'fontSize': 14}
            })
            
        except Exception as e:
            logger.warning(f"Failed to add instructions: {e}")
    
    def _move_to_folder(self, file_id: str, folder_id: str):
        """Move file to specific folder"""
        try:
            # Get current parents
            file = self.drive_service.files().get(
                fileId=file_id,
                fields='parents'
            ).execute()
            
            previous_parents = ",".join(file.get('parents', []))
            
            # Move file
            self.drive_service.files().update(
                fileId=file_id,
                addParents=folder_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            
        except Exception as e:
            logger.warning(f"Failed to move file to folder: {e}")
    
    def _set_sharing_permissions(self, sheet_id: str):
        """Set sharing permissions for the sheet"""
        try:
            # Make it accessible by anyone with link
            permission = {
                'type': 'anyone',
                'role': 'writer',
                'allowFileDiscovery': False
            }
            
            self.drive_service.permissions().create(
                fileId=sheet_id,
                body=permission
            ).execute()
            
        except Exception as e:
            logger.warning(f"Failed to set sharing permissions: {e}")
    
    def get_sheet_url(self, sheet_id: str) -> str:
        """Get the URL for a sheet"""
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"