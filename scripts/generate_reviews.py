"""Generate a mock review corpus + patch product ratings.

Run from the project root:
    python scripts/generate_reviews.py

Reads:  data/mock/products.json
Writes: data/mock/reviews.json
        data/mock/products.json   (rating + review_count are recomputed)

The distribution rules per product:
    1-star: 5-25%   (pre-normalization weight)
    2-star: 5-15%
    3-star: 20-60%
    4-star: 30-70%
    5-star: 50-95%
After drawing one value per range, weights are normalized to sum to 1 and
multiplied by a per-product review_count drawn uniformly from [20, 30].

Reviews come from category-aware text templates (positive / neutral / negative).
No LLM calls — fully deterministic given the seed.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = ROOT / "data" / "mock" / "products.json"
REVIEWS_PATH = ROOT / "data" / "mock" / "reviews.json"

SEED = 42
TODAY = date(2026, 5, 9)

# Per-star pre-normalization weight ranges (from the user's rules).
STAR_RANGES: dict[int, tuple[float, float]] = {
    1: (0.05, 0.25),
    2: (0.05, 0.15),
    3: (0.20, 0.60),
    4: (0.30, 0.70),
    5: (0.50, 0.95),
}

REVIEW_COUNT_RANGE = (20, 30)

# ---------------------------------------------------------------------------
# Author name pool (Italian / Portuguese / English mix)
# ---------------------------------------------------------------------------

AUTHOR_NAMES: list[str] = [
    # Italian
    "Marco Rossi", "Sofia Bianchi", "Luca Ferrari", "Giulia Russo",
    "Alessandro Marino", "Francesca Gallo", "Matteo Ricci", "Chiara De Luca",
    "Lorenzo Bruno", "Valentina Conti", "Davide Esposito", "Martina Romano",
    "Riccardo Greco", "Eleonora Lombardi", "Federico Costa",
    # Portuguese
    "João Silva", "Maria Santos", "Pedro Oliveira", "Ana Pereira",
    "Carlos Mendes", "Sofia Rodrigues", "Tiago Costa", "Inês Lopes",
    "Rui Ferreira", "Beatriz Martins", "Diogo Almeida", "Catarina Gomes",
    "Miguel Sousa", "Mariana Carvalho", "André Pinto",
    # English
    "Emma Johnson", "James Smith", "Olivia Brown", "Liam Wilson",
    "Sophia Davis", "Noah Miller", "Isabella Garcia", "Mason Anderson",
    "Mia Taylor", "Ethan Thomas", "Ava Martinez", "Lucas Robinson",
    "Charlotte Clark", "Henry Lewis", "Amelia Walker",
    # Spanish
    "Carlos Hernández", "Lucía García", "Pablo Fernández", "María López",
    "Diego Sánchez", "Carmen Ruiz",
    # French
    "Antoine Martin", "Camille Dubois", "Julien Bernard", "Léa Petit",
]

# ---------------------------------------------------------------------------
# Template banks
# Each (category, tone) bucket holds ~12 (title, body) pairs.
# Tone is derived from the rating: 5/4 = positive, 3 = neutral, 2/1 = negative.
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict[str, list[tuple[str, str]]]] = {
    # ── BEAUTY ──────────────────────────────────────────────────────────────
    "cat_beauty": {
        "positive": [
            ("Glowing results", "Real difference on my skin after just a few weeks. The texture, the smell, everything feels premium."),
            ("My new favorite", "Lightweight, absorbs fast, and doesn't pill under makeup. I've already reordered."),
            ("Worth every cent", "I've used cheaper alternatives for years and never had results like this. Totally won me over."),
            ("Pleasantly surprised", "Wasn't sure if the marketing was real but it actually delivers. Skin looks fresher and calmer."),
            ("Holy grail status", "I've tried at least ten products in this category and this one is a clear step above. Recommended."),
            ("Smells amazing", "The scent is subtle and clean. Doesn't compete with my perfume. Bonus points for the packaging."),
            ("Great daily go-to", "Nothing dramatic but consistent results day after day. That's exactly what I want from a routine product."),
            ("Beautifully formulated", "You can tell from the texture that this isn't a generic formula. Sinks in fast, never sticky."),
            ("Confidence booster", "I get more compliments when I'm wearing this. The finish is gorgeous and lasts all day."),
            ("Perfect gift", "Bought one for myself and one for a friend. Beautiful packaging, beautiful product. Both of us are converts."),
            ("Game changer for sensitive skin", "I'm reactive to almost everything and this didn't sting or break me out. Very impressed."),
            ("Love everything about it", "Texture, scent, packaging, results. I can't think of a single thing I'd change."),
        ],
        "neutral": [
            ("It's fine", "Does what it says, no more no less. I'd buy it again if it were on sale, otherwise probably not."),
            ("Okay but not amazing", "Decent enough product. I expected a bit more given the price point and the reviews."),
            ("Mixed feelings", "The texture is great but I'm not seeing the dramatic results others mention. Maybe needs more time."),
            ("Solid but unremarkable", "There's nothing wrong with it — works fine — but it didn't blow me away either."),
            ("Average product", "Middle of the road. Not bad, not exceptional. Plenty of other options on the market at this price."),
            ("Decent for the price", "Gets the job done. The packaging feels a bit basic and I'm not in love with the scent, but functionally OK."),
            ("Could be better", "I like it overall, but the formula could be lighter and the bottle could be more functional."),
            ("Works, but…", "It does work, it just hasn't replaced my long-time favorite. Worth trying once if you're curious."),
            ("Three stars feels right", "Not a regret, not a recommendation. Pretty neutral experience throughout."),
            ("Reasonable but unspectacular", "Standard quality for the segment. I think there's better out there if you're willing to look."),
            ("It's alright", "Nothing to write home about. I'll finish the bottle but probably won't repurchase."),
            ("Functional", "Smells okay, performs okay, looks okay on the shelf. Just okay."),
        ],
        "negative": [
            ("Disappointing", "Expected a lot more for the price. Didn't see any visible difference after weeks of use."),
            ("Caused breakouts", "Skin reacted badly within a few days. Had to stop using it entirely."),
            ("Smell is overpowering", "The fragrance is way too strong — gives me a headache. Hard to use daily."),
            ("Not as advertised", "Marketing makes promises the product can't keep. Save your money for something else."),
            ("Texture is off", "Sticky and never absorbs properly. Sits on top of the skin all day."),
            ("Returned it", "Returned within the first week. Just didn't work for me at all."),
            ("Overpriced", "Quality doesn't justify the price tag at all. Better options for half the cost."),
            ("Felt cheap", "Packaging feels flimsy and the product itself underwhelms. Not what I expected from this brand."),
            ("Made my skin worse", "After two weeks my skin was drier and more irritated than before. Had to revert to my old routine."),
            ("Won't repurchase", "Tried it, gave it a fair shot, didn't love it. Moving on."),
            ("Almost no scent and weak finish", "Color/scent both barely there. Maybe I got a bad batch but I'm not happy."),
            ("Major letdown", "Hyped product, lukewarm result. Plenty of better choices."),
        ],
    },
    # ── BOOKS ───────────────────────────────────────────────────────────────
    "cat_books": {
        "positive": [
            ("Couldn't put it down", "Read it in two sittings. Beautifully paced, with characters that stay with you."),
            ("Thoughtful and engaging", "A rare book that respects the reader's intelligence. Highly recommend to anyone curious about the topic."),
            ("Beautifully produced", "Paper quality, typesetting, cover design — every detail shows care. Lovely on the shelf."),
            ("Wish I'd read it sooner", "Genuinely shifted how I think about a few things. Wish I'd discovered it years ago."),
            ("Perfect gift", "Gave it as a present and the recipient was thrilled. Will be buying another copy for myself."),
            ("Excellent reference", "I keep coming back to this book. Well organized, indexed, and the writing is clear without dumbing things down."),
            ("Compelling from page one", "Great opening hook and the momentum doesn't let up. Couldn't recommend more enthusiastically."),
            ("Refreshingly honest", "Doesn't oversell, doesn't pander. Just solid, well-researched writing on a subject I care about."),
            ("A modern classic", "I think this one will be read for years to come. Genuinely worth the hype."),
            ("Stunning illustrations", "The visuals carry the book as much as the text. A real pleasure to leaf through."),
            ("Read it twice already", "Different things landed on the second read — the kind of book that rewards rereading."),
            ("Worth every euro", "Long, dense, and absolutely worth the time. I keep telling friends about it."),
        ],
        "neutral": [
            ("Decent read", "Some chapters are excellent, others drag. Worth picking up but I wouldn't put it at the top of the list."),
            ("Slow start, better second half", "Took me a while to get into. The payoff is decent but the first 100 pages tested my patience."),
            ("Repetitive in places", "Good ideas but they're explained over and over. Could have been 50 pages shorter."),
            ("Solid, not exceptional", "Reads well enough but doesn't bring much new to the genre. Fine if you want something easy."),
            ("Mixed quality", "Some sections are great. Others felt phoned in. Frustrating because the highs are really high."),
            ("Average", "I finished it but I won't be recommending it. Not bad, just unmemorable."),
            ("Three out of five", "Some genuine moments of insight. Padding around them. Net positive but a near-miss."),
            ("Okay introduction", "If you're new to the topic this is fine. If you've read more than a couple of books on it you'll find it shallow."),
            ("Reasonable but flawed", "Editing could have been tighter. Several typos and one factual mistake I caught immediately."),
            ("Not bad", "Has its moments. Probably worth borrowing rather than buying."),
            ("Fine for a long flight", "Easy to read, doesn't demand much, doesn't reward much either."),
            ("Middle of the road", "I don't regret reading it. I also don't think about it much."),
        ],
        "negative": [
            ("Disappointing", "Loved the premise, hated the execution. The writing feels rushed and the structure is muddled."),
            ("Couldn't finish", "Gave up around chapter four. The pacing was painfully slow and I didn't care about any character."),
            ("Poorly edited", "Multiple typos, inconsistent style, factual errors. Felt like the publisher rushed it out."),
            ("Misleading title", "The book is barely about what the title claims. Felt baited."),
            ("Not for me", "Lots of people seem to love this. I just couldn't get into it. Style felt forced."),
            ("Pages came damaged", "Print quality was rough — bent corners, off-color photos. Sent it back."),
            ("Shallow treatment", "Skims the surface of every topic without really engaging. I expected more depth."),
            ("Hype outpaces the book", "Read so many positive reviews. Reality didn't match. Ended up frustrated."),
            ("Overlong", "Could have been half the length and twice as effective. Lost interest by the middle."),
            ("Confusing structure", "The chapters jump around without clear logic. Hard to follow the argument."),
            ("Felt dated", "Some references and assumptions haven't aged well. Pulled me out of the reading every few pages."),
            ("Returned for a refund", "Couldn't justify keeping this on the shelf. Not what I'd hoped for."),
        ],
    },
    # ── FASHION ─────────────────────────────────────────────────────────────
    "cat_fashion": {
        "positive": [
            ("Perfect fit", "Sizing is true and the cut is flattering. Already ordered a second color."),
            ("Beautiful quality", "The fabric and stitching make it feel like something twice the price. Holds up wash after wash."),
            ("Compliments every time", "Wore it twice this week and got compliments both times. Definitely a wardrobe staple now."),
            ("Looks even better in person", "Photos don't do justice to the color and texture. Genuinely impressed when it arrived."),
            ("Versatile and easy", "Goes with everything I already own. The kind of piece I reach for without thinking."),
            ("Great wash and wear", "Survived multiple machine washes with zero shape loss. The sign of a properly made garment."),
            ("Worth the splurge", "A bit pricey but justified. The construction is excellent and it's something I'll wear for years."),
            ("Beautiful drape", "Falls just right. Not bunchy, not stiff. The kind of detail that's hard to capture in a photo."),
            ("Quickly became a favorite", "Within a week it was already my go-to. Fits well, looks good, comfortable all day."),
            ("Excellent craftsmanship", "Real attention to seams, finishing, and details. You can tell someone cared when they made this."),
            ("Got my size right", "Size chart was accurate, ordered my usual and it fits perfectly. So rare with online shopping."),
            ("Surpassed expectations", "I was hesitant at first because of the price. Now I wish I'd bought two."),
        ],
        "neutral": [
            ("Decent but runs small", "Fabric is fine but I had to size up. Order a size larger than usual if you're between sizes."),
            ("Looks ok, color is off", "Real-life color is a touch different from the photos. Not a deal breaker but worth flagging."),
            ("Average quality", "Functional. Not bad but not what I'd call premium. About what you'd expect at this price."),
            ("Fits oddly", "Cut is unusual — works on some body types better than others. I'll keep it but it's not perfect."),
            ("Three stars", "Solid basics. Nothing exciting. Would I buy it again? Probably not at full price."),
            ("Decent material, weak finish", "The fabric is nice but the stitching has loose threads in a few places. Quality control could be better."),
            ("Wearable but not exciting", "Comfortable enough, looks fine in the mirror. Doesn't make me want to grab it first."),
            ("Hits and misses", "Looks great with one outfit, weird with another. Hard to integrate."),
            ("So-so", "Bought on sale, glad I didn't pay full price. Neither bad nor memorable."),
            ("OK for the price", "Reasonable value. Not the kind of thing you'd splurge on but does the job."),
            ("Wash drained the color", "After a few washes it lost some of the original vibrancy. Holding shape but looking tired."),
            ("Functional", "Wears okay, fits okay, looks okay. Just okay."),
        ],
        "negative": [
            ("Quality disappointment", "Stitching unraveled after the first wear. Sent it back — not what I expected at this price."),
            ("Sizing way off", "I usually wear M and even L was tight. Returned and gave up on the brand."),
            ("Color faded fast", "Looked great new, looked tired after three washes. Won't buy from this line again."),
            ("Cheap fabric", "The material feels nothing like the photos suggest. Thin, scratchy, disappointing."),
            ("Doesn't match the photos", "Color, fit, and texture all different from what's shown online. Frustrating experience."),
            ("Returned immediately", "Pulled it out of the package, knew within seconds it wasn't right. Returned same day."),
            ("Shrunk in the wash", "Followed the care label, still ended up two sizes smaller. Now unwearable."),
            ("Falling apart", "After a month of normal wear there are loose threads everywhere. Construction is poor."),
            ("Overpriced", "For what you get, the price is unreasonable. There are much better options at this level."),
            ("Disappointed", "Looked beautiful in the listing. The reality is nowhere near. Sad."),
            ("Hardware broke", "The button/zipper failed within weeks. Cheap mechanism that didn't survive normal use."),
            ("Fit is unflattering", "On a model it might work. On me it just doesn't. Awkward proportions."),
        ],
    },
}


def tone_for(rating: int) -> str:
    if rating >= 4:
        return "positive"
    if rating == 3:
        return "neutral"
    return "negative"


# ---------------------------------------------------------------------------
# Distribution sampler
# ---------------------------------------------------------------------------

def sample_star_counts(rng: random.Random, total: int) -> dict[int, int]:
    """Draw raw weights per star, normalize, scale to `total` reviews."""
    raw = {star: rng.uniform(lo, hi) for star, (lo, hi) in STAR_RANGES.items()}
    s = sum(raw.values())
    norm = {star: w / s for star, w in raw.items()}
    counts = {star: round(p * total) for star, p in norm.items()}

    # Adjust rounding drift onto the largest bucket so total matches exactly.
    diff = total - sum(counts.values())
    if diff != 0:
        biggest = max(counts, key=counts.get)
        counts[biggest] += diff
    return counts


def random_date(rng: random.Random, days_back: int = 540) -> str:
    delta = rng.randint(1, days_back)
    return (TODAY - timedelta(days=delta)).isoformat()


def helpful_count(rng: random.Random, rating: int) -> int:
    if rating >= 4:
        return rng.randint(0, 35)
    if rating == 3:
        return rng.randint(0, 15)
    return rng.randint(0, 10)


# ---------------------------------------------------------------------------
# Per-product review generation
# ---------------------------------------------------------------------------

def generate_reviews_for_product(
    product: dict,
    rng: random.Random,
) -> tuple[list[dict], float]:
    """Return (reviews_list, average_rating)."""
    cat = product["category_id"]
    pid = product["id"]

    total = rng.randint(*REVIEW_COUNT_RANGE)
    counts = sample_star_counts(rng, total)

    # Build a per-tone shuffled queue so we don't repeat templates inside one product.
    template_queues: dict[str, list[tuple[str, str]]] = {}
    for tone, items in TEMPLATES[cat].items():
        copy = list(items)
        rng.shuffle(copy)
        template_queues[tone] = copy

    reviews: list[dict] = []
    counter = 0
    rating_sum = 0
    for star in (5, 4, 3, 2, 1):
        n = counts[star]
        if n <= 0:
            continue
        tone = tone_for(star)
        rating_sum += star * n
        for _ in range(n):
            counter += 1
            queue = template_queues[tone]
            if not queue:
                queue.extend(TEMPLATES[cat][tone])
                rng.shuffle(queue)
            title, body = queue.pop()
            reviews.append({
                "id": f"rev_{pid}_{counter:02d}",
                "product_id": pid,
                "author_name": rng.choice(AUTHOR_NAMES),
                "rating": star,
                "date": random_date(rng),
                "title": title,
                "body": body,
                "verified_purchase": rng.random() < 0.80,
                "helpful_count": helpful_count(rng, star),
            })

    avg = rating_sum / total if total else 0.0
    return reviews, avg


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    rng = random.Random(SEED)

    with open(PRODUCTS_PATH, encoding="utf-8") as f:
        products = json.load(f)

    all_reviews: list[dict] = []
    cat_summary: dict[str, list[float]] = {}

    for product in products:
        reviews, avg = generate_reviews_for_product(product, rng)
        all_reviews.extend(reviews)
        product["rating"] = round(avg, 1)
        product["review_count"] = len(reviews)
        cat_summary.setdefault(product["category_id"], []).append(avg)

    with open(REVIEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_reviews, f, ensure_ascii=False, indent=2)

    with open(PRODUCTS_PATH, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(all_reviews)} reviews across {len(products)} products.")
    for cat, ratings in cat_summary.items():
        avg = sum(ratings) / len(ratings)
        print(f"  {cat:12s} | products={len(ratings):2d} | avg rating={avg:.2f}")


if __name__ == "__main__":
    main()
