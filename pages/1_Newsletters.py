import altair as alt
import csv
import re

import pandas as pd
import streamlit as st

from metrics import CAMPAIGN_COUNTS, DATA_DIR, clean_campaigns, read_export

CAMPAIGN_FILE = DATA_DIR / "nl_campaigns.csv"
COUNTS = ["Emails Sent", "Unique Opens", "Unique clicks"]
RATES = {
    "Open rate": ("Unique Opens", "Emails Sent"),
    "Click rate": ("Unique clicks", "Emails Sent"),
    "Click-to-open rate": ("Unique clicks", "Unique Opens"),
}
AD_PATTERN = r"\b(?:sponsor(?:ed|ship)?|advertis(?:e|ing|ement)|paid promotion)\b"


def report_window(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if row and row[0].strip() == "Campaign Name":
                break
            if len(row) > 1 and row[0].strip() == "Filters applied:":
                dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", row[1])
                if len(dates) == 2:
                    return tuple(pd.to_datetime(dates, format="%m/%d/%Y"))
    raise ValueError("Expected a start and end date in the campaign report filters.")


def period_label(start, days):
    end = start + pd.Timedelta(days=days - 1)
    if days == 1:
        return f"{start:%b %d, %Y}"
    return f"{start:%b %d, %Y} – {end:%b %d, %Y}"


def totals(frame):
    result = {"Campaigns": len(frame)}
    for column in COUNTS:
        values = frame[column]
        result[column] = None if values.isna().any() else int(values.sum())
    for rate, (numerator, denominator) in RATES.items():
        top, bottom = result[numerator], result[denominator]
        result[rate] = top / bottom if top is not None and bottom else None
    return result


def compare(current, prior):
    rows = []
    for metric, value in current.items():
        previous = prior[metric]
        delta = value - previous if value is not None and previous is not None else None
        is_rate = metric in RATES

        def display(number):
            if number is None:
                return "Unavailable"
            return f"{number:.2%}" if is_rate else f"{number:,}"

        absolute = "Unavailable"
        if delta is not None:
            absolute = f"{delta * 100:+.2f} pp" if is_rate else f"{delta:+,}"
        rows.append({
            "Metric": metric,
            "Current": display(value),
            "Prior": display(previous),
            "Change": absolute,
            "Relative change": f"{delta / previous:+.1%}"
            if not is_rate and delta is not None and previous else "—",
        })
    return pd.DataFrame(rows)


st.title("Newsletter audience")

report_tab, dictionary_tab = st.tabs(["Dashboard", "Metric dictionary"])

with dictionary_tab:
    st.markdown("""
**Source and scope.** ActiveCampaign’s `data_folder/nl_campaigns.csv` covers
the LA Local and Long Beach clusters together. The export lacks a recipient list
or cluster column, so this page reports **Network** totals. It uses `Sent Date`
to group campaign rows into days or Sunday–Saturday weeks.

| Dashboard metric | Raw column or input | Definition | Type |
|---|---|---|---|
| Campaigns | Campaign table rows, dated by `Sent Date` | Count of campaign records sent in the reporting period. | Flow |
| Emails Sent | `Emails Sent` | Sum of sends across included campaign records. | Flow |
| Unique Opens | `Unique Opens` | Sum of campaign-level unique opens. A recipient can count on multiple sends. Apple Mail Privacy Protection can inflate opens. | Flow across sends |
| Unique clicks | `Unique clicks` | Sum of campaign-level unique clicks. A recipient can count on multiple sends. | Flow across sends |
| Open rate | `Unique Opens`, `Emails Sent` | Total unique opens divided by total sends. | Rate |
| Click rate | `Unique clicks`, `Emails Sent` | Total unique clicks divided by total sends. Top Campaigns uses the same formula per campaign. | Rate |
| Click-to-open rate | `Unique clicks`, `Unique Opens` | Total unique clicks divided by total unique opens. | Rate |

**Comparison and ranking.** Count change = current minus prior. Relative count
change = change divided by prior. Rate changes are differences in percentage
points. A zero denominator makes the result unavailable. Top Campaigns ranks
eligible sends in the selected period by click rate. `Campaign Name` is used to
screen for paid content, and `Subject` is shown for reference.
### Formulas for each comparison row

Current means the selected day or Sunday–Saturday week. Prior means the immediately preceding day or week.

| Metric | Current | Prior | Change | Relative change (%) |
|---|---|---|---|---|
| Campaigns | count of campaign rows sent in Current | count of campaign rows sent in Prior | Campaigns (Current) − Campaigns (Prior) | (Campaigns (Current) − Campaigns (Prior)) ÷ Campaigns (Prior) × 100 |
| Emails sent | sum(`Emails Sent` in Current) | sum(`Emails Sent` in Prior) | Emails sent (Current) − Emails sent (Prior) | (Emails sent (Current) − Emails sent (Prior)) ÷ Emails sent (Prior) × 100 |
| Unique opens | sum(`Unique Opens` in Current) | sum(`Unique Opens` in Prior) | Unique opens (Current) − Unique opens (Prior) | (Unique opens (Current) − Unique opens (Prior)) ÷ Unique opens (Prior) × 100 |
| Unique clicks | sum(`Unique clicks` in Current) | sum(`Unique clicks` in Prior) | Unique clicks (Current) − Unique clicks (Prior) | (Unique clicks (Current) − Unique clicks (Prior)) ÷ Unique clicks (Prior) × 100 |
| Open rate | sum(`Unique Opens` in Current) ÷ sum(`Emails Sent` in Current) | sum(`Unique Opens` in Prior) ÷ sum(`Emails Sent` in Prior) | (Open rate (Current) − Open rate (Prior)) × 100 pp | — |
| Click rate | sum(`Unique clicks` in Current) ÷ sum(`Emails Sent` in Current) | sum(`Unique clicks` in Prior) ÷ sum(`Emails Sent` in Prior) | (Click rate (Current) − Click rate (Prior)) × 100 pp | — |
| Click-to-open rate | sum(`Unique clicks` in Current) ÷ sum(`Unique Opens` in Current) | sum(`Unique clicks` in Prior) ÷ sum(`Unique Opens` in Prior) | (Click-to-open rate (Current) − Click-to-open rate (Prior)) × 100 pp | — |

**Timing.** Performance counts are attributed to the send period and may change as more recipients interact before the next export.

Rate formulas return proportions. Multiply by 100 to display each rate as a percentage.
""")

with report_tab:
    try:
        first, last = report_window(CAMPAIGN_FILE)
        raw, _ = read_export(
            CAMPAIGN_FILE, ["Campaign Name", "Subject", "Sent Date", *CAMPAIGN_COUNTS]
        )
        campaigns, _ = clean_campaigns(raw, first, last)
    except (OSError, ValueError) as error:
        st.error(f"Campaign export could not be loaded: {error}")
        st.stop()

    st.info(
        "Network-wide reporting covers LA Local and Long Beach. The ActiveCampaign "
        "export has no recipient list or cluster field, so campaign metrics are "
        "shown for the whole network."
    )
    campaigns["send_day"] = campaigns["sent_at"].dt.normalize()

    view = st.radio("Reporting frequency", ["Daily", "Weekly"], horizontal=True)
    days = 1 if view == "Daily" else 7
    step = pd.Timedelta(days=days)
    periods = pd.date_range(
        first, last - pd.Timedelta(days=days - 1),
        freq="D" if days == 1 else "W-SUN",
    )
    choices = [start for start in reversed(periods) if start - step >= first]
    if not choices:
        st.warning("The export does not cover two complete reporting periods.")
        st.stop()

    current = st.selectbox(
        "Reporting period", choices, format_func=lambda start: period_label(start, days)
    )
    prior = current - step

    current_rows = campaigns.loc[campaigns["send_day"].ge(current)
                                & campaigns["send_day"].lt(current + step)]
    prior_rows = campaigns.loc[campaigns["send_day"].ge(prior)
                              & campaigns["send_day"].lt(current)]
    st.caption(
        f"Network · Current {period_label(current, days)} · "
        f"Prior {period_label(prior, days)} · Export through {last:%b %d, %Y}"
    )
    st.dataframe(compare(totals(current_rows), totals(prior_rows)), hide_index=True)

    trend_periods = periods[periods <= current]
    trend_metrics = ["Unique Opens", "Unique clicks"]
    trend_rows = []
    for start in trend_periods:
        period_rows = campaigns.loc[
            campaigns["send_day"].ge(start) & campaigns["send_day"].lt(start + step)
        ]
        period_totals = totals(period_rows)
        trend_rows.append({metric: period_totals[metric] for metric in trend_metrics})
    trend = pd.DataFrame(trend_rows, index=trend_periods).rename(
        columns={"Unique Opens": "Unique opens"}
    )
    trend.index.name = "Period start"
    st.subheader(f"{view} unique opens and clicks")
    st.caption(
        f"Network · {period_label(trend_periods[0], days)} "
        f"through {period_label(current, days)}"
    )
    chart_metrics = {
        "Unique opens": "#16447D",
        "Unique clicks": "#63B9EF",
    }
    chart_view = st.radio(
        "Metrics to display", ["Both", *chart_metrics], horizontal=True
    )
    visible = list(chart_metrics) if chart_view == "Both" else [chart_view]
    chart_data = trend[visible].reset_index().melt(
        id_vars="Period start", var_name="Metric", value_name="Count"
    )
    chart = alt.Chart(chart_data).mark_line().encode(
        x=alt.X("Period start:T", title="Period start"),
        y=alt.Y("Count:Q", title="Count"),
        color=alt.Color(
            "Metric:N",
            scale=alt.Scale(
                domain=visible, range=[chart_metrics[metric] for metric in visible]
            ),
            legend=alt.Legend(title="Metric"),
        ),
        tooltip=["Period start:T", "Metric:N", "Count:Q"],
    )
    st.altair_chart(chart)

    st.subheader("Top campaigns by click rate")
    ranked = current_rows.loc[
        ~current_rows["Campaign Name"].str.contains(AD_PATTERN, case=False, na=False)
        & current_rows["Emails Sent"].gt(0)
        & current_rows["Unique clicks"].notna()
    ].copy()
    ranked["Click rate"] = ranked["Unique clicks"] / ranked["Emails Sent"]
    ranked = ranked.sort_values(["Click rate", "Emails Sent"], ascending=False).head(10)
    st.caption("Campaign names are screened for sponsorship and advertising terms.")
    if ranked.empty:
        st.info("No campaigns eligible for ranking in this period and scope.")
    else:
        ranked["Click rate"] = ranked["Click rate"].map("{:.2%}".format)
        st.dataframe(ranked[[
            "Campaign Name", "Subject", "Emails Sent", "Unique clicks", "Click rate"
        ]], hide_index=True)

    with st.expander("Excluded campaign records"):
        excluded = raw.loc[
            ~raw["source_record"].isin(campaigns["source_record"]),
            ["source_record", "Campaign Name", "Subject", "Sent Date"],
        ].copy()
        if excluded.empty:
            st.info("No campaign records were excluded during date validation.")
        else:
            valid_date = pd.to_datetime(
                excluded["Sent Date"], format="%Y-%m-%d %H:%M:%S", errors="coerce"
            ).notna()
            excluded["Exclusion reason"] = valid_date.map({
                True: "Outside reporting window",
                False: "Missing or invalid send date",
            })
            st.caption(
                f"Campaigns are excluded when their send date falls outside "
                f"{first:%b %d, %Y} – {last:%b %d, %Y}, or when the send date "
                "is missing or invalid and the campaign cannot be assigned to a period. "
                "Source record numbers start at 1 after the campaign table header."
            )
            st.dataframe(excluded, hide_index=True)
