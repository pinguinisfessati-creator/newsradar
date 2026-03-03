#!/usr/bin/env python3
import os, json, re, requests
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
HTML_FILE    = "index.html"
CET          = timezone(timedelta(hours=1))
today        = datetime.now(CET).strftime("%d %b %Y")

# Feed RSS per notizie Campania (non coperti da GDELT)
RSS_CAMPANIA = [
    ("ANSA Campania",  "https://www.ansa.it/campania/notizie/campania_rss.xml"),
    ("Il Mattino",     "https://www.ilmattino.it/rss/home.xml"),
    ("Pupia Campania", "https://www.pupia.tv/feed/"),
]

def fetch_gdelt_italy():
    """
    GDELT DOC 2.0 API — cerca notizie italiane degli ultimi 7 giorni.
    Nessuna API key richiesta, completamente gratuito.
    """
    articles = []
    queries = [
        "politica italiana",
        "economia italia",
        "governo italiano",
        "cronaca italia",
    ]
    for q in queries:
        try:
            url = (
                "https://api.gdeltproject.org/api/v2/doc/doc"
                f"?query={requests.utils.quote(q + ' sourcelang:italian')}"
                "&mode=ArtList&maxrecords=25&timespan=7d&format=json"
            )
            r = requests.get(url, timeout=15, headers={"User-Agent": "NewsRadar/1.0"})
            data = r.json()
            for art in data.get("articles", []):
                title = art.get("title", "").strip()
                url_a = art.get("url", "")
                source = art.get("domain", "")
                seendate = art.get("seendate", today)
                if title and url_a:
                    articles.append({
                        "title": title[:100],
                        "description": art.get("title", "")[:150],
                        "url": url_a,
                        "source": source,
                        "pubDate": seendate
                    })
        except Exception as e:
            print(f"  Errore GDELT query '{q}': {e}")
    print(f"  GDELT: {len(articles)} articoli italiani (7 giorni)")
    return articles

def fetch_rss_campania():
    articles = []
    for source_name, url in RSS_CAMPANIA:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "NewsRadar/1.0"})
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:15]:
                title = item.findtext("title", "").strip()
                desc  = item.findtext("description", "").strip()
                link  = item.findtext("link", "").strip()
                if title:
                    articles.append({
                        "title": title[:100],
                        "description": desc[:150],
                        "url": link,
                        "source": source_name,
                        "pubDate": today
                    })
        except Exception as e:
            print(f"  Errore feed {source_name}: {e}")
    print(f"  RSS Campania: {len(articles)} articoli")
    return articles

def call_groq(prompt, max_tokens=8000):
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
    raw = response.json()["choices"][0]["message"]["content"].strip()
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
        lines.append(f"{i}. [{a['source']}] {a['title']} | URL: {a['url']}")
    news_text = "\n".join(lines)

    prompt = (
        f"Sei un editor TV italiano. Rassegna degli ultimi 7 giorni. Oggi e' {today}.\n"
        f"Articoli disponibili:\n{news_text}\n\n"
        "Seleziona le 20 notizie PIU' RILEVANTI E DISCUSSE della settimana (ALMENO 3 categoria campania).\n"
        "Per ciascuna restituisci un array JSON con ESATTAMENTE questi campi:\n"
        "id (1-20), score (1-10), cat (politica|economia|esteri|cronaca|tecnologia|societa|ambiente|sport|campania), "
        "date (data pubblicazione es '01 mar 2026'), title (max 80 car), desc (max 150 car), "
        "source, sourceUrl, buzz (es '📱 45.000 menzioni stimate'), buzzNum (intero), "
        "trending (true|false), socials (array max 3), detail (max 200 car).\n"
        "Ordina per buzzNum decrescente.\n"
        "SOLO JSON valido e completo, nessun testo fuori."
    )
    return call_groq(prompt, max_tokens=8000)

def tv_recs_with_groq(news_list):
    top = "\n".join([f"ID {n['id']}: {n['title']} (score {n['score']}, cat: {n['cat']})" for n in news_list[:12]])
    prompt = (
        f"Notizie italiane della settimana:\n{top}\n\n"
        "Scegli le 5 migliori per un talk show politico italiano.\n"
        "JSON array con: num (1-5), newsId, title (max 80 car), reason (max 150 car).\n"
        "SOLO JSON valido, nessun testo fuori."
    )
    return call_groq(prompt, max_tokens=1000)

def update_html(news_list, tv_recs):
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    date_label = datetime.now(CET).strftime("%-d %B %Y")
    html = re.sub(r"📅 Aggiornato.*?</div>", f"📅 Aggiornato {date_label}</div>", html)
    html = re.sub(r"📅 Settimana.*?</div>", f"📅 Aggiornato {date_label}</div>", html)

    news_js = "const news = " + json.dumps(news_list, ensure_ascii=False, indent=2) + ";"
    ai_js   = "const aiRecommendations = " + json.dumps(tv_recs, ensure_ascii=False, indent=2) + ";"

    sn = html.index("const news = [")
    en = html.index("];\n\nconst aiRecommendations") + 2
    html = html[:sn] + news_js + "\n\n" + html[en:]

    sa = html.index("const aiRecommendations = [")
    ea = html.index("];\n\nfunction getScoreClass") + 2
    html = html[:sa] + ai_js + "\n\n" + html[ea:]

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Aggiornato — {len(news_list)} notizie, {len(tv_recs)} consigli TV")

if __name__ == "__main__":
    print(f"🔄 Avvio NewsRadar settimanale — {today}")
    print("🌍 Recupero notizie GDELT (ultimi 7 giorni)...")
    gdelt_articles = fetch_gdelt_italy()
    print("🌋 Recupero notizie Campania (RSS)...")
    campania_articles = fetch_rss_campania()
    all_articles = gdelt_articles + campania_articles
    print(f"   Totale: {len(all_articles)} articoli")
    print("🤖 Selezione e rating con Groq AI...")
    news_list = rate_with_groq(all_articles)
    print(f"   {len(news_list)} notizie selezionate")
    print("📺 Consigli TV...")
    tv_recs = tv_recs_with_groq(news_list)
    print("💾 Aggiornamento HTML...")
    update_html(news_list, tv_recs)
    print("🎉 Completato!")
