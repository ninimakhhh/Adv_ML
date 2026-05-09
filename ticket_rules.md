# Project Rules — Olá Market Demo Catalog

**Project:** Nova SBE — Advanced Topics in Machine Learning (2025/26)
**Author:** Maddalena Manfredini
**Last updated:** 2026-05-09

This document captures the rules behind the simplified mock catalog and the reviews dataset, plus a short note on where AI was actually used in the project.

---

## 1. Catalog scope

The store sells products in **three categories only**:

| Category | ID         | Products |
| -------- | ---------- | -------- |
| Beauty   | `cat_beauty`  | 15       |
| Books    | `cat_books`   | 15       |
| Fashion  | `cat_fashion` | 15       |

**Total: 45 products.**

Source files:
- [`data/mock/categories.json`](data/mock/categories.json)
- [`data/mock/products.json`](data/mock/products.json)

Product IDs follow the convention `prod_{b|k|f}{NN}` (`b` = beauty, `k` = books, `f` = fashion), e.g. `prod_b07`.

---

## 2. Image rules

**Every `image_url` uses `loremflickr.com`.** Format:

```
https://loremflickr.com/600/600/{keyword1},{keyword2}?lock={N}
```

- The keywords describe what the photo should depict (e.g. `lipstick,makeup`, `cookbook,kitchen`, `linen,dress`). Loremflickr returns a real Flickr photo tagged with those keywords.
- The `lock=N` parameter pins one specific image, so the photo is **stable** across page reloads.
- Lock numbers `1–45` are reserved for products; `100–102` for the category banner images.

**Why loremflickr and not picsum or Unsplash:**
- `picsum.photos` returns random photos, not topical ones — bad for an e-commerce demo.
- The Unsplash Source API was deprecated in mid-2024.
- Loremflickr requires no API key and is stable.

If a specific photo doesn't load or doesn't match well, change its `lock` number.

---

## 3. Review rules

**Source file:** [`data/mock/reviews.json`](data/mock/reviews.json) (~1100 entries)
**Generator:** [`scripts/generate_reviews.py`](scripts/generate_reviews.py)
**Run with:** `python scripts/generate_reviews.py`

### 3.1 Per-product count

Each product gets a random number of reviews drawn from a **uniform distribution in `[20, 30]`**. For 45 products this produces between 900 and 1350 reviews; the actual seeded run produced **1101**.

### 3.2 Per-star distribution

For each product, a raw weight is drawn uniformly from these ranges (one draw per star):

| Stars | Weight range  |
| ----- | ------------- |
| 1 ★   | 5%  – 25%     |
| 2 ★   | 5%  – 15%     |
| 3 ★   | 20% – 60%     |
| 4 ★   | 30% – 70%     |
| 5 ★   | 50% – 95%     |

These ranges sum to more than 100%, so they are interpreted as **pre-normalization weights**: after sampling, all five values are normalized to sum to 1.0. The result is a per-product distribution that respects the *relative* shape of the ranges (positive-skewed on average, but with realistic variance — some products will be more critical, some near-perfect).

The number of reviews per star is then `round(weight * total_reviews)`, with rounding drift adjusted onto the largest bucket so the total matches exactly.

### 3.3 Review content

- **Templates, not LLM.** Each review's title and body are picked from a category-specific template bank (positive / neutral / negative buckets, ~12 entries each) so that 5/4-star, 3-star, and 1/2-star reviews read with the right tone.
- Within a single product page, templates do not repeat until the bank is exhausted (then the bank is reshuffled).
- **Authors** are drawn from a 50-name pool mixing Italian / Portuguese / English / Spanish / French names.
- **Dates** are randomized within the past 18 months from `2026-05-09`.
- `verified_purchase` is `true` ~80% of the time.
- `helpful_count` is randomized but capped higher for positive reviews than negative ones, mirroring how real e-commerce sites behave.

### 3.4 Determinism

The script uses `random.seed(42)`. Re-running `python scripts/generate_reviews.py` produces the **exact same** dataset. Bumping the seed regenerates everything fresh.

---

## 4. Schema invariants

After running the review generator, two product fields are **always derived**, never hand-set:

- `product["rating"]` = arithmetic mean of all generated review ratings, rounded to 1 decimal.
- `product["review_count"]` = number of generated reviews for that product.

This means catalog and reviews are guaranteed consistent — no risk of `rating: 4.8` shown next to a sea of 1-star reviews.

---

## 5. AI usage in the project

This section is about *what AI was actually used for*, not *what could be added later*.

### 5.1 Ticket classifier (real AI usage)

`ticket_routing/classifier.py` calls **Claude (`claude-sonnet-4-6`)** through the official `anthropic` Python SDK. The classifier is exposed as `classify_ticket(subject, raw_text)` and returns:

- `category` — one of `Bug`, `Shipping`, `Returns`, `Payments`, `Other`
- `confidence` — integer 0-100
- `sentiment` — `Positive` / `Neutral` / `Negative`
- `urgency` — `High` / `Medium` / `Low`
- `assigned_queue` — derived in Python from the category (deterministic)
- `reasoning` — one short sentence

Implementation choices:
- **Tool-use for structured output** (instead of free-form JSON parsing) so the model cannot return invalid enum values.
- **Prompt caching** (`cache_control: ephemeral`) on the system prompt, since the same taxonomy is reused across every ticket in a batch.
- **Singleton client** via `functools.lru_cache` so Streamlit reruns don't churn HTTPS connections.

The classifier is invoked from the admin dashboard via a "🤖 Auto-classify pending" button in the Tickets tab ([`frontend/admin_app.py`](frontend/admin_app.py)).

### 5.2 Review corpus (deliberately no AI)

The 1100+ reviews are **not** generated by an LLM. They come from a deterministic Python script with category-keyed templates ([`scripts/generate_reviews.py`](scripts/generate_reviews.py)).

This is an explicit design choice for the demo dataset:
- Generating 1100 reviews via API would mean ~1100 calls = real cost and several minutes of latency.
- The script runs in under a second, free, and is deterministic — same seed gives the same dataset.
- For a demo whose goal is to test sentiment / search / filters, template variation is good enough; the metric of interest is the **distribution shape**, not the linguistic creativity of each review.

### 5.3 Other modules (placeholders, not yet wired)

- **RAG chatbot (`chatbot/`):** scaffolding only; the floating chat widget on the user site is a placeholder UI with no LLM behind it yet.
- **Sentiment analysis on social media (`sentiment_analysis/`):** module still empty.

---

## 6. How to verify

1. **Inspect catalog files:**
   - `data/mock/categories.json` → 3 entries
   - `data/mock/products.json` → 45 entries, every `image_url` contains `loremflickr.com`, every `rating ∈ [1.0, 5.0]`, every `review_count ∈ [20, 30]`
   - `data/mock/reviews.json` → ~1100 entries with valid `product_id`s

2. **Regenerate reviews from scratch:**
   ```
   python scripts/generate_reviews.py
   ```
   Should print one summary line per category and produce identical output every run (seed = 42).

3. **Run the user site** to see the catalog rendered:
   ```
   streamlit run frontend/user_app.py
   ```
   Home page shows 3 category cards. Open a product → reviews tab shows 20-30 reviews with realistic star variance.

4. **Run the admin dashboard** to test the LLM classifier:
   ```
   streamlit run frontend/admin_app.py
   ```
   Tickets tab → click "🤖 Auto-classify pending" (requires `ANTHROPIC_API_KEY` in `.env`).
