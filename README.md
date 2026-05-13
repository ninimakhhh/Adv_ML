# Olá Market — AI-Powered Customer Experience Platform
**Nova SBE — Advanced Topics in Machine Learning (S2.2)**

An end-to-end AI platform for Portuguese SMB e-commerce, combining a RAG-style support chatbot, automated ticket routing, and aspect-based sentiment analysis of customer reviews and support tickets. The platform exposes a customer-facing storefront and an admin dashboard for operations.

---

## Modules

| Module | Description | Entry point |
|---|---|---|
| **Chatbot** | Intent classification, conversation orchestration, and resolution playbooks for customer queries | `chatbot/` |
| **Ticket Routing** | Classifies incoming support tickets by category, sentiment, urgency, and routes them to the right team | `ticket_routing/classifier.py` |
| **Sentiment Analysis** | Extracts six-aspect sentiment (delivery, quality, accuracy, packaging, customer service, value) from reviews and tickets | `sentiment_analysis/` |

---

## Project Structure

```
├── chatbot/                # Intent classifier, orchestrator, registry, escalation, feedback, session
├── ticket_routing/         # Ticket classifier (DeepSeek tool-use) and category→queue mapping
├── sentiment_analysis/     # Aspect-based analyzer, pipeline, aggregator, admin dashboard rendering
├── shared/                 # Config, LLM client (DeepSeek), logger, DB helpers
├── frontend/               # Streamlit apps (admin + customer) + components + styles
│   ├── admin_app.py        # Admin dashboard: Main / Tickets / Comments / Sentiment Analysis
│   ├── user_app.py         # Customer storefront
│   ├── components/         # Reusable Streamlit components (sidebar, cards, chatbot widget)
│   └── pages/              # Category view and product detail pages (custom-routed)
├── data/
│   ├── mock/               # Mock JSON datasets (products, reviews, tickets, sentiment events…)
│   └── tickets.db          # SQLite store used by the chatbot session/repository
├── scripts/                # Generators and one-shot data utilities (review corpus, date alignment)
├── tests/                  # Unit and integration tests
├── docs/                   # Architecture notes and research material
└── logs/                   # Per-module rotating logs
```

---

## Setup

### 1. Clone & create environment

```bash
git clone <repo-url>
cd Adv_ML
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in the required keys. The platform uses the **DeepSeek** chat API (OpenAI-compatible). The app starts and renders without a key — the error is raised lazily only when a feature that calls the LLM is invoked (auto-classify, re-classify, sentiment pipeline).

Required variables:

- `DEEPSEEK_API_KEY` — needed for ticket classification, comment auto-classification, and re-running the sentiment pipeline.

---

## Running the platform

### Streamlit apps

```bash
# Admin dashboard
streamlit run frontend/admin_app.py

# Customer storefront
streamlit run frontend/user_app.py
```

The admin dashboard has four tabs:

- **Main** — KPI strip and trend charts (historical 30-day aggregates).
- **Tickets** — Support tickets pending classification + already classified, with filters (Status / Urgency / Category / Time Range / Product) and a Manage panel for editing or re-classifying via the AI.
- **Comments** — The 20 customer reviews already processed by the sentiment pipeline (last 7 days) plus 5 pending. Filters: Sentiment / Severity / Aspect / Product.
- **Sentiment Analysis** — Aggregated dashboards over `sentiment_events.json`: aspect heatmap, sentiment trend, top problem products, cross-reference alerts between negative reviews and tickets, problem-frequency ranking.

### Sentiment analysis pipeline

```bash
# Process reviews and tickets through the aspect-sentiment analyzer
python -m sentiment_analysis.pipeline --max-reviews 20 --max-tickets 10
```

Results are written incrementally to `data/mock/sentiment_events.json` and read back by the Sentiment Analysis tab and the Comments tab. Requires `DEEPSEEK_API_KEY`.

### Ticket classification (standalone)

```python
from ticket_routing.classifier import classify_ticket
result = classify_ticket(subject, raw_text)
# returns: category, confidence, sentiment, urgency, assigned_queue, reasoning
```

### Data utility scripts

```bash
# Generate the review corpus from scratch (rebuilds reviews.json + patches products.json)
python scripts/generate_reviews.py

# Append ~113 new reviews using a pool of 100 fresh (title, body) pairs
python scripts/regenerate_reviews.py

# Compress all review dates into a skewed-recent 6-month window
python scripts/redistribute_review_dates.py

# Realign 25 review dates (20 classified + 5 pending) to the last 7 days
# for the admin Comments tab
python scripts/realign_comment_dates.py
```

All scripts are deterministic given a fixed seed and safe to re-run.

---

## Requirements

- Python 3.11+
- `DEEPSEEK_API_KEY` for any LLM-backed feature (classification, sentiment extraction, re-classification)

---

## Tech Stack

- **LLM**: DeepSeek (`deepseek-chat`) via the OpenAI-compatible SDK (`openai` Python client)
- **Frontend**: Streamlit + Plotly
- **Data**: JSON mock datasets + SQLite (`data/tickets.db`) for chatbot session state
- **Analysis**: aspect-based sentiment extraction with custom prompts; `pandas` for aggregation; six aspects per record (delivery / quality / accuracy / packaging / customer service / value) plus dominant problem and severity

---

## Architecture notes

- Both `reviews` and `tickets` flow into the same `sentiment_events.json` event store with a unified schema. The aggregator filters by `source` when needed (e.g. negative reviews vs. negative tickets) to power cross-reference alerts.
- The admin app's `Comments` tab uses the **20 already-processed review events** as the source of truth. The other ~1,189 reviews remain in the corpus but are not surfaced in that tab until the sentiment pipeline is re-run on a larger sample.
- `LLMClient` (in `shared/llm_client.py`) defers DeepSeek client instantiation until the first API call, so the app can be imported and rendered without a key — the lazy error from `require_deepseek_api_key()` only fires at the call site that needs it.
- Streamlit's auto-generated page navigation is hidden via CSS in both apps; routing inside the customer storefront is handled by a custom session-state mechanism in `shared/navigation.py`.
