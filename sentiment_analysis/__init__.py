"""
sentiment_analysis/
────────────────────────────────────────────────────────────────────────────────
Aspect-Based Sentiment Analysis module for Olá Market.

Modules:
  analyzer    — single-text ABSA via Claude tool_use  (mirrors classifier.py)
  pipeline    — incremental batch processor → sentiment_events.json
  aggregator  — pure-query layer over the event store
  llm_dashboard — Streamlit rendering for the LLM Dashboard tab

Quick start:
  1. Run the pipeline:
       python -m sentiment_analysis.pipeline --max-reviews 20 --max-tickets 10

  2. Wire the dashboard into admin_app.py:
       elif selected_tab == "LLM Dashboard":
           from sentiment_analysis.llm_dashboard import render_llm_dashboard
           render_llm_dashboard()
"""

from sentiment_analysis.analyzer import analyse_text, AspectSentiment
from sentiment_analysis.aggregator import (
    load_events,
    aspect_heatmap,
    top_problem_products,
    problem_frequency,
    sentiment_trend,
    cross_reference_alerts,
    category_sentiment,
)

__all__ = [
    "analyse_text",
    "AspectSentiment",
    "load_events",
    "aspect_heatmap",
    "top_problem_products",
    "problem_frequency",
    "sentiment_trend",
    "cross_reference_alerts",
    "category_sentiment",
]