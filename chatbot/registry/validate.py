"""
Intent registry validator.

Checks every intent file against intent.schema.json, then runs additional
semantic checks that JSON Schema cannot express:
  - no duplicate intent_id values
  - every required (non-optional) slot has a non-empty prompt
  - resolution_config contains the expected keys for its resolution_type

Run via:
    python -m chatbot.registry.validate
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
    from jsonschema import Draft7Validator
except ImportError:
    print("ERROR: 'jsonschema' is not installed.")
    print("       Run:  pip install jsonschema")
    sys.exit(1)

_REGISTRY_DIR = Path(__file__).parent
_SCHEMA_FILE = _REGISTRY_DIR / "intent.schema.json"
_INTENTS_DIR = _REGISTRY_DIR / "intents"

# Required top-level keys per resolution_type
_RESOLUTION_REQUIRED: dict[str, list[str]] = {
    "api_call":     ["endpoint", "method", "response_template"],
    "faq_answer":   ["answer"],
    "guided_flow":  ["steps"],
}


def _load_schema() -> dict:
    with open(_SCHEMA_FILE, encoding="utf-8") as f:
        return json.load(f)


def _load_intent_files() -> list[tuple[Path, dict]]:
    results = []
    for path in sorted(_INTENTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  ✗  {path.name}  — invalid JSON: {exc}")
            continue
        results.append((path, data))
    return results


def _check_resolution_config(intent: dict) -> list[str]:
    errors: list[str] = []
    res_type = intent.get("resolution_type", "")
    config = intent.get("resolution_config", {})
    required_keys = _RESOLUTION_REQUIRED.get(res_type, [])

    for key in required_keys:
        if key not in config:
            errors.append(
                f"resolution_config is missing '{key}' (required for {res_type})"
            )

    # Extra shape checks for guided_flow
    if res_type == "guided_flow":
        steps = config.get("steps")
        if isinstance(steps, list):
            for i, step in enumerate(steps):
                for field in ("prompt", "expected_input_type"):
                    if field not in step:
                        errors.append(
                            f"guided_flow step {i} is missing field '{field}'"
                        )

    return errors


def validate_all() -> bool:
    schema = _load_schema()
    validator = Draft7Validator(schema)

    intent_files = _load_intent_files()
    if not intent_files:
        print(f"WARNING: No intent files found in {_INTENTS_DIR}")
        return True

    total_errors = 0
    seen_ids: dict[str, str] = {}   # intent_id -> filename

    SEP = "-" * 75
    print(f"\nValidating {len(intent_files)} intent(s) in {_INTENTS_DIR}\n")
    print(f"{'File':<38}  {'Intent ID':<26}  Result")
    print(SEP)

    for path, intent in intent_files:
        file_errors: list[str] = []

        # 1. JSON Schema
        for err in validator.iter_errors(intent):
            loc = " > ".join(str(p) for p in err.absolute_path) or "(root)"
            file_errors.append(f"[schema] {loc}: {err.message}")

        # 2. Duplicate intent_id
        intent_id = intent.get("intent_id", "")
        if intent_id:
            if intent_id in seen_ids:
                file_errors.append(
                    f"[duplicate] intent_id '{intent_id}' already defined in "
                    f"{seen_ids[intent_id]}"
                )
            else:
                seen_ids[intent_id] = path.name

        # 3. Slot prompt check (non-optional slots must have a non-empty prompt)
        for slot in intent.get("required_slots", []):
            if not slot.get("optional", False):
                if not slot.get("prompt", "").strip():
                    file_errors.append(
                        f"[slots] required slot '{slot.get('name')}' has no prompt"
                    )

        # 4. resolution_config shape
        file_errors.extend(_check_resolution_config(intent))

        # Report row
        status = "PASS" if not file_errors else f"FAIL ({len(file_errors)} error(s))"
        print(f"  {path.name:<36}  {intent_id:<26}  {status}")
        for msg in file_errors:
            print(f"      -> {msg}")

        total_errors += len(file_errors)

    print(SEP)
    if total_errors == 0:
        print(f"\n[OK] All {len(intent_files)} intents passed validation.\n")
        return True
    else:
        print(
            f"\n[FAIL] {total_errors} error(s) found across "
            f"{len(intent_files)} intent file(s).\n"
        )
        return False


if __name__ == "__main__":
    ok = validate_all()
    sys.exit(0 if ok else 1)
