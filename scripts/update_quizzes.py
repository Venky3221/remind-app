import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

def get_rss(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())

    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title")
        link = item.findtext("link")
        pub = item.findtext("pubDate")

        if title and link:
            items.append({
                "title": title.strip(),
                "link": link.strip(),
                "date": pub or ""
            })

    return items

def get_pib():
    return get_rss(
        "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1"
    )

def get_google_news(query):
    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode({
            "q": query,
            "hl": "en-IN",
            "gl": "IN",
            "ceid": "IN:en"
        })
    )
    return get_rss(url)

def make_questions(news, title, today):
    news = news[:5]

    questions = []

    for item in news:
        options = [x["title"] for x in news]

        questions.append({
            "q": f"Which headline was reported in {title} on {today}?",
            "o": options,
            "a": 0,
            "source": item["link"]
        })

    return questions

import urllib.parse

today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

categories = {
    "national.json": (
        "National Current Affairs",
        "India latest news"
    ),
    "international.json": (
        "International Current Affairs",
        "world latest news"
    ),
    "daily.json": (
        "Daily Current Affairs",
        "India world latest news"
    ),
    "weekly.json": (
        "Weekly Current Affairs",
        "India world latest news this week"
    ),
    "monthly.json": (
        "Monthly Current Affairs",
        "India world major news"
    )
}

for filename, (title, query) in categories.items():

    google_news = get_google_news(query)

    if filename == "national.json":
        news = get_pib() + google_news
    else:
        news = google_news

    # Remove duplicate headlines
    seen = set()
    unique = []

    for item in news:
        key = item["title"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    unique = unique[:5]

    data = {
        "title": title,
        "updated": today,
        "questions": make_questions(unique, title, today)
    }

    with open("public/" + filename, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(filename, "updated with", len(unique), "news items")

print("All current-affairs files updated.")
