# Intent Registry

The **single source of truth** for everything the chatbot can resolve.
Non-developers (support leads, product managers) can add or modify intents here
without touching any bot code — just edit JSON, run the validator, and open a PR.

---

## Directory layout

```
chatbot/registry/
├── intent.schema.json     # JSON Schema that every intent must satisfy
├── loader.py              # Runtime loader used by the bot and UI
├── validate.py            # Offline validator (run before merging a PR)
├── README.md              # This file
└── intents/
    ├── order_status.json
    ├── return_policy.json
    ├── refund_status.json
    ├── shipping_info.json
    ├── product_availability.json
    └── cancel_order.json
```

---

## How to add a new intent (step-by-step)

### 1 — Copy the template

```bash
cp chatbot/registry/intents/return_policy.json \
   chatbot/registry/intents/my_new_intent.json
```

### 2 — Edit the fields

Open `my_new_intent.json` in any text editor and fill in:

| Field | What to write |
|---|---|
| `intent_id` | Unique `snake_case` id, e.g. `"size_guide"`. Must match the filename. |
| `display_name` | Short label for the UI button, e.g. `"Size Guide"`. |
| `category` | One of `orders` / `returns` / `products` / `account` / `other`. |
| `example_utterances` | **At least 5** real phrases shoppers type. More = better classification. |
| `required_slots` | Leave `[]` if no info is needed. Otherwise add slot objects (see below). |
| `resolution_type` | `"faq_answer"` for static text, `"api_call"` for live data, `"guided_flow"` for multi-step. |
| `resolution_config` | Depends on `resolution_type` — see shapes below. |
| `escalation_triggers` | Conditions that should route the user to a human agent. |
| `confidence_threshold` | How confident the classifier must be (default `0.70`). |
| `is_button_visible` | `true` = show as a quick-action button when the chat opens. |

### 3 — resolution_config shapes

**faq_answer** — static answer, supports Markdown:
```json
"resolution_config": {
  "answer": "Your answer here. Supports **bold**, lists, and [links](https://example.com)."
}
```

**api_call** — calls a backend endpoint, fills a response template:
```json
"resolution_config": {
  "endpoint": "/api/v1/some-resource/{slot_name}",
  "method": "GET",
  "response_template": "Here is your result: {field_from_api_response}"
}
```

**guided_flow** — multi-step conversation:
```json
"resolution_config": {
  "steps": [
    { "prompt": "First question?", "expected_input_type": "confirmation" },
    { "prompt": "Second question?", "expected_input_type": "choice" },
    { "prompt": "Final message shown to user.", "expected_input_type": "free_text" }
  ]
}
```
`expected_input_type` options: `confirmation`, `choice`, `free_text`, `number`.

### 4 — Validate locally

```bash
# From the project root:
python -m chatbot.registry.validate
```

All intents must show `✓  OK`. Fix any errors before continuing.

### 5 — Open a PR

Commit only the new JSON file(s). The CI pipeline runs the validator automatically.
A tech-team reviewer will approve the PR — no code changes needed on their side.

---

## How the bot uses this registry

- **Classifier** (`chatbot/classifier/`) uses `example_utterances` for few-shot prompting or fine-tuning.
- **Slot collector** iterates `required_slots` to ask the user for missing information.
- **Resolver** reads `resolution_type` + `resolution_config` to produce the answer.
- **Escalation handler** triggers human handoff when any string in `escalation_triggers` is returned by the API or detected in the conversation.
- **UI button generator** (`frontend/`) calls `get_visible_buttons()` from `loader.py` to render quick-action chips.

---

## Editing an existing intent

Open the relevant file in `intents/`, make your changes, re-run `validate.py`, and open a PR.
**Do not change `intent_id`** after the intent is live — it is used as the primary key in logs and analytics.

---

*Built for Nova SBE · Advanced Topics in Machine Learning 2026*
