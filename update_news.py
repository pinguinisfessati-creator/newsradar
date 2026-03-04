#!/usr/bin/env python3
import os, json, re, requests
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
HTML_FILE    = "index.html"
ARCHIVE_FILE = "archive.json"
CET          = timezone(timedelta(hours=1))
today        = datetime.now(CET).strftime("%d %b %Y")

RSS_FEEDS = [
    ("ANSA",                "https://www.ansa.it/sito/notizie/topnews/topnews_rss.xml"),
    ("Repubblica",          "https://www.repubblica.it/rss/homepage/rss2.0.xml"),
    ("Corriere",            "https://xml2.corriereobjects.it/rss/homepage.xml"),
    ("Il Fatto",            "https://www.ilfattoquotidiano.it/feed/"),
    ("ANSA Campania",       "https://www.ansa.it/campania/notizie/campania_rss.xml"),
    ("Il Mattino",          "https://www.ilmattino.it/rss/home.xml"),
    ("Pupia Campania",      "https://www.pupia.tv/feed/"),
    ("Google News IT",      "https://news.google.com/rss?hl=it&gl=IT&ceid=IT:it"),
    ("Google News Politica","https://news.google.com/rss/search?q=politica+italiana&hl=it&gl=IT&ceid=IT:it"),
    ("Google News Campania","https://news.google.com/rss/search?q=campania+napoli&hl=it&gl=IT&ceid=IT:it"),
    ("Google News Economia","https://news.google.com/rss/search?q=economia+italia&hl=it&gl=IT&ceid=IT:it"),
]

def fetch_rss():
    articles = []
    for source_name, url in RSS_FEEDS:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "NewsRadar/1.0"})
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:15]:
                title = item.findtext("title", "").strip()
                desc  = item.findtext("description", "").strip()
                link  = item.findtext("link", "").strip()
                pub   = item.findtext("pubDate", "").strip()
                if title:
                    articles.append({
                        "title": title[:100],
                        "description": desc[:150],
                        "url": link,
                        "source": source_name,
                        "date": pub[:16] if pub else today
                    })
        except Exception as e:
            print(f"  Errore feed {source_name}: {e}")
    print(f"  Raccolti {len(articles)} articoli")
    return articles

def call_groq(prompt, max_tokens=6000):
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": max_tokens
        },
        timeout=90
    )
    resp_json = response.json()
    if "choices" not in resp_json:
        print(f"  Errore Groq: {resp_json}")
        raise Exception(f"Groq error: {resp_json}")
    raw = resp_json["choices"][0]["message"]["content"].strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"```$", "", raw).strip()
    if not raw.endswith("]"):
        last = raw.rfind("},")
        if last != -1:
            raw = raw[:last+1] + "]"
    return json.loads(raw)


def rate_with_groq(articles):
    lines = []
    for i, a in enumerate(articles[:60], 1):
        lines.append(f"{i}. [ID:{i}] [{a['source']}] {a['title']} | {a['description'][:80]} | URL: {a['url']} | DATA: {a['date']}")

    news_text = "\n".join(lines)
    prompt = (
        f"Sei un editor TV italiano. Oggi e' {today}.\n"
        f"Articoli disponibili:\n{news_text}\n\n"
        "Seleziona ESATTAMENTE 10 notizie:\n"
        "- 3 obbligatorie categoria 'campania'\n"
        "- 7 scelte tra TUTTE le categorie, ordinate per buzzNum decrescente (menzioni social)\n"
        "JSON array con ESATTAMENTE questi campi:\n"
        "id (1-10), score (1-10), cat (politica|economia|esteri|cronaca|tecnologia|societa|ambiente|sport|campania), "
        "date, title (max 80 car), desc (max 150 car), source, sourceUrl, "
        "buzz (es '📱 45.000 menzioni stimate'), buzzNum (intero), trending (true|false), "
        "socials (array max 3), detail (max 200 car).\n"
        "Ordina per buzzNum decrescente.\n"
        "SOLO JSON valido e completo, nessun testo fuori."
    )

    date_map = {i: a['date'] for i, a in enumerate(articles[:60], 1)}
    result = call_groq(prompt, max_tokens=6000)

    for item in result:
        original_id = item.get("id")
        if original_id and original_id in date_map:
            item["date"] = date_map[original_id]

    return result


