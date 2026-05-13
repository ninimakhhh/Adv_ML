"""
Quick smoke test — sends a real message through IntentClassifier and prints result.

Usage:
    python scripts/smoke_test_classifier.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from chatbot.classifier.classifier import IntentClassifier

def main():
    clf = IntentClassifier()

    tests = [
        "where is my order ORD-1001",
        "I want to return my purchase",
        "what is your return policy",
    ]

    for msg in tests:
        result = clf.classify(msg)
        print(f"\nMessage : {msg}")
        print(f"Intent  : {result.intent_id}")
        print(f"Conf    : {result.confidence:.2f}")
        print(f"Reasoning: {result.reasoning}")
        if result.top_3_alternatives:
            print(f"Alts    : {result.top_3_alternatives}")

if __name__ == "__main__":
    main()
