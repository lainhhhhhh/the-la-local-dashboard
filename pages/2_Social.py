import pandas as pd
import streamlit as st

from dashboard_charts import views_chart
from metrics import DATA_DIR, read_export
from source_scope import SOCIAL_ACCOUNTS, social_label

SOCIAL_FILE = DATA_DIR / "social_posts_snd.csv"
FIELDS = {
    "Facebook": {
        "Engagements": ("Total Engagement", "Total Engagement"),
        "Views": ("Views", "Views"),
        "Link clicks": ("Link Clicks", "Link Clicks"),
    },
    "Instagram": {
        "Engagements": ("IG Engagement", "IG Story Total Interactions"),
        "Views": ("IG Views", "IG Story Views"),
        "Summed post reach": ("IG Reach", "IG Story Reach"),
    },
}

PAID_MARKER = (
    r"\[sponsored\]|"
    r"\bsponsored (?:content|posts?|by)\b|"
    r"/(?:ads|sponsored(?:-content)?)(?:/|$)"
)


def load_posts():
    columns = ["Post Time", "ID", "Account", "Network", "Type", "Post", "Link", "Is Deleted"]
    metrics = sorted({
        field for platform in FIELDS.values() for pair in platform.values() for field in pair
    })
    posts, _ = read_export(SOCIAL_FILE, columns + metrics)
    posted = pd.to_datetime(posts["Post Time"], format="%B %d, %Y %I:%M %p", errors="coerce")
    if posted.isna().any() or posted.empty:
        raise ValueError("Missing or invalid post timestamps.")
    posts["day"] = posted.dt.normalize()
    posts["Network"] = posts["Network"].str.lower()
    keys = ["Network", "Account", "ID"]
    if posts[keys].isna().any().any() or posts.duplicated(keys).any():
        raise ValueError("Missing or duplicate platform, account, or post identifiers.")
    deleted = posts["Is Deleted"].str.lower()
    if not deleted.isin(["true", "false"]).all():
        raise ValueError("Missing or invalid deletion flags.")
    first, last = posts["day"].min(), posts["day"].max()
    posts["Cluster"] = [
        social_label(platform, account)[0]
        for platform, account in zip(posts["Network"], posts["Account"])
    ]
    in_scope = posts["Cluster"].isin(["LA Local", "Long Beach"])
    keep = in_scope & deleted.eq("false")
    excluded = posts.loc[~keep].copy()
    excluded["Exclusion reason"] = in_scope.loc[excluded.index].map({
        True: "Deleted network post", False: "Out-of-scope account"
    })
    return posts.loc[keep].copy(), first, last, excluded


def platform_metrics(posts, platform):
    df = posts.loc[posts["Network"].eq(platform.lower())].copy()
    is_story = df["Type"].str.lower().eq("story")
    for name, (regular, story) in FIELDS[platform].items():
        raw = df[regular].where(~is_story, df[story])
        values = pd.to_numeric(raw, errors="coerce")
        df[name] = values.where(values.ge(0) & values.mod(1).eq(0))
    return df


def period_label(start, days):
    end = start + pd.Timedelta(days=days - 1)
    return f"{start:%b %d, %Y}" if days == 1 else f"{start:%b %d} – {end:%b %d, %Y}"


def summarize(posts, metrics):
    totals = {"Posts": len(posts)}
    for metric in metrics:
        values = posts[metric]
        totals[metric] = None if values.isna().any() else int(values.sum())
    return totals


def compare(current, prior):
    rows = []
    for metric, value in current.items():
        previous = prior[metric]
        change = None if value is None or previous is None else value - previous
        rows.append({
            "Metric": metric,
            "Current": "Unavailable" if value is None else f"{value:,}",
            "Prior": "Unavailable" if previous is None else f"{previous:,}",
            "Change": "Unavailable" if change is None else f"{change:+,}",
            "% change": f"{change / previous:+.1%}" if previous and change is not None else "Unavailable",
        })
    return pd.DataFrame(rows)


st.title("Social audience")

report_tab, dictionary_tab = st.tabs(["Dashboard", "Metric dictionary"])

