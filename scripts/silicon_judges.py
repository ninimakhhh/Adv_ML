"""Silicon Judges: LLM-as-a-Judge evaluation of the TICXIS pitch."""

import sys
import os
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from shared.llm_client import get_deepseek_client
from shared.config import DEFAULT_DEEPSEEK_MODEL

PITCH_SUMMARY = """
TICXIS — AI-Powered Customer Experience Platform

PRODUCT
Two modules sold together:
1. CS Automation: AI chatbot + intent classifier + ticket auto-routing
2. Operational Intelligence: SKU trend analysis, sentiment monitoring, anomaly alerts

TARGET MARKET
- EU e-commerce brands, 100–800 employees, direct-to-consumer (D2C)
- Addressable segment: ~15,000 brands in EU with this profile
- Pain: CS teams overwhelmed at scale; no unified CX intelligence layer

GO-TO-MARKET
- Direct sales to Operations/CX leads
- Land-and-expand: start with one module, upsell the other
- Portuguese market first, then Spanish/Italian e-commerce clusters

PRICING & ACV
- SaaS subscription: €20k–€60k/year per customer
- Target: 10 customers Y1, growing to 80+ by Y4
- Blended ACV ~€35k

UNIT ECONOMICS
- AI compute cost: $0.00082 per ticket (blended Claude Haiku 4.5 + Sonnet 4.6)
- AI compute as % of revenue: <2.5% at scale
- Gross margin target: ~70–75%

FINANCIALS (projected)
- Y1: €175K ARR
- Y2: €650K ARR
- Y3: €2.1M ARR
- Y4: €5.5M ARR
- Break-even: month 14–18
- Funding ask: not specified in pitch (pre-seed / seed stage implied)

DEFENSIBILITY CLAIMS
1. Data network effect: proprietary EU e-commerce interaction data improves models over time
2. Workflow lock-in: deep integration into ops workflows creates switching cost
3. GDPR moat: EU-first data architecture as competitive barrier vs US hyperscalers
4. Vertical specialization: e-commerce-specific training data and prompts

TEAM
- University project team (Nova SBE); implied early-stage / student founders
- No enterprise sales experience mentioned
- Technical stack: Python, Streamlit, DeepSeek/Claude APIs, ChromaDB (RAG)

COMPETITION
- Zendesk, Freshdesk (horizontal; expensive; not AI-native for SMB)
- Intercom (chat-focused; no deep operational intelligence)
- In-house LLM wrappers (DIY; no vertical specialization)

RISKS ACKNOWLEDGED IN PITCH
- API dependency on third-party LLM providers
- EU AI Act compliance requirements
- Sales cycle length for mid-market
"""

SILICON_JUDGES_PROMPT = """You are The Silicon Judges — a panel of three ruthless but fair venture analysts embedded inside a single model. Your job is to evaluate startup pitches with the cold precision of a partner meeting and the structured output of an investment memo.

You have just reviewed the following pitch:

--- PITCH SUMMARY START ---
""" + PITCH_SUMMARY + """
--- PITCH SUMMARY END ---

Now deliver your verdict using EXACTLY this structure:

---

## SILICON JUDGES VERDICT

### ONE-PARAGRAPH SUMMARY
Describe what TICXIS is, what it does, and why it matters (or doesn't) in 4–6 sentences.

---

### SCORECARD (1–10)
Rate each dimension and give a one-sentence justification:

| Dimension | Score | Justification |
|---|---|---|
| Problem severity | /10 | |
| Market size & timing | /10 | |
| Solution differentiation | /10 | |
| Unit economics | /10 | |
| Team credibility | /10 | |
| Go-to-market realism | /10 | |
| Defensibility | /10 | |
| Execution risk | /10 | |

**COMPOSITE SCORE: X/10**

---

### THE WRAPPER TEST
*"Is this a product or a wrapper?"*
A wrapper is a thin prompt layer over an existing API with no proprietary data, no network effects, and no switching cost. Answer in 3–5 sentences: Where does TICXIS sit on the wrapper-to-moat spectrum, and what specifically would need to be true for it to escape wrapper status?

---

### CRITICAL FAULT LINES
List the top 3 deal-breaker risks in order of severity. For each:
- **Fault**: [name it]
- **Why it matters**: [1–2 sentences]
- **What would neutralize it**: [1 sentence]

---

### EDGE-CASE STRESS TESTS
Walk through 3 adversarial scenarios:
1. A hyperscaler (e.g., Salesforce, HubSpot, Zendesk) ships a native AI CX module at 1/3 the price — what happens to TICXIS?
2. EU AI Act Article 22 compliance requirements force a 6-month product rebuild — what happens?
3. Two of their first 10 customers churn in year 1 — what does that signal, and can they recover?

---

### COST STRUCTURE REVIEW
The pitch claims $0.00082/ticket blended AI compute cost.
- Is this figure plausible given current LLM API pricing? Show your math.
- At what ticket volume does AI compute become a material cost problem (>5% of revenue)?
- What is the hidden cost category the pitch likely underestimates?

---

### WHAT WOULD CHANGE YOUR MIND
List 3 specific, observable facts (not vibes) that — if true — would upgrade your conviction by 2+ points:
1.
2.
3.

---

### FINAL DECISION

**Verdict**: [Pass | Pass for now | Worth deeper diligence | Hard pass]

**One-line rationale**: [The single most important reason for your verdict]

**If "Worth deeper diligence" or "Pass for now"**: What specific milestone or data point should the founders hit before the next conversation?

---
"""

def run_evaluation():
    print("=" * 70)
    print("SILICON JUDGES — TICXIS PITCH EVALUATION")
    print("=" * 70)
    print()

    client = get_deepseek_client()

    print("Sending to DeepSeek... (this may take 30–60 seconds)\n")

    response = client.chat.completions.create(
        model=DEFAULT_DEEPSEEK_MODEL,
        messages=[
            {
                "role": "user",
                "content": SILICON_JUDGES_PROMPT,
            }
        ],
        temperature=0.7,
        max_tokens=4096,
    )

    verdict = response.choices[0].message.content
    print(verdict)

    # Save to file
    output_path = project_root / "docs" / "silicon_judges_verdict.md"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(
        f"# Silicon Judges Verdict — TICXIS\n\n*Generated by DeepSeek {DEFAULT_DEEPSEEK_MODEL}*\n\n{verdict}",
        encoding="utf-8",
    )
    print(f"\n{'=' * 70}")
    print(f"Verdict saved to: {output_path}")


if __name__ == "__main__":
    run_evaluation()
