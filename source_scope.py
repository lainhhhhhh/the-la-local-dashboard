"""Classify the packet exports using Context.docx and observed source labels."""

import argparse
import re

import pandas as pd

from metrics import clean_campaigns, load_packet

LA = "LA Local"
LB = "Long Beach"

WEB_PROPERTIES = {
    "TLL": (LA, "thelalocal.org"),
    "LBP": (LB, "lbpost.com"),
}

CONTACT_LISTS = {
    "The LA Local": "Central",
    "Koreatown, Pico Union and Westlake": "KPW",
    "Inglewood and South LA": "ISLA",
    "Boyle Heights Beat": "BHB",
}

SOCIAL_ACCOUNTS = {
    ("facebook", "The L.A. Local"): (LA, "Central"),
    ("instagram", "The LA Local"): (LA, "Central"),
    ("facebook", "LA Local: Koreatown Pico Union Westlake"): (LA, "KPW"),
    ("instagram", "Koreatown, Pico Union and Westlake"): (LA, "KPW"),
    ("facebook", "L.A. Local: South of the 10"): (LA, "ISLA"),
    ("instagram", "Inglewood and South LA"): (LA, "ISLA"),
    ("facebook", "Boyle Heights Beat"): (LA, "BHB"),
    ("instagram", "Boyle Heights Beat"): (LA, "BHB"),
    ("facebook", "Long Beach Post"): (LB, "Long Beach Post"),
    ("instagram", "Long Beach Post"): (LB, "Long Beach Post"),
    ("facebook", "Eat.See.Do"): (LB, "Eat.See.Do"),
    ("instagram", "Eat. See. Do: LB Food + Culture"): (LB, "Eat.See.Do"),
}

# These prefixes suggest an edition. Confirm actual recipient lists before
# reporting list metrics, especially when one campaign goes to multiple lists.
CAMPAIGN_HINTS = [
    (r"Central Newsletter\b", LA, "Central"),
    (r"KPW Newsletter\b", LA, "KPW"),
    (r"ISLA Newsletter\b", LA, "ISLA"),
    (r"BHB Newsletter\b", LA, "BHB"),
    (r"ESD[_ -]", LB, "Eat.See.Do"),
]


def campaign_hint(name):
    if pd.notna(name):
        for pattern, cluster, edition in CAMPAIGN_HINTS:
            if re.match(pattern, name, flags=re.IGNORECASE):
                return cluster, edition, "Inferred from campaign name"
    return "Unassigned", "Unassigned", "Needs list review"


def label_rows(df, labels):
    scope = pd.DataFrame(
        labels, index=df.index, columns=["cluster", "entity", "scope_status"]
    )
    return df.join(scope)


def social_label(platform, account):
    if pd.isna(platform) or pd.isna(account):
        return "Unassigned", account if pd.notna(account) else "Unknown", "Missing account or platform"
    if (platform, account) in SOCIAL_ACCOUNTS:
        cluster, edition = SOCIAL_ACCOUNTS[platform, account]
        return cluster, edition, "In scope"
    return "Outside network", account, "Not on network account list"


def classify_packet(start, end):
    tables, inventory = load_packet()
    scoped = {"Website": {}, "Newsletter": {}, "Contact": {}, "Social": {}}
    campaign_issues = pd.DataFrame()

    for name, df in tables.items():
        if name.startswith("web_ga4_"):
            property_code = name.rsplit("_", 1)[-1]
            cluster, site = WEB_PROPERTIES.get(property_code, ("Unassigned", property_code))
            status = "Needs property review" if cluster == "Unassigned" else "In scope"
            scoped["Website"][name] = df.assign(
                cluster=cluster, entity=site, scope_status=status
            )
        elif name == "nl_campaigns":
            campaigns, campaign_issues = clean_campaigns(df, start, end)
            scoped["Newsletter"][name] = label_rows(
                campaigns, [campaign_hint(value) for value in campaigns["Campaign Name"]]
            )
        elif name.startswith("nl_contacts_"):
            lists = df["List"].map(CONTACT_LISTS)
            scoped["Contact"][name] = df.assign(
                cluster=lists.notna().map({True: LA, False: "Unassigned"}),
                entity=lists.fillna("Unassigned"),
                scope_status=lists.notna().map({
                    True: "In scope", False: "Needs list review"
                }),
            )
        elif name == "social_posts_snd":
            df = df.assign(platform=df["Network"].str.lower())
            labels = [
                social_label(platform, account)
                for platform, account in zip(df["platform"], df["Account"])
            ]
            scoped["Social"][name] = label_rows(df, labels)

    return scoped, inventory, campaign_issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-10-31")
    args = parser.parse_args()

    scoped, inventory, campaign_issues = classify_packet(args.start, args.end)
    if inventory.empty:
        raise SystemExit("No exports found in data_folder.")

    for category, tables in scoped.items():
        print(f"\n{category}")
        if not tables:
            print("No supported exports loaded.")
            continue

        if category == "Website":
            # Different web grains are different views of the same traffic.
            rows = [
                {"export": name, "cluster": df["cluster"].iloc[0],
                 "property": df["entity"].iloc[0], "records": len(df)}
                for name, df in tables.items() if not df.empty
            ]
            print(pd.DataFrame(rows).to_string(index=False))
        else:
            rows = pd.concat(tables.values(), ignore_index=True)
            keys = ["cluster", "entity", "scope_status"]
            if category == "Social":
                keys.append("platform")
            print(rows.groupby(keys, dropna=False).size().rename("records").to_string())

    if not campaign_issues.empty:
        print("\nCampaign validation")
        print(campaign_issues.to_string(index=False))


if __name__ == "__main__":
    main()
