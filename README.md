# Fantasy Football Draft Tools

A Python tool that aggregates fantasy football rankings from multiple expert sources for the 2025 NFL season, calculates consensus rankings with advanced Value-Based Drafting (VBD), and exports them to various formats including Google Sheets for your draft day.

## Features

- 🏈 **Multi-Source Rankings**: Aggregates data from FantasyPros and Yahoo (more sources coming soon)
- 📊 **Value-Based Drafting (VBD)**: Calculate VORP with multiple baseline methodologies
- 🎯 **Cross-Positional Value**: Fair comparison of players across all positions
- 📈 **Tier-Based Analysis**: Players grouped into value tiers
- 💰 **Projected Points**: Fantasy point projections for all players
- 📑 **Multiple Export Formats**: CSV with VORP values and Google Sheets
- 🎮 **Draft Day Optimized**: Fast, offline-capable, mobile-friendly
- ⚙️ **Customizable**: Support for PPR, Half-PPR, and Standard scoring

## Quick Start

### Prerequisites

- Python 3.8+
- Google Cloud account (for Google Sheets export)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ff_draft_tools.git
cd ff_draft_tools
```

2. Set up the project:
```bash
make setup
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Fetch rankings and create draft sheets:
```bash
make run
```

Your rankings will be exported to:
- `data/output/latest/` - Always contains the most recent rankings
- `data/output/archive/` - Timestamped folders with historical rankings

## Usage

### Basic Commands

```bash
# Fetch latest rankings with Value-Based Drafting
python main.py fetch-rankings --use-vbd

# Use different VBD baselines
python main.py fetch-rankings --use-vbd --vbd-baseline vols  # Aggressive approach
python main.py fetch-rankings --use-vbd --vbd-baseline vorp  # Balanced (default)
python main.py fetch-rankings --use-vbd --vbd-baseline beer  # Injury-adjusted

# Learn about Value-Based Drafting
python main.py vbd-info

# Force refresh (ignore cache)
python main.py fetch-rankings --force-refresh --use-vbd

# Use a platform preset
python main.py use-preset yahoo_half_ppr

# List available rankings
python main.py list-rankings

# Clean up old archives (keep last 5)
python main.py cleanup --keep 5
```

### Export Formats

The tool generates multiple CSV files:

1. **Overall Rankings** - All players with consensus rankings, VORP, and projections
2. **Position Rankings** - Separate files for each position with VORP values
3. **Cheat Sheet** - Condensed draft reference with VORP for quick decisions
4. **Tier Rankings** - Players grouped by position and tier

### Value-Based Drafting (VBD)

VBD helps you make better draft decisions by comparing players across positions:

- **VORP (Value Over Replacement Player)**: How many points a player scores above a replacement-level player
- **Multiple Baselines**: Choose between VOLS (aggressive), VORP (balanced), or BEER (injury-adjusted)
- **Cross-Positional Rankings**: See why that elite RB might be worth more than a top QB

### Google Sheets Integration

To enable Google Sheets export:

1. Create a Google Cloud service account
2. Download the credentials JSON file
3. Place it in `credentials/service_account.json`
4. Share your target Google Sheet with the service account email

## Configuration

### League Settings

Edit `config.py` to customize:

- Scoring system (PPR, Half-PPR, Standard)
- Roster requirements
- Number of teams
- Tier sizes

### Platform Presets

Built-in configurations for popular platforms:

- `espn_standard` - 10 team standard scoring
- `yahoo_half_ppr` - 12 team half-PPR
- `sleeper_ppr` - 12 team full PPR

## Development

### Project Structure

```
ff_draft_tools/
├── src/
│   ├── scrapers/      # Data source scrapers
│   ├── core/          # Core logic (models, aggregation)
│   ├── exporters/     # Export to various formats
│   └── web/           # Web interface (coming soon)
├── data/
│   ├── cache/         # Cached rankings
│   └── output/        # Generated files
├── tests/             # Test files
├── config.py          # Configuration
└── main.py            # CLI entry point
```

### Running Tests

```bash
make test
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## Roadmap

- [x] FantasyPros scraper
- [x] Consensus ranking algorithm
- [x] CSV export
- [x] Value-Based Drafting (VBD/VORP)
- [x] Multiple VBD baselines (VOLS, VORP, BEER)
- [x] Fantasy point projections
- [x] Yahoo API integration
- [ ] Google Sheets live sync
- [ ] Risk analysis (uncertainty & volatility)
- [ ] Monte Carlo draft simulator
- [ ] Portfolio optimization
- [ ] Web interface
- [ ] Trade analyzer
- [ ] Keeper/Dynasty support

## License

MIT License - see LICENSE file for details

## Disclaimer

This tool is for educational and personal use. Be respectful of data sources and their terms of service. The tool includes rate limiting and caching to minimize server load.