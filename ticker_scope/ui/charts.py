from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


MOVING_AVERAGE_WINDOWS = (5, 20, 60, 120, 240)

MOVING_AVERAGE_COLORS = {
    5: "#F97316",
    20: "#16A34A",
    60: "#0891B2",
    120: "#9333EA",
    240: "#DC2626",
}


def make_forecast_chart(
    actual: pd.DataFrame,
    forecast: pd.DataFrame,
    anomalies: pd.DataFrame | None = None,
    events: pd.DataFrame | None = None,
    fear_greed: pd.DataFrame | None = None,
    moving_average_windows: list[int] | tuple[int, ...] | None = MOVING_AVERAGE_WINDOWS,
) -> go.Figure:
    has_fear_greed = fear_greed is not None and not fear_greed.empty
    fig = (
        make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.72, 0.28],
            vertical_spacing=0.06,
        )
        if has_fear_greed
        else go.Figure()
    )

    def add_trace(trace, row: int = 1) -> None:
        if has_fear_greed:
            fig.add_trace(trace, row=row, col=1)
        else:
            fig.add_trace(trace)

    add_trace(
        go.Scatter(
            x=forecast["ds"],
            y=forecast["yhat_upper"],
            line={"width": 0},
            hoverinfo="skip",
            name="Upper",
            showlegend=False,
        )
    )
    add_trace(
        go.Scatter(
            x=forecast["ds"],
            y=forecast["yhat_lower"],
            fill="tonexty",
            fillcolor="rgba(99, 110, 250, 0.14)",
            line={"width": 0},
            hoverinfo="skip",
            name="Forecast range",
        )
    )
    add_trace(
        go.Scatter(
            x=forecast["ds"],
            y=forecast["yhat"],
            mode="lines",
            line={"color": "#636EFA", "width": 2},
            name="Forecast",
        )
    )
    add_trace(
        go.Scatter(
            x=actual["ds"],
            y=actual["y"],
            mode="lines",
            line={"color": "#111827", "width": 2},
            name="Actual",
        )
    )
    for window in moving_average_windows or ():
        moving_average = actual["y"].rolling(window=window, min_periods=window).mean()
        if moving_average.notna().any():
            add_trace(
                go.Scatter(
                    x=actual["ds"],
                    y=moving_average,
                    mode="lines",
                    line={
                        "color": MOVING_AVERAGE_COLORS.get(window, "#64748B"),
                        "width": 1.7,
                    },
                    name=f"MA {window}",
                    connectgaps=False,
                    hovertemplate=(
                        "Date: %{x|%Y-%m-%d}<br>"
                        f"MA {window}: "
                        "%{y:,.2f}<extra></extra>"
                    ),
                )
            )

    if anomalies is not None and not anomalies.empty:
        anomaly_points = anomalies[anomalies["is_anomaly"]]
        add_trace(
            go.Scatter(
                x=anomaly_points["ds"],
                y=anomaly_points["y"],
                mode="markers",
                marker={"color": "#EF4444", "size": 8, "symbol": "x"},
                name="Anomaly",
            )
        )

    event_trace = _make_event_marker_trace(
        events=events,
        min_date=forecast["ds"].min(),
        max_date=forecast["ds"].max(),
        y_value=_top_marker_value(actual, forecast),
    )
    if event_trace is not None:
        add_trace(event_trace)

    if has_fear_greed:
        sentiment = _normalize_fear_greed_for_chart(fear_greed)
        fig.add_trace(
            go.Scatter(
                x=sentiment["index_date"],
                y=sentiment["value"],
                mode="lines+markers",
                line={"color": "#0F766E", "width": 2},
                marker={"color": "#0F766E", "size": 5},
                customdata=sentiment[["classification", "source"]],
                hovertemplate=(
                    "Date: %{x|%Y-%m-%d}<br>"
                    "Fear & Greed: %{y:.0f}<br>"
                    "Class: %{customdata[0]}<br>"
                    "Source: %{customdata[1]}<extra>Sentiment</extra>"
                ),
                name="Fear & Greed",
                connectgaps=False,
            ),
            row=2,
            col=1,
        )
        _add_fear_greed_bands(fig)

    fig.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    if has_fear_greed:
        fig.update_layout(height=620)
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(
            title_text="Fear & Greed",
            range=[0, 100],
            tickmode="array",
            tickvals=[0, 25, 50, 75, 100],
            row=2,
            col=1,
        )
        fig.update_xaxes(title_text=None)
    else:
        fig.update_layout(xaxis_title=None, yaxis_title="Price")
    return fig