with dictionary_tab:
    st.markdown("""
**Source and scope.** Social News Desk’s `data_folder/social_posts_snd.csv`.
`Network` selects Facebook or Instagram. The combination of `Network` and
`Account` maps each post to LA Local or Long Beach. Network totals combine both
clusters within the selected platform. `Post Time` assigns a post to a day or
Sunday–Saturday week. `Type` identifies Instagram Stories, which are excluded
because their metric coverage is incomplete.

| Dashboard metric | Facebook column | Instagram feed and reels column | Definition and type |
|---|---|---|---|
| Posts | `ID` | `ID` | Count of eligible post records, validated by platform, account, and ID. Flow by publish period. |
| Views | `Views` | `IG Views` | Sum of views recorded for posts published in the period. Flow across posts. Used in the trend chart. |
| Engagements | `Total Engagement` | `IG Engagement` | Sum of the platform’s reported post engagements. Flow across posts. Individual values rank the YTD Top 10. |
| Link clicks | `Link Clicks` | Unavailable on this page | Sum of reported Facebook link clicks. Flow across posts. |
| Summed post reach | Unavailable on this page | `IG Reach` | Sum of the reach recorded for each Instagram post. Summed count across posts; the same person can count on several posts. |
| Excluded posts | `Network`, `Account`, `Is Deleted` | Same fields | Counts across the full export by exclusion reason. Out-of-scope accounts are outside the configured network mapping. Deleted network posts carry the source deletion flag. |

**Comparison and ranking.** Change = current minus prior. Percent change =
change divided by prior. Missing required metric values make the affected total
unavailable. Views and engagements reflect counts as of the export for posts
published in the selected period. The YTD Top 10 screens `Post` text and `Link`
for paid markers before ranking by engagements.
### Formulas for each comparison row

Current means the selected day or Sunday–Saturday week. Prior means the immediately preceding day or week.

| Metric | Current | Prior | Change | Relative change (%) |
|---|---|---|---|---|
| Posts | count of eligible post rows published in Current | count of eligible post rows published in Prior | Posts (Current) − Posts (Prior) | (Posts (Current) − Posts (Prior)) ÷ Posts (Prior) × 100 |
| Facebook engagements | sum(`Total Engagement` in Current) | sum(`Total Engagement` in Prior) | Facebook engagements (Current) − Facebook engagements (Prior) | (Facebook engagements (Current) − Facebook engagements (Prior)) ÷ Facebook engagements (Prior) × 100 |
| Facebook views | sum(`Views` in Current) | sum(`Views` in Prior) | Facebook views (Current) − Facebook views (Prior) | (Facebook views (Current) − Facebook views (Prior)) ÷ Facebook views (Prior) × 100 |
| Facebook link clicks | sum(`Link Clicks` in Current) | sum(`Link Clicks` in Prior) | Facebook link clicks (Current) − Facebook link clicks (Prior) | (Facebook link clicks (Current) − Facebook link clicks (Prior)) ÷ Facebook link clicks (Prior) × 100 |
| Instagram engagements | sum(`IG Engagement` in Current) | sum(`IG Engagement` in Prior) | Instagram engagements (Current) − Instagram engagements (Prior) | (Instagram engagements (Current) − Instagram engagements (Prior)) ÷ Instagram engagements (Prior) × 100 |
| Instagram views | sum(`IG Views` in Current) | sum(`IG Views` in Prior) | Instagram views (Current) − Instagram views (Prior) | (Instagram views (Current) − Instagram views (Prior)) ÷ Instagram views (Prior) × 100 |
| Instagram summed post reach | sum(`IG Reach` in Current) | sum(`IG Reach` in Prior) | Instagram summed post reach (Current) − Instagram summed post reach (Prior) | (Instagram summed post reach (Current) − Instagram summed post reach (Prior)) ÷ Instagram summed post reach (Prior) × 100 |
""")
    st.subheader("Account-to-cluster mapping")
    st.dataframe(pd.DataFrame([
        {"Network": platform, "Account": account, "Cluster": cluster, "Edition": edition}
        for (platform, account), (cluster, edition) in SOCIAL_ACCOUNTS.items()
    ]), hide_index=True)

