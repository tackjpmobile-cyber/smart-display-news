import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

THEME_FILE = "theme.json"
OUTPUT_FILE = "news.json"
MAX_ITEMS = 10


def load_theme():
    with open(THEME_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_query(keywords):
    # 複数キーワードをORで結合。スペースを含む語は引用符で囲む
    parts = [f'"{k}"' if " " in k else k for k in keywords]
    return " OR ".join(parts)


def fetch_rss(query):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def parse_items(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""
        items.append({
            "title": title,
            "link": link,
            "source": source,
            "pub_date": pub_date,
        })
    return items


def dedupe_and_sort(items):
    seen = set()
    unique = []
    for it in items:
        key = re.sub(r"\s+", "", it["title"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    def parse_date(d):
        try:
            return datetime.strptime(d, "%a, %d %b %Y %H:%M:%S %Z")
        except Exception:
            return datetime.min

    unique.sort(key=lambda x: parse_date(x["pub_date"]), reverse=True)
    return unique


def main():
    theme = load_theme()
    keywords = theme.get("keywords") or [theme.get("theme", "")]
    query = build_query(keywords)

    xml_bytes = fetch_rss(query)
    items = parse_items(xml_bytes)
    items = dedupe_and_sort(items)[:MAX_ITEMS]

    output = {
        "theme": theme.get("theme", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(items)} items to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
