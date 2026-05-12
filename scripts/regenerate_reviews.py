"""Expand the review corpus with 100 brand-new unique (title, body) pairs.

Run from the project root:
    python scripts/regenerate_reviews.py

Reads:  data/mock/products.json
        data/mock/reviews.json   (preserved as-is, used as the base)
Writes: data/mock/reviews.json   (existing + appended new records)

Goals (set by the user):
- Existing 1,101 reviews stay completely untouched (id, date, rating, author,
  helpful_count, body, title, verified_purchase — everything).
- Add ~114 new reviews so that the per-product distribution becomes:
    * ~35 products with 20-30 reviews (the head, unchanged)
    * ~8  products with 31-40 reviews
    * ~2  products with 41-45 reviews
  Global average rises from 24.5 to ~27.
- The 100 new (title, body) pairs below are unique vs. the existing corpus and
  unique vs. each other, written by category and sentiment tone.
- Ratings for the new records are sampled around each product's current rating
  so the displayed average doesn't drift noticeably.

Deterministic given SEED.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = ROOT / "data" / "mock" / "products.json"
REVIEWS_PATH = ROOT / "data" / "mock" / "reviews.json"

SEED = 17
TODAY = date(2026, 5, 12)
DATE_WINDOW_DAYS = 315  # ~10.5 months back from TODAY → 2025-07 .. 2026-05

AUTHOR_NAMES: list[str] = [
    "Marco Rossi", "Sofia Bianchi", "Luca Ferrari", "Giulia Russo",
    "Alessandro Marino", "Francesca Gallo", "Matteo Ricci", "Chiara De Luca",
    "Lorenzo Bruno", "Valentina Conti", "Davide Esposito", "Martina Romano",
    "Riccardo Greco", "Eleonora Lombardi", "Federico Costa",
    "João Silva", "Maria Santos", "Pedro Oliveira", "Ana Pereira",
    "Carlos Mendes", "Sofia Rodrigues", "Tiago Costa", "Inês Lopes",
    "Rui Ferreira", "Beatriz Martins", "Diogo Almeida", "Catarina Gomes",
    "Miguel Sousa", "Mariana Carvalho", "André Pinto",
    "Emma Johnson", "James Smith", "Olivia Brown", "Liam Wilson",
    "Sophia Davis", "Noah Miller", "Isabella Garcia", "Mason Anderson",
    "Mia Taylor", "Ethan Thomas", "Ava Martinez", "Lucas Robinson",
    "Charlotte Clark", "Henry Lewis", "Amelia Walker",
    "Carlos Hernández", "Lucía García", "Pablo Fernández", "María López",
    "Diego Sánchez", "Carmen Ruiz",
    "Antoine Martin", "Camille Dubois", "Julien Bernard", "Léa Petit",
]

# ---------------------------------------------------------------------------
# 100 new (title, body) pairs — unique, organised by category and tone.
# Tone distribution per category: ~60% positive, ~25% neutral, ~15% negative.
# ---------------------------------------------------------------------------

NEW_TEMPLATES: dict[str, dict[str, list[tuple[str, str]]]] = {
    "cat_beauty": {
        "positive": [
            ("Skin feels reborn", "Two weeks in and my complexion is noticeably more even. The whole ritual feels luxurious without being fussy."),
            ("Quietly addictive", "I keep finding excuses to use it again. Soft, comforting, with results that build slowly."),
            ("Travels beautifully", "Compact, doesn't leak, and stays effective even after a long flight. Now lives permanently in my carry-on."),
            ("Cleaner ingredients", "Read the full ingredient list and it's genuinely well thought out. No fillers, no harsh extras."),
            ("Replaces three products", "Simplified my routine in the best way. One step instead of three, with better results."),
            ("Calm and clear", "Worked through a stressful month without a single breakout. That alone earns five stars."),
            ("Subtle finish, big impact", "Doesn't look made up but everyone keeps asking what I'm using. The greatest compliment."),
            ("Forgot what tight skin felt like", "Hydration that actually holds. Even in air-conditioning all day my skin doesn't feel parched."),
            ("Smells like a spa", "The fragrance alone is worth the price. Closing my eyes during application feels like a mini vacation."),
            ("Honest formula", "No greenwashing, no overclaiming. Just a good product that does what's on the label."),
            ("Sensitive-skin savior", "Years of trial and error, finally something my reactive skin tolerates. Will repurchase before I run out."),
            ("Brightening, not bleaching", "Genuine glow without that weird flat finish other products give. Looks natural even in daylight."),
            ("Generous size", "The bottle lasted me almost three months with daily use. Excellent value for the price."),
            ("A friend asked where I bought it", "She thought I'd had a facial. The compliments started after week two and haven't stopped."),
            ("Texture I keep going back to", "Some products you tolerate, this one you enjoy. Glides on, sinks in, no residue."),
            ("Reordered already", "Halfway through the bottle and I've already placed a second order. That's how much I trust it."),
            ("Beautiful before bedtime", "Layers perfectly under my nighttime routine. Wake up looking rested even when I'm not."),
            ("Soft, never sticky", "Some products in this space stay tacky for an hour. This one absorbs in seconds and stays comfortable."),
            ("Bridal-ready", "Used it for two months before my wedding. My skin looked the best it ever has in photos."),
            ("Subtle scent, lasting effect", "Doesn't fight my perfume and the benefits last well into the next day."),
            ("Better than the cult favorite", "Tried the famous competitor for years. This is comparable at half the price."),
        ],
        "neutral": [
            ("Took time to see results", "First few weeks were unimpressive. Around day twenty things started improving. Patience required."),
            ("Better in winter", "Hydration is welcome in dry months. Felt too heavy when it warmed up. Season-dependent."),
            ("Inconsistent batches", "First bottle was great, second one feels watered down. Same brand, different experience."),
            ("Decent but pricey", "Effects are real but the markup is steep. I'd grab it on a promo, not at full price."),
            ("Average performer", "Worked as expected, didn't surprise me. There are several similar products at this tier."),
            ("Mild improvement", "Small step forward, not the leap I was hoping for. Will finish but probably move on."),
            ("Shade differs from photo", "Slightly cooler tone than shown online. Workable but not a perfect match."),
            ("Packaging looks dated", "Product is solid, the bottle design looks a decade behind. Doesn't change how it works."),
            ("Mostly fine", "A few minor gripes, otherwise unremarkable. Three stars feels honest."),
        ],
        "negative": [
            ("Caused redness", "Within four days my cheeks were burning. Had to switch to a calming routine. Not for me."),
            ("Pump broke quickly", "Within two weeks the dispenser stopped working. I had to unscrew the cap to get the rest out."),
            ("Scent is chemical", "Smells like a cleaning product, not a beauty product. Couldn't stand applying it."),
            ("Greasy residue", "Sits on top of my skin all day. No matter how little I use, it never absorbs properly."),
            ("Did nothing", "Used it daily for six weeks. Zero visible difference. Saved my receipt for a refund."),
        ],
    },
    "cat_books": {
        "positive": [
            ("Made me think for weeks", "Finished it on a Tuesday and was still mulling over it the following weekend. That's the mark of good writing."),
            ("A book to underline", "Practically every page has something quotable. Buying a second copy for friends."),
            ("Patient and rewarding", "Doesn't rush. Each chapter earns its conclusions. Worth taking the time."),
            ("Brought back the joy of reading", "Hadn't finished a book in months. This one pulled me right back into the habit."),
            ("Honest and human", "No grandstanding, no shortcuts. The author respects the reader and the material."),
            ("Found my new favorite author", "Already ordered everything else they've written. Hope the rest holds up to this standard."),
            ("Stunning prose", "Sentences I read twice just for the rhythm. The kind of writing you savor."),
            ("Surprisingly funny", "Didn't expect to laugh out loud on a train. Got a few odd looks. Highly recommend."),
            ("Perfect bedtime read", "Calming, intelligent, the right length per chapter. Reading it became the best part of my day."),
            ("Changed my routine", "The practical sections were genuinely useful. Several small habits stuck."),
            ("Felt seen", "The author articulated experiences I'd struggled to put into words. Quietly powerful."),
            ("Excellent translation", "Read both the original and this version. The English captures the spirit beautifully."),
            ("Worth re-reading", "Finished it, waited two months, started again. Different things stood out the second time."),
            ("Generous with examples", "Concepts grounded in specific cases. Made the ideas stick in a way pure theory wouldn't."),
            ("Beautiful object", "The hardcover edition is genuinely a pleasure to hold. Print quality is top-tier."),
            ("Recommended to my book club", "We had our best discussion in months. Everyone had a different favorite chapter."),
            ("Final chapter floored me", "Built quietly to a conclusion that earned every page. Closed the book and just sat there."),
            ("Rare voice", "There's a perspective here you don't see often in the genre. Refreshing."),
            ("Concise without being thin", "Every page has weight. Nothing padded out. Respect for the reader's time."),
            ("Useful for years", "Bookmarking pages I'll come back to. The kind of reference that earns shelf space."),
            ("Felt like a long conversation", "Reading it was like talking to someone who genuinely knows the subject. Warm and rigorous."),
        ],
        "neutral": [
            ("Solid first half", "Started strong, lost steam past chapter ten. Glad I read it but didn't reread."),
            ("Some sections are gold", "Three chapters really stuck with me. The rest blurred together."),
            ("Better as an audiobook", "Found my attention drifting in print. Probably my preference more than the book's fault."),
            ("Decent overview", "Good if you're new to the topic. Felt thin if you've read around the subject before."),
            ("Worth it on sale", "Picked it up discounted, glad I didn't pay full price. Worth a once-through."),
            ("Not bad, not memorable", "Finished without complaint, won't bring it up at dinner."),
            ("Reasonable effort", "Author clearly cares but the structure could use one more editing pass."),
            ("Predictable arc", "Could see the shape of it from chapter two. Still pleasant enough company."),
            ("Average prose", "Function over style. Communicates fine, doesn't dazzle."),
        ],
        "negative": [
            ("Couldn't connect", "Tried twice and shelved it both times. Style just didn't work for me."),
            ("Riddled with errors", "Found at least six factual mistakes I could verify quickly. Hurts the credibility of the rest."),
            ("Repetitive", "Same idea explained four different ways. Could have been an essay, padded into a book."),
            ("Pages fell out", "Binding gave up halfway through. The picture of a book that wasn't built to last."),
            ("Boring", "Tried, gave up at page sixty. Life is short and the bookshelf is full."),
        ],
    },
    "cat_fashion": {
        "positive": [
            ("Stitches still tight a year later", "Worn weekly through a winter and shows no wear. Real quality construction."),
            ("Cut suits my body type", "Most pieces in this style flatten my frame. This one has shape in the right places."),
            ("Fabric breathes", "Comfortable in heat and layered well in cooler months. Genuinely versatile."),
            ("Hides the wash", "Three cycles in and it still looks new. Color and shape both intact."),
            ("Perfect dress-up dress-down piece", "Pairs with sneakers and with heels. Earned its spot in my wardrobe rotation."),
            ("Color is even better in person", "Photos undersell it. Beautiful saturation, looks rich and modern."),
            ("Lining is a nice surprise", "Many similar items skip the lining. This one has it and it makes a real difference."),
            ("Pockets that actually fit a hand", "Functional pockets in womenswear feel like winning the lottery. Bravo."),
            ("Got compliments at work", "Two colleagues asked about it the first day. Subtle but striking."),
            ("Feels like a good investment", "Pricier than fast fashion, but easily three times the lifespan. Math checks out."),
            ("Holds shape after wear", "Lots of garments stretch out by evening. This one ends the day looking sharp."),
            ("Right on size", "Size chart was accurate and my usual size fits well. No returns hassle."),
            ("Soft against the skin", "Sensitive skin, no irritation. Wore it for ten hours straight without thinking about it."),
            ("Wears in beautifully", "Looked good new, looks even better after two months. Like good denim used to."),
            ("Worth the wait", "Restock notification arrived three weeks late but I'd wait again. Easily worth it."),
            ("Easy travel piece", "Packs flat, doesn't crease, looks pulled together right out of the suitcase."),
            ("Layered well", "Slips under a coat and over a tee equally smoothly. The kind of versatility I look for."),
            ("Stylish without trying", "Doesn't look like it's trying to follow a trend. It just looks well-made and right."),
        ],
        "neutral": [
            ("Sizing inconsistent across colors", "The black fits me, the green is a touch tighter. Same size, different feel."),
            ("Comfortable, less flattering", "Feels great to wear, the cut isn't my favorite in the mirror. Trade-offs."),
            ("OK quality for the price", "What you pay for, basically. Not a bargain, not a rip-off."),
            ("Better casual than dressed up", "Works for weekends, doesn't quite elevate for events. A niche piece."),
            ("Hardware looks plasticky", "Buttons or zipper feel cheaper than the fabric suggests. Functional, not premium."),
            ("Color slightly off in evening light", "Looks great by day, slightly muddier in artificial light. Minor gripe."),
            ("Slightly itchy first wash", "Eased up after the second wash. Worth flagging for sensitive folks."),
            ("Standard fit, standard feel", "No surprises. You get what you'd expect from the segment."),
        ],
        "negative": [
            ("Pilling after one wear", "Looked terrible by the second outing. Fabric quality clearly isn't there."),
            ("Sleeves too short", "Proportions on the arms feel off. Couldn't return in time, now it's a regret."),
            ("Color bled in the wash", "Stained other items the first time it went in. Won't risk it again."),
            ("Looks cheap next to my other pieces", "Wore it side by side with similar items in my closet — it visibly doesn't compare."),
        ],
    },
}


def tone_for(rating: int) -> str:
    if rating >= 4:
        return "positive"
    if rating == 3:
        return "neutral"
    return "negative"


def random_date(rng: random.Random) -> str:
    delta = rng.randint(1, DATE_WINDOW_DAYS)
    return (TODAY - timedelta(days=delta)).isoformat()


def sample_rating(rng: random.Random, product_avg: float) -> int:
    """Sample a 1-5 rating biased around product_avg (to preserve the displayed mean)."""
    weights = {}
    for star in (1, 2, 3, 4, 5):
        distance = abs(star - product_avg)
        weights[star] = max(0.04, 1.0 / (1.0 + distance * distance * 2.0))
    stars = list(weights.keys())
    w = [weights[s] for s in stars]
    return rng.choices(stars, weights=w, k=1)[0]


def helpful_count(rng: random.Random, rating: int) -> int:
    """Log-ish distribution: usually small, occasionally large."""
    base = rng.randint(0, 5)
    if rng.random() < 0.10:
        base += rng.randint(8, 25)
    if rating <= 2 and rng.random() < 0.15:
        base += rng.randint(2, 8)
    return base


def pick_template(rng: random.Random, queues: dict[str, list[tuple[str, str]]], category: str, tone: str) -> tuple[str, str]:
    queue = queues[(category, tone)]
    if not queue:
        # Refill from the original pool, reshuffle, keep going.
        queue.extend(NEW_TEMPLATES[category][tone])
        rng.shuffle(queue)
    return queue.pop()


def main() -> None:
    rng = random.Random(SEED)

    with open(PRODUCTS_PATH, encoding="utf-8") as f:
        products = json.load(f)
    with open(REVIEWS_PATH, encoding="utf-8") as f:
        existing_reviews = json.load(f)

    # Map product_id → current review count, current max review number, product info
    reviews_by_product: dict[str, list[dict]] = {}
    for r in existing_reviews:
        reviews_by_product.setdefault(r["product_id"], []).append(r)

    def next_review_number(pid: str) -> int:
        nums = []
        for r in reviews_by_product.get(pid, []):
            try:
                nums.append(int(r["id"].rsplit("_", 1)[-1]))
            except ValueError:
                continue
        return (max(nums) if nums else 0) + 1

    # Decide the target distribution.
    # 35 products in the head (20-30, unchanged), 8 in mid (31-40), 2 in tail (41-45).
    product_ids = [p["id"] for p in products]
    rng.shuffle(product_ids)
    tail_ids = set(product_ids[:2])
    mid_ids = set(product_ids[2:10])
    # head_ids: the remaining 35 products keep their current count

    target_count: dict[str, int] = {}
    for pid in product_ids:
        current = len(reviews_by_product.get(pid, []))
        if pid in tail_ids:
            target_count[pid] = max(current, rng.randint(41, 45))
        elif pid in mid_ids:
            target_count[pid] = max(current, rng.randint(31, 40))
        else:
            target_count[pid] = current  # head: leave alone

    # Per-(category, tone) shuffled queue so we don't repeat templates back-to-back
    # within the same product.
    queues: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for cat, tones in NEW_TEMPLATES.items():
        for tone, items in tones.items():
            copy = list(items)
            rng.shuffle(copy)
            queues[(cat, tone)] = copy

    # Verify the 100 new bodies don't collide with any existing body.
    existing_bodies = {r["body"] for r in existing_reviews}
    new_bodies = {b for tones in NEW_TEMPLATES.values() for items in tones.values() for _, b in items}
    overlap = existing_bodies & new_bodies
    if overlap:
        raise SystemExit(f"ERROR: {len(overlap)} new bodies collide with existing ones: {list(overlap)[:3]}")
    total_new_unique = len(new_bodies)
    print(f"Loaded {total_new_unique} new unique bodies (target was 100).")

    # Generate the new records.
    new_records: list[dict] = []
    product_by_id = {p["id"]: p for p in products}
    for pid in product_ids:
        n_to_add = target_count[pid] - len(reviews_by_product.get(pid, []))
        if n_to_add <= 0:
            continue
        product = product_by_id[pid]
        category = product["category_id"]
        avg = product.get("rating", 4.0)
        start_num = next_review_number(pid)
        for offset in range(n_to_add):
            rating = sample_rating(rng, avg)
            tone = tone_for(rating)
            title, body = pick_template(rng, queues, category, tone)
            new_records.append({
                "id": f"rev_{pid}_{start_num + offset:02d}",
                "product_id": pid,
                "author_name": rng.choice(AUTHOR_NAMES),
                "rating": rating,
                "date": random_date(rng),
                "title": title,
                "body": body,
                "verified_purchase": rng.random() < 0.80,
                "helpful_count": helpful_count(rng, rating),
            })

    # Concatenate and write.
    merged = list(existing_reviews) + new_records
    with open(REVIEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # Report.
    from collections import Counter
    counts_per_product = Counter(r["product_id"] for r in merged)
    buckets = {"20-30": 0, "31-40": 0, "41-45": 0, "other": 0}
    for c in counts_per_product.values():
        if 20 <= c <= 30:
            buckets["20-30"] += 1
        elif 31 <= c <= 40:
            buckets["31-40"] += 1
        elif 41 <= c <= 45:
            buckets["41-45"] += 1
        else:
            buckets["other"] += 1

    total_unique_bodies = len({r["body"] for r in merged})
    avg_per_product = sum(counts_per_product.values()) / len(counts_per_product)

    print(f"Existing reviews:       {len(existing_reviews)}")
    print(f"New reviews appended:   {len(new_records)}")
    print(f"Total reviews now:      {len(merged)}")
    print(f"Unique bodies in file:  {total_unique_bodies}")
    print(f"Avg reviews / product:  {avg_per_product:.1f}")
    print(f"Distribution buckets:   {buckets}")


if __name__ == "__main__":
    main()
