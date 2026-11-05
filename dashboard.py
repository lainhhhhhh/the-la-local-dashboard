import pandas as pd
import streamlit as st

from dashboard_charts import views_chart
from metrics import load_packet

PROPERTIES = {
    "LA Local": {"TLL": "thelalocal.org"},
    "Long Beach": {"LBP": "lbpost.com"},
    "Network": {"TLL": "thelalocal.org", "LBP": "lbpost.com"},
}
METRICS = ["Views", "Sessions", "Active users"]


def web_periods(tables, inventory, grain, property_code):
    export = f"web_ga4_{grain}_{property_code}"
    df = tables[export].copy()

    if grain == "daily":
        df["period_start"] = pd.to_datetime(df["Date"], format="%Y%m%d")
    else:
        metadata = inventory.loc[inventory["file"].eq(f"{export}.csv")].iloc[0]
        starts = pd.date_range(
            pd.to_datetime(metadata["declared_start"], format="%Y%m%d"),
            pd.to_datetime(metadata["declared_end"], format="%Y%m%d")
            - pd.Timedelta(days=6),
            freq="W-SUN",
        )

        # Week numbering verified against the daily exports for this packet.
        week_numbers = starts.strftime("%U").astype(int) + 1
        if week_numbers.has_duplicates:
            raise ValueError(f"{export}: week numbers are ambiguous across years.")

        week_to_date = dict(zip(week_numbers, starts))
        df["period_start"] = pd.to_numeric(df["Week"]).map(week_to_date)

    for metric in METRICS:
        df[metric] = pd.to_numeric(
            df[metric].str.replace(",", "", regex=False), errors="coerce"
        )

    if df[["period_start", *METRICS]].isna().any().any():
        raise ValueError(f"{export}: missing or invalid dates or metrics.")
    if df["period_start"].duplicated().any():
        raise ValueError(f"{export}: duplicate reporting periods.")
    if df[METRICS].lt(0).any().any():
        raise ValueError(f"{export}: negative metric counts.")

    return df.set_index("period_start")[METRICS].sort_index()


def period_label(start, days):
    end = start + pd.Timedelta(days=days - 1)
    if days == 1:
        return start.strftime("%b %d, %Y")
    return f"{start:%b %d} – {end:%b %d, %Y}"


def comparison_row(metric, scope, current, prior):
    change = current - prior
    return {
        "Metric": metric,
        "Scope": scope,
        "Current": f"{current:,.0f}",
        "Prior": f"{prior:,.0f}",
        "Change": f"{change:+,.0f}",
        "% change": f"{change / prior:+.1%}" if prior else "Unavailable",
    }


st.title("Website audience")

report_tab, dictionary_tab = st.tabs(["Dashboard", "Metric dictionary"])

with dictionary_tab:
    st.markdown("""
**Cluster sources.** LA Local uses the `_TLL.csv` exports for thelalocal.org.
Long Beach uses the `_LBP.csv` exports for lbpost.com. The Network scope covers
both properties.

| Dashboard metric | Raw export and columns | Definition and reporting grain | Type and cluster rule |
|---|---|---|---|
| Views | W3 `web_ga4_daily_*.csv` → `Date`, `Views`; W2 `web_ga4_weekly_*.csv` → `Week`, `Views` | GA4 page or screen views for the selected day or Sunday–Saturday week. Repeat views count. | Flow. Network sums both properties for matching periods. |
| Sessions | W3 or W2 → `Sessions`, keyed by `Date` or `Week` | GA4 sessions recorded by the property during the selected period. | Flow. Network sums the two property counts for matching periods. |
| Active users | W3 or W2 → `Active users`, keyed by `Date` or `Week` | Distinct active users within the exported property and period. The weekly count comes directly from W2. | Period distinct count. Show each property separately in Network. |
| Top 10 story views | W5 `web_ga4_pages_*.csv` → `Page path and screen class`, `Views` | Views per eligible story path over the page export’s full date range. Sum views for trailing-slash variants within a property. | Flow. Network ranks stories from both properties separately by property and path when coverage dates match. |

**Comparison columns.** Change = current minus prior. Percent change = change
divided by the prior value. A zero prior value makes percent change unavailable.
### Formulas for each comparison row

Current means the selected day or Sunday–Saturday week. Prior means the immediately preceding day or week.

| Metric | Current | Prior | Change | Relative change (%) |
|---|---|---|---|---|
| Property views | `Views` for property at Current | `Views` for property at Prior | Property views (Current) − Property views (Prior) | (Property views (Current) − Property views (Prior)) ÷ Property views (Prior) × 100 |
| Network views | TLL `Views` at Current + LBP `Views` at Current | TLL `Views` at Prior + LBP `Views` at Prior | Network views (Current) − Network views (Prior) | (Network views (Current) − Network views (Prior)) ÷ Network views (Prior) × 100 |
| Property sessions | `Sessions` for property at Current | `Sessions` for property at Prior | Property sessions (Current) − Property sessions (Prior) | (Property sessions (Current) − Property sessions (Prior)) ÷ Property sessions (Prior) × 100 |
| Network sessions | TLL `Sessions` at Current + LBP `Sessions` at Current | TLL `Sessions` at Prior + LBP `Sessions` at Prior | Network sessions (Current) − Network sessions (Prior) | (Network sessions (Current) − Network sessions (Prior)) ÷ Network sessions (Prior) × 100 |
| Property active users | `Active users` for property at Current | `Active users` for property at Prior | Property active users (Current) − Property active users (Prior) | (Property active users (Current) − Property active users (Prior)) ÷ Property active users (Prior) × 100 |
""")

