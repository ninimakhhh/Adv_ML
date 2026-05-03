# AI-Powered Customer Experience Platform
**Nova SBE — Advanced Topics in Machine Learning (S2.2)**

An end-to-end AI platform for Portuguese SMB e-commerce on Shopify, combining a RAG chatbot, automated ticket routing, and social media sentiment analysis.

---

## Modules

| Module | Description | Entry point |
|---|---|---|
| **RAG Chatbot** | Answers customer queries using store-specific knowledge (FAQs, policies, product catalogue) | `chatbot/` |
| **Ticket Routing** | Classifies and routes support tickets to the right team/priority | `ticket_routing/` |
| **Sentiment Analysis** | Monitors brand sentiment on Reddit/social media in Portuguese and English | `sentiment_analysis/` |

---

## Project Structure

```
├── chatbot/             # RAG pipeline, vector store ingestion, chain logic
├── ticket_routing/      # Classifier training, inference, evaluation
├── sentiment_analysis/  # Data collection, NLP pipeline, dashboard
├── shared/              # Shared config, utilities, base models
├── data/                # Datasets (raw/ excluded from git)
├── frontend/            # Streamlit multi-page app
├── tests/               # Unit & integration tests
└── docs/                # Architecture diagrams, research notes
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

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

---

## Running each module

### RAG Chatbot

```bash
# Ingest documents into the vector store
python chatbot/ingest.py

# Run the chatbot (standalone CLI)
python chatbot/chat.py
```

### Ticket Routing

```bash
# Train the classifier
python ticket_routing/train.py

# Run inference on a CSV of tickets
python ticket_routing/predict.py --input data/tickets.csv
```

### Sentiment Analysis

```bash
# Collect Reddit posts
python sentiment_analysis/collect.py

# Run the analysis pipeline
python sentiment_analysis/analyze.py
```

### Streamlit Frontend (all modules)

```bash
streamlit run frontend/app.py
```

---

## Requirements

- Python 3.11+
- API keys: Anthropic (required), OpenAI (optional), Reddit (for data collection)

---

## Tech Stack

- **LLM**: Claude (Anthropic) via `anthropic` SDK
- **RAG**: LangChain + ChromaDB + `sentence-transformers`
- **ML**: scikit-learn, HuggingFace `transformers`
- **Sentiment**: VADER + transformer-based multilingual models
- **Frontend**: Streamlit + Plotly
- **Data**: Reddit API via PRAW, BeautifulSoup for web scraping