def rerate_archive(archive):
    if not archive:
        return archive
    lines = []
    for i, a in enumerate(archive, 1):
        lines.append(f"{i}. [ID:{i}] [{a.get('source','')}] {a.get('title','')} | {a.get('desc','')[:80]} | DATA: {a.get('date','')}")

        news_text = "\n".join(lines)
    prompt = (
        f"Sei un editor TV italiano. Oggi e' {today}.\n"
        f"Notizie in archivio (ultimi 7 giorni):\n{news_text}\n\n"
        "Rivaluta TUTTE le notizie aggiornando score e buzzNum in base alla rilevanza attuale.\n"
        "Restituisci lo stesso JSON array con gli stessi campi, aggiornando solo: score, buzzNum, trending.\n"
        "Mantieni TUTTI gli altri campi invariati (id, date, title, desc, source, ecc.).\n"
        "SOLO JSON valido e completo, nessun testo fuori."
    )


    try:
        result = call_groq(prompt, max_tokens=6000)
        # Mantieni la data originale dall'archivio
        date_map = {a.get("title"): a.get("date") for a in archive}
        for item in result:
            if item.get("title") in date_map:
                item["date"] = date_map[item["title"]]
        return result
    except Exception as e:
        print(f"  Errore rivalutazione: {e} — uso archivio originale")
        return archive

def tv_recs_with_groq(news_list):
    top = "\n".join([f"ID {n.get('id','')}: {n.get('title','')} (score {n.get('score',5)}, cat: {n.get('cat','cronaca')})" for n in news_list[:12]])
    prompt = (
        f"Notizie italiane:\n{top}\n\n"
        "Scegli le 5 migliori per un talk show politico italiano.\n"
        "JSON array con: num (1-5), newsId, title (max 80 car), reason (max 150 car).\n"
        "SOLO JSON valido, nessun testo fuori."
    )

    return call_groq(prompt, max_tokens=1000)

def load_archive():
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_archive(all_news):
    seen = set()
    unique = []
    for n in all_news:
        if n["title"] not in seen:
            seen.add(n["title"])
            unique.append(n)
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(unique[-70:], f, ensure_ascii=False, indent=2)
    return unique[-70:]

def update_html(news_list, tv_recs):
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    now_str    = datetime.now(CET).strftime("%d/%m/%Y %H:%M")
    date_label = datetime.now(CET).strftime("%-d %B %Y")

    html = html.replace(
        "<title>📰 NewsRadar — Rassegna Settimanale</title>",
        f"<title>📰 NewsRadar — Aggiornato {now_str}</title>"
    )
    html = re.sub(r"📅[^<]*</div>", f"📅 Aggiornato {date_label}</div>", html)

    news_js = "const news = " + json.dumps(news_list, ensure_ascii=False, indent=2) + ";"
    ai_js   = "const aiRecommendations = " + json.dumps(tv_recs, ensure_ascii=False, indent=2) + ";"

    html = re.sub(
        r"const news = \[.*?\];(?=\s*const aiRecommendations)",
        news_js, html, flags=re.DOTALL
    )
    html = re.sub(
        r"const aiRecommendations = \[.*?\];(?=\s*(?:function|//|renderNews|saveToday))",
        ai_js, html, flags=re.DOTALL
    )

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Aggiornato alle {now_str} — {len(news_list)} notizie, {len(tv_recs)} consigli TV")

if __name__ == "__main__":
    print(f"🔄 Avvio NewsRadar — {today}")
    print("📡 Recupero RSS...")
    articles = fetch_rss()
    print("🤖 Rating notizie di oggi...")
    news_list = rate_with_groq(articles)
    print(f"   {len(news_list)} notizie selezionate")
    archive = load_archive()
    archive = save_archive(archive + news_list)
    print(f"   📦 Archivio: {len(archive)} notizie")
    print("🔄 Rivalutazione archivio...")
    archive = rerate_archive(archive)
    archive = save_archive(archive)
    print("📺 Consigli TV...")
    tv_recs = tv_recs_with_groq(archive[:12])
    print("💾 Aggiornamento HTML...")
    update_html(archive, tv_recs)
    print("🎉 Completato!")