with report_tab:
    view = st.radio("Reporting frequency", ["Daily", "Weekly"], horizontal=True)
    scope = st.selectbox("Cluster", list(PROPERTIES), index=2)

    grain = view.lower()
    days = 1 if grain == "daily" else 7
    step = pd.Timedelta(days=days)

    try:
        tables, inventory = load_packet()
        series = {
            site: web_periods(tables, inventory, grain, code)
            for code, site in PROPERTIES[scope].items()
        }
    except (KeyError, ValueError, OSError) as error:
        st.error(f"Website exports could not be loaded: {error}")
        st.stop()

    # A network comparison requires both periods on both properties.
    common = next(iter(series.values())).index
    for df in series.values():
        common = common.intersection(df.index)

    choices = sorted(
        (date for date in common if date - step in common),
        reverse=True,
    )
    if not choices:
        st.warning("No current and prior periods are available for this scope.")
        st.stop()

    current = st.selectbox(
        "Reporting period", choices, format_func=lambda date: period_label(date, days)
    )
    prior = current - step

    st.caption(
        f"{', '.join(series)} · Current {period_label(current, days)} "
        f"· Prior {period_label(prior, days)}"
    )

    rows = []
    for metric in ["Views", "Sessions"]:
        rows.append(comparison_row(
            metric,
            scope,
            sum(df.at[current, metric] for df in series.values()),
            sum(df.at[prior, metric] for df in series.values()),
        ))

    for site, df in series.items():
        rows.append(comparison_row(
            "Active users", site, df.at[current, "Active users"],
            df.at[prior, "Active users"],
        ))

    st.dataframe(pd.DataFrame(rows), hide_index=True)

    trend = pd.DataFrame({site: df["Views"] for site, df in series.items()})
    trend = trend.loc[trend.index <= current].copy()

    if scope == "Network":
        trend["Network total"] = trend.sum(axis=1, min_count=len(series))

    st.subheader(
        f"{view} views by property and network total"
        if scope == "Network"
        else f"{view} views by property"
    )
    st.caption(
        f"{', '.join(series)} · {trend.index.min():%b %d, %Y} "
        f"through {period_label(current, days)}"
    )

    views_chart(trend.rename(columns={"thelalocal.org": "LA Local", "lbpost.com": "Long Beach"}))

    PAGE_PATH = "Page path and screen class"

    NON_STORY_SEGMENTS = (
        r"(?:^|/)(?:tag|tags|category|author|authors|page|search|wp-admin|"
        r"advertise|ads|sponsored(?:-content)?)(?:/|$)"
    )

    PAID_SLUG_PREFIX = r"(?:^|/)sponsored-"


    def top_story_paths(pages, limit=10):
        df = pages[[PAGE_PATH, "Views"]].copy()
        df["Story path"] = df[PAGE_PATH].str.rstrip("/")
        df["Views"] = pd.to_numeric(
            df["Views"].str.replace(",", "", regex=False), errors="coerce"
        )
        path = df["Story path"]
        # Both sites use section/article paths for the stories reviewed in W5.
        eligible = (
            path.str.fullmatch(r"/[^/?#]+(?:/[^/?#]+)+", na=False)
            & ~path.str.contains(NON_STORY_SEGMENTS, case=False, regex=True, na=False)
            & ~path.str.contains(PAID_SLUG_PREFIX, case=False, regex=True, na=False)
            & df["Views"].gt(0)
        )
        # Treat trailing-slash variants as one article. Views are additive.
        return (
            df.loc[eligible].groupby("Story path", as_index=False)["Views"].sum()
            .sort_values(["Views", "Story path"], ascending=[False, True])
            .head(limit)
        )


    st.subheader("Top 10 stories by views")
    st.caption(
        "Full page-export period. The daily and weekly selector applies to the "
        "audience comparison above. Story eligibility is based on page paths."
    )

    rankings = {}

    for code, site in PROPERTIES[scope].items():
        export = f"web_ga4_pages_{code}"
        metadata = inventory.loc[inventory["file"].eq(f"{export}.csv")]
        if export not in tables or metadata.empty:
            st.warning(f"Page export unavailable for {site}.")
            continue

        dates = pd.to_datetime(
            metadata[["declared_start", "declared_end"]].iloc[0],
            format="%Y%m%d",
            errors="coerce",
        )
        if dates.isna().any():
            st.warning(f"Page export reporting dates unavailable for {site}.")
            continue

        first, last = dates
        stories = top_story_paths(tables[export])
        rankings[site] = (first, last, stories)
        st.markdown(f"**{site} Top 10 · {first:%b %d, %Y} – {last:%b %d, %Y}**")
        if stories.empty:
            st.info("No eligible story paths in this page export.")
        else:
            st.dataframe(stories, hide_index=True)

    if scope == "Network":
        windows = {(first, last) for first, last, _ in rankings.values()}
        if len(rankings) != len(PROPERTIES[scope]) or len(windows) != 1:
            st.warning("The Network Top 10 requires both page exports for the same dates.")
        else:
            first, last = windows.pop()
            network = pd.concat(
                [stories.assign(Property=site) for site, (_, _, stories) in rankings.items()],
                ignore_index=True,
            ).sort_values(
                ["Views", "Story path", "Property"], ascending=[False, True, True]
            ).head(10)
            st.markdown(f"**Network Top 10 · {first:%b %d, %Y} – {last:%b %d, %Y}**")
            if network.empty:
                st.info("No eligible story paths in the page exports.")
            else:
                st.dataframe(network[["Property", "Story path", "Views"]], hide_index=True)
