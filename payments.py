"""Stripe Checkout helpers — thin wrapper.

If STRIPE_SECRET_KEY is missing, helpers return None so the caller can fall
back to a stub flow (mark order as pending and show a manual-pay screen).
"""
import os
from typing import Optional


def stripe_enabled() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY", "").strip())


def _client():
    import stripe
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    return stripe


def create_checkout_session(
    *, order_id: int, line_items: list, customer_email: Optional[str],
    success_url: str, cancel_url: str, metadata: Optional[dict] = None,
):
    """Create a Stripe Checkout Session and return (id, url) or (None, None).

    line_items: list of {name, image, price_cents, quantity}
    """
    if not stripe_enabled():
        return None, None
    stripe = _client()
    currency = os.getenv("STRIPE_CURRENCY", "nzd")
    items = []
    for li in line_items:
        items.append({
            "price_data": {
                "currency": currency,
                "unit_amount": int(li["price_cents"]),
                "product_data": {
                    "name": li["name"],
                    **({"images": [li["image"]]} if li.get("image") else {}),
                },
            },
            "quantity": int(li["quantity"]),
        })
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=items,
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=customer_email or None,
        metadata={"order_id": str(order_id), **(metadata or {})},
        payment_intent_data={
            "metadata": {"order_id": str(order_id)},
        },
    )
    return session.id, session.url


def verify_webhook(payload: bytes, signature: str):
    """Returns the parsed event or raises."""
    stripe = _client()
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        # In dev with no secret, accept payload as-is (NOT for prod)
        import json
        return json.loads(payload)
    return stripe.Webhook.construct_event(payload, signature, secret)
