"""Run all 6 pre-review prompts against the VOXLY pitch via DeepSeek."""

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

--- PROBLEM ---
Two levels of pain:
Level 1 — Operational: Support teams spend too much time manually reading, categorising,
and routing tickets. "Where is my order?" / "I want a refund" / "My product arrived broken"
Level 2 — Insight: E-commerce businesses fail to use CS interactions as operational intelligence.
Product complaints → supply chain issues; "not as described" spikes → fix listings;
high return on one SKU → quality mismatch; rising negative sentiment → early warning before reviews crater.

--- MARKET ---
$23B+ EU Customer Care BPO market (2023) → $42.6B by 2031 at 7.6% CAGR
AI for CS growing 22–26%/yr in EU; ~75% of contact centres not yet using AI (early-majority phase)
Global CC outsourcing $97B (2024) → $164B (2030) at 9.8% CAGR
VoC platform market grew 22% in 2025 alone (Gartner)
AI-enabled CS delivers 40–50% reduction in service interactions
No dominant EU-native player in the mid-market sub-segment.

--- TARGET MARKET (ICP) ---
E-Commerce & D2C brands · 100–800 employees · €15M–€200M revenue
Support team 15–80 agents · 10,000–150,000 monthly contacts
Economic buyer: Head of CX / VP Customer Care
ACV: €20,000–€60,000/year · Sales cycle 6–10 weeks
Qualification: 5,000+ contacts/month; churn-sensitive or operationally complex;
stack already includes Zendesk, Gorgias, Freshdesk, or Intercom.
Geography v1: PT · ES · UK

--- VALUE PROPOSITION ---
Module 1 — CS Automation:
  Centralised intake (one chatbot across channels)
  Structured ticket creation (extracts category, product, urgency, action)
  AI classification: Damaged product · refund · delay · return · wrong item · payment issue
  Confidence threshold ≥85%: auto-handled; below 85% → routed to human agent
Module 2 — Operational Intelligence:
  Product complaint sentiment analysis; SKU-level ticket volume and reason breakdown
  Trend detection (contact spike vs product releases / logistics events)
  Recurring issue alerts (auto-flag when SKU exceeds complaint threshold in time window)
  Cross-team intelligence pushed to Product, Ops, C-suite

--- COMPETITIVE LANDSCAPE ---
VOXLY: EU native ✓, mid-market ✓, GDPR ✓, ticket intel ✓, multilingual PT/ES/IT/DE — €20k–€60k ACV
SentiSum: not EU native, no GDPR, partial intel — $36k+/yr
Chattermill: not EU native, enterprise only — €80k+ ACV
Qualtrics: partial EU, enterprise only — €100k+
Medallia: partial EU, enterprise only — €150k+

--- DEFENSIBILITY ---
1. Regulatory: Built EU-native/GDPR-first; US hyperscalers cannot guarantee EU data residency without major restructuring.
2. Vertical domain: Pre-built e-commerce ticket taxonomy, classification schema, escalation logic — assembling from raw APIs would take months.
3. Full stack: Not a raw model — includes helpdesk integrations, 85% confidence threshold, human-in-the-loop routing, operational dashboards.
4. Reliability by design: Below-threshold tickets always go to human; this is structural, not configurable.

--- GO-TO-MARKET ---
Phase 1 (M1–6): 5 design-partner customers in Iberian e-commerce; founder-led direct outreach; 50–60% discount for case study rights. Target: 40%+ ticket deflection.
Phase 2 (M6–18): Expand to Spain + UK; small sales team; helpdesk integrations; €490K ARR target (15–18 customers).
Phase 3 (M18–36): Partner channel via CX consulting firms; vertical approach (fashion, electronics, home goods); expand to SaaS/B2B; 35–45 customers · €1.4M ARR.

--- UNIT ECONOMICS ---
Inference model: DeepSeek V4 Flash
Input: ~400 tokens @ $0.14/1M = $0.000056
Output: ~50 tokens @ $0.28/1M = $0.000014
Total per ticket: ~$0.00007 ($0.07 per 1,000 tickets)

Monthly cost by tier:
  Starter: 20,000 tickets/mo — €20–30k ACV — $1.40/mo AI cost
  Growth: 60,000 tickets/mo — €35–60k ACV — $4.20/mo AI cost
  Scale: 120,000 tickets/mo — €60k+ ACV — $8.40/mo AI cost

Infrastructure (50 customers): hosting €300–600/mo, monitoring €200/mo → ~€550–900/mo total (~€8k/yr)
AI compute < 0.1% of revenue at any tier.

--- COST STRUCTURE ---
COGS: AI inference $0.00007/ticket + hosting €300–600/mo
OPEX: R&D (founding team Y1, grows with revenue); sales (founder-led Y1, direct + content); G&A + GDPR/SOC2 compliance

Headcount:
  Y1: 2 (1 eng/ML + 1 sales/founder)
  Y2: 5
  Y3: 10
  Y4: 16

