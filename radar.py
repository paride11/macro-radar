import os
import re
import smtplib
import feedparser
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parsedate_to_datetime


EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_TO = os.environ["EMAIL_TO"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))


KEYWORDS = {
    "Fed / FOMC": [
        "fed", "federal reserve", "fomc", "powell", "dot plot",
        "federal funds", "beige book"
    ],
    "ECB": [
        "ecb", "european central bank", "lagarde", "euro area",
        "monetary policy account", "governing council"
    ],
    "BOE": [
        "bank of england", "boe", "bailey", "monetary policy committee",
        "mpc", "uk inflation"
    ],
    "BOJ": [
        "bank of japan", "boj", "ueda", "yield curve control",
        "japan inflation"
    ],
    "Inflation": [
        "inflation", "cpi", "core cpi", "pce", "prices",
        "disinflation", "wages", "price stability"
    ],
    "Growth / labor": [
        "growth", "gdp", "recession", "employment", "unemployment",
        "payrolls", "labor market", "labour market", "wages",
        "activity", "output", "pmi"
    ],
    "Rates / bonds": [
        "rates", "rate cut", "rate hike", "yields", "yield",
        "treasury", "bond", "bonds", "curve", "term premium"
    ],
    "Fiscal / sovereign": [
        "fiscal", "budget", "deficit", "debt", "sovereign",
        "treasury issuance", "auction", "spread"
    ],
    "FX": [
        "fx", "currency", "dollar", "euro", "yen", "sterling",
        "exchange rate"
    ],
    "International institutions": [
        "imf", "bis", "oecd", "world bank", "financial stability",
        "global economy"
    ],
}


HIGH_VALUE_TERMS = [
    "monetary policy", "interest rate", "inflation", "cpi", "pce",
    "fomc", "governing council", "policy rate", "rate cut", "rate hike",
    "financial stability", "gdp", "labor market", "unemployment",
    "fiscal", "debt", "deficit", "sovereign", "bond", "yield"
]


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
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def classify_article(title, summary, source):
    text = f"{title} {summary} {source}".lower()
    categories = []

    for category, terms in KEYWORDS.items():
        if any(term.lower() in text for term in terms):
            categories.append(category)

    return categories or ["Other macro"]


def score_article(title, summary, source, categories):
    text = f"{title} {summary} {source}".lower()

    score = 0
    score += len(categories) * 2

    for term in HIGH_VALUE_TERMS:
        if term in text:
            score += 3

    official_sources = [
        "federal reserve", "european central bank", "bank of england",
        "bank of japan", "imf", "bis", "oecd"
    ]

    if any(src in source.lower() for src in official_sources):
        score += 3

    if any(cb in text for cb in ["fomc", "ecb", "boe", "boj", "policy rate"]):
        score += 4

    return score


def fetch_articles(feed_urls, max_articles_per_feed=10):
    articles = []

    for feed_url in feed_urls:
        feed = feedparser.parse(feed_url)
        source = feed.feed.get("title", feed_url)

        for entry in feed.entries[:max_articles_per_feed]:
            title = clean_text(entry.get("title", ""))
            summary = clean_text(entry.get("summary", ""))
            link = entry.get("link", "").strip()
            published = entry.get("published") or entry.get("updated") or ""
            published_dt = parse_entry_date(entry)

            if not title or not link:
                continue

            categories = classify_article(title, summary, source)
            score = score_article(title, summary, source, categories)

            articles.append({
                "source": source,
                "title": title,
                "summary": summary,
                "link": link,
                "published": published,
                "published_dt": published_dt,
                "categories": categories,
                "score": score,
            })

    seen = set()
    deduped = []

    for article in articles:
        key = article["title"].lower().strip()
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


def format_article(article, index):
    categories = ", ".join(article["categories"])
    summary = article["summary"]

    if len(summary) > 600:
        summary = summary[:600].rsplit(" ", 1)[0] + "..."

    return (
        f"{index}. {article['title']}\n"
        f"   Source: {article['source']}\n"
        f"   Published: {article['published']}\n"
        f"   Categories: {categories}\n"
        f"   Relevance score: {article['score']}\n"
        f"   Summary: {summary if summary else 'No summary available from feed.'}\n"
        f"   Link: {article['link']}\n"
    )


def group_by_category(articles):
    grouped = {}

    for article in articles:
        primary = article["categories"][0]
        grouped.setdefault(primary, []).append(article)

    return grouped


def build_email_body(articles):
    today = datetime.now().strftime("%d/%m/%Y")

    top_articles = articles[:12]
    grouped = group_by_category(articles[:40])

    body = []
    body.append(f"# Macro & Central Banks Radar | {today}")
    body.append("")
    body.append(
        "This is a rules-based macro and central bank news radar generated from RSS feeds. "
        "It does not use AI and does not infer facts beyond the source metadata."
    )
    body.append("")

    body.append("## Top flagged items")
    body.append("")

    if not top_articles:
        body.append("No articles were retrieved from the configured feeds today.")
    else:
        for idx, article in enumerate(top_articles, start=1):
            body.append(format_article(article, idx))

    body.append("")
    body.append("## By category")
    body.append("")

    for category, items in grouped.items():
        body.append(f"### {category}")
        body.append("")

        for article in items[:5]:
            body.append(f"- {article['title']} ({article['source']})")
            body.append(f"  {article['link']}")

        body.append("")

    body.append("## How to read this radar")
    body.append("")
    body.append(
        "- High scores usually indicate central bank, inflation, rates, labor market, "
        "fiscal, or sovereign-risk relevance."
    )
    body.append(
        "- This version does not provide AI interpretation. It is designed to surface "
        "the most relevant official-source items for manual review."
    )
    body.append(
        "- If a feed only publishes titles and no summaries, the email will be less informative."
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
    subject = f"Macro & Central Banks Radar | {today}"

    send_email(subject, body)


if __name__ == "__main__":
    main()
