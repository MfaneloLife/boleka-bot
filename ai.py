"""
ai.py - AI Post Generator for E-BOLEKA Marketplace Bot v2.0

Uses DeepSeek (deepseek-chat) to generate high-converting South African
Facebook posts written with the "Sell Like Crazy" (Sabri Suby)
direct-response framework:

  - Enter the conversation already taking place in the customer's mind
  - Lead with PAIN (fear of loss) before the solution
  - Numbered, curiosity-driven headline using a power word
  - Sell the vivid AFTER state (benefits, not features)
  - An IRRESISTIBLE, specific offer (what they get + what to do next)

Targets a NATIONAL South Africa audience (single market).
Posts NEVER include website links / URLs - Facebook's algorithm punishes them,
so all direct action happens via comments or DMs instead.
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
    '  "headline": "a numbered, curiosity-driven, ALL-CAPS headline using a power word '
    "(Alarming, Shocking, Hidden, Secret, Warning) and a specific promised outcome\",\n"
    '  "primary_text": "enter the conversation already in the reader\'s mind - name their '
    "exact pain or fear in their own words, then introduce the solution as the fast path to "
    "relief (2-4 sentences, warm SA tone)\",\n"
    '  "description": "a before/after or side-by-side contrast that translates features into '
    "vivid, life-changing benefits\",\n"
    '  "offer": "an IRRESISTIBLE, specific offer - exactly what they get + exactly what to '
    "do next, with urgency or scarcity\",\n"
    '  "hashtags": "#EBOLEKA #SouthAfrica plus 3-5 relevant topic hashtags"\n'
    "}\n"
)


def _get_client(api_key):
    return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


def _build_prompt(post_type, category_or_item, price):
    price_display = f"R{price}" if price else None

    system_prompt = (
        "You are a world-class direct-response copywriter for E-BOLEKA, South Africa's "
        "national marketplace where anyone can list items to rent or sell. You write every "
        "post using the 'Sell Like Crazy' (Sabri Suby) framework.\n\n"
        + STRUCTURE_GUIDE
        + "\nWrite for ONE person reading on Facebook. Target a NATIONAL South Africa "
        "audience - never mention specific cities, provinces or townships. Use warm, "
        "money-motivated SA slang (howzit, yebo, lekker, shap shap) but keep it natural.\n\n"
        "COPYWRITING RULES (from Sell Like Crazy):\n"
        "1. Enter the conversation already taking place in the reader's mind. Mirror their "
        "exact words, pains, fears, hopes and dreams - never open with 'we' or the product.\n"
        "2. Lead with PAIN, not pleasure. People are motivated far more by fear of loss than "
        "by desire to gain. Name a sharp, specific pain point (idle items, missed income, "
        "rental chaos, overpaying, endless searching) before offering the solution.\n"
        "3. The headline must stop the scroll: a NUMBER + a power word (Alarming, Shocking, "
        "Hidden, Secret, Warning) + a specific promised outcome, plus intrigue.\n"
        "4. Sell the benefit and the dream, not the feature. Translate every feature into a "
        "vivid, specific, life-changing AFTER state.\n"
        "5. Make an IRRESISTIBLE, specific offer: what they get + exactly what to do next, "
        "with urgency or scarcity. Be concrete, never vague.\n"
        "6. Absolutely NO website links, URLs or 'eboleka.co.za' anywhere in the post. "
        "Facebook's algorithm punishes links, so drive action via comments/DMs instead.\n"
        "Keep the whole post under 150 words."
    )

    if post_type in ("A", "CALL_TO_LIST"):
        user_prompt = (
            f"Write a Facebook post calling on people ACROSS SOUTH AFRICA who have "
            f"'{category_or_item}' items to list them for FREE on E-BOLEKA and turn idle "
            f"stuff into income. Category: {category_or_item}.\n\n"
            "Enter the conversation already in their mind: open the primary_text with their "
            "sharpest pain point (unused items gathering dust, cash sitting idle, missed "
            "income) in their own words, then present E-BOLEKA as the instant relief. Make the "
            "offer specific and irresistible (list FREE in minutes, keep 100% of your "
            "earnings, no listing fees). Do NOT mention any website, link or URL."
        )
    else:
        user_prompt = (
            f"Write a Facebook post promoting a NEW listing on E-BOLEKA to a NATIONAL South "
            f"Africa audience.\n"
            f"Item: {category_or_item}\n"
            f"Price: {price_display or 'Ask for price'}\n\n"
            "Open the primary_text by naming the reader's exact frustration (endless "
            "searching, overpaying, missing out on deals) then present this item as the fast, "
            "specific solution. Sell the vivid AFTER state of owning it. Make the offer a "
            "direct, urgent action (comment/DM to secure, limited availability, buy before "
            "it's gone). Do NOT mention any website, link or URL."
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
    if structured.get("hashtags"):
        parts.append(structured["hashtags"])

    caption = "\n\n".join(parts)

    # Safety net: Facebook's algorithm punishes links. Strip any URL / domain the
    # model may have slipped in so the post always stays link-free.
    caption = re.sub(r"https?://\S+", "", caption, flags=re.IGNORECASE)
    caption = re.sub(r"www\.\S+", "", caption, flags=re.IGNORECASE)
    caption = re.sub(r"eboleka\.co\.za", "", caption, flags=re.IGNORECASE)

    # Collapse any blank gaps left behind.
    caption = re.sub(r"\n{3,}", "\n\n", caption).strip()
    return caption


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
    """Hardcoded 'Sell Like Crazy' structured templates used when DeepSeek is unavailable."""
    post_type_normalized = post_type.upper() if isinstance(post_type, str) else "A"
    item = (category_or_item or "your gear").strip()
    cleaned = "".join(ch for ch in item.title().replace(" & ", " ").replace("'", "") if ch.isalnum())
    item_hashtag = cleaned[:20] or "Marketplace"
    price_display = f"R{price}" if price else None

    if post_type_normalized in ("A", "CALL_TO_LIST"):
        templates = [
            {
                "headline": "3 WAYS YOUR UNUSED STUFF IS ROBBING YOU BLIND (No. 2 Will Shock You)",
                "primary_text": (
                    f"Still storing {item.lower()} you never use while cash is tight? Every idle "
                    "item is money quietly leaking out of your pocket. E-BOLEKA turns that "
                    "clutter into Rands in minutes - no fees, no fuss."
                ),
                "description": (
                    f"❌ Before: {item} gathering dust and losing value. "
                    "✅ After: listed free and earning by tonight."
                ),
                "offer": (
                    "List it FREE on E-BOLEKA today and keep 100% of every Rand you earn. "
                    "Comment 'LIST' to start now."
                ),
                "hashtags": f"#EBOLEKA #{item_hashtag} #Rent #Sell #MakeMoney #SideHustle #SouthAfrica",
            },
            {
                "headline": "WARNING: THE SIDE HUSTLE MOST SOUTH AFRICANS NEVER START (It Takes 2 Minutes)",
                "primary_text": (
                    f"Rental and resale chaos ends now. Got {item.lower()}? Stop letting it sit "
                    "unused while someone out there is ready to pay for it. E-BOLEKA connects you "
                    "to buyers and renters across South Africa in seconds."
                ),
                "description": (
                    "❌ Before: months of nothing. ✅ After: live listing in 2 minutes, "
                    "inquiries the same day."
                ),
                "offer": (
                    "Sign up now and list your first item 100% FREE - no fees, no catches. "
                    "Comment 'YES' and turn your stuff into cash."
                ),
                "hashtags": f"#EBOLEKA #{item_hashtag} #ListFree #RentalBusiness #EarnExtra #SouthAfrica",
            },
            {
                "headline": "5 REASONS YOUR {ITEM} SHOULD BE EARNING FOR YOU WHILE YOU SLEEP".replace(
                    "{ITEM}", item.upper()
                ),
                "primary_text": (
                    f"Feeling the squeeze? Your {item.lower()} could be earning for you while you "
                    "sleep. E-BOLEKA makes listing simple, fast and free - no complicated setup, "
                    "just instant reach nationwide."
                ),
                "description": (
                    "❌ Before: extra cash feels out of reach. ✅ After: your item listed on "
                    "E-BOLEKA and working for you from day one."
                ),
                "offer": (
                    "List FREE on E-BOLEKA today and unlock a brand-new income stream this week. "
                    "Comment 'INCOME' to begin."
                ),
                "hashtags": f"#EBOLEKA #{item_hashtag} #HustleSmart #MakeMoney #SellOnline #SouthAfrica",
            },
        ]
    else:
        templates = [
            {
                "headline": "1 HOT FIND - GRAB IT BEFORE IT'S GONE",
                "primary_text": (
                    f"Tired of endless searching and overpaying? We just found it for you: "
                    f"{item}" + (f" for {price_display}" if price_display else "") +
                    ". Fresh on E-BOLEKA and ready for a new owner right now."
                ),
                "description": (
                    "❌ Before: hunting across sites with no luck. ✅ After: this deal found, "
                    "priced right, and one message away."
                ),
                "offer": (
                    "Comment 'MINE' or DM now to secure it - first come, first served. "
                    "Limited stock, don't snooze."
                ),
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
                "offer": (
                    "Comment or DM now to secure yours - this one won't last long on E-BOLEKA."
                ),
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
                "offer": "Comment or DM to buy now - when it's gone, it's gone.",
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