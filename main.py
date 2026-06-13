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
    price_raw = result.get("price") or result.get("lowest_price") or 0
    try:
        price = round(float(str(price_raw).replace("$", "").replace(",", "").strip()), 2)
    except (ValueError, TypeError):
        price = None

    error_code = str(result.get("error_code", "")).upper()
    message = str(result.get("message", "")).upper()
    error_msg = str(result.get("error", "")).upper()

    if status == "Charged":
        response_str = "CARD_CHARGED"
    elif status == "Approved":
        if "3DS" in error_code or "3DS_REQUIRED" in error_code:
            response_str = "3DS_REQUIRED"
        else:
            response_str = "CARD_APPROVED"
    elif status == "Declined":
        response_str = "CARD_DECLINED"
    elif "CAPTCHA" in error_code or "CAPTCHA_REQUIRED" in error_code:
        response_str = "CAPTCHA_REQUIRED"
    elif "THROTTLED" in error_code:
        response_str = "THROTTLED"
    elif status == "Error":
        # Improved error classification
        combined = f"{message} {error_msg} {error_code}"

        if any(x in combined for x in ["DECLINED", "CARD_DECLINED"]):
            response_str = "CARD_DECLINED"
        elif any(x in combined for x in ["APPROVED", "INSUFFICIENT", "CVC"]):
            response_str = "CARD_APPROVED"
        elif any(x in combined for x in ["NO PRODUCT", "NO AVAILABLE PRODUCT", "PRODUCTS NOT FOUND"]):
            response_str = "NO_PRODUCTS"
        elif any(x in combined for x in ["CART ADD FAILED", "CART FAILED", "NO CART TOKEN"]):
            response_str = "CART_FAILED"
        elif any(x in combined for x in ["CHECKOUT", "SUBMIT"]):
            response_str = "CHECKOUT_FAILED"
        elif any(x in combined for x in ["TIMEOUT", "NETWORK"]):
            response_str = "NETWORK_TIMEOUT"
        elif "CAPTCHA" in combined:
            response_str = "CAPTCHA_REQUIRED"
        else:
            response_str = "ERROR"
    else:
        response_str = error_code or status.upper().replace(" ", "_")

    return {
        "Gateway": "Shopify Payments",
        "Price": price,
        "Response": response_str,
        "Status": True,
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
    if "|" not in cc or len(cc.split("|")) != 4:
        raise HTTPException(status_code=400, detail={"error": "Invalid cc format. Use cc|mm|yy|cvv"})

    site = site.strip().rstrip("/")

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
    return {
        "status": "healthy",
        "framework": "Litestar",
        "message": "Ready"
    }


app = Litestar(route_handlers=[shopii_check, root, health])


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Litestar Shopify Checker API (Fixed)")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
