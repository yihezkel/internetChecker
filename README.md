# Internet Checker

A continuous internet connectivity monitor for Windows. Periodically pings well-known websites, logs results to a CSV file, alerts you audibly when the connection drops, and provides an interactive graph to visualize your connectivity history.

## Setup

```
pip install -r requirements.txt
```

## Usage

### 1. Run the checker

```
python checker.py
```

Leave this running in a terminal window. It will:

- **Round-robin** through 20 well-known URLs (Google, Bing, GitHub, etc.), testing one every **10 seconds**.
- **Log** each result (timestamp, success, URL) to `output.csv`, creating the file on first run and appending thereafter.
- **Prevent Windows from sleeping** so the checker can run unattended overnight.
- **Sound an audible alert** (three rising beeps) when **two consecutive checks fail**.
- **Shut down gracefully** on Ctrl+C, restoring normal sleep behaviour.

### 2. View the graph

In a separate terminal (while the checker is still running, or after stopping it):

```
python graph.py
```

This opens an interactive Plotly chart in your browser with:

- **Top panel** — UP/DOWN scatter plot (green = success, red = failure) with connecting lines.
- **Bottom panel** — Rolling 10-minute failure density to spot patterns.
- **Range selector buttons** — Quickly zoom to 10m, 30m, 1h, 6h, 1d, or all data.
- **Range slider** — Drag to pan across the full timeline.
- **Zoom & pan** — Click-and-drag to zoom into any region; double-click to reset.
- **Hover tooltips** — See the exact timestamp, URL tested, and result.

You can also pass a custom CSV path:

```
python graph.py path/to/output.csv
```

## Data file

All data is stored in `output.csv` in the project directory. The format is:

```
timestamp,success,url
2026-03-22T14:30:00,True,https://www.google.com
2026-03-22T14:30:10,False,https://www.bing.com
```

- The file is created automatically if it doesn't exist.
- New data points are always appended — no data is overwritten.
- To clear history, delete or rename `output.csv` manually.

## Configuration

Edit the constants at the top of `checker.py` to customise behaviour:

| Constant | Default | Description |
|---|---|---|
| `CHECK_INTERVAL_SECONDS` | `10` | Seconds between each check |
| `REQUEST_TIMEOUT_SECONDS` | `5` | HTTP request timeout |
| `URLS` | 20 entries | List of URLs to cycle through |
| `OUTPUT_FILE` | `output.csv` | Path to the data file |

## Requirements

- **Python 3.8+**
- **Windows** (uses `winsound` for alerts and `ctypes` for sleep prevention)
- Dependencies: `requests`, `pandas`, `plotly` (see `requirements.txt`)
