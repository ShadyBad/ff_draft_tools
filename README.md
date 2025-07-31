# Fantasy Football Draft Tools

A Python tool that aggregates fantasy football rankings from multiple expert sources for the 2025 NFL season, calculates consensus rankings with advanced Value-Based Drafting (VBD), and exports them to various formats including Google Sheets for your draft day.

## Current Features

### Core Functionality
- 🏈 **Multi-Source Rankings**: Aggregates data from FantasyPros, ESPN, Yahoo, NFL.com, and CBS Sports
- 📊 **Advanced Value-Based Drafting (VBD)**: Three baseline methodologies:
  - VOLS (Value Over Last Starter): Aggressive drafting strategy
  - VORP (Value Over Replacement): Balanced approach
  - BEER (Best Ever Evaluation): Injury-adjusted baselines
- 🎯 **Cross-Positional Value**: Fair VORP-based comparison across all positions
- 📈 **Tier-Based Analysis**: Players grouped into value tiers with customizable breakpoints
- 💰 **Fantasy Point Projections**: Accurate projections for all scoring formats
- 📑 **Multiple Export Formats**: 
  - CSV files with detailed stats
  - Google Sheets with live draft tracking
  - Position-specific rankings
  - Printable cheat sheets
- 🎮 **Draft Day Optimized**: Fast performance, offline-capable, mobile-friendly
- ⚙️ **Highly Customizable**: 
  - PPR, Half-PPR, and Standard scoring systems
  - Platform presets (ESPN, Yahoo, Sleeper)
  - Custom roster configurations
  - Adjustable tier sizes

### Advanced Features
- 🔄 **Smart Caching**: Optimized file-based caching with compression
- 🔍 **Player Name Normalization**: Handles name variations across sources
- 📊 **Consensus Algorithm**: Weighted averaging with source reliability
- 🛡️ **Error Resilience**: Fallback data and graceful degradation
- 📈 **Performance Monitoring**: Built-in metrics and profiling
- 🔐 **Input Validation**: Comprehensive data validation
- 🌐 **Yahoo Fantasy API**: Official API integration for real-time data

## Upcoming Features (Roadmap)

### High Priority
- [ ] **Live Draft Tracker**: Real-time pick tracking with value indicators
- [ ] **ADP Value Finder**: Identify players falling below their ADP
- [ ] **Trade Analyzer**: Evaluate trade fairness using VORP calculations
- [ ] **Mock Draft Simulator**: Practice drafting against AI opponents
- [ ] **Web Interface**: Interactive draft board with real-time updates

### Medium Priority
- [ ] **Keeper Value Calculator**: Determine optimal keepers for next season
- [ ] **Injury Risk Analysis**: Factor in injury history and probability
- [ ] **Schedule Strength Analysis**: Playoff schedule optimization
- [ ] **Stack Builder**: QB/WR and game stack recommendations
- [ ] **Auction Value Calculator**: Convert rankings to auction dollar values

### Future Enhancements
- [ ] **Draft Grade Report**: Post-draft analysis and team grading
- [ ] **Waiver Wire Predictor**: ML-based breakout candidate predictions
- [ ] **Dynasty Mode**: Multi-year player valuations
- [ ] **DFS Optimizer**: Daily fantasy lineup optimization
- [ ] **League Analyzer**: Analyze league-specific drafting tendencies
- [ ] **Mobile App**: Native iOS/Android draft companion
- [ ] **Voice Assistant**: Hands-free draft day assistant
- [ ] **Custom Scoring**: Support for unique league scoring rules
- [ ] **Historical Analysis**: Track accuracy of projections over time
- [ ] **Weather Integration**: Game-day weather impact on projections

## Quick Start

### Prerequisites

- Python 3.8+
- Google Cloud account (optional, for Google Sheets export)

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

# Export to Google Sheets
python main.py fetch-rankings --export-format sheets

# Set up Google Sheets authentication
python main.py setup-sheets

# Use a platform preset
python main.py use-preset yahoo_half_ppr

# List available rankings
python main.py list-rankings

# Clean up old archives (keep last 5)
python main.py cleanup --keep 5
```

### Export Formats

#### CSV Files
The tool generates multiple CSV files in `data/output/latest/`:

1. **Overall Rankings** - All players with consensus rankings, VORP, and projections
2. **Position Rankings** - Separate files for each position with VORP values
3. **Cheat Sheet** - Condensed draft reference with VORP for quick decisions
4. **Tier Rankings** - Players grouped by position and tier

#### Google Sheets
With `--export-format sheets`, creates a comprehensive draft spreadsheet with:

1. **Overall Rankings** - Complete player data with tier coloring
2. **Position Sheets** - Filtered views for each position
3. **Cheat Sheet** - Printable format with draft tracking
4. **Draft Board** - Live draft tracking with value indicators
5. **Instructions** - How to use the draft tools

### Value-Based Drafting (VBD)

VBD helps you make better draft decisions by comparing players across positions:

- **VORP (Value Over Replacement Player)**: How many points a player scores above a replacement-level player
- **Multiple Baselines**: Choose between VOLS (aggressive), VORP (balanced), or BEER (injury-adjusted)
- **Cross-Positional Rankings**: See why that elite RB might be worth more than a top QB

### Google Sheets Integration

To enable Google Sheets export:

1. Run `python main.py setup-sheets` for setup instructions
2. Create a Google Cloud service account
3. Enable Google Sheets API and Google Drive API
4. Download the credentials JSON file
5. Save it as `credentials/service_account.json`
6. Run `python main.py fetch-rankings --export-format sheets`

The tool will automatically create and format your draft sheet!

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
make test                # Run all tests
pytest tests/ -v         # Run with verbose output
pytest tests/test_vbd.py # Run specific test file
```

### Code Quality

```bash
make lint    # Run ruff and mypy
make format  # Auto-format with black
```

### Recent Improvements (2024)

- **Enhanced Testing**: Fixed VBD calculator tests and improved coverage
- **Cache Robustness**: Better handling of special characters and error cases
- **Player Matching**: Improved fuzzy matching with proper team/position validation
- **Documentation**: Comprehensive feature list and roadmap
- **Code Quality**: Fixed test failures and improved error handling

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting (`make test && make lint`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Submit a pull request

## Technical Improvements (Engineering Roadmap)

### Completed ✅
- [x] Multi-source data aggregation (5 sources)
- [x] Advanced VBD implementation with 3 baselines
- [x] Consensus ranking algorithm with weighted averaging
- [x] Fantasy point projection system
- [x] Google Sheets integration with live updates
- [x] Optimized caching with compression
- [x] Player name normalization and fuzzy matching
- [x] Comprehensive test coverage
- [x] Performance monitoring and metrics

### In Progress 🚧
- [ ] Web interface development (Flask-based)
- [ ] Real-time draft tracking system
- [ ] Enhanced error handling and recovery
- [ ] API rate limiting improvements

### Planned 📋
- [ ] Microservices architecture migration
- [ ] GraphQL API for web interface
- [ ] Redis caching layer
- [ ] Docker containerization
- [ ] CI/CD pipeline with GitHub Actions
- [ ] Comprehensive API documentation
- [ ] Load testing and optimization
- [ ] Machine learning pipeline for predictions

## License

MIT License - see LICENSE file for details

## Disclaimer

This tool is for educational and personal use. Be respectful of data sources and their terms of service. The tool includes rate limiting and caching to minimize server load.