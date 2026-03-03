# 📰 NewsRadar — Setup Automatico

## File nel repository
```
/
├── newsradar.html          ← La web app (aggiornata automaticamente)
├── update_news.py          ← Script Python di aggiornamento
└── .github/
    └── workflows/
        └── update_news.yml ← GitHub Actions scheduler
```

## Setup in 5 passi

### 1. Crea il repository GitHub
- Vai su github.com → New repository → nome: `newsradar`
- Carica i 3 file: `newsradar.html`, `update_news.py`, `.github/workflows/update_news.yml`

### 2. Attiva GitHub Pages
- Settings → Pages → Source: Deploy from branch → Branch: main → /root
- Il tuo sito sarà su: `https://TUO-USERNAME.github.io/newsradar/`

### 3. Aggiungi le API Keys come Secrets
- Settings → Secrets and variables → Actions → New repository secret
- Aggiungi:
  - `NEWSAPI_KEY` → la tua chiave da newsapi.org (gratuita)
  - `PERPLEXITY_API_KEY` → la tua chiave da perplexity.ai/settings/api

### 4. Ottieni le chiavi API
- **NewsAPI**: registrati su https://newsapi.org → copia API Key
- **Perplexity API**: vai su https://www.perplexity.ai/settings/api → Generate

### 5. Testa manualmente
- Vai su Actions → "NewsRadar Daily Update" → Run workflow
- Dopo ~60 secondi il sito è aggiornato!

## Aggiornamento automatico
Ogni giorno alle **08:00 CET** GitHub Actions esegue lo script automaticamente.
Puoi anche avviarlo manualmente dal tab Actions → Run workflow.

## Costi
| Servizio | Piano | Costo |
|---|---|---|
| GitHub + GitHub Pages | Free | 0€ |
| GitHub Actions | Free (2.000 min/mese) | 0€ |
| NewsAPI | Developer | 0€ |
| Perplexity API | ~30 chiamate/mese | ~1-2€ |
| **TOTALE** | | **~1-2€/mese** |
