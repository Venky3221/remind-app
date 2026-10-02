import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime, timezone


GEMINI_MODEL = "gemini-2.5-flash"


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


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)


def get_article_text(url):
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")

        parser = TextParser()
        parser.feed(html)

        text = " ".join(parser.parts)
        text = re.sub(r"\s+", " ", text)

        return text[:7000]

    except Exception as e:
        print("Article fetch failed:", url, e)
        return ""


def ask_gemini(category, articles):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not available")


    article_text = []

    for i, article in enumerate(articles, 1):
        text = get_article_text(article["link"])

        if not text:
            text = article["title"]

        article_text.append(
            f"""
ARTICLE {i}
Headline: {article["title"]}
Source: {article["link"]}
Content:
{text}
"""
        )

    prompt = f"""
Create exactly 5 high-quality multiple-choice current-affairs questions
for the category "{category}".

Use ONLY the factual information contained in the supplied articles.
Do NOT use your own background knowledge.
Do NOT invent facts.
Do NOT create questions merely asking which headline appeared.
Instead ask factual questions about people, places, organizations, events,
dates, decisions, numbers, agreements, discoveries, appointments or other
specific information actually stated in the articles.

Each question must have exactly 4 options and exactly 1 correct answer.

Return ONLY valid JSON in this exact structure:

{{
  "questions": [
    {{
      "q": "Question text",
      "o": ["Option 1", "Option 2", "Option 3", "Option 4"],
      "a": 0,
      "explanation": "Brief explanation based only on the article.",
      "source": "Article URL"
    }}
  ]
}}

Rules:
- "a" must be 0, 1, 2, or 3.
- The correct option must be factually supported by the supplied article.
- Wrong options must be plausible but incorrect.
- Avoid yes/no questions.
- Avoid duplicate questions.
- Keep questions suitable for competitive-exam current-affairs practice.
- For political subjects, use neutral factual wording.
- Use the article URL as the source.
- Do not include Markdown or code fences.

Articles:

{"".join(article_text)}
"""


    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + GEMINI_MODEL
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=90) as r:
        response = json.loads(r.read().decode("utf-8"))

    text = response["candidates"][0]["content"]["parts"][0]["text"]

    result = json.loads(text)

    questions = result.get("questions", [])

    valid = []

    for q in questions:
        if not isinstance(q, dict):
            continue

        question = q.get("q")
        options = q.get("o")
        answer = q.get("a")
        explanation = q.get("explanation")
        source = q.get("source")

        if not isinstance(question, str):
            continue

        if not isinstance(options, list) or len(options) != 4:
            continue

        if not isinstance(answer, int) or answer not in [0, 1, 2, 3]:
            continue

        if not all(isinstance(x, str) and x.strip() for x in options):
            continue

        if not isinstance(explanation, str):
            explanation = ""

        if not isinstance(source, str):
            source = articles[0]["link"]

        valid.append({
            "q": question.strip(),
            "o": [x.strip() for x in options],
            "a": answer,
            "explanation": explanation.strip(),
            "source": source
        })

    if len(valid) < 5:
        raise RuntimeError(
            f"Gemini returned only {len(valid)} valid questions"
        )

    return valid[:5]


def unique_news(items):
    seen = set()
    result = []

    for item in items:
        key = item["title"].lower()

        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

categories = {
    "national.json": (
        "National Current Affairs",
        "India latest news today"
    ),
    "international.json": (
        "International Current Affairs",
        "world latest news today"
    ),
    "daily.json": (
        "Daily Current Affairs",
        "India world latest current affairs today"
    ),
    "weekly.json": (
        "Weekly Current Affairs",
        "India world major news this week"
    ),
    "monthly.json": (
        "Monthly Current Affairs",
        "India world major news this month"
    )
}


for filename, (title, query) in categories.items():

    print("\nUpdating:", filename)

    google_news = get_google_news(query)

    if filename == "national.json":
        news = get_pib() + google_news
    else:
        news = google_news

    news = unique_news(news)

    if not news:
        print("No news found; keeping existing file.")
        continue

    articles = news[:5]

    try:
        questions = ask_gemini(title, articles)

        data = {
            "title": title,
            "updated": today,
            "questions": questions
        }

        with open("public/" + filename, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(
            filename,
            "updated with",
            len(questions),
            "real MCQs"
        )

    except Exception as e:
        print(
            "Gemini update failed for",
            filename,
            ":",
            e
        )
        print("Keeping previous quiz data.")


print("\nAll quiz files processed.")
