#!/usr/bin/env python3
"""
NewsRadar Auto-Updater - versione GRATUITA
Usa: RSS ANSA/Repubblica/Corriere + Groq AI (gratis) + GitHub Actions
Gira ogni giorno alle 08:00 CET
"""

import os, json, re, requests
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
HTML_FILE    = "newsradar.html"
CET          = timezone(timedelta(hours=1))
today        = datetime.now(CET).strftime("%d %b %Y")

RSS_FEEDS = [
    ("ANSA",           "https://www.ansa.it/sito/notizie/topnews/topnews_rss.xml"),
    ("Repubblica",     "https://www.repubblica.it/rss/homepage/rss2.0.xml"),
    ("Corriere",       "https://xml2.corriereobjects.it/rss/homepage.xml"),
    ("Sky TG24",       "https://tg24.sky.it/rss.xml"),
    ("Il Fatto",       "https://www.ilfattoquotidiano.it/feed/"),
    ("ANSA Campania",  "https://www.ansa.it/campania/notizie/campania_rss.xml"),
    ("Pupia Campania", "https://www.pupia.tv/feed/"),
]

def fetch_rss():
    articles = []
    for source_name, url in RSS_FEEDS:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "NewsRadar/1.0"})
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:8]:
                title = item.findtext("title", "").strip()
                desc  = item.findtext("description", "").strip()
                link  = item.findtext("link", "").strip()
                pub   = item.findtext("pubDate", today).strip()
                if title:
                    articles.append({
                        "title": title,
                        "description": desc[:200],
                        "url": link,
                        "source": source_name,
                        "pubDate": pub
                    })
        except Exception as e:
            print(f"  Errore feed {source_name}: {e}")
    print(f"  Raccolti {len(articles)} articoli dai feed RSS")
    return articles

def rate_with_groq(articles):
    lines = []
    for i, a in enumerate(articles[:50], 1):
        lines.append(f"{i}. [{a['source']}] {a['title']} | {a['description'][:100]} | URL: {a['url']}")
    news_text = "\n".join(lines)

    prompt = f"""Sei un editor di un telegiornale italiano. Oggi e' {today}.
Hai questi articoli raccolti dai principali giornali italiani:

{news_text}

Seleziona le 20 notizie piu' rilevanti e discusse (includi ALMENO 3 di categoria "campania").
Per ciascuna restituisci un array JSON con questi campi esatti:
- id (numero 1-20)
- score (intero 1-10: impatto mediatico e rilevanza nazionale)
- cat (una tra: politica, economia, esteri, cronaca, tecnologia, societa, ambiente, sport, campania)
- date (es. "{today}")
- title (titolo in italiano, max 90 caratteri)
- desc (descrizione 2 righe in italiano, max 200 caratteri)
- source (nome testata)
- sourceUrl (URL diretto all'articolo)
- buzz (stringa es. "📱 45.000 menzioni stimate")
- buzzNum (intero per ordinamento, es. 45000)
- trending (true se molto discussa, false altrimenti)
- socials (array con i social dove va per la maggiore, es. ["X/Twitter","TikTok","Facebook"])
- detail (approfondimento 3-4 righe in italiano)

Ordina dal buzzNum piu' alto al piu' basso.
Rispondi SOLO con il JSON array valido, senza testo prima o dopo, senza markdown."""

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 4000
        },
        timeout=60
    )
    raw = response.json()["choices"][0]["message"]["content"].strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)

def tv_recs_with_groq(news_list):
    top = "\n".join([f"ID {n['id']}: {n['title']} (score {n['score']}, cat: {n['cat']})" for n in news_list[:12]])
    prompt = f"""Date queste notizie italiane di oggi:
{top}

Scegli le 5 migliori per una trasmissione televisiva politica italiana.
Restituisci JSON array con:
- num (1-5)
- newsId (id della notizia)
- title (titolo accattivante per la TV, max 80 caratteri)
- reason (motivazione 1-2 frasi: perche' funziona in TV, quale pubblico coinvolge)

Rispondi SOLO con il JSON array valido, senza testo prima o dopo, senza markdown."""

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1000
        },
        timeout=30
    )
    raw = response.json()["choices"][0]["message"]["content"].strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)

def update_html(news_list, tv_recs):
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    date_label = datetime.now(CET).strftime("%-d %B %Y")
    html = re.sub(r"📅 Aggiornato.*?</div>", f"📅 Aggiornato {date_label}</div>", html)
    html = re.sub(r"📅 Settimana.*?</div>", f"📅 Aggiornato {date_label}</div>", html)

    news_js = "const news = " + json.dumps(news_list, ensure_ascii=False, indent=2) + ";"
    ai_js   = "const aiRecommendations = " + json.dumps(tv_recs, ensure_ascii=False, indent=2) + ";"

    start_n = html.index("const news = [")
    end_n   = html.index("];

const aiRecommendations") + 2
    html    = html[:start_n] + news_js + "\n\n" + html[end_n:]

    start_a = html.index("const aiRecommendations = [")
    end_a   = html.index("];

function getScoreClass") + 2
    html    = html[:start_a] + ai_js + "\n\n" + html[end_a:]

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ newsradar.html aggiornato — {len(news_list)} notizie, {len(tv_recs)} consigli TV")

if __name__ == "__main__":
    print(f"🔄 Avvio NewsRadar — {today}")
    print("📡 Recupero notizie dai feed RSS...")
    articles = fetch_rss()
    print("🤖 Rating con Groq AI...")
    news_list = rate_with_groq(articles)
    print(f"   {len(news_list)} notizie classificate")
    print("📺 Generazione consigli TV...")
    tv_recs = tv_recs_with_groq(news_list)
    print("💾 Aggiornamento HTML...")
    update_html(news_list, tv_recs)
    print("🎉 Completato!")