def make_components_chart(forecast: pd.DataFrame) -> go.Figure:
    component_columns = [
        column
        for column in ("trend", "weekly", "yearly", "holidays")
        if column in forecast.columns and forecast[column].notna().any()
    ]
    fig = make_subplots(
        rows=max(1, len(component_columns)),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=[column.title() for column in component_columns],
    )
    if not component_columns:
        fig.update_layout(
            margin={"l": 12, "r": 12, "t": 24, "b": 12},
            xaxis_title=None,
            yaxis_title=None,
        )
        return fig

    colors = {
        "trend": "#2563EB",
        "weekly": "#059669",
        "yearly": "#D97706",
        "holidays": "#7C3AED",
    }
    for row_index, column in enumerate(component_columns, start=1):
        fig.add_trace(
            go.Scatter(
                x=forecast["ds"],
                y=forecast[column],
                mode="lines",
                line={"color": colors.get(column, "#475569"), "width": 2},
                name=column.title(),
                showlegend=False,
            ),
            row=row_index,
            col=1,
        )

    fig.update_layout(
        height=max(320, 180 * len(component_columns)),
        margin={"l": 12, "r": 12, "t": 36, "b": 12},
        hovermode="x unified",
    )
    fig.update_xaxes(title_text=None)
    fig.update_yaxes(title_text=None)
    return fig


def make_backtest_chart(result: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result["ds"],
            y=result["y"],
            mode="lines",
            line={"color": "#111827", "width": 2},
            name="Actual",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result["ds"],
            y=result["yhat"],
            mode="lines",
            line={"color": "#10B981", "width": 2},
            name="Predicted",
        )
    )
    fig.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        xaxis_title=None,
        yaxis_title="Price",
    )
    return fig


def make_rolling_backtest_chart(
    result: pd.DataFrame,
    horizon_days: int,
) -> go.Figure:
    fig = go.Figure()
    if result.empty:
        return fig

    selected = result[result["horizon_days"] == horizon_days].copy()
    if selected.empty:
        return fig

    selected["cutoff_date"] = pd.to_datetime(selected["cutoff_date"]).dt.date.astype(str)
    fig.add_trace(
        go.Scatter(
            x=selected["ds"],
            y=selected["y"],
            mode="markers",
            marker={"color": "#111827", "size": 6},
            customdata=selected["cutoff_date"],
            hovertemplate=(
                "Date: %{x|%Y-%m-%d}<br>"
                "Actual: %{y:,.2f}<br>"
                "Cutoff: %{customdata}<extra>Actual</extra>"
            ),
            name="Actual",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=selected["ds"],
            y=selected["yhat"],
            mode="markers",
            marker={"color": "#10B981", "size": 6, "symbol": "diamond"},
            customdata=selected["cutoff_date"],
            hovertemplate=(
                "Date: %{x|%Y-%m-%d}<br>"
                "Predicted: %{y:,.2f}<br>"
                "Cutoff: %{customdata}<extra>Predicted</extra>"
            ),
            name="Predicted",
        )
    )
    fig.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        hovermode="closest",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        xaxis_title=None,
        yaxis_title="Price",
    )
    return fig


def make_backtest_comparison_chart(
    summary: pd.DataFrame,
    metric: str = "mape",
) -> go.Figure:
    fig = go.Figure()
    if summary.empty or metric not in summary.columns:
        return fig

    for run_label, group in summary.groupby("run_label", sort=False):
        sorted_group = group.sort_values("horizon_sort")
        fig.add_trace(
            go.Scatter(
                x=sorted_group["horizon_label"],
                y=sorted_group[metric],
                mode="lines+markers",
                name=str(run_label),
            )
        )

    fig.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        xaxis_title="Horizon",
        yaxis_title=metric.upper(),
    )
    return fig


def make_multi_metric_bar_chart(
    summary: pd.DataFrame,
    metric: str = "mape",
) -> go.Figure:
    fig = go.Figure()
    if summary.empty or metric not in summary.columns:
        return fig

    sorted_summary = summary.sort_values(metric, ascending=metric != "coverage")
    fig.add_trace(
        go.Bar(
            x=sorted_summary["ticker"],
            y=sorted_summary[metric],
            marker={"color": "#2563EB"},
            text=sorted_summary[metric].round(2),
            textposition="outside",
            name=metric.upper(),
        )
    )
    fig.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        xaxis_title=None,
        yaxis_title=metric.upper(),
        showlegend=False,
    )
    return fig


def make_multi_anomaly_chart(summary: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if summary.empty or "anomaly_rate_pct" not in summary.columns:
        return fig

    sorted_summary = summary.sort_values("anomaly_rate_pct", ascending=False)
    fig.add_trace(
        go.Bar(
            x=sorted_summary["ticker"],
            y=sorted_summary["anomaly_rate_pct"],
            marker={"color": "#DC2626"},
            text=sorted_summary["anomaly_count"],
            texttemplate="%{text} points",
            textposition="outside",
            name="Anomaly rate",
        )
    )
    fig.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        xaxis_title=None,
        yaxis_title="Anomaly rate (%)",
        showlegend=False,
    )
    return fig


