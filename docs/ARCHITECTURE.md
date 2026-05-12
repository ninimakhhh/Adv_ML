# Olá Market — CX Platform Architecture

## LLM Provider

**Current provider:** DeepSeek (`deepseek-chat`)

**Rationale for choosing DeepSeek:**
- Competitive pricing vs. GPT-4 / Claude for high-volume classification
- OpenAI-compatible API — drop-in swap via the `openai` Python SDK
- Strong reasoning quality on structured JSON tasks

**History:**
- Originally prototyped with Anthropic Claude (claude-sonnet-4-6)
- Briefly switched to Google Gemini (gemini-2.0-flash) — quota issues on free tier
- Migrated to DeepSeek for cost-efficiency and API stability

---

## LLM Abstraction Layer

All LLM calls go through a single class: **`shared/llm_client.py → LLMClient`**.

```
chatbot/classifier/classifier.py
        │
        └── LLMClient.chat(messages, response_format="json")
                │
                └── openai.OpenAI(api_key=DEEPSEEK_API_KEY,
                                  base_url=DEEPSEEK_BASE_URL)
                        │
                        └── DeepSeek API
```

### Why one abstraction point?

Swapping providers in the future means editing **one file** (`shared/llm_client.py`):
- Change `base_url` and `api_key` source to point at a new provider
- The classifier, orchestrator, and any future callers are unaffected

### LLMClient capabilities

| Feature | Detail |
|---|---|
| JSON mode | `response_format="json"` injects a system instruction + sets `response_format: {type: json_object}` + auto-parses the response |
| Retry | 3 attempts with exponential backoff (1s, 2s, 4s) on 5xx and rate-limit errors |
| Safe errors | Never crashes the orchestrator — returns `{"error": ..., "raw": ...}` on parse failure |
| Temperature | Defaults to 0.2 for deterministic classification tasks |

---

## Chatbot Pipeline

```
User message
    │
    ▼
IntentClassifier.classify()        ← LLMClient (DeepSeek)
    │
    ├── intent found → ResolutionEngine.resolve()
    │       ├── faq_answer  → static text from intent JSON
    │       ├── api_call    → mock backend (orders/refunds/inventory)
    │       └── guided_flow → multi-step slot collection
    │
    └── no intent / low confidence → EscalationEngine
            └── human handoff or NO_INTENT_RESPONSE

All turns → TicketRepository (SQLite)
```

---

## Directory Structure

```
shared/
  config.py        — env vars, startup validation
  llm_client.py    — LLMClient (single provider abstraction)
  db/              — SQLite models, repository, migrations

chatbot/
  classifier/      — IntentClassifier (uses LLMClient)
  escalation/      — EscalationEngine
  resolution/      — ResolutionEngine + mock backends
  session/         — ConversationState
  registry/        — Intent JSON definitions
  feedback/        — weekly_review(), JSONL export

frontend/
  user_app.py      — Streamlit storefront
  admin_app.py     — Streamlit admin dashboard
  components/      — Shared UI components
  pages/           — Category view, product detail
```

---

## Adding a New LLM Provider

1. Add credentials to `.env` (see `.env.example`)
2. Update `shared/config.py` to load the new key/URL
3. Edit `shared/llm_client.py` — change the `OpenAI(base_url=...)` call or add a branch
4. Run `pytest tests/test_classifier.py` — all tests mock `LLMClient.chat`, so they pass regardless of provider