with report_tab:
    try:
        posts, first, last, excluded = load_posts()
    except (OSError, ValueError) as error:
        st.error(f"Social export could not be loaded: {error}")
        st.stop()

    view = st.radio("Reporting frequency", ["Daily", "Weekly"], horizontal=True)
    platform = st.radio("Platform", list(FIELDS), horizontal=True)
    scope = st.selectbox("Cluster", ["Network", "LA Local", "Long Beach"])
    days = 1 if view == "Daily" else 7
    step = pd.Timedelta(days=days)
    periods = pd.date_range(first, last - pd.Timedelta(days=days - 1),
                            freq="D" if days == 1 else "W-SUN")
    choices = [date for date in reversed(periods) if date - step >= first]
    if not choices:
        st.warning("The export does not cover two comparable periods.")
        st.stop()

    current = st.selectbox("Reporting period", choices,
                           format_func=lambda start: period_label(start, days))
    prior = current - step
    selected = platform_metrics(posts, platform)
    if scope != "Network":
        selected = selected.loc[selected["Cluster"].eq(scope)]

    report_scope = f"{platform} · {scope}"
    if platform == "Instagram":
        selected = selected.loc[~selected["Type"].str.lower().eq("story").fillna(False)]
        report_scope += " · Feed and reels"
        st.caption("Instagram Stories are excluded because their metrics are incomplete.")

    current_posts = selected.loc[selected["day"].ge(current) & selected["day"].lt(current + step)]
    prior_posts = selected.loc[selected["day"].ge(prior) & selected["day"].lt(current)]

    st.caption(f"{report_scope} · Current {period_label(current, days)} "
               f"· Prior {period_label(prior, days)}")
    st.caption("Metrics reflect the performance of posts published in each period, "
               "as recorded at export time.")
    coverage = pd.DataFrame([
        {"Metric": metric,
         "Current posts reporting": f"{current_posts[metric].count():,} / {len(current_posts):,}",
         "Prior posts reporting": f"{prior_posts[metric].count():,} / {len(prior_posts):,}"}
        for metric in FIELDS[platform]
        if current_posts[metric].isna().any() or prior_posts[metric].isna().any()
    ])
    if not coverage.empty:
        st.warning("Some posts are missing metrics. Affected totals are unavailable; "
                   "rankings include only posts with reported engagements.")
        with st.expander("Metric coverage for selected periods"):
            st.dataframe(coverage, hide_index=True)

    st.dataframe(compare(summarize(current_posts, FIELDS[platform]),
                         summarize(prior_posts, FIELDS[platform])), hide_index=True)

    chart_periods = periods[periods <= current]
    chart_scopes = (
        {"LA Local": selected.loc[selected["Cluster"].eq("LA Local")],
         "Long Beach": selected.loc[selected["Cluster"].eq("Long Beach")],
         "Network total": selected}
        if scope == "Network" else {scope: selected}
    )
    trend = pd.DataFrame({
        label: [
            summarize(frame.loc[frame["day"].ge(start) & frame["day"].lt(start + step)],
                      ["Views"])["Views"]
            for start in chart_periods
        ]
        for label, frame in chart_scopes.items()
    }, index=chart_periods)
    trend.index.name = "Period start"
    st.subheader(f"{view} views")
    st.caption(f"{report_scope} · {period_label(periods[0], days)} "
               f"through {period_label(current, days)}")
    missing_periods = int(trend.isna().any(axis=1).sum())
    if missing_periods:
        st.caption(
            f"All view series are complete for {len(trend) - missing_periods} of "
            f"{len(trend)} periods. Gaps indicate missing post metrics."
        )
    if trend.isna().all().all():
        st.info("No complete view totals are available in this date range.")
    else:
        views_chart(trend)

    st.subheader("Top 10 posts by engagements · Year to date")
    year_start = pd.Timestamp(year=last.year, month=1, day=1)
    ranking_start = max(first, year_start)
    st.caption(f"{report_scope} · {ranking_start:%b %d, %Y} – {last:%b %d, %Y}. "
               "Post text and links are screened for explicit paid-content markers.")
    year_posts = selected.loc[selected["day"].ge(ranking_start)]
    paid = (
        year_posts["Post"].str.contains(PAID_MARKER, case=False, na=False)
        | year_posts["Link"].str.contains(PAID_MARKER, case=False, na=False)
    )
    top = year_posts.loc[~paid & year_posts["Engagements"].notna()].sort_values(
        ["Engagements", "day", "ID"], ascending=[False, False, True]
    ).head(10).copy()
    if top.empty:
        st.info("No posts with reported engagements are eligible for ranking.")
    else:
        top["Post"] = top["Post"].str.slice(0, 160)
        st.dataframe(top[["Cluster", "Account", "Type", "Post", "Link", "Engagements", "Views"]],
                     hide_index=True)

    with st.expander("Social metric definitions and data checks"):
        st.markdown(
            "**Source and grain.** Social News Desk post export, grouped by publish date "
            "or Sunday–Saturday week. Posts and reported interactions and views are "
            "counts across posts. Network totals combine the two clusters within the "
            "selected platform.\n\n"
            "**Facebook.** Engagements, views, and link clicks use Total Engagement, "
            "Views, and Link Clicks. The deprecated Facebook reach field is omitted.\n\n"
            "**Instagram.** Feed and reel metrics use IG Engagement, IG Views, and "
            "IG Reach. Instagram Stories are excluded. Summed post reach can count "
            "someone more than once.\n\n"
            "**Coverage.** The earliest and latest post dates bound the reporting "
            "window. Within that window a day with no records is treated as zero posts. "
            "An aggregate is unavailable when an included post lacks the metric. "
            "Paid posts without a recognizable marker can still appear in the ranking."
        )
    counts = excluded["Exclusion reason"].value_counts()
    outside = counts.get("Out-of-scope account", 0)
    deleted = counts.get("Deleted network post", 0)
    st.caption(f"Export dates {first:%b %d, %Y} – {last:%b %d, %Y}. "
               f"Excluded {outside:,} out-of-scope posts and {deleted:,} network posts "
               "marked deleted in Social News Desk. The data team only excludes these "
               "records from reporting.")

    with st.expander("Excluded posts across the full export"):
        if excluded.empty:
            st.info("No out-of-scope or deleted network posts were found.")
        else:
            display_columns = [
                "Exclusion reason", "Post Time", "Network", "Account", "Type", "ID", "Link"
            ]
            st.dataframe(
                excluded.sort_values(["Exclusion reason", "day"], ascending=[True, False])[
                    display_columns
                ],
                hide_index=True,
            )
