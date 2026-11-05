import altair as alt
import streamlit as st

VIEWS_COLORS = {
    "LA Local": "#16447D",
    "Long Beach": "#63B9EF",
    "Network total": "#C92D39",
}


def views_chart(trend):
    """Plot selected cluster totals with a stable legend, even for one series."""
    clusters = trend.columns.tolist()
    data = trend.rename_axis("Period start").reset_index().melt(
        id_vars="Period start", var_name="Cluster", value_name="Views"
    )
    chart = alt.Chart(data).mark_line().encode(
        x=alt.X("Period start:T", title="Period start"),
        y=alt.Y("Views:Q", title="Views"),
        color=alt.Color(
            "Cluster:N",
            scale=alt.Scale(domain=clusters, range=[VIEWS_COLORS[name] for name in clusters]),
            legend=alt.Legend(title="Cluster"),
        ),
        tooltip=["Period start:T", "Cluster:N", "Views:Q"],
    )
    st.altair_chart(chart)
