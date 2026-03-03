#!/usr/bin/env python3
"""
NewsRadar Auto-Updater
Runs daily via GitHub Actions at 08:00 CET
Fetches top Italian news, rates them with Perplexity AI, updates newsradar.html
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
NEWSAPI_KEY        = os.environ["NEWSAPI_KEY"]
PERPLEXITY_API_KEY = os.environ["PERPLEXITY_API_KEY"]
HTML_FILE          = "newsradar.html"

CET = timezone(timedelta(hours=1))
today = datetime.now(CET).strftime("%d %b %Y")

# ── 1. FETCH NEWS from NewsAPI ────────────────────────────────────────────────
def fetch_news():
    headers = {"X-Api-Key": NEWSAPI_KEY}

    # National Italian news
    r1 = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={"country": "it", "pageSize": 20, "language": "it"},
        headers=headers, timeout=10
    )
    national = r1.json().get("articles", [])

    # Campania-specific news
    r2 = requests.get(
        "https://newsapi.org/v2/everything",
        params={"q": "Campania OR Napoli OR Salerno", "language": "it",
                "sortBy": "popularity", "pageSize": 10},
        headers=headers, timeout=10
    )
    campania = r2.json().get("articles", [])

    return national, campania

# ── 2. RATE NEWS with Perplexity AI ──────────────────────────────────────────
def rate_news_with_ai(national_articles, campania_articles):

    def fmt(articles, label):
        lines = []
        for i, a in enumerate(articles[:15], 1):
            lines.append(f"{i}. [{label}] {a.get('title','')} | Fonte: {a.get('source',{}).get('name','')} | URL: {a.get('url','')} | {a.get('description','')[:120]}")
        return "\n".join(lines)

    news_text = fmt(national_articles, "ITALIA") + "\n" + fmt(campania_articles, "CAMPANIA")

    prompt = f"""Hai questa lista di notizie italiane di oggi {today}:

{news_text}

Seleziona le 20 notizie più rilevanti e discusse (includine ALMENO 3 di categoria "campania").
Per ciascuna restituisci un array JSON con questi campi esatti:
- id (numero 1-20)
- score (intero 1-10 basato su impatto mediatico e discussione social)
- cat (una tra: politica, economia, esteri, cronaca, tecnologia, societa, ambiente, sport, campania)
- date (data nel formato "DD mmm YYYY", es. "03 mar 2026")
- title (titolo in italiano, max 90 caratteri)
- desc (descrizione 2 righe in italiano)
- source (nome testata)
- sourceUrl (URL diretto all'articolo)
- buzz (stringa es. "📱 45.000 menzioni")
- buzzNum (numero intero per ordinamento, es. 45000)
- trending (true/false)
- socials (array di stringhe, es. ["X/Twitter","TikTok","Facebook"])
- detail (approfondimento 3-4 righe in italiano)

Ordina il risultato dal buzzNum più alto al più basso.
Rispondi SOLO con il JSON array valido, nessun testo prima o dopo."""

    response = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "sonar",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        },
        timeout=60
    )

    raw = response.json()["choices"][0]["message"]["content"]

    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)

# ── 3. GENERATE AI TV RECOMMENDATIONS ────────────────────────────────────────
def generate_tv_recs(news_list):
    top_titles = "\n".join([f"ID {n['id']}: {n['title']} (score {n['score']}, cat: {n['cat']})" for n in news_list[:12]])

    prompt = f"""Date queste notizie italiane di oggi:
{top_titles}

Scegli le 5 migliori per essere discusse in una trasmissione televisiva politica italiana.
Restituisci un JSON array con:
- num (1-5)
- newsId (id della notizia corrispondente)
- title (titolo accattivante per il format TV, max 80 caratteri)
- reason (motivazione 1-2 frasi: perché funziona in TV, quale pubblico coinvolge)

Rispondi SOLO con il JSON array valido."""

    response = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "sonar",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        },
        timeout=30
    )

    raw = response.json()["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)

# ── 4. INJECT INTO HTML ───────────────────────────────────────────────────────
def update_html(news_list, tv_recs):
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Build JS news array
    news_js = "const news = " + json.dumps(news_list, ensure_ascii=False, indent=2) + ";"
    ai_js   = "const aiRecommendations = " + json.dumps(tv_recs, ensure_ascii=False, indent=2) + ";"

    # Update week badge date
    from datetime import datetime, timezone, timedelta
    CET = timezone(timedelta(hours=1))
    date_label = datetime.now(CET).strftime("%-d %B %Y")
    html = __import__("re").sub(
        r'📅 Settimana.*?</div>',
        f'📅 Aggiornato {date_label}</div>',
        html
    )

    # Replace news array
    start_n = html.index("const news = [")
    end_n   = html.index("];

const aiRecommendations") + 2
    html = html[:start_n] + news_js + "\n\n" + html[end_n:]

    # Replace AI recs array
    start_a = html.index("const aiRecommendations = [")
    end_a   = html.index("];

function getScoreClass") + 2
    html = html[:start_a] + ai_js + "\n\n" + html[end_a:]

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ newsradar.html aggiornato con {len(news_list)} notizie e {len(tv_recs)} consigli TV")

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🔄 Avvio aggiornamento NewsRadar — {today}")

    print("📡 Recupero notizie da NewsAPI...")
    national, campania = fetch_news()
    print(f"   Trovate {len(national)} notizie nazionali, {len(campania)} campane")

    print("🤖 Classificazione e rating con Perplexity AI...")
    news_list = rate_news_with_ai(national, campania)
    print(f"   Classificate {len(news_list)} notizie")

    print("📺 Generazione consigli TV...")
    tv_recs = generate_tv_recs(news_list)
    print(f"   Generati {len(tv_recs)} consigli")

    print("💾 Aggiornamento HTML...")
    update_html(news_list, tv_recs)

    print("🎉 Completato!")
