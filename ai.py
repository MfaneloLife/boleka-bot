"""
ai.py - AI Post Generator for E-BOLEKA Marketplace Bot v2.0

Uses DeepSeek (deepseek-chat) to generate high-converting South African
Facebook posts that follow the E-BOLEKA ad framework:

  - Primary Text: hook + pain point + solution
  - Headline: bold CTA / value highlight
  - Description: clarifying subtext (with before/after where relevant)
  - OFFER: incentive / discount / direct action prompt

Targets a NATIONAL South Africa audience (single market - no city segmentation).
"""

import os
import re
import json
import logging
import hashlib
from openai import OpenAI

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# Single national market - never segment by city/township.
MARKET = "South Africa"

STRUCTURE_GUIDE = (
    "Return ONLY valid JSON with exactly these keys:\n"
    "{\n"
    '  "headline": "a bold, punchy, ALL-CAPS call-to-action or value highlight (5-12 words)",\n'
    '  "primary_text": "a compelling hook that names a specific pain point and introduces '
    'the solution immediately (2-4 sentences, warm SA tone)",\n'
    '  "description": "a short clarifying subtext expanding the benefit, including a '
    'before/after or side-by-side comparison where relevant",\n'
    '  "offer": "a clear OFFER with an incentive, discount or direct action prompt",\n'
    '  "hashtags": "#EBOLEKA #SouthAfrica plus 3-5 relevant topic hashtags"\n'
    "}\n"
)


def _get_client(api_key):
    return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


def _build_prompt(post_type, category_or_item, price):
    price_display = f"R{price}" if price else None

    system_prompt = (
        "You are a high-converting South African social media copywriter for E-BOLEKA "
        "(eboleka.co.za), a national marketplace where anyone in South Africa can list items "
        "for FREE to rent or sell. Target a NATIONAL South Africa audience - never mention "
        "specific cities, provinces or townships. Use warm, confident, money-motivated SA slang "
        "(howzit, yebo, lekker, shap shap) but keep it natural.\n\n"
        + STRUCTURE_GUIDE
        + "\nThe 4 pillars EVERY post must satisfy:\n"
        "1. High-contrast, clean visual energy (bold, clear, scannable tone).\n"
        "2. A clear value proposition that shows instant utility.\n"
        "3. A before/after or side-by-side comparison where relevant.\n"
        "4. An OFFER - a clear incentive, discount or direct action prompt.\n"
        "Keep the whole post under 150 words."
    )

    if post_type in ("A", "CALL_TO_LIST"):
        user_prompt = (
            f"Write a Facebook post calling on people ACROSS SOUTH AFRICA who have "
            f"'{category_or_item}' items to list them for FREE on E-BOLEKA and start making "
            f"money. Category: {category_or_item}.\n\n"
            "Open the primary_text with a sharp pain point (unused items gathering dust, missed "
            "income, rental chaos, cash sitting idle) and introduce E-BOLEKA as the instant "
            "solution. Make the offer a clear incentive (list FREE today, keep 100% of your "
            "earnings, no listing fees)."
        )
    else:
        user_prompt = (
            f"Write a Facebook post promoting a NEW listing on E-BOLEKA (eboleka.co.za) to a "
            f"NATIONAL South Africa audience.\n"
            f"Item: {category_or_item}\n"
            f"Price: {price_display or 'Ask for price'}\n\n"
            "Open the primary_text with a hook about a specific problem (endless searching, "
            "overpaying, missing out on deals) and present this item as the solution. Make the "
            "offer a direct action (DM to secure, limited availability, buy before it's gone)."
        )

    return system_prompt, user_prompt


def _compose_caption(structured):
    parts = []
    if structured.get("headline"):
        parts.append(f"🔥 {structured['headline']}")
    if structured.get("primary_text"):
        parts.append(structured["primary_text"])
    if structured.get("description"):
        parts.append(structured["description"])
    if structured.get("offer"):
        parts.append(f"🎁 {structured['offer']}")
    parts.append("👉 eboleka.co.za")
    if structured.get("hashtags"):
        parts.append(structured["hashtags"])
    return "\n\n".join(parts)


def _parse_ai_response(content):
    data = {}
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except (json.JSONDecodeError, TypeError):
                data = {}

    def _get(*keys):
        for key in keys:
            val = data.get(key)
            if val:
                return str(val).strip()
        return ""

    return {
        "headline": _get("headline"),
        "primary_text": _get("primary_text", "primaryText", "primary"),
        "description": _get("description"),
        "offer": _get("offer"),
        "hashtags": _get("hashtags"),
    }


def generate_post(post_type, category_or_item, price=None, market=MARKET, api_key=None):
    """
    Generate a structured E-BOLEKA Facebook post using DeepSeek AI.

    Args:
        post_type: "A"/"call_to_list" or "B"/"new_listing".
        category_or_item: Category name (Type A) or item title (Type B).
        price: Item price (Type B only).
        market: Target market (defaults to national South Africa).
        api_key: DeepSeek API key (defaults to env).

    Returns:
        dict with keys: headline, primary_text, description, offer, hashtags, full_caption.
    """
    if not api_key:
        api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        logger.warning("No DeepSeek API key found. Using fallback post generator.")
        return _generate_fallback_post(post_type, category_or_item, price, market)

    post_type_normalized = post_type.upper() if isinstance(post_type, str) else "A"

    try:
        client = _get_client(api_key)
        system_prompt, user_prompt = _build_prompt(post_type_normalized, category_or_item, price)

        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=600,
            temperature=0.85,
            top_p=0.9,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content.strip()
        structured = _parse_ai_response(content)

        if not (structured["headline"] and structured["primary_text"] and structured["offer"]):
            logger.warning("AI returned incomplete structure; using fallback post generator.")
            return _generate_fallback_post(post_type, category_or_item, price, market)

        structured["full_caption"] = _compose_caption(structured)
        logger.info(f"AI generated structured post (Type {post_type_normalized})")
        return structured

    except Exception as e:
        logger.error(f"DeepSeek API error: {e}. Using fallback post generator.")
        return _generate_fallback_post(post_type, category_or_item, price, market)