def make_event_comparison_chart(
    actual: pd.DataFrame,
    baseline_forecast: pd.DataFrame,
    event_forecast: pd.DataFrame,
    events: pd.DataFrame | None = None,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=actual["ds"],
            y=actual["y"],
            mode="lines",
            line={"color": "#111827", "width": 2},
            name="Actual",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=baseline_forecast["ds"],
            y=baseline_forecast["yhat"],
            mode="lines",
            line={"color": "#94A3B8", "width": 2, "dash": "dot"},
            name="Without events",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=event_forecast["ds"],
            y=event_forecast["yhat"],
            mode="lines",
            line={"color": "#F97316", "width": 2},
            name="With events",
        )
    )

    event_trace = _make_event_marker_trace(
        events=events,
        min_date=event_forecast["ds"].min(),
        max_date=event_forecast["ds"].max(),
        y_value=max(
            float(actual["y"].max()),
            float(baseline_forecast["yhat"].max()),
            float(event_forecast["yhat"].max()),
        )
    )
    if event_trace is not None:
        fig.add_trace(event_trace)

    fig.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        xaxis_title=None,
        yaxis_title="Price",
    )
    return fig


def _make_event_marker_trace(
    events: pd.DataFrame | None,
    min_date,
    max_date,
    y_value: float,
) -> go.Scatter | None:
    visible_events = _visible_events(events, min_date, max_date)
    if visible_events.empty:
        return None

    return go.Scatter(
        x=visible_events["event_date"],
        y=[y_value] * len(visible_events),
        mode="markers",
        marker={"color": "#7C3AED", "size": 9, "symbol": "triangle-down"},
        text=_event_hover_text(visible_events),
        hovertemplate="%{text}<extra>Event</extra>",
        name="Events",
    )


def _normalize_fear_greed_for_chart(fear_greed: pd.DataFrame) -> pd.DataFrame:
    sentiment = fear_greed.copy()
    sentiment["index_date"] = pd.to_datetime(
        sentiment["index_date"],
        errors="coerce",
    )
    sentiment["value"] = pd.to_numeric(sentiment["value"], errors="coerce")
    if "classification" not in sentiment.columns:
        sentiment["classification"] = ""
    if "source" not in sentiment.columns:
        sentiment["source"] = ""
    return sentiment.dropna(subset=["index_date", "value"]).sort_values("index_date")


def _add_fear_greed_bands(fig: go.Figure) -> None:
    bands = [
        (0, 24, "rgba(239, 68, 68, 0.10)"),
        (24, 44, "rgba(249, 115, 22, 0.10)"),
        (44, 55, "rgba(148, 163, 184, 0.10)"),
        (55, 75, "rgba(34, 197, 94, 0.10)"),
        (75, 100, "rgba(16, 185, 129, 0.14)"),
    ]
    for y0, y1, color in bands:
        fig.add_shape(
            type="rect",
            xref="paper",
            yref="y2",
            x0=0,
            x1=1,
            y0=y0,
            y1=y1,
            fillcolor=color,
            line={"width": 0},
            layer="below",
        )


def _visible_events(
    events: pd.DataFrame | None,
    min_date,
    max_date,
) -> pd.DataFrame:
    if events is None or events.empty:
        return pd.DataFrame()

    visible_events = events.copy()
    visible_events["event_date"] = pd.to_datetime(
        visible_events["event_date"],
        errors="coerce",
    )
    return visible_events[
        visible_events["event_date"].between(min_date, max_date)
    ].reset_index(drop=True)


def _event_hover_text(events: pd.DataFrame) -> list[str]:
    texts = []
    for row in events.itertuples(index=False):
        ticker = getattr(row, "ticker", None)
        scope = ticker if pd.notna(ticker) else "GLOBAL"
        texts.append(
            "<br>".join(
                [
                    str(getattr(row, "name")),
                    f"Date: {getattr(row, 'event_date').date()}",
                    f"Category: {getattr(row, 'category', '-')}",
                    f"Scope: {scope}",
                    (
                        "Window: "
                        f"{getattr(row, 'lower_window', 0)}"
                        f" ~ +{getattr(row, 'upper_window', 0)}"
                    ),
                ]
            )
        )
    return texts


def _top_marker_value(actual: pd.DataFrame, forecast: pd.DataFrame) -> float:
    candidates = [
        float(actual["y"].max()),
        float(forecast["yhat"].max()),
    ]
    if "yhat_upper" in forecast.columns:
        candidates.append(float(forecast["yhat_upper"].max()))
    return max(candidates)
