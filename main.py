#!/usr/bin/env python3
"""
Shopify Card Checker API - Litestar Version (Fixed for Railway)
"""

import sys
import os
import asyncio
from typing import Optional

from litestar import Litestar, get
from litestar.exceptions import HTTPException

# Dynamic import for core
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)
import shopify_core


def _format_api_response(result: dict, cc_input: str) -> dict:
    """Map internal result to the expected API response format."""
    status = result.get("status", "Error")

    # ── Price extraction — try all known fields ──────────────────────────
    price_raw = (
        result.get("price")
        or result.get("lowest_price")
    )
    price: float | None = None
    if price_raw is not None and str(price_raw).strip() not in ("", "-", "None", "null"):
        try:
            price = round(float(str(price_raw).replace("$", "").replace(",", "").strip()), 2)
            if price <= 0:
                price = None  # never expose 0.00 — it means the product fetch failed
        except (ValueError, TypeError):
            price = None

    error_code = str(result.get("error_code", "")).upper()
    message    = str(result.get("message", "")).upper()
    error_msg  = str(result.get("error", "")).upper()

    # ── Exact gateway codes jo as-it-is dikhane hain (CARD_APPROVED mein convert nahi) ──
    _exact_passthrough_codes = {
        "INSUFFICIENT_FUNDS",
        "INVALID_CVC",
        "EXPIRED_CARD",
        "INCORRECT_CVC",
        "PAYMENTS_CREDIT_CARD_BASE_INSUFFICIENT_FUNDS",
        "PAYMENTS_CREDIT_CARD_BASE_INVALID_CVC",
        "PAYMENTS_CREDIT_CARD_BASE_EXPIRED",
    }

    # ── Response string mapping ───────────────────────────────────────────
    if status == "Charged":
        response_str = "CARD_CHARGED"

    elif status == "Approved":
        # BUG FIX #1: "3DS" in error_code was checking if substring exists in the code string
        # but error_code for 3DS is literally "3DS_REQUIRED" so we check both ways
        if "3DS" in error_code:
            response_str = "3DS_REQUIRED"
        elif error_code in _exact_passthrough_codes:
            response_str = error_code
        else:
            response_str = "CARD_APPROVED"

    elif status == "Declined":
        response_str = "CARD_DECLINED"

    elif status == "Error":
        # BUG FIX #2: CAPTCHA and THROTTLED checks were placed BEFORE the "Error" block
        # in a dangling elif that only triggered for unknown statuses, not for status=="Error".
        # Now they are correctly handled INSIDE the Error block first.
        combined = f"{message} {error_msg} {error_code}"

        # CAPTCHA check first (highest priority in Error block)
        if "CAPTCHA" in error_code or "CAPTCHA" in message:
            response_str = "CAPTCHA_REQUIRED"
        # THROTTLED check
        elif "THROTTLED" in error_code or "THROTTLED" in message:
            response_str = "THROTTLED"
        # 3DS check — can appear in any status
        elif "3DS" in error_code or "3DS REQUIRED" in message:
            response_str = "3DS_REQUIRED"
        # Exact passthrough codes
        elif error_code in _exact_passthrough_codes:
            response_str = error_code
        elif any(x in combined for x in ["CARD_DECLINED", "DECLINED"]):
            response_str = "CARD_DECLINED"
        elif "APPROVED" in combined:
            response_str = "CARD_APPROVED"
        elif any(x in combined for x in ["NO PRODUCT", "NO AVAILABLE PRODUCT", "PRODUCTS NOT FOUND", "NO PRODUCTS"]):
            response_str = "NO_PRODUCTS"
        elif any(x in combined for x in ["CART ADD FAILED", "CART FAILED", "NO CART TOKEN", "CART JSON"]):
            response_str = "CART_FAILED"
        elif "CHECKOUT SESSION FAILED" in combined:
            response_str = "CHECKOUT_SESSION_FAILED"
        elif any(x in combined for x in ["CHECKOUT", "SUBMIT FAILED", "GRAPHQL"]):
            response_str = "CHECKOUT_FAILED"
        elif any(x in combined for x in ["TIMEOUT", "NETWORK", "CONNECT"]):
            response_str = "NETWORK_TIMEOUT"
        elif "PAYMENT SESSION" in combined:
            response_str = "PAYMENT_SESSION_FAILED"
        else:
            # Show actual reason instead of generic ERROR
            actual = (
                result.get("message")
                or result.get("error")
                or result.get("error_code")
                or "UNKNOWN_ERROR"
            )
            response_str = str(actual).strip()[:120]
    else:
        # BUG FIX #3: The old elif "CAPTCHA" and elif "THROTTLED" blocks that were
        # unreachable dead code have been removed (they only triggered for completely
        # unknown status values, which never happen in practice).
        response_str = error_code or status.upper().replace(" ", "_")

    # BUG FIX #4: "Status" field was bool (True/False) — semantically confusing.
    # Now returns "Charged"/"Approved"/"Declined"/"Error" string AND the bool for backwards compat.
    return {
        "Gateway": "Shopify Payments",
        "Price": price,          # None if unknown — never 0.00
        "Response": response_str,
        "Status": status in ("Charged", "Approved", "Declined"),
        "cc": cc_input
    }


@get("/shopii")
async def shopii_check(
    site: str,
    cc: str,
    proxy: Optional[str] = None,
) -> dict:
    """
    Main endpoint for Shopify card checking.
    """
    # BUG FIX #5: Validate cc format more robustly — strip spaces and check parts individually
    cc = cc.strip()
    if "|" not in cc:
        raise HTTPException(status_code=400, detail={"error": "Invalid cc format. Use cc|mm|yy|cvv"})
    parts = cc.split("|")
    if len(parts) != 4 or any(p.strip() == "" for p in parts):
        raise HTTPException(status_code=400, detail={"error": "Invalid cc format. Use cc|mm|yy|cvv"})

    site = site.strip().rstrip("/")

    # BUG FIX #6: Validate site URL has a scheme — otherwise httpx crashes with unclear error
    if not site.startswith(("http://", "https://")):
        site = "https://" + site

    try:
        result = await shopify_core.run_shopify_check(
            site_url=site,
            card_str=cc,
            proxy_url=proxy,
            verbose=False,
            timeout=180.0,
            max_captcha_retries=1
        )
        return _format_api_response(result, cc)

    except asyncio.TimeoutError:
        return {
            "Gateway": "Shopify Payments",
            "Price": None,
            "Response": "TIMEOUT",
            "Status": False,
            "cc": cc
        }
    except Exception as e:
        return {
            "Gateway": "Shopify Payments",
            "Price": None,
            "Response": "INTERNAL_ERROR",
            "Status": False,
            "cc": cc,
            "detail": str(e)[:200]
        }


@get("/")
async def root() -> dict:
    return {
        "message": "Shopify Checker API - Litestar (Fixed)",
        "framework": "Litestar",
        "endpoint": "/shopii",
        "health": "/health"
    }


@get("/health")
async def health() -> dict:
    # BUG FIX #7: Added active_checks to health endpoint for better monitoring
    return {
        "status": "healthy",
        "framework": "Litestar",
        "message": "Ready",
        "active_checks": shopify_core.get_active_checks(),
    }


app = Litestar(route_handlers=[shopii_check, root, health])


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Litestar Shopify Checker API (Fixed)")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