def _generate_fallback_post(post_type, category_or_item, price=None, market=MARKET):
    """Hardcoded structured templates used when DeepSeek is unavailable."""
    post_type_normalized = post_type.upper() if isinstance(post_type, str) else "A"
    item = (category_or_item or "your gear").strip()
    cleaned = "".join(ch for ch in item.title().replace(" & ", " ").replace("'", "") if ch.isalnum())
    item_hashtag = cleaned[:20] or "Marketplace"
    price_display = f"R{price}" if price else None

    if post_type_normalized in ("A", "CALL_TO_LIST"):
        templates = [
            {
                "headline": "STOP LETTING YOUR STUFF COLLECT DUST - EARN TODAY",
                "primary_text": (
                    f"Still storing {item.lower()} you barely use while cash is tight? "
                    "Every unused item is money sitting idle in your home. E-BOLEKA turns that "
                    "clutter into income in minutes."
                ),
                "description": (
                    f"❌ Before: {item} gathering dust and losing value. "
                    "✅ After: listed FREE on E-BOLEKA and earning Rands by tonight."
                ),
                "offer": "List FREE today on E-BOLEKA - no listing fees and you keep 100% of your earnings.",
                "hashtags": f"#EBOLEKA #{item_hashtag} #Rent #Sell #MakeMoney #SideHustle #SouthAfrica",
            },
            {
                "headline": "TURN IDLE ITEMS INTO INSTANT CASH",
                "primary_text": (
                    f"Rental and resale chaos ends now. Got {item.lower()}? Stop letting it sit "
                    "unused while someone out there is ready to pay for it. E-BOLEKA connects you "
                    "to buyers and renters across South Africa in seconds."
                ),
                "description": (
                    "❌ Before: months of nothing. ✅ After: live listing in 2 minutes, "
                    "inquiries the same day."
                ),
                "offer": "Sign up now and list your first item 100% FREE - no fees, no catches.",
                "hashtags": f"#EBOLEKA #{item_hashtag} #ListFree #RentalBusiness #EarnExtra #SouthAfrica",
            },
            {
                "headline": "YOUR SIDE HUSTLE STARTS IN 2 MINUTES",
                "primary_text": (
                    f"Feeling the squeeze? Your {item.lower()} could be earning for you while you "
                    "sleep. E-BOLEKA makes listing simple, fast and free - no complicated setup, "
                    "just instant reach nationwide."
                ),
                "description": (
                    "❌ Before: extra cash feels out of reach. ✅ After: your item listed on "
                    "E-BOLEKA and working for you from day one."
                ),
                "offer": "List FREE on E-BOLEKA today and unlock a brand-new income stream this week.",
                "hashtags": f"#EBOLEKA #{item_hashtag} #HustleSmart #MakeMoney #SellOnline #SouthAfrica",
            },
        ]
    else:
        templates = [
            {
                "headline": "HOT FIND - GRAB IT BEFORE IT'S GONE",
                "primary_text": (
                    f"Tired of endless searching and overpaying? We just found it for you: "
                    f"{item}" + (f" for {price_display}" if price_display else "") +
                    ". Fresh on E-BOLEKA and ready for a new owner right now."
                ),
                "description": (
                    "❌ Before: hunting across sites with no luck. ✅ After: this deal found, "
                    "priced right, and one message away."
                ),
                "offer": "DM now to secure it - first come, first served. Limited stock, don't snooze.",
                "hashtags": f"#EBOLEKA #{item_hashtag} #ForSale #BuyNow #DealAlert #SouthAfrica",
            },
            {
                "headline": "NEW LISTING, NEW DEAL, DON'T MISS OUT",
                "primary_text": (
                    f"Howzit, South Africa! Check this {item.lower()} just listed on E-BOLEKA"
                    + (f" for {price_display}" if price_display else "") +
                    ". Quality item, fair price, local seller - exactly what you've been looking for."
                ),
                "description": (
                    "❌ Before: searching and settling for less. ✅ After: found it here, "
                    "fast, safe and local."
                ),
                "offer": "Message now to secure yours - this one won't last long on E-BOLEKA.",
                "hashtags": f"#EBOLEKA #{item_hashtag} #SupportLocal #ForSale #BuyNow #SouthAfrica",
            },
            {
                "headline": "THE DEAL YOU'VE BEEN WAITING FOR",
                "primary_text": (
                    f"Stop scrolling. This {item.lower()}"
                    + (f" is going for {price_display}" if price_display else " is available now") +
                    " on E-BOLEKA and the seller is ready to deal. Skip the hassle and get straight "
                    "to the good stuff."
                ),
                "description": (
                    "❌ Before: wasted time, missed deals. ✅ After: quality item, "
                    "clear price, direct access."
                ),
                "offer": "DM or comment to buy now - when it's gone, it's gone.",
                "hashtags": f"#EBOLEKA #{item_hashtag} #ForSale #BuyNow #GreatDeal #SouthAfrica",
            },
        ]

    seed = hashlib.md5(f"{item}{post_type_normalized}".encode()).hexdigest()
    index = int(seed, 16) % len(templates)
    structured = dict(templates[index])
    structured["full_caption"] = _compose_caption(structured)
    logger.info(
        f"Generated fallback structured post (Type {post_type_normalized}, template {index + 1}/{len(templates)})"
    )
    return structured
