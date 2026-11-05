
import csv
import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data_folder"

WEB_DIMENSIONS = {
    "daily": ["Date"],
    "weekly": ["Week"],
    "monthly": ["Month"],
    "sources": [
        "Session primary channel group (Default Channel Group)",
        "Month",
    ],
    "pages": ["Page path and screen class"],
}
WEB_COUNTS = ["Active users", "New users", "Views", "Sessions", "Engaged sessions"]

CAMPAIGN_COUNTS = [
    "Emails Sent", "Unique Opens", "Unique clicks", "Bounces", "Unsubscribes"
]


def read_export(path, required_columns):
    """Find the real table header and preserve export metadata."""
    metadata = {}

    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line_number, row in enumerate(csv.reader(handle)):
            fields = [value.strip() for value in row]
            if set(required_columns).issubset(fields):
                header_line = line_number
                break

            if row and row[0].startswith("#") and ":" in row[0]:
                key, value = row[0].lstrip("# ").split(":", 1)
                metadata[key.strip()] = value.strip()
        else:
            raise ValueError(
                f"{path.name}: couldn't find a header with {required_columns}"
            )

    df = pd.read_csv(
        path,
        skiprows=header_line,
        dtype="string",
        encoding="utf-8-sig",
        keep_default_na=False,
    )
    df.columns = df.columns.str.strip()
    for column in df.columns:
        df[column] = df[column].str.strip().replace("", pd.NA)

    df["source_file"] = path.name
    df["source_record"] = range(1, len(df) + 1)
    return df, metadata


def load_packet(data_dir=DATA_DIR):
    """Return separate tables plus an inventory for review."""
    tables = {}
    inventory = []

    for path in sorted(data_dir.glob("*.csv")):
        if path.name.startswith("."):
            continue

        web = re.fullmatch(
            r"web_ga4_(daily|weekly|monthly|sources|pages)_([A-Za-z0-9]+)\.csv",
            path.name,
        )
        if web:
            kind, property_code = web.groups()
            required = WEB_DIMENSIONS[kind] + WEB_COUNTS
        elif path.name == "nl_campaigns.csv":
            kind, property_code = "campaigns", None
            required = ["Campaign Name", "Subject", "Sent Date"] + CAMPAIGN_COUNTS
        elif re.fullmatch(r"nl_contacts_.+\.csv", path.name):
            kind, property_code = "contacts", None
            required = [
                "Email code", "Contact ID", "List", "Status",
                "Date Subscribed", "Date Unsubscribed",
            ]
        elif path.name == "social_posts_snd.csv":
            kind, property_code = "social", None
            required = ["Post Time", "ID", "Account", "Network", "Type", "Is Deleted"]
        else:
            inventory.append({"file": path.name, "status": "Unrecognized export"})
            continue

        df, metadata = read_export(path, required)
        if property_code:
            df["property_code"] = property_code

        tables[path.stem] = df
        inventory.append({
            "file": path.name,
            "type": kind,
            "rows": len(df),
            "property": metadata.get("Property"),
            "declared_start": metadata.get("Start date"),
            "declared_end": metadata.get("End date"),
            "status": "Loaded",
        })

    return tables, pd.DataFrame(inventory)



def clean_campaigns(raw, start, end):
    df = raw.copy()
    issues = []

    def record_issue(mask, field, problem, handling):
        if mask.any():
            issues.append({
                "file": "nl_campaigns.csv",
                "field": field,
                "issue": problem,
                "rows": int(mask.sum()),
                "example_records": df.loc[mask, "source_record"].head(5).tolist(),
                "handling": handling,
            })

    sent_at = pd.to_datetime(
        df["Sent Date"], format="%Y-%m-%d %H:%M:%S", errors="coerce"
    )
    record_issue(
        sent_at.isna(), "Sent Date", "Missing or invalid send time",
        "Excluded from date-based analysis; review source records",
    )

    start = pd.Timestamp(start).normalize()
    stop = pd.Timestamp(end).normalize() + pd.Timedelta(days=1)
    in_window = sent_at.ge(start) & sent_at.lt(stop)
    record_issue(
        sent_at.notna() & ~in_window, "Sent Date", "Outside reporting window",
        "Kept in raw table; excluded from this analysis",
    )

    df["sent_at"] = sent_at
    for column in CAMPAIGN_COUNTS:
        values = pd.to_numeric(
            df[column].str.replace(",", "", regex=False), errors="coerce"
        )
        invalid = values.isna() | values.lt(0) | values.mod(1).ne(0)
        record_issue(
            in_window & invalid, column, "Missing or invalid count",
            "Flagged for review before publishing campaign metrics",
        )
        df[column] = values.mask(invalid).astype("Int64")

    return df.loc[in_window].copy(), pd.DataFrame(issues)

def audit_table(df, key_columns):
    """Summarize missing values and return rows flagged as duplicates."""
    provenance = ["source_file", "source_record"]
    data_columns = df.columns.difference(provenance).tolist()

    missing_count = df[data_columns].isna().sum()
    missing = (
        missing_count[missing_count.gt(0)]
        .rename("missing_rows")
        .rename_axis("column")
        .reset_index()
    )
    missing["percent_missing"] = (
        missing["missing_rows"].div(max(len(df), 1)).mul(100).round(2)
    )

    # keep=False shows every row in a duplicate group.
    exact_duplicates = df.loc[
        df.duplicated(subset=data_columns, keep=False)
    ].copy()

    # Check key completeness separately so blank IDs don't form duplicate groups.
    has_key = df[key_columns].notna().all(axis=1)
    missing_keys = df.loc[~has_key].copy()
    complete = df.loc[has_key]
    duplicate_keys = complete.loc[
        complete.duplicated(subset=key_columns, keep=False)
    ].sort_values(key_columns)

    return {
        "missing": missing,
        "missing_keys": missing_keys,
        "exact_duplicates": exact_duplicates,
        "duplicate_keys": duplicate_keys,
    }