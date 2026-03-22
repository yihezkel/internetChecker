"""
Render an interactive graph of the internet-checker data.

Reads output.csv and displays a Plotly timeline showing up/down status.
The graph supports zoom, pan, range selection, hover details, and more.

Usage:
    python graph.py
    python graph.py path/to/output.csv
"""

import os
import sys

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output.csv")


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df["success"] = df["success"].astype(str).str.strip().str.lower() == "true"
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def build_figure(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=("Internet Status Over Time", "Failure Density (rolling 10-min count)"),
    )

    # ── Row 1: scatter of each check result ──────────────────────────────────
    colours = df["success"].map({True: "#2ecc71", False: "#e74c3c"})
    labels = df["success"].map({True: "UP", False: "DOWN"})

    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["success"].astype(int),
            mode="markers+lines",
            marker=dict(color=colours, size=7, line=dict(width=0.5, color="white")),
            line=dict(color="rgba(127,127,127,0.3)", width=1),
            text=[
                f"{lbl}<br>{url}<br>{ts}"
                for lbl, url, ts in zip(labels, df["url"], df["timestamp"])
            ],
            hoverinfo="text",
            name="Check result",
        ),
        row=1,
        col=1,
    )

    # ── Row 2: rolling failure count ─────────────────────────────────────────
    df_ts = df.set_index("timestamp")
    failures = (~df_ts["success"]).astype(int)
    rolling_fail = failures.rolling("10min").sum()

    fig.add_trace(
        go.Scatter(
            x=rolling_fail.index,
            y=rolling_fail.values,
            fill="tozeroy",
            line=dict(color="#e74c3c", width=1),
            fillcolor="rgba(231,76,60,0.25)",
            name="Failures (10 min)",
        ),
        row=2,
        col=1,
    )

    # ── Layout polish ────────────────────────────────────────────────────────
    fig.update_yaxes(
        tickvals=[0, 1],
        ticktext=["DOWN", "UP"],
        range=[-0.15, 1.15],
        row=1,
        col=1,
    )
    fig.update_yaxes(title_text="Failure count", row=2, col=1)
    fig.update_xaxes(title_text="Time", row=2, col=1)

    fig.update_layout(
        title="Internet Connectivity Report",
        template="plotly_white",
        hovermode="x unified",
        height=650,
        showlegend=False,
        xaxis=dict(
            rangeselector=dict(
                buttons=[
                    dict(count=10, label="10m", step="minute", stepmode="backward"),
                    dict(count=30, label="30m", step="minute", stepmode="backward"),
                    dict(count=1, label="1h", step="hour", stepmode="backward"),
                    dict(count=6, label="6h", step="hour", stepmode="backward"),
                    dict(count=1, label="1d", step="day", stepmode="backward"),
                    dict(step="all", label="All"),
                ]
            ),
            rangeslider=dict(visible=True),
            type="date",
        ),
    )

    return fig


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE

    if not os.path.exists(path):
        print(f"[ERROR] Data file not found: {path}")
        sys.exit(1)

    df = load_data(path)
    if df.empty:
        print("[ERROR] No data rows in the CSV.")
        sys.exit(1)

    total = len(df)
    failures = (~df["success"]).sum()
    uptime = (total - failures) / total * 100
    print(f"[INFO] Loaded {total} data points  —  uptime {uptime:.1f}%")

    fig = build_figure(df)
    fig.show()


if __name__ == "__main__":
    main()
