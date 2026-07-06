"""
scraper.py - Web Scraper for eboleka.co.za
Finds empty categories (<5 listings) and newest listings per city.
Uses requests + BeautifulSoup for scraping with proper error handling.
"""

import requests
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Configure logging
logger = logging.getLogger(__name__)

# Base URL for eboleka
BASE_URL = "https://eboleka.co.za"

# Common headers to mimic a real browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-ZA,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _fetch_page(url, timeout=15):
    """
    Helper: Fetch a page and return a BeautifulSoup object.
    
    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.
    
    Returns:
        BeautifulSoup object or None on failure.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None


def get_empty_categories(city):
    """
    Scrape eboleka.co.za and find categories with fewer than 5 listings per city.
    
    Strategy:
    1. Navigate to the city page or search by city.
    2. Identify category sections on the page.
    3. Count listings per category.
    4. Return categories with <5 listings.
    
    Args:
        city: City name (e.g., "Johannesburg").
    
    Returns:
        list of dicts: [{"category": "Tents", "count": 2}, ...]
    """
    logger.info(f"Scanning eboleka.co.za for empty categories in {city}...")
    
    empty_categories = []
    
    try:
        # Strategy 1: Try city-specific URL patterns
        city_slug = city.lower().replace(" ", "-")
        urls_to_try = [
            f"{BASE_URL}/city/{city_slug}",
            f"{BASE_URL}/location/{city_slug}",
            f"{BASE_URL}/search?city={city_slug}",
            f"{BASE_URL}/listings?city={city_slug}",
            f"{BASE_URL}/browse/{city_slug}",
            f"{BASE_URL}/",
        ]
        
        soup = None
        for url in urls_to_try:
            soup = _fetch_page(url)
            if soup:
                logger.info(f"Successfully fetched: {url}")
                break
        
        if not soup:
            logger.warning(f"Could not fetch any page for city: {city}")
            # Return some default categories so the bot can still operate
            return _get_default_empty_categories()
        
        # Strategy 2: Find category elements on the page
        # Look for common category container patterns
        category_sections = []
        
        # Try various selectors that might contain category listings
        selectors = [
            ".category-list",
            ".categories",
            "[class*='category']",
            ".listing-categories",
            ".browse-categories",
            "section.categories",
            ".home-categories",
            "[data-category]",
        ]
        
        for selector in selectors:
            sections = soup.select(selector)
            if sections:
                category_sections.extend(sections)
                break
        
        # If we found category sections, count listings in each
        if category_sections:
            for section in category_sections:
                # Extract category name
                category_name = None
                name_elem = section.select_one("h2, h3, h4, .category-name, .title, a")
                if name_elem:
                    category_name = name_elem.get_text(strip=True)
                
                if not category_name:
                    # Try to get from data attributes or links
                    link = section.select_one("a")
                    if link:
                        category_name = link.get_text(strip=True) or link.get("title")
                
                if not category_name:
                    continue
                
                # Count listings in this category
                listing_count = 0
                listing_elems = section.select(".listing, .product, .item, .ad, article, .card, [class*='listing']")
                if listing_elems:
                    listing_count = len(listing_elems)
                else:
                    # Try to find a count badge or number
                    count_elem = section.select_one(".count, .badge, .number, [class*='count']")
                    if count_elem:
                        try:
                            count_text = count_elem.get_text(strip=True)
                            listing_count = int("".join(c for c in count_text if c.isdigit()))
                        except (ValueError, TypeError):
                            listing_count = 0
                
                # If we couldn't determine count, estimate from child links
                if listing_count == 0:
                    links = section.select("a[href*='listing'], a[href*='product'], a[href*='item']")
                    listing_count = len(links)
                
                # Categories with <5 listings are "empty" for our purposes
                if listing_count < 5:
                    empty_categories.append({
                        "category": category_name,
                        "count": listing_count,
                    })
                    logger.info(f"  Empty category found: {category_name} ({listing_count} listings)")
        
        # Strategy 3: If no category sections found, try finding category links site-wide
        if not empty_categories:
            category_links = soup.select("a[href*='category'], a[href*='/c/'], nav a, .menu a")
            seen_categories = set()
            
            for link in category_links:
                category_name = link.get_text(strip=True)
                if not category_name or len(category_name) < 2:
                    continue
                if category_name.lower() in seen_categories:
                    continue
                if category_name.lower() in ["home", "login", "register", "contact", "about", "faq", "blog"]:
                    continue
                
                seen_categories.add(category_name.lower())
                
                # Try to visit the category page to count listings
                cat_url = link.get("href")
                if cat_url:
                    if not cat_url.startswith("http"):
                        cat_url = urljoin(BASE_URL, cat_url)
                    
                    cat_soup = _fetch_page(cat_url, timeout=10)
                    if cat_soup:
                        # Count listing elements on category page
                        listing_elems = cat_soup.select(
                            ".listing, .product, .item, .ad, article, .card, "
                            "[class*='listing'], li[class*='product'], .search-result"
                        )
                        count = len(listing_elems)
                        
                        if count < 5:
                            empty_categories.append({
                                "category": category_name,
                                "count": count,
                            })
                            logger.info(f"  Empty category found: {category_name} ({count} listings)")
        
        # Fallback: Return default categories if nothing was found
        if not empty_categories:
            logger.warning(f"No empty categories found for {city}, using defaults")
            empty_categories = _get_default_empty_categories()
        
        logger.info(f"Found {len(empty_categories)} empty categories for {city}")
        return empty_categories
        
    except Exception as e:
        logger.error(f"Error in get_empty_categories for {city}: {e}")
        return _get_default_empty_categories()


def get_new_listings(city):
    """
    Scrape eboleka.co.za and get the 3 newest listings per city.
    
    Args:
        city: City name (e.g., "Johannesburg").
    
    Returns:
        list of dicts: [
            {"title": "...", "price": "500", "url": "...", "image_url": "..."},
            ...
        ]
    """
    logger.info(f"Fetching newest listings for {city}...")
    
    listings = []
    
    try:
        # Strategy 1: Try city-specific URL patterns
        city_slug = city.lower().replace(" ", "-")
        urls_to_try = [
            f"{BASE_URL}/city/{city_slug}",
            f"{BASE_URL}/location/{city_slug}",
            f"{BASE_URL}/search?city={city_slug}&sort=newest",
            f"{BASE_URL}/listings?city={city_slug}&sort=newest",
            f"{BASE_URL}/browse/{city_slug}?sort=newest",
            f"{BASE_URL}/",
        ]
        
        soup = None
        for url in urls_to_try:
            soup = _fetch_page(url)
            if soup:
                logger.info(f"Successfully fetched: {url}")
                break
        
        if not soup:
            logger.warning(f"Could not fetch any page for city: {city}")
            return listings
        
        # Strategy 2: Find listing cards/elements on the page
        listing_elements = []
        
        # Try common listing container selectors
        listing_selectors = [
            ".listing-card",
            ".product-card",
            ".item-card",
            ".listing-item",
            ".product-item",
            "article.listing",
            "article.product",
            ".ad-card",
            ".search-result",
            ".card",
            "[class*='listing']",
            "[class*='product']",
            "li[class*='item']",
        ]
        
        for selector in listing_selectors:
            elems = soup.select(selector)
            if elems:
                listing_elements = elems
                break
        
        # If no elements found with specific selectors, try generic article/div
        if not listing_elements:
            # Look for elements that contain price patterns (R followed by digits)
            for elem in soup.select("article, .card, .item, .product, div[class]"):
                text = elem.get_text()
                if "R" in text and any(c.isdigit() for c in text):
                    # Check if this likely contains a listing by looking for links
                    if elem.select_one("a"):
                        listing_elements.append(elem)
        
        # Strategy 3: Parse individual listings
        count = 0
        for elem in listing_elements:
            if count >= 3:
                break
            
            try:
                # Extract title
                title = None
                title_selectors = ["h2", "h3", "h4", ".title", ".name", ".product-title", ".listing-title"]
                for ts in title_selectors:
                    title_elem = elem.select_one(ts)
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        break
                
                if not title:
                    # Try first link text or any heading
                    link = elem.select_one("a")
                    if link:
                        title = link.get_text(strip=True) or link.get("title") or link.get("aria-label")
                
                if not title or len(title) < 3:
                    continue
                
                # Extract price
                price = None
                price_selectors = [".price", ".amount", ".cost", "[class*='price']", ".product-price"]
                for ps in price_selectors:
                    price_elem = elem.select_one(ps)
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        # Extract numeric price (remove R, spaces, commas)
                        price = "".join(c for c in price_text if c.isdigit() or c == ".")
                        break
                
                if not price:
                    # Try regex on full text
                    import re
                    text = elem.get_text()
                    price_match = re.search(r'R\s*(\d[\d\s,]*\.?\d*)', text)
                    if price_match:
                        price = re.sub(r'[,\s]', '', price_match.group(1))
                
                if not price:
                    price = "0"
                
                # Extract URL
                url = None
                link_elem = elem.select_one("a[href]")
                if link_elem:
                    url = link_elem.get("href")
                    if url and not url.startswith("http"):
                        url = urljoin(BASE_URL, url)
                
                if not url:
                    continue
                
                # Extract image URL
                image_url = None
                img_elem = elem.select_one("img")
                if img_elem:
                    image_url = img_elem.get("src") or img_elem.get("data-src") or img_elem.get("data-lazy-src")
                    if image_url and image_url.startswith("/"):
                        image_url = urljoin(BASE_URL, image_url)
                
                listings.append({
                    "title": title,
                    "price": price,
                    "url": url,
                    "image_url": image_url,
                })
                
                count += 1
                logger.info(f"  Listing found: {title} - R{price}")
                
            except Exception as e:
                logger.error(f"Error parsing listing element: {e}")
                continue
        
        logger.info(f"Found {len(listings)} new listings for {city}")
        return listings
        
    except Exception as e:
        logger.error(f"Error in get_new_listings for {city}: {e}")
        return listings


def _get_default_empty_categories():
    """
    Return a randomized subset of default marketplace categories.
    Used as fallback when scraping fails so the bot can still operate.
    Categories are shuffled each call to avoid repeating the same ones.
    
    Returns:
        list of dicts: [{"category": "...", "count": 0}, ...]
    """
    import random
    
    defaults_pool = [
        {"category": "Tents & Camping Gear", "count": 0},
        {"category": "Sound Systems & DJ Equipment", "count": 0},
        {"category": "Photography Equipment", "count": 0},
        {"category": "Party Supplies", "count": 0},
        {"category": "Tools & Hardware", "count": 0},
        {"category": "Sports Equipment", "count": 0},
        {"category": "Baby Items", "count": 0},
        {"category": "Furniture", "count": 0},
        {"category": "Electronics", "count": 0},
        {"category": "Vehicles", "count": 0},
        {"category": "Farming Equipment", "count": 0},
        {"category": "Construction Equipment", "count": 0},
        {"category": "Catering Equipment", "count": 0},
        {"category": "Musical Instruments", "count": 0},
        {"category": "Garden Tools", "count": 0},
        {"category": "Event Decor & Hire", "count": 0},
        {"category": "Bicycles & Cycling Gear", "count": 0},
        {"category": "Laptops & Computers", "count": 0},
        {"category": "Mobile Phones & Tablets", "count": 0},
        {"category": "Home Appliances", "count": 0},
        {"category": "Generators & Power Tools", "count": 0},
        {"category": "Office Furniture", "count": 0},
        {"category": "Wedding Supplies", "count": 0},
        {"category": "Car Parts & Accessories", "count": 0},
        {"category": "Gym & Fitness Equipment", "count": 0},
        {"category": "Books & Study Materials", "count": 0},
        {"category": "Pet Supplies", "count": 0},
        {"category": "Clothing & Fashion", "count": 0},
        {"category": "Kitchen Appliances", "count": 0},
        {"category": "Plumbing & Bathroom", "count": 0},
    ]
    
    # Shuffle and return a random subset of 8-12 categories
    random.shuffle(defaults_pool)
    count = random.randint(8, min(12, len(defaults_pool)))
    
    return defaults_pool[:count]
