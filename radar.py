import os
import re
import smtplib
import feedparser
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parsedate_to_datetime


EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_TO = os.environ["EMAIL_TO"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

MAX_ARTICLES_PER_FEED = 15
MAX_AGE_DAYS = 10
MAX_ITEMS_PER_SECTION = 5


SECTION_RULES = {
    "fed": [
        "federal reserve", "fomc", "fed ", " fed", "powell", "waller",
        "bowman", "bostic", "barr", "beige book", "federal funds",
        "discount rate", "fomc minutes", "board of governors"
    ],
    "ecb": [
        "ecb", "european central bank", "lagarde", "lane", "schnabel",
        "de guindos", "panetta", "villeroy", "nagel", "governing council",
        "euro area", "eurosystem"
    ],
    "boe": [
        "bank of england", "boe", "bailey", "mpc", "bank rate",
        "monetary policy committee", "uk inflation", "sterling"
    ],
    "boj": [
        "bank of japan", "boj", "ueda", "jgb", "yield curve control",
        "japan inflation", "yen", "tokyo cpi"
    ],
    "us_policy": [
        "white house", "congress", "senate", "house of representatives",
        "us treasury", "treasury department", "treasury", "ustr",
        "united states trade representative", "debt ceiling", "tariff",
        "tariffs", "budget", "deficit", "fiscal", "sanctions",
        "government shutdown", "tax bill", "public debt", "auction",
        "trade representative", "export controls", "section 301",
        "chips", "critical minerals"
    ],
    "europe_policy": [
        "european commission", "european council", "european parliament",
        "eurogroup", "ecofin", "eu fiscal rules", "stability and growth pact",
        "germany budget", "france budget", "italy budget",
        "sanctions", "energy policy", "defence spending", "defense spending",
        "state aid", "single market", "industrial policy", "green deal",
        "trade defence", "trade defense", "critical raw materials",
        "ukraine facility", "enlargement", "migration pact"
    ],
    "global_geopolitics": [
        "china", "taiwan", "south china sea", "yuan", "renminbi",
        "beijing", "hong kong", "semiconductor", "export controls",
        "iran", "israel", "gaza", "red sea", "houthi", "houthis",
        "saudi", "opec", "opec+", "strait of hormuz", "oil supply",
        "gulf", "qatar", "uae", "iraq", "syria", "lebanon",
        "russia", "ukraine", "black sea", "russian oil", "russian gas",
        "grain corridor", "sanctions", "suez", "panama canal",
        "shipping", "freight", "supply chain", "supply chains",
        "argentina", "turkey", "brazil", "mexico", "south africa",
        "india", "indonesia", "imf program", "capital controls",
        "sovereign debt", "default", "currency crisis", "food security",
        "nuclear", "iaea", "uranium", "energy security"
    ],
}


SIGNAL_RULES = {
    "policy_decision": [
        "rate decision", "policy decision", "maintained", "raised",
        "lowered", "cut rates", "hiked", "bank rate", "policy rate",
        "interest rates", "monetary policy decision"
    ],
    "policy_signal": [
        "minutes", "speech", "interview", "remarks", "testimony",
        "press conference", "governing council", "fomc", "reaction function",
        "forward guidance", "monetary policy"
    ],
    "inflation_labor": [
        "inflation", "cpi", "core cpi", "pce", "prices", "wage", "wages",
        "employment", "unemployment", "payrolls", "labor market",
        "labour market", "inflation expectations"
    ],
    "growth_activity": [
        "gdp", "growth", "activity", "output", "pmi", "retail sales",
        "industrial production", "recession", "survey", "confidence"
    ],
    "fiscal_sovereign": [
        "fiscal", "budget", "deficit", "debt", "sovereign",
        "treasury issuance", "bond auction", "government bonds",
        "asset purchase facility", "rating"
    ],
    "financial_stability": [
        "financial stability", "vulnerabilities", "banking stress",
        "credit conditions", "liquidity", "leverage", "stress test",
        "macroprudential", "commercial real estate"
    ],
    "geopolitical_macro": [
        "oil", "gas", "energy", "shipping", "freight", "sanctions",
        "tariffs", "trade", "supply chain", "supply chains", "fx",
        "currency", "risk premium", "safe haven", "commodities",
        "inflation", "food prices", "grain", "nuclear", "uranium",
        "export controls", "critical minerals", "semiconductors",
        "capital flows", "sovereign", "debt", "default"
    ],
    "market_plumbing": [
        "payments", "settlement", "clearing", "collateral", "repo",
        "tokenisation", "tokenization", "cbdc", "resolution", "ring-fence",
        "derivatives", "otc"
    ],
    "low_signal": [
        "enforcement action", "former employee", "statistical notice",
        "user acceptance testing", "taxonomy", "conversion of",
        "does not object", "court of directors"
    ],
}


SECTION_LABELS = {
    "fed": "Fed",
    "ecb": "ECB",
    "boe": "BOE",
    "boj": "BOJ",
    "us_policy": "US policy risk",
    "europe_policy": "Europe policy risk",
    "global_geopolitics": "Global geopolitics",
    "other": "Other macro"
}


SIGNAL_LABELS = {
    "policy_decision": "Policy decision",
    "policy_signal": "Policy signal",
    "inflation_labor": "Inflation / labor",
    "growth_activity": "Growth / activity",
    "fiscal_sovereign": "Fiscal / sovereign",
    "financial_stability": "Financial stability",
    "geopolitical_macro": "Geopolitical macro channel",
    "market_plumbing": "Market plumbing",
    "low_signal": "Low signal",
    "other": "Other"
}


WHY_IT_MATTERS = {
    "policy_decision": "Formal policy decisions directly affect the expected path of rates and the credibility of the central bank reaction function.",
    "policy_signal": "Central-bank communication can shift expectations even when there is no formal rate decision.",
    "inflation_labor": "Inflation and labor-market evidence drive the trade-off between keeping policy restrictive and starting or extending rate cuts.",
    "growth_activity": "Growth data matter because they determine whether central banks can focus on inflation or must respond to weaker demand.",
    "fiscal_sovereign": "Fiscal news can affect bond supply, sovereign spreads, term premium and market confidence in public finances.",
    "financial_stability": "Financial-stability signals matter when high rates, leverage or geopolitical shocks start to threaten the transmission of policy.",
    "geopolitical_macro": "Geopolitical events matter for macro when they transmit through energy, trade, inflation, FX, commodities or risk sentiment.",
    "market_plumbing": "Market-structure items rarely move markets immediately, but they matter for liquidity, regulation, payments and systemic resilience.",
    "low_signal": "This is mostly procedural or institution-specific and is unlikely to change the macro narrative unless it escalates.",
    "other": "This item is macro-relevant but does not yet have a clear high-conviction transmission channel."
}


def load_feeds(path="feeds.txt"):
    with open(path, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def parse_entry_date(entry):
    raw_date = entry.get("published") or entry.get("updated")
    if not raw_date:
        return None
    try:
        return parsedate_to_datetime(raw_date)
    except Exception:
        return None


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def match_terms(text, terms):
    text = text.lower()
    return any(term.lower() in text for term in terms)


def detect_sections(title, summary, source):
    text = f"{title} {summary} {source}".lower()
    sections = []

    for section, terms in SECTION_RULES.items():
        if match_terms(text, terms):
            sections.append(section)

    return sections or ["other"]


def detect_signal_type(title, summary, source):
    text = f"{title} {summary} {source}".lower()

    if match_terms(text, SIGNAL_RULES["low_signal"]):
        return "low_signal"

    priority = [
        "policy_decision",
        "policy_signal",
        "inflation_labor",
        "financial_stability",
        "fiscal_sovereign",
        "geopolitical_macro",
        "growth_activity",
        "market_plumbing",
    ]

    for signal in priority:
        if match_terms(text, SIGNAL_RULES[signal]):
            return signal

    return "other"


def has_macro_geopolitical_channel(title, summary, source):
    text = f"{title} {summary} {source}".lower()
    has_geo = match_terms(text, SECTION_RULES["global_geopolitics"])
    has_channel = match_terms(text, SIGNAL_RULES["geopolitical_macro"])
    return has_geo and has_channel


def score_article(article):
    score = 0
    signal = article["signal_type"]
    sections = article["sections"]

    signal_boost = {
        "policy_decision": 18,
        "policy_signal": 13,
        "inflation_labor": 12,
        "financial_stability": 11,
        "fiscal_sovereign": 10,
        "geopolitical_macro": 10,
        "growth_activity": 8,
        "market_plumbing": 4,
        "other": 1,
        "low_signal": -8,
    }
    score += signal_boost.get(signal, 0)

    if "fed" in sections:
        score += 8
    if "ecb" in sections:
        score += 7
    if "boe" in sections:
        score += 3
    if "boj" in sections:
        score += 3
    if "us_policy" in sections:
        score += 5
    if "europe_policy" in sections:
        score += 5
    if "global_geopolitics" in sections and has_macro_geopolitical_channel(
        article["title"], article["summary"], article["source"]
    ):
        score += 6

    source_lower = article["source"].lower()
    if any(
        official in source_lower
        for official in [
            "federal reserve",
            "european central bank",
            "bank of england",
            "bank of japan",
            "imf",
            "bis",
            "oecd",
        ]
    ):
        score += 3

    published_dt = article["published_dt"]
    if published_dt:
        now = datetime.now(timezone.utc)
        age_days = (now - published_dt.astimezone(timezone.utc)).days
        if age_days <= 1:
            score += 6
        elif age_days <= 3:
            score += 4
        elif age_days <= 7:
            score += 2
        elif age_days > MAX_AGE_DAYS:
            score -= 10

    return score


def fetch_articles(feed_urls):
    articles = []
    now = datetime.now(timezone.utc)

    for feed_url in feed_urls:
        feed = feedparser.parse(feed_url)
        source = feed.feed.get("title", feed_url)

        for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
            title = clean_text(entry.get("title", ""))
            summary = clean_text(entry.get("summary", ""))
            link = entry.get("link", "").strip()
            published = entry.get("published") or entry.get("updated") or ""
            published_dt = parse_entry_date(entry)

            if not title or not link:
                continue

            if published_dt:
                age = now - published_dt.astimezone(timezone.utc)
                if age > timedelta(days=MAX_AGE_DAYS):
                    continue

            sections = detect_sections(title, summary, source)
            signal_type = detect_signal_type(title, summary, source)

            article = {
                "source": source,
                "title": title,
                "summary": summary,
                "link": link,
                "published": published,
                "published_dt": published_dt,
                "sections": sections,
                "signal_type": signal_type,
                "score": 0,
            }
            article["score"] = score_article(article)
            articles.append(article)

    return dedupe_and_sort(articles)


def dedupe_and_sort(articles):
    seen = set()
    deduped = []

    for article in articles:
        key = re.sub(r"[^a-z0-9]+", " ", article["title"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(article)

    deduped.sort(
        key=lambda x: (
            x["score"],
            x["published_dt"] or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True
    )
    return deduped


def primary_section(article):
    priority = [
        "fed",
        "ecb",
        "boe",
        "boj",
        "us_policy",
        "europe_policy",
        "global_geopolitics",
        "other",
    ]
    for section in priority:
        if section in article["sections"]:
            return section
    return "other"


def articles_for_section(articles, section, limit=MAX_ITEMS_PER_SECTION, min_score=None):
    items = [a for a in articles if section in a["sections"]]
    if min_score is not None:
        items = [a for a in items if a["score"] >= min_score]
    return items[:limit]


def build_item_block(article):
    summary = article["summary"]
    if summary:
        summary = summary[:350].rsplit(" ", 1)[0] + ("..." if len(summary) > 350 else "")
    else:
        summary = "The source feed does not provide a summary; the item is flagged from the title, source and metadata."

    signal_label = SIGNAL_LABELS.get(article["signal_type"], "Other")
    why = WHY_IT_MATTERS.get(article["signal_type"], WHY_IT_MATTERS["other"])

    return (
        f"**{article['title']}**\n"
        f"Source: {article['source']} | Signal: {signal_label}\n"
        f"What happened: {summary}\n"
        f"Why it matters: {why}\n"
        f"Link: {article['link']}\n"
    )


def build_short_item(article):
    signal_label = SIGNAL_LABELS.get(article["signal_type"], "Other")
    return (
        f"- **{article['title']}** "
        f"({article['source']} | {signal_label})\n"
        f"  {article['link']}"
    )


def best_item_for_sections(articles, sections):
    candidates = [a for a in articles if any(s in a["sections"] for s in sections)]
    return candidates[0] if candidates else None


def build_subtitle(articles):
    fed = best_item_for_sections(articles, ["fed"])
    ecb = best_item_for_sections(articles, ["ecb"])
    geo = best_item_for_sections(articles, ["global_geopolitics"])

    if fed and fed["score"] >= 12:
        return "Fed remains the main radar line; the key question is whether the latest flow changes the expected path of rates."
    if ecb and ecb["score"] >= 12:
        return "ECB communication dominates today’s official flow, with markets focused on policy guidance and financial-stability signals."
    if geo and geo["score"] >= 12:
        return "The main non-central-bank risk comes from geopolitics, but only where it transmits into energy, trade, FX or risk sentiment."
    return "Today’s macro flow is mostly incremental: useful for monitoring, but not a clear policy turning point."


def build_three_things(articles):
    fed = best_item_for_sections(articles, ["fed"])
    ecb = best_item_for_sections(articles, ["ecb"])
    geo = best_item_for_sections(articles, ["us_policy", "europe_policy", "global_geopolitics"])

    lines = []

    if fed:
        lines.append(f"Fed: {fed['title']}")
    else:
        lines.append("Fed: no high-signal Fed item was detected in the configured feeds.")

    if ecb:
        lines.append(f"ECB: {ecb['title']}")
    else:
        lines.append("ECB: no high-signal ECB item was detected in the configured feeds.")

    if geo:
        lines.append(f"Policy/geopolitics: {geo['title']}")
    else:
        lines.append("Watch next: the next central-bank speech, minutes or inflation/labor release.")

    return lines[:3]


def build_institution_section(title, items):
    body = []
    body.append(f"## {title}")
    body.append("")

    if not items:
        body.append("No relevant item detected from the configured feeds.")
        body.append("")
        return body

    main = items[0]
    body.append("### Main signal")
    body.append(build_item_block(main))
    body.append("")

    others = items[1:]
    if others:
        body.append("### Other related items")
        for article in others:
            body.append(build_short_item(article))
        body.append("")

    body.append("### Reading")
    body.append(
        "The key question is whether this changes the policy reaction function, "
        "the expected timing of rate moves, or the balance between inflation risk and growth risk."
    )
    body.append("")

    return body


def build_boe_boj_section(articles):
    body = []
    body.append("## 3. BOE / BOJ")
    body.append("")

    boe_items = articles_for_section(articles, "boe", limit=3, min_score=5)
    boj_items = articles_for_section(articles, "boj", limit=3, min_score=5)

    body.append("### BOE")
    if boe_items:
        for item in boe_items:
            body.append(build_short_item(item))
    else:
        body.append("No high- or medium-signal BOE item detected.")
    body.append("")

    body.append("### BOJ")
    if boj_items:
        for item in boj_items:
            body.append(build_short_item(item))
    else:
        body.append("No high- or medium-signal BOJ item detected.")
    body.append("")

    body.append("### Reading")
    body.append(
        "BOE and BOJ items are included selectively: they matter most when they change the inflation, wage, currency or normalization story."
    )
    body.append("")

    return body


def build_policy_section(articles):
    body = []
    body.append("## 4. US & Europe policy risk")
    body.append("")

    us_items = articles_for_section(articles, "us_policy", limit=4, min_score=5)
    eu_items = articles_for_section(articles, "europe_policy", limit=4, min_score=5)

    body.append("### United States")
    if us_items:
        for item in us_items:
            body.append(build_short_item(item))
    else:
        body.append("No relevant US policy-risk item detected.")
    body.append("")

    body.append("### Europe")
    if eu_items:
        for item in eu_items:
            body.append(build_short_item(item))
    else:
        body.append("No relevant Europe policy-risk item detected.")
    body.append("")

    body.append("### Reading")
    body.append(
        "Policy risk matters for macro only when it has a clear transmission channel: fiscal policy, tariffs, sanctions, energy, sovereign risk or central-bank independence."
    )
    body.append("")

    return body


def build_global_geopolitics_section(articles):
    body = []
    body.append("## 5. Global geopolitics")
    body.append("")

    geo_items = [
        a for a in articles_for_section(articles, "global_geopolitics", limit=8, min_score=5)
        if has_macro_geopolitical_channel(a["title"], a["summary"], a["source"])
    ]

    if not geo_items:
        body.append(
            "No global geopolitical item with a clear macro channel was detected. "
            "This section only includes events that can transmit through energy, trade, shipping, FX, commodities, sovereign risk or risk sentiment."
        )
        body.append("")
        return body

    for item in geo_items[:5]:
        body.append(build_item_block(item))
        body.append("")

    return body


def build_signal_vs_noise(articles):
    body = []
    body.append("## 6. Signal vs noise")
    body.append("")

    signals = [a for a in articles if a["score"] >= 14 and a["signal_type"] != "low_signal"][:5]
    noise = [a for a in articles if a["score"] < 6 or a["signal_type"] == "low_signal"][:5]

    body.append("### Signal")
    if signals:
        for item in signals:
            body.append(
                f"- **{item['title']}**: signal because it is classified as "
                f"{SIGNAL_LABELS.get(item['signal_type'], 'Other')} and comes from {item['source']}."
            )
    else:
        body.append("- No high-signal item detected.")
    body.append("")

    body.append("### Noise / lower signal")
    if noise:
        for item in noise:
            body.append(
                f"- **{item['title']}**: lower signal unless it later connects to rates, inflation, FX, fiscal risk or financial stability."
            )
    else:
        body.append("- No obvious low-signal items detected.")
    body.append("")

    return body


def build_what_to_watch_next(articles):
    body = []
    body.append("## 7. What to watch next")
    body.append("")

    body.append("### Main central-bank events")
    body.append("- Fed: next FOMC communication, minutes, speeches, Beige Book or inflation/labor data that affect the dual mandate.")
    body.append("- ECB: next Governing Council communication, inflation data, wage evidence or financial-stability update.")
    body.append("- BOE: next MPC communication, CPI, wage or labor-market release.")
    body.append("- BOJ: next inflation, wage, JGB or yen-related signal relevant to normalization.")
    body.append("")

    body.append("### Policy and geopolitical catalysts")
    body.append("- US: fiscal deadlines, debt issuance, tariffs, sanctions and central-bank independence issues.")
    body.append("- Europe: EU fiscal rules, sanctions, energy policy, defense spending and sovereign-spread risk.")
    body.append("- Global: oil, Red Sea / shipping, China-Taiwan, Russia-Ukraine, OPEC+ and EM sovereign stress.")
    body.append("")

    body.append("### From today’s source flow")
    watch_items = [a for a in articles if a["score"] >= 10][:5]
    if watch_items:
        for item in watch_items:
            body.append(f"- Follow-up on: **{item['title']}**")
    else:
        body.append("- No specific follow-up item detected from today’s source flow.")
    body.append("")

    return body


def build_email_body(articles):
    today = datetime.now().strftime("%d/%m/%Y")

    body = []
    body.append(f"# Macro Radar | {today}")
    body.append("")
    body.append(build_subtitle(articles))
    body.append("")

    body.append("## Three things to know")
    for line in build_three_things(articles):
        body.append(f"- {line}")
    body.append("")

    fed_items = articles_for_section(articles, "fed", limit=MAX_ITEMS_PER_SECTION, min_score=5)
    ecb_items = articles_for_section(articles, "ecb", limit=MAX_ITEMS_PER_SECTION, min_score=5)

    body.extend(build_institution_section("1. Fed", fed_items))
    body.extend(build_institution_section("2. ECB", ecb_items))
    body.extend(build_boe_boj_section(articles))
    body.extend(build_policy_section(articles))
    body.extend(build_global_geopolitics_section(articles))
    body.append("## Method note")
    body.append("")
    body.append(
        "This email is generated without AI or paid APIs. It uses RSS feeds, keyword classification, "
        "recency filters and rule-based scoring. It is a curated radar, not a full analyst note."
    )

    return "\n".join(body)


def send_email(subject, body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)


def main():
    feeds = load_feeds()
    articles = fetch_articles(feeds)
    body = build_email_body(articles)

    today = datetime.now().strftime("%d/%m/%Y")
    subject = f"Macro Radar | {today}"

    send_email(subject, body)


if __name__ == "__main__":
    main()
