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
    if "protocol" not in df.columns:
        df["protocol"] = "TCP"
    df["protocol"] = df["protocol"].fillna("TCP")
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def build_figure(df: pd.DataFrame) -> go.Figure:
    has_udp = (df["protocol"] == "UDP").any()
    n_rows = 3 if has_udp else 2
    row_heights = [0.45, 0.25, 0.3] if has_udp else [0.7, 0.3]
    subtitles = (
        ("TCP Status (HTTP)", "UDP Status (DNS)", "Failure Density (rolling 10-min)")
        if has_udp
        else ("Internet Status Over Time", "Failure Density (rolling 10-min count)")
    )

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        row_heights=row_heights,
        subplot_titles=subtitles,
    )

    # ── Helper to add a status trace ─────────────────────────────────────────
    def add_status_trace(subset, row, name):
        colours = subset["success"].map({True: "#2ecc71", False: "#e74c3c"})
        labels = subset["success"].map({True: "UP", False: "DOWN"})
        proto = subset["protocol"].iloc[0] if len(subset) else ""
        fig.add_trace(
            go.Scatter(
                x=subset["timestamp"],
                y=subset["success"].astype(int),
                mode="markers+lines",
                marker=dict(color=colours, size=7, line=dict(width=0.5, color="white")),
                line=dict(color="rgba(127,127,127,0.3)", width=1),
                text=[
                    f"{lbl}<br>{proto}: {url}<br>{ts}"
                    for lbl, url, ts in zip(labels, subset["url"], subset["timestamp"])
                ],
                hoverinfo="text",
                name=name,
            ),
            row=row,
            col=1,
        )
        fig.update_yaxes(
            tickvals=[0, 1], ticktext=["DOWN", "UP"], range=[-0.15, 1.15], row=row, col=1
        )

    # ── Status traces ────────────────────────────────────────────────────────
    tcp_df = df[df["protocol"] == "TCP"]
    add_status_trace(tcp_df, 1, "TCP")

    if has_udp:
        udp_df = df[df["protocol"] == "UDP"]
        add_status_trace(udp_df, 2, "UDP")

    # ── Rolling failure count (all protocols) ────────────────────────────────
    fail_row = n_rows
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
        row=fail_row,
        col=1,
    )

    # ── Layout polish ────────────────────────────────────────────────────────
    fig.update_yaxes(title_text="Failure count", row=fail_row, col=1)
    fig.update_xaxes(title_text="Time", row=fail_row, col=1)

    fig.update_layout(
        title="Internet Connectivity Report",
        template="plotly_white",
        hovermode="x unified",
        height=700,
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