--- FINANCIALS ---
Year  | Revenue | Gross Profit (margin) | OpEx  | EBITDA      | EBITDA %
Y1    | €125K   | €103K (82%)           | €150K | –€47K       | –38%
Y2    | €490K   | €411K (84%)           | €400K | €11K        | 2%
Y3    | €1.4M   | €1.22M (87%)          | €850K | €370K       | 26%
Y4    | €3.2M   | €2.88M (90%)          | €1.5M | €1.38M      | 43%

Break-even: ~15 Growth-tier customers · reached in Year 2.

--- TECHNICAL STACK ---
Backend: Python, FastAPI, DeepSeek API (classification + chatbot), ChromaDB (RAG/vector store)
Frontend: Streamlit (admin dashboard + user chatbot widget)
DB: SQLite (tickets), ChromaDB (embeddings)
Pipeline: user message → intent classifier (confidence ≥85% auto-resolve / <85% human queue) → escalation engine → resolution engine → ticket storage
Chatbot: @st.dialog Streamlit modal, session state, CSAT feedback loop
Classification: few-shot prompt + JSON output schema, confidence scoring
Ticket routing: category → queue mapping (Bug→Technical Support, Shipping→Logistics, etc.)
Helpdesk integration: Zendesk/Freshdesk webhook guidance documented

--- GenAI TRANSPARENCY ---
Claude used for: token cost calculations, break-even analysis, P&L modelling, EU market data research,
business plan drafting (human-reviewed), prompt engineering design, backend architecture,
classification prompt engineering, React dashboard scaffolding, Zendesk/Freshdesk integration guidance.
All AI output reviewed, edited, and validated by team. Data verified against primary sources.
"""

PROMPTS = [
    (
        "Prompt 1: Business Model Review",
        "You are a critical venture investor and business school professor. Evaluate the following AI startup project. Focus on the target market, customer pain point, value proposition, go-to-market strategy, revenue model, and commercial feasibility. Identify the strongest parts of the business model, the weakest assumptions, and the most serious reasons why this startup may fail. Be strict and specific.",
    ),
    (
        "Prompt 2: Technical Architecture Review",
        "You are a senior AI product engineer. Evaluate the following AI startup prototype. Focus on whether the system is technically feasible, whether the frontend and backend are clearly connected, whether the AI component is necessary, whether the workflow is deployable by real users, and whether the documentation is sufficient. Identify missing technical details, likely implementation risks, and improvements needed before demo day.",
    ),
    (
        "Prompt 3: AI Unit Economics Review",
        "You are an AI infrastructure and startup finance expert. Evaluate the unit economics of the following AI startup. Focus on token costs, API usage, model choice, hosting costs, vector database or storage costs, expected usage volume, pricing model, gross margin, and scalability. Identify whether the proposed business can become profitable, and explain which cost assumptions are unrealistic.",
    ),
    (
        "Prompt 4: Defensibility and Wrapper Risk Review",
        "You are a highly skeptical LLM-as-a-Judge. Evaluate whether the following project is merely an AI wrapper or whether it has a defensible moat. Consider proprietary data, workflow integration, domain expertise, switching costs, user experience, technical complexity, and business positioning. Explain why OpenAI, Google, Anthropic, or another platform could or could not easily replicate this project.",
    ),
    (
        "Prompt 5: AI Safety and Risk Review",
        "You are an AI safety reviewer. Evaluate the following AI startup for risks related to hallucination, privacy, data leakage, user harm, bias, misuse, overreliance, and lack of transparency. Identify the most important risks and propose concrete safeguards. Be specific about what should be added to the product, the documentation, and the user interface.",
    ),
    (
        "Prompt 6: Final Presentation Simulation",
        "You are a combined panel of venture investors, AI engineers, and business school faculty. Grade the following AI startup project according to four criteria: commercial innovation and feasibility, technical execution and prototype quality, defensibility and safety, and presentation clarity. Give a score from 1 to 10 for each criterion, justify each score, and list the top five improvements the team should make before the final presentation.",
    ),
]


def run_prompt(client, title, system_prompt):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")
    response = client.chat.completions.create(
        model=DEFAULT_DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the startup pitch to evaluate:\n\n{PITCH}"},
        ],
        temperature=0.5,
        max_tokens=2000,
    )
    result = response.choices[0].message.content
    print(result)
    return result


def main():
    print("VOXLY — 6-Prompt Pre-Review Evaluation")
    print(f"Model: {DEFAULT_DEEPSEEK_MODEL}")
    print("=" * 70)

    client = get_deepseek_client()
    all_output = ["# VOXLY — 6-Prompt Pre-Review Evaluation\n"]

    for title, system_prompt in PROMPTS:
        result = run_prompt(client, title, system_prompt)
        all_output.append(f"\n## {title}\n\n{result}\n")

    out_path = project_root / "docs" / "review_prompts_output.md"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text("\n".join(all_output), encoding="utf-8")
    print(f"\n{'=' * 70}")
    print(f"Full output saved to: {out_path}")


if __name__ == "__main__":
    main()
