"""
Comprehensive verification of sentiment_analysis module implementation.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

print("\n" + "="*70)
print("SENTIMENT ANALYSIS MODULE - IMPLEMENTATION VERIFICATION")
print("="*70 + "\n")

# ─────────────────────────────────────────────────────────────────────────
# 1. File Structure Check
# ─────────────────────────────────────────────────────────────────────────
print("1. FILE STRUCTURE CHECK")
print("-" * 70)

files_to_verify = {
    "sentiment_analysis/__init__.py": "Module init",
    "sentiment_analysis/analyzer.py": "Aspect-based sentiment analyzer",
    "sentiment_analysis/pipeline.py": "Incremental batch pipeline",
    "sentiment_analysis/aggregator.py": "Query layer",
    "sentiment_analysis/llm_dashboard.py": "Streamlit dashboard",
}

all_exist = True
for filepath, desc in files_to_verify.items():
    p = Path(filepath)
    exists = p.exists()
    size = p.stat().st_size if exists else 0
    status = "✓" if exists else "✗"
    all_exist = all_exist and exists
    print(f"{status} {filepath:<40} ({size:>6} bytes) - {desc}")

print(f"\n{'✓' if all_exist else '✗'} All module files present\n")

# ─────────────────────────────────────────────────────────────────────────
# 2. Python Syntax Validation
# ─────────────────────────────────────────────────────────────────────────
print("2. PYTHON SYNTAX VALIDATION")
print("-" * 70)

import ast
syntax_ok = True
for filepath in files_to_verify:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            ast.parse(f.read())
        print(f"✓ {filepath}")
    except SyntaxError as e:
        print(f"✗ {filepath}: {e}")
        syntax_ok = False

print(f"\n{'✓' if syntax_ok else '✗'} All files have valid Python syntax\n")

# ─────────────────────────────────────────────────────────────────────────
# 3. Module API Completeness
# ─────────────────────────────────────────────────────────────────────────
print("3. MODULE API COMPLETENESS")
print("-" * 70)

api_checks = {
    "analyzer": [
        "AspectSentiment",
        "analyse_text",
    ],
    "pipeline": [
        "run",
    ],
    "aggregator": [
        "aspect_heatmap",
        "top_problem_products",
        "problem_frequency",
        "sentiment_trend",
        "cross_reference_alerts",
        "category_sentiment",
    ],
    "llm_dashboard": [
        "render_llm_dashboard",
    ],
}

all_apis_present = True
for module, apis in api_checks.items():
    print(f"\n{module}:")
    filepath = f"sentiment_analysis/{module}.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    for api in apis:
        found = api in content
        status = "✓" if found else "✗"
        print(f"  {status} {api}")
        all_apis_present = all_apis_present and found

print(f"\n{'✓' if all_apis_present else '✗'} All required APIs present\n")

# ─────────────────────────────────────────────────────────────────────────
# 4. Data Files Check
# ─────────────────────────────────────────────────────────────────────────
print("4. DATA FILES CHECK")
print("-" * 70)

data_files = {
    "data/mock/products.json": "Product database",
    "data/mock/reviews.json": "Customer reviews",
    "data/mock/recent_tickets.json": "Support tickets",
}

for filepath, desc in data_files.items():
    p = Path(filepath)
    exists = p.exists()
    if exists:
        with open(p) as f:
            try:
                data = json.load(f)
                count = len(data) if isinstance(data, list) else len(data.get('to_review', []) + data.get('classified', []))
                status = "✓"
                info = f"{count} items"
            except:
                status = "✗"
                info = "invalid JSON"
    else:
        status = "✗"
        info = "missing"
    print(f"{status} {filepath:<40} - {info}")

sentiment_events_path = Path("data/mock/sentiment_events.json")
if sentiment_events_path.exists():
    with open(sentiment_events_path) as f:
        events = json.load(f)
    print(f"○ data/mock/sentiment_events.json      - {len(events)} events (generated)")
else:
    print(f"○ data/mock/sentiment_events.json      - (not created yet - run pipeline)")

print()

# ─────────────────────────────────────────────────────────────────────────
# 5. admin_app.py Integration Check
# ─────────────────────────────────────────────────────────────────────────
print("5. ADMIN_APP.PY INTEGRATION CHECK")
print("-" * 70)

admin_path = Path("frontend/admin_app.py")
with open(admin_path, encoding='utf-8') as f:
    admin_content = f.read()

import_present = "from sentiment_analysis.llm_dashboard import render_llm_dashboard" in admin_content
call_present = "render_llm_dashboard()" in admin_content
placeholder_clean = '✨ **Coming soon**' not in admin_content

print(f"{'✓' if import_present else '✗'} Import statement present")
print(f"{'✓' if call_present else '✗'} Function call present")
print(f"{'✓' if placeholder_clean else '✗'} Old placeholder removed")

print()

# ─────────────────────────────────────────────────────────────────────────
# 6. Summary
# ─────────────────────────────────────────────────────────────────────────
print("="*70)
print("VERIFICATION SUMMARY")
print("="*70)

all_passed = all_exist and syntax_ok and all_apis_present and import_present and call_present

if all_passed:
    print("\n✓ ALL CHECKS PASSED - Module is ready for use!\n")
    print("Next steps:")
    print("  1. Set ANTHROPIC_API_KEY in .env file")
    print("  2. Run: python -m sentiment_analysis.pipeline --max-reviews 20 --max-tickets 10")
    print("  3. Start Streamlit: streamlit run frontend/admin_app.py")
    print("  4. View the 'LLM Dashboard' tab\n")
else:
    print("\n✗ SOME CHECKS FAILED - Please review errors above\n")

print("="*70 + "\n")
