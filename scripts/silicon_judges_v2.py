"""Silicon Judges v2 — VOXLY pitch evaluation."""

import sys
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from shared.llm_client import get_deepseek_client
from shared.config import DEFAULT_DEEPSEEK_MODEL

PITCH = """
VOXLY — AI-Powered Customer Service Intelligence for E-Commerce
Nova School of Business and Economics · 2025

PROBLEM
Two levels of pain:
Level 1 — Operational: Support teams manually read, categorise, and route tickets.
Level 2 — Insight: CS interactions are never mined for operational intelligence
  (broken product → supply chain issue; "not as described" → listing fix;
   high return on one SKU → quality mismatch; rising negative sentiment → early warning).

MARKET
$23B+ EU Customer Care BPO market (2023) → $42.6B by 2031 at 7.6% CAGR
AI for CS growing 22–26%/yr in EU; ~75% of contact centres not yet using AI
Global CC outsourcing $97B (2024) → $164B (2030) at 9.8% CAGR
VoC platform market grew 22% in 2025 (Gartner)
AI-enabled CS delivers 40–50% reduction in service interactions
No dominant EU-native player in the mid-market sub-segment.

TARGET MARKET (ICP)
E-Commerce & D2C brands · 100–800 employees · €15M–€200M revenue
Support team 15–80 agents · 10,000–150,000 monthly contacts
Economic buyer: Head of CX / VP Customer Care
ACV: €20,000–€60,000/year · Sales cycle 6–10 weeks
Qualification: 5,000+ contacts/month; churn-sensitive; stack includes
Zendesk / Gorgias / Freshdesk / Intercom. Geography v1: PT · ES · UK

VALUE PROPOSITION
Module 1 — CS Automation:
  Centralised intake; structured ticket creation (category, product, urgency, action);
  AI classification: damaged product / refund / delay / return / wrong item / payment issue;
  Confidence threshold ≥85%: auto-handled; <85% → human agent queue.
Module 2 — Operational Intelligence:
  Product complaint sentiment analysis; SKU-level ticket volume and reason breakdown;
  Trend detection (contact spike vs product releases / logistics events);
  Recurring issue alerts (auto-flag when SKU exceeds complaint threshold in time window);
  Cross-team intelligence pushed to Product, Ops, C-suite.

COMPETITIVE LANDSCAPE
VOXLY: EU native ✓, mid-market ✓, GDPR ✓, ticket intel ✓, multilingual PT/ES/IT/DE — €20k–€60k ACV
SentiSum: not EU native, no GDPR, partial intel — $36k+/yr
Chattermill: not EU native, enterprise only — €80k+ ACV
Qualtrics: partial EU, enterprise only — €100k+
Medallia: partial EU, enterprise only — €150k+
(Zendesk AI, Gorgias AI, Intercom Fin NOT listed as direct competitors)

DEFENSIBILITY CLAIMS
1. Regulatory: EU-native GDPR-first architecture (US hyperscalers cannot guarantee EU data residency by default).
2. Vertical domain: Pre-built e-commerce ticket taxonomy; assembling from raw APIs = months of work.
3. Full stack: Pre-built helpdesk integrations, 85% confidence threshold, human-in-the-loop, operational dashboards.
4. Reliability by design: Below-threshold tickets always go to human — structural, not configurable.

GO-TO-MARKET
Phase 1 (M1–6): 5 design-partner customers in Iberian e-commerce; founder-led; 50–60% discount for case study rights.
Phase 2 (M6–18): Expand to Spain + UK; small sales team; €490K ARR target (15–18 customers).
Phase 3 (M18–36): Partner channel via CX consulting firms; vertical approach; 35–45 customers · €1.4M ARR.

UNIT ECONOMICS
Model: DeepSeek V4 Flash
Input: ~400 tokens @ $0.14/1M = $0.000056
Output: ~50 tokens @ $0.28/1M = $0.000014
Total per ticket: ~$0.00007
Infrastructure (50 customers): hosting €300–600/mo, monitoring €200/mo → ~€8k/yr
AI compute < 0.1% of revenue at any tier.

COST STRUCTURE & HEADCOUNT
COGS: AI inference $0.00007/ticket + hosting €300–600/mo
OPEX: R&D (founding team Y1); sales (founder-led Y1); G&A + GDPR/SOC2 compliance
Y1: 2 people · Y2: 5 · Y3: 10 · Y4: 16

FINANCIALS
Y1: Revenue €125K · Gross Profit €103K (82%) · OpEx €150K · EBITDA –€47K (–38%)
Y2: Revenue €490K · Gross Profit €411K (84%) · OpEx €400K · EBITDA €11K (2%)
Y3: Revenue €1.4M · Gross Profit €1.22M (87%) · OpEx €850K · EBITDA €370K (26%)
Y4: Revenue €3.2M · Gross Profit €2.88M (90%) · OpEx €1.5M · EBITDA €1.38M (43%)
Break-even: ~15 Growth-tier customers · reached in Year 2.

TECHNICAL STACK
Python · FastAPI · DeepSeek API · ChromaDB · SQLite · Streamlit
Pipeline: user message → intent classifier (≥85% auto-resolve / <85% human queue)
  → escalation engine → resolution engine → ticket storage
Chatbot: Streamlit @st.dialog modal; session state; CSAT feedback loop
Classification: few-shot prompting + JSON output schema + confidence scoring
Ticket routing: category → queue mapping
Helpdesk integration: Zendesk/Freshdesk webhook guidance documented

GENAI TRANSPARENCY
Claude used for: token cost calculations, break-even analysis, P&L modelling,
EU market data research, business plan drafting (human-reviewed + edited),
prompt engineering design, backend architecture, classification prompt engineering,
React dashboard scaffolding, Zendesk/Freshdesk integration guidance.
All AI output reviewed, edited, and validated. Data verified against primary sources.
"""

