#!/usr/bin/env python3
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

def call_groq(prompt, max_tokens=4000):
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": max_tokens
        },
        timeout=60
    )
    raw = response.json()["choices"][0]["message"]["content"].strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)

def rate_with_groq(articles):
    lines = []
    for i, a in enumerate(articles[:50], 1):
        lines.append(f"{i}. [{a['source']}] {a['title']} | {a['description'][:100]} | URL: {a['url']}")
    news_text = "\n".join(lines)
    prompt = (
        f"Sei un editor di un telegiornale italiano. Oggi e' {today}.\n"
        f"Hai questi articoli raccolti dai principali giornali italiani:\n\n{news_text}\n\n"
        "Seleziona le 20 notizie piu' rilevanti (includi ALMENO 3 di categoria campania).\n"
        "Per ciascuna restituisci un array JSON con questi campi:\n"
        "id (1-20), score (1-10), cat (politica/economia/esteri/cronaca/tecnologia/societa/ambiente/sport/campania), "
        f"date ('{today}'), title (max 90 car), desc (max 200 car), source, sourceUrl, "
        "buzz (es '📱 45.000 menzioni stimate'), buzzNum (intero), trending (bool), "
        "socials (array stringhe), detail (3-4 righe).\n"
        "Ordina dal buzzNum piu' alto al piu' basso.\n"
        "Rispondi SOLO con il JSON array valido, senza testo prima o dopo, senza markdown."
    )
    return call_groq(prompt, max_tokens=4000)

def tv_recs_with_groq(news_list):
    top = "\n".join([f"ID {n['id']}: {n['title']} (score {n['score']}, cat: {n['cat']})" for n in news_list[:12]])
    prompt = (
        f"Date queste notizie italiane di oggi:\n{top}\n\n"
        "Scegli le 5 migliori per una trasmissione televisiva politica italiana.\n"
        "Restituisci JSON array con: num (1-5), newsId, title (max 80 car), reason (1-2 frasi).\n"
        "Rispondi SOLO con il JSON array valido, senza testo prima o dopo, senza markdown."
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

    news_start_marker = "const news = ["
    news_end_marker   = "];\n\nconst aiRecommendations"
    ai_start_marker   = "const aiRecommendations = ["
    ai_end_marker     = "];\n\nfunction getScoreClass"

    start_n = html.index(news_start_marker)
    end_n   = html.index(news_end_marker) + 2
    html    = html[:start_n] + news_js + "\n\n" + html[end_n:]

    start_a = html.index(ai_start_marker)
    end_a   = html.index(ai_end_marker) + 2
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
