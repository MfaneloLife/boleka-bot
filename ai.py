"""
ai.py - AI Post Generator for Boleka SA Marketplace Bot v1.0
Uses DeepSeek API (deepseek-chat v4 pro) to generate SA-flavored social media captions.
Tone: South African, friendly, money-making, with emojis + hashtags.
"""

import os
import logging
from openai import OpenAI

# Configure logging
logger = logging.getLogger(__name__)

# DeepSeek API configuration
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


def _get_client(api_key):
    """
    Create and return an OpenAI-compatible client configured for DeepSeek.
    
    Args:
        api_key: DeepSeek API key.
    
    Returns:
        OpenAI client instance.
    """
    return OpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
    )


def generate_post(post_type, city, category_or_item, price=None, api_key=None):
    """
    Generate a South African social media post using DeepSeek AI.
    
    Post Type A (call_to_list): "Who in [CITY] has [CATEGORY] to rent/sell?
                                 List FREE on Boleka.co.za and make money this week 💰"
    
    Post Type B (new_listing): "NEW in [CITY]: [ITEM NAME] for R[PRICE] on Boleka.co.za.
                                DM to buy."
    
    Args:
        post_type: "A" or "call_to_list" for Type A, "B" or "new_listing" for Type B.
        city: City name (e.g., "Johannesburg").
        category_or_item: Category name (Type A) or item title (Type B).
        price: Item price (only for Type B).
        api_key: DeepSeek API key (if not provided, reads from env).
    
    Returns:
        str: The generated post caption with hashtags, or a fallback if AI fails.
    """
    # Get API key from parameter or environment
    if not api_key:
        api_key = os.getenv("DEEPSEEK_API_KEY")
    
    if not api_key:
        logger.warning("No DeepSeek API key found. Using fallback post generator.")
        return _generate_fallback_post(post_type, city, category_or_item, price)
    
    try:
        client = _get_client(api_key)
        
        # Build the prompt based on post type
        post_type_normalized = post_type.upper() if isinstance(post_type, str) else "A"
        
        if post_type_normalized in ("A", "CALL_TO_LIST"):
            system_prompt = (
                "You are a friendly, persuasive South African social media manager for Boleka.co.za, "
                "an online marketplace where people can list items for free to rent or sell. "
                "Your tone is warm, enthusiastic, and money-motivated - like a savvy friend "
                "sharing a business tip. Use South African slang naturally (e.g., 'howzit', 'yebo', "
                "'lekker', 'shap shap') but don't overdo it. "
                "Always include emojis (💰, 📦, 🏠, 🎉, etc.) and relevant hashtags."
            )
            
            user_prompt = (
                f"Write a short, punchy social media post (2-3 sentences max) asking people in "
                f"{city}, South Africa who have '{category_or_item}' items to list them for FREE "
                f"on Boleka.co.za and make money this week.\n\n"
                f"Requirements:\n"
                f"- Must mention '{city}' and '{category_or_item}'\n"
                f"- Must mention 'Boleka.co.za' and that listing is FREE\n"
                f"- Use money-making angle (earn extra cash, side hustle, etc.)\n"
                f"- Include 2-3 relevant emojis\n"
                f"- Do NOT include 'Photo:' or image credits - those are added separately\n"
                f"- End with exactly these hashtags on one line: #{city.replace(' ', '')} "
                f"#Boleka #{category_or_item.replace(' ', '')} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica\n"
                f"- Keep it under 150 words"
            )
        
        else:  # Type B: New listing promotion
            price_display = f"R{price}" if price else "R???"
            
            system_prompt = (
                "You are a friendly, persuasive South African social media manager for Boleka.co.za, "
                "an online marketplace where people buy, sell, and rent items. "
                "Your tone is excited and urgent - like announcing a hot new deal. "
                "Use South African slang naturally (e.g., 'howzit', 'yebo', "
                "'lekker', 'shap shap') but don't overdo it. "
                "Always include emojis and relevant hashtags."
            )
            
            user_prompt = (
                f"Write a short, exciting social media post (2-3 sentences max) announcing a "
                f"NEW listing on Boleka.co.za in {city}, South Africa.\n\n"
                f"Item: {category_or_item}\n"
                f"Price: {price_display}\n\n"
                f"Requirements:\n"
                f"- Must mention the item '{category_or_item}' and city '{city}'\n"
                f"- Must mention the price ({price_display})\n"
                f"- Must mention 'Boleka.co.za'\n"
                f"- Encourage people to DM/comment to buy or check the link\n"
                f"- Include 2-3 relevant emojis\n"
                f"- Do NOT include 'Photo:' or image credits - those are added separately\n"
                f"- End with exactly these hashtags on one line: #{city.replace(' ', '')} "
                f"#Boleka #{category_or_item.replace(' ', '')[:20]} #ForSale #BuyNow "
                f"#SouthAfrica\n"
                f"- Keep it under 150 words"
            )
        
        # Call DeepSeek API
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.8,
            top_p=0.9,
        )
        
        caption = response.choices[0].message.content.strip()
        logger.info(f"AI generated post for {city} (Type {post_type_normalized})")
        return caption
        
    except Exception as e:
        logger.error(f"DeepSeek API error: {e}. Using fallback post generator.")
        return _generate_fallback_post(post_type, city, category_or_item, price)


