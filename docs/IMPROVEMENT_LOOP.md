# Feedback Loop & Continuous Improvement

This document describes the weekly cadence for turning chatbot failures into
bot improvements at Olá Market.

---

## 1. Overview

The feedback loop runs weekly and covers three improvement pathways:

| Pathway | Trigger | Owner | Output |
|---|---|---|---|
| New intent | Recurring unmatched messages | Support Lead | Draft intent JSON |
| Response improvement | Thumbs-down feedback | Merchant | Updated `resolution_config` |
| Fine-tuning dataset | Human-verified tickets | ML Engineer | `labeled_tickets.jsonl` |

---

## 2. Weekly Cadence

### Monday — Data Pull (automated)

`chatbot/feedback/analyzer.py::weekly_review()` is called automatically (or
manually from the Admin Dashboard → Bot Improvement tab) and produces a
report containing:

- **Low-confidence messages** — classifier confidence < 70%; candidates for
  new intents or additional few-shot examples.
- **Attempted-but-escalated intents** — the bot recognised the intent but
  still ended up handing off to a human; the bot's responses need improvement.
- **Thumbs-down tickets** — users explicitly rated the bot negatively; the
  existing response should be revised.
- **Unmatched messages** — no intent was triggered; recurring patterns should
  become new intents.

### Tuesday — Review Session (30 min)

**Attendees:** Merchant (product owner) + Support Lead  
**Location:** Admin Dashboard → Bot Improvement tab

Agenda:
1. Review the four summary cards (< 5 min).
2. Scan low-confidence messages — are any recurring? → flag for new intent.
3. Scan unmatched messages — are any recurring? → draft a new intent using
   the "Create new intent" form in the dashboard.
4. Review thumbs-down tickets — type a better response suggestion in the
   textarea provided.
5. Note any intent with escalation rate > 50% for the ML Engineer to
   investigate the resolution engine.

### Wednesday — Implementation

**Support Lead:**
- Promote any draft intents that look good: move the JSON file from
  `chatbot/registry/intents/_drafts/` to `chatbot/registry/intents/` and
  open a pull request.

**ML Engineer:**
- Run `python -m chatbot.registry.validate` to confirm the new intent passes
  schema validation.
- Review suggested response improvements from the dashboard; update the
  relevant `resolution_config.answer` or `response_template` in the intent
  JSON.
- Export the fine-tuning dataset (Admin → Bot Improvement → Export Labeled
  Tickets as JSONL) and kick off any scheduled fine-tuning job.

### Friday — Deploy & Measure

- Merge the intent PR after review.
- Re-seed `load_intents.cache_clear()` or restart the chatbot server so the
  new intents are picked up.
- Check the following week's Dashboard KPIs to confirm escalation rate drops
  for the targeted intents.

---

## 3. How Draft Intents Get Promoted to Live Intents

```
Admin UI form
    │
    ▼
chatbot/registry/intents/_drafts/<intent_id>.json
    │
    │  (Support Lead reviews, fills in missing utterances / response template)
    │
    ▼
git mv _drafts/<intent_id>.json intents/<intent_id>.json
    │
    ▼
python -m chatbot.registry.validate          ← must pass (all errors = 0)
    │
    ▼
Open Pull Request
    │  (Merchant approves content, ML Engineer approves schema)
    │
    ▼
Merge to main → chatbot restarts → new intent is live
```

**Promotion checklist (PR template):**
- [ ] `intent_id` is unique and matches filename
- [ ] At least 5 diverse `example_utterances`
- [ ] All required slots have a prompt and optional regex validation
- [ ] `resolution_config` is complete and tested against mock backend
- [ ] `python -m chatbot.registry.validate` exits 0
- [ ] At least one manual test in the chatbot widget confirms the happy path

---

## 4. Fine-Tuning Dataset Export

The **Export Labeled Tickets as JSONL** button (Admin → Bot Improvement tab)
produces a JSONL file where every line is a JSON object:

```json
{
  "ticket_id": "abc-123",
  "user_message": "where is my order?",
  "correct_intent": "order_status",
  "confidence": 1.0,
  "resolution_path": "bot_resolved",
  "bot_response": "Here's the latest on order ORD-1001…"
}
```

**Included tickets:** only those where `human_verified = 1`, meaning an admin
has confirmed the intent label via the Tickets tab → Approve Classification.

**Usage:** feed this JSONL to an Anthropic fine-tuning job (or any
compatible LLM fine-tuning pipeline) as training examples for the intent
classifier. The `correct_intent` field is the ground-truth label;
`bot_response` can be used as the target completion for response generation.

---

## 5. Response Improvement Suggestions

Suggested responses saved from the Bot Improvement tab are stored as JSON
files in `data/response_suggestions/<ticket_id>.json`:

```json
{
  "ticket_id": "…",
  "user_message": "…",
  "bot_response": "… (original)",
  "suggested_response": "… (admin's improved version)",
  "intent": "order_status",
  "saved_at": "2025-01-15T10:00:00"
}
```

The ML Engineer reviews these during the Wednesday implementation step and
updates the relevant `resolution_config` in the intent JSON file.

---

## 6. Roles & Responsibilities

| Role | Responsibility |
|---|---|
| **Merchant** | Content sign-off on new intents; reviews response suggestions for tone |
| **Support Lead** | Identifies patterns in unmatched messages; promotes draft intents |
| **ML Engineer** | Runs validation, exports fine-tuning data, updates resolution configs, deploys |
| **Bot (Oli)** | Flags low-confidence turns automatically; collects CSAT feedback post-resolution |
