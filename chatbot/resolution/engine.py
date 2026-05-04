"""
Resolution engine — the final step of the chatbot pipeline.

Receives a confirmed intent + collected slots and produces a bot response,
calling mock backend APIs as needed.

Usage:
    from chatbot.resolution.engine import ResolutionEngine
    from chatbot.session.state import ConversationState

    engine = ResolutionEngine()
    state  = ConversationState()
    state.set_intent("order_status")
    state.collect_slot("order_id", "ORD-1001")
    state.collect_slot("email", "test@example.com")

    result = engine.resolve("order_status", state.collected_slots, state)
    print(result.status, result.bot_response)
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chatbot.mock_backend import inventory_api, orders_api, refunds_api
from chatbot.registry.loader import load_intents
from chatbot.session.state import ConversationState


@dataclass
class ResolutionResult:
    status: str                        # "resolved" | "needs_slot" | "failed"
    bot_response: str
    missing_slot: Optional[str] = None
    api_data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Backend router
# ---------------------------------------------------------------------------

def _extract_path_slots(endpoint_template: str, slots: dict[str, str]) -> str:
    """Fill {slot_name} placeholders in an endpoint string."""
    return re.sub(
        r"\{(\w+)\}",
        lambda m: slots.get(m.group(1), m.group(0)),
        endpoint_template,
    )


def _call_backend(endpoint: str, slots: dict[str, str]) -> dict:
    """Dispatch to the appropriate mock API function based on endpoint pattern."""
    # Order cancellation pre-check
    if re.search(r"/orders/[^/]+/cancel-check", endpoint):
        return orders_api.cancel_check(slots.get("order_id", ""))

    # Refund status
    if re.search(r"/orders/[^/]+/refund", endpoint):
        return refunds_api.get_refund_status(slots.get("order_id", ""))

    # Order status (generic /orders/* — must come after more specific patterns)
    if re.search(r"/orders/", endpoint):
        return orders_api.get_order(
            slots.get("order_id", ""),
            slots.get("email", ""),
        )

    # Product / inventory
    if "products" in endpoint:
        return inventory_api.check_availability(slots.get("product_name", ""))

    return {"error": "unknown_endpoint"}


def _format_template(template: str, context: dict) -> str:
    """
    Substitute {key} placeholders.
    Missing keys render as empty string rather than raising KeyError.
    """
    return template.format_map(defaultdict(str, context))


# ---------------------------------------------------------------------------
# Resolution engine
# ---------------------------------------------------------------------------

class ResolutionEngine:
    def __init__(self) -> None:
        self._intents = load_intents()

    def resolve(
        self,
        intent_id: str,
        slots: dict[str, str],
        state: ConversationState,
    ) -> ResolutionResult:
        intent = self._intents.get(intent_id)
        if intent is None:
            return ResolutionResult(
                status="failed",
                bot_response="I'm not sure how to help with that. Let me get a human agent for you.",
            )

        # ------------------------------------------------------------------
        # 1. Slot collection — find first missing required slot
        # ------------------------------------------------------------------
        for slot_def in intent.get("required_slots", []):
            if slot_def.get("optional"):
                continue
            name = slot_def["name"]
            if name not in slots or not str(slots[name]).strip():
                return ResolutionResult(
                    status="needs_slot",
                    bot_response=slot_def["prompt"],
                    missing_slot=name,
                )

        # ------------------------------------------------------------------
        # 2. Dispatch by resolution_type
        # ------------------------------------------------------------------
        res_type = intent.get("resolution_type")

        if res_type == "faq_answer":
            return self._resolve_faq(intent)

        if res_type == "api_call":
            return self._resolve_api_call(intent, slots, state)

        if res_type == "guided_flow":
            return self._resolve_guided_flow(intent, slots, state)

        return ResolutionResult(
            status="failed",
            bot_response="I encountered an unexpected configuration issue. Let me connect you with an agent.",
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _resolve_faq(self, intent: dict) -> ResolutionResult:
        answer = intent["resolution_config"].get("answer", "")
        return ResolutionResult(
            status="resolved",
            bot_response=answer,
        )

    def _resolve_api_call(
        self,
        intent: dict,
        slots: dict[str, str],
        state: ConversationState,
    ) -> ResolutionResult:
        config = intent["resolution_config"]
        endpoint_tpl = config.get("endpoint", "")
        endpoint = _extract_path_slots(endpoint_tpl, slots)
        template = config.get("response_template", "")

        api_data = _call_backend(endpoint, slots)

        # Check for escalation trigger in API response
        if "escalation_trigger" in api_data:
            trigger = api_data["escalation_trigger"]
            state.fire_trigger(trigger)
            state.record_failure(intent["intent_id"])
            return ResolutionResult(
                status="failed",
                bot_response=(
                    f"I ran into an issue ({trigger.replace('_', ' ')}). "
                    "Let me connect you with a team member who can resolve this."
                ),
                api_data=api_data,
            )

        # Format response template with slot values + API data merged
        context = {**slots, **api_data}
        bot_response = _format_template(template, context)

        return ResolutionResult(
            status="resolved",
            bot_response=bot_response,
            api_data=api_data,
        )

    def _resolve_guided_flow(
        self,
        intent: dict,
        slots: dict[str, str],
        state: ConversationState,
    ) -> ResolutionResult:
        config = intent["resolution_config"]
        steps: list[dict] = config.get("steps", [])
        step_idx = state.guided_flow_step

        # ------------------------------------------------------------------
        # Pre-check at step 0 (e.g. cancel eligibility)
        # ------------------------------------------------------------------
        if step_idx == 0:
            pre_check_tpl = config.get("pre_check_endpoint")
            if pre_check_tpl:
                endpoint = _extract_path_slots(pre_check_tpl, slots)
                check_result = _call_backend(endpoint, slots)
                if not check_result.get("cancellable", True):
                    trigger = check_result.get("escalation_trigger", "order_already_shipped")
                    state.fire_trigger(trigger)
                    state.record_failure(intent["intent_id"])
                    return ResolutionResult(
                        status="failed",
                        bot_response=(
                            "Unfortunately I can't process that request right now "
                            f"({trigger.replace('_', ' ')}). "
                            "I'm connecting you with a support agent who can help."
                        ),
                        api_data={"escalation_trigger": trigger},
                    )

        # ------------------------------------------------------------------
        # Advance through steps
        # ------------------------------------------------------------------
        if not steps:
            return ResolutionResult(
                status="failed",
                bot_response="This flow has no steps configured. Please contact support.",
            )

        if step_idx >= len(steps):
            # Already completed — idempotent: replay final step
            step_idx = len(steps) - 1

        step = steps[step_idx]
        prompt = _format_template(step.get("prompt", ""), slots)

        is_final = step_idx == len(steps) - 1
        state.advance_flow_step()

        return ResolutionResult(
            status="resolved" if is_final else "needs_slot",
            bot_response=prompt,
            missing_slot=None if is_final else f"guided_step_{step_idx}",
            api_data={"step": step_idx, "expected_input_type": step.get("expected_input_type")},
        )