def _generate_fallback_post(post_type, city, category_or_item, price=None):
    """
    Generate a fallback post without AI when the DeepSeek API is unavailable.
    These are hardcoded templates that maintain the SA tone.
    Uses 10 Type A templates and 6 Type B templates for variety.
    
    Args:
        post_type: "A" or "B".
        city: City name.
        category_or_item: Category or item name.
        price: Item price (Type B only).
    
    Returns:
        str: Fallback post caption.
    """
    import hashlib
    
    post_type_normalized = post_type.upper() if isinstance(post_type, str) else "A"
    city_hashtag = city.replace(" ", "")
    item_hashtag = category_or_item.replace(" ", "")[:20]
    
    if post_type_normalized in ("A", "CALL_TO_LIST"):
        # Type A: Call to list items (10 templates)
        templates = [
            (
                f"📢 Who in {city} has {category_or_item} to rent or sell? 💰\n\n"
                f"List it for FREE on Boleka.co.za and start making money this week! "
                f"Your side hustle starts here 🚀\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica"
            ),
            (
                f"💡 Got {category_or_item} lying around in {city}?\n\n"
                f"Turn it into CASH! List FREE on Boleka.co.za and earn extra money "
                f"this month. It's quick, it's easy, and it's FREE! 💸\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica"
            ),
            (
                f"🔔 Calling all {city} hustlers!\n\n"
                f"Do you have {category_or_item}? List it FREE on Boleka.co.za "
                f"and watch the money roll in! Don't let your stuff collect dust - "
                f"let it make you money! 💰🔥\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica"
            ),
            (
                f"🇿🇦 {city}, turn your {category_or_item} into income! 💸\n\n"
                f"Boleka.co.za lets you list for FREE — no fees, no catches. "
                f"Just post your item and start earning. Simple! 🎯\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica"
            ),
            (
                f"🤔 Why let your {category_or_item} sit unused, {city}?\n\n"
                f"Rent it out or sell it on Boleka.co.za! Listing is 100% FREE "
                f"and you could be making money by tomorrow. Yebo! 🙌\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica"
            ),
            (
                f"💼 Side hustle alert for {city}! 🔔\n\n"
                f"Have {category_or_item}? List them FREE on Boleka.co.za "
                f"and build your rental business today. Every item could "
                f"be extra income in your pocket! 💰\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica"
            ),
            (
                f"📦 {city}, don't let your {category_or_item} gather dust!\n\n"
                f"Someone out there needs what you have. List FREE on "
                f"Boleka.co.za and connect with buyers & renters today. "
                f"Make your stuff work for YOU! 💪\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica"
            ),
            (
                f"🎯 Target: Extra cash this month, {city}!\n\n"
                f"Your {category_or_item} could be earning you money right now. "
                f"Free listing on Boleka.co.za — no risk, all reward. "
                f"Shap shap! 💸🔥\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica"
            ),
            (
                f"🏠 {city} — ever thought of renting out your {category_or_item}?\n\n"
                f"Boleka.co.za makes it easy and FREE to list. From "
                f"weekend rentals to outright sales, earn on your terms. "
                f"Start today! 🚀\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica"
            ),
            (
                f"✨ New week, new income stream for {city}!\n\n"
                f"List your {category_or_item} for FREE on Boleka.co.za. "
                f"It takes 2 minutes and could put Rands in your pocket by tonight. "
                f"Come on, what are you waiting for? 💰🇿🇦\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #Rent #Sell #MakeMoney "
                f"#RentalBusiness #SouthAfrica"
            ),
        ]
    else:
        # Type B: New listing promotion (6 templates)
        price_display = f"R{price}" if price else "R???"
        templates = [
            (
                f"🆕 NEW in {city}!\n\n"
                f"🔥 {category_or_item} - {price_display}\n\n"
                f"Available now on Boleka.co.za! DM to buy or check the link below. "
                f"First come, first served! 🏃‍♂️💨\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #ForSale #BuyNow "
                f"#SouthAfrica"
            ),
            (
                f"📍 Hot deal in {city}! 🔥\n\n"
                f"{category_or_item} for just {price_display} on Boleka.co.za!\n\n"
                f"Don't miss out - grab this deal before it's gone. "
                f"DM or comment to secure yours! 💰\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #ForSale #BuyNow "
                f"#SouthAfrica"
            ),
            (
                f"🚨 Just listed in {city}! 🇿🇦\n\n"
                f"✨ {category_or_item} — {price_display} ✨\n\n"
                f"This one won't last long on Boleka.co.za. DM or comment "
                f"'SOLD' to grab it now! Fast, safe, local. 🎯\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #ForSale #BuyNow "
                f"#SouthAfrica"
            ),
            (
                f"💎 Check this out, {city}!\n\n"
                f"{category_or_item} — {price_display}\n\n"
                f"Fresh on Boleka.co.za and ready for a new owner. "
                f"Message us to arrange pickup or delivery. "
                f"You snooze, you lose! 😴💨\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #ForSale #BuyNow "
                f"#SouthAfrica"
            ),
            (
                f"🏷️ PRICE DROP in {city}!\n\n"
                f"📦 {category_or_item}\n"
                f"💰 {price_display}\n\n"
                f"Get it now on Boleka.co.za before someone else does! "
                f"DM to make an offer. We deliver too! 🚚\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #ForSale #BuyNow "
                f"#SouthAfrica"
            ),
            (
                f"👀 Look what just hit Boleka.co.za in {city}!\n\n"
                f"🎯 {category_or_item}\n"
                f"💵 {price_display}\n\n"
                f"Quality item, great price, local seller. DM to chat or "
                f"click the link to buy direct. #SupportLocal 🇿🇦\n\n"
                f"👉 eboleka.co.za\n\n"
                f"#{city_hashtag} #Boleka #{item_hashtag} #ForSale #BuyNow "
                f"#SouthAfrica"
            ),
        ]
    
    # Pick a template based on hash of the input for variety
    seed = hashlib.md5(f"{city}{category_or_item}".encode()).hexdigest()
    index = int(seed, 16) % len(templates)
    
    logger.info(f"Generated fallback post for {city} (Type {post_type_normalized}, template {index}/{len(templates)})")
    return templates[index]
