import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

THEME_FILE = "theme.json"
OUTPUT_FILE = "news.json"
MAX_ITEMS = 10
BODY_CHARS = 500
FETCH_TIMEOUT = 10


def load_theme():
    with open(THEME_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_rss_for_keyword(keyword):
    q = urllib.parse.quote(keyword)
    url = f"https://www.bing.com/news/search?q={q}&format=rss&mkt=ja-JP"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "ja-JP,ja;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        status = resp.status
        raw = resp.read()
    print(f"  [{keyword}] status={status} bytes={len(raw)}")
    return raw


def resolve_link(raw_link):
    """BingのリンクがリダイレクトURL(apiclick.aspx等)の場合、
    クエリパラメータ内の実URLを取り出す。通常のURLならそのまま返す。"""
    try:
        parsed = urllib.parse.urlparse(raw_link)
        qs = urllib.parse.parse_qs(parsed.query)
        for key in ("url", "u"):
            if key in qs and qs[key]:
                return qs[key][0]
    except Exception:
        pass
    return raw_link


def fetch_article_body(url, max_chars=BODY_CHARS):
    """記事リンク先から本文らしきテキストを抜き出し、冒頭max_chars文字を返す。
    取得・解析に失敗した場合は空文字を返す(呼び出し側でタイトルのみにフォールバック)。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
        html = raw.decode(charset, errors="ignore")
    except Exception:
        return ""

    # script/style等を除去してからタグを剥がす簡易抽出(サイト構造に依存しない代わりに精度は粗い)
    html = re.sub(r"(?is)<(script|style|noscript|header|footer|nav)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&amp;|&lt;|&gt;|&quot;|&#39;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def strip_html(s):
    s = re.sub(r"(?s)<[^>]+>", " ", s or "")
    s = re.sub(r"&nbsp;|&amp;|&lt;|&gt;|&quot;|&#39;", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_items(xml_bytes, keyword=""):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"  [{keyword}] XML parse error: {e}")
        print(f"  [{keyword}] response head: {xml_bytes[:300]!r}")
        return []

    items = []
    channel_items = root.findall("./channel/item")
    if not channel_items:
        print(f"  [{keyword}] 0 <item> found. response head: {xml_bytes[:300]!r}")

    for item in channel_items:
        title = (item.findtext("title") or "").strip()
        raw_link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = strip_html(item.findtext("description") or "")
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""
        items.append({
            "title": title,
            "link": resolve_link(raw_link),
            "source": source,
            "pub_date": pub_date,
            "snippet": description,
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

    all_items = []
    for kw in keywords:
        try:
            raw = fetch_rss_for_keyword(kw)
        except Exception as e:
            print(f"  [{kw}] fetch failed: {e}")
            continue
        all_items.extend(parse_items(raw, keyword=kw))

    items = dedupe_and_sort(all_items)[:MAX_ITEMS]
    print(f"Total merged items after dedupe: {len(items)}")

    for it in items:
        body = fetch_article_body(it["link"]) if it["link"] else ""
        # フル本文が取れなければRSSのスニペット、それも無ければタイトルで代替する
        it["body"] = body or it.get("snippet") or it["title"]
        it.pop("snippet", None)

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