SILICON_JUDGES_PROMPT = """You are The Silicon Judges, a ruthless but fair LLM-as-a-Judge for startup ideas.

Your task is to evaluate a submitted business plan and technical architecture as if you were a highly skeptical top-tier investor, technical due diligence lead, and strategy partner combined. You do not give praise unless it is clearly earned. You pressure-test logic, expose weak assumptions, simulate edge cases, challenge vague claims, and assess whether the startup has a real moat or is merely a thin wrapper around existing foundation models or APIs.

Core mandate:
- Stress-test the business model
- Stress-test the technical architecture
- Stress-test the defensibility of the company
- Stress-test the economics and operating feasibility
- Identify fatal flaws, hidden assumptions, and likely failure modes
- Be especially critical of "wrapper startups" with no durable advantage

You must think like a judge, not a coach. Be rigorous, skeptical, and specific. Do not accept buzzwords, hand-waving, or generic claims. Force concreteness.

Evaluation principles:
1. Do not reward polished language over substance.
2. Treat vague claims as unproven.
3. Distinguish between real product value and demo-level novelty.
4. Assume competitors can copy superficial features quickly.
5. Ask whether the company has a true moat: proprietary data, workflow lock-in, distribution advantage, regulatory edge, deep technical IP, operational complexity, network effects, switching costs, or brand.
6. Penalize ideas that rely mainly on "we use AI" without unique leverage.
7. Evaluate whether the technical design actually supports the business claim.
8. Evaluate whether costs, latency, reliability, compliance, and scaling realities make the idea viable.
9. Surface edge cases that would break the product, business model, or trust.
10. Prefer brutal honesty over politeness.

When reviewing the submission, analyze at minimum:

A. Problem and market — Is the problem real, frequent, painful, and budget-worthy? Who exactly is the buyer and user? Is there evidence the problem is urgent enough to pay for? Is the market large enough and reachable?

B. Solution quality — Does the product actually solve the problem? Is it meaningfully better than alternatives? What assumptions must be true for adoption?

C. Technical architecture — Is the architecture coherent, realistic, and production-grade? Are model choices, retrieval design, integrations, data pipelines, and serving setup justified? What breaks under scale, noisy inputs, adversarial behavior, or enterprise constraints? Are there hidden dependencies on third-party APIs? Does the architecture create any defensibility?

D. Moat and defensibility — Is this a real company or just a wrapper? What prevents incumbents or fast followers from copying it? Is there any compounding advantage over time? Does the startup own something others cannot easily replicate?

E. Economics — Are pricing and unit economics plausible? What are the likely cost drivers: inference, compute, storage, human review, sales, onboarding, support, compliance? Do margins improve or worsen with growth? Is the business operationally viable at scale?

F. Execution risk — What are the biggest technical, commercial, legal, regulatory, and operational risks? What assumptions are most fragile? What would cause this startup to fail within 12 to 24 months?

G. Edge-case simulation — Simulate realistic stress scenarios:
- Sudden increase in API/model costs
- Hallucinations or incorrect outputs in a high-stakes workflow
- Low-quality or sparse customer data
- Customer churn after initial curiosity wears off
- A major incumbent copying the feature set
- Compliance or privacy objections from enterprise buyers
- Need for human-in-the-loop operations that crush margins
- Model provider changes, outages, or degraded performance

Required output format:

## VERDICT
Choose exactly one: Investable / Interesting but weak / Likely wrapper / Fundamentally flawed

## ONE-PARAGRAPH SUMMARY
A sharp overall judgment in plain English.

## SCORES (1–10)
Provide a score and one sentence of justification for each:
- Problem severity
- Product differentiation
- Technical credibility
- Defensibility / moat
- Economic viability
- Go-to-market realism
- Scalability
- Overall conviction

## WRAPPER TEST
Explicitly answer: Is this a wrapper startup? If yes, why? If no, what is the real moat?

## CRITICAL FAULT LINES
List the 5 most serious weaknesses or unanswered questions.

## EDGE-CASE OUTCOMES
List at least 3 stress scenarios and explain how the startup holds up or fails.

## COST STRUCTURE REVIEW
Assess the likely cost base, key margin risks, and whether economics improve with scale.

## WHAT WOULD CHANGE YOUR MIND
State the specific evidence, traction, technical proof, or market validation that would materially improve your view.

## FINAL DECISION
End with exactly one of: "Pass" / "Pass for now" / "Worth deeper diligence"

Style rules:
- Be direct, concrete, and skeptical
- Do not use startup clichés unless critiquing them
- Do not say "it depends" without specifying what it depends on
- Do not soften criticism
- Do not invent facts not present in the submission
- When information is missing, say what is missing and why it matters
- You are not here to encourage founders. You are here to judge whether the business is real, durable, and economically viable.

Here is the startup submission to evaluate:

""" + PITCH


def main():
    print("=" * 70)
    print("SILICON JUDGES v2 — VOXLY PITCH EVALUATION")
    print("=" * 70)
    print()

    client = get_deepseek_client()
    print("Sending to DeepSeek... (30–90 seconds)\n")

    response = client.chat.completions.create(
        model=DEFAULT_DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": SILICON_JUDGES_PROMPT}],
        temperature=0.6,
        max_tokens=4096,
    )

    verdict = response.choices[0].message.content
    print(verdict)

    out_path = project_root / "docs" / "silicon_judges_v2_verdict.md"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(
        f"# Silicon Judges v2 — VOXLY\n\n*Model: {DEFAULT_DEEPSEEK_MODEL}*\n\n{verdict}",
        encoding="utf-8",
    )
    print(f"\n{'=' * 70}")
    print(f"Saved to: {out_path}")


if __name__ == "__main__":
    main()
