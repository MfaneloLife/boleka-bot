"""
images.py - Image Handler for Boleka SA Marketplace Bot v1.0
Handles downloading images from eboleka.co.za listings and Unsplash API.
Rule: Never use Pinterest or Google Images. Only Unsplash, Pexels, or eboleka.co.za.
"""

import os
import requests
import logging
from PIL import Image
from io import BytesIO

# Configure logging
logger = logging.getLogger(__name__)

# Paths
IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")


def ensure_images_dir():
    """Create /images folder if it doesn't exist."""
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)
        logger.info(f"Created images directory: {IMAGES_DIR}")


def get_listing_image(listing_url):
    """
    Download the MAIN image from an eboleka.co.za listing page.
    This is our #1 priority image source.
    
    Args:
        listing_url: Full URL to the eboleka.co.za listing page.
    
    Returns:
        str: Local file path to the downloaded image, or None if failed.
    """
    ensure_images_dir()
    
    try:
        from bs4 import BeautifulSoup
        
        # Fetch the listing page
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(listing_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Try to find the main product image - common selectors
        img_url = None
        
        # Strategy 1: Look for meta property="og:image"
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            img_url = og_image["content"]
        
        # Strategy 2: Look for main product image with specific class patterns
        if not img_url:
            for selector in [
                ".product-image img",
                ".listing-image img",
                ".main-image img",
                ".featured-image img",
                "img.listing-main",
                "img.product-main",
                ".carousel-item.active img",
                ".gallery img:first-child",
            ]:
                elem = soup.select_one(selector)
                if elem and elem.get("src"):
                    img_url = elem["src"]
                    break
        
        # Strategy 3: Find any large image on the page
        if not img_url:
            images = soup.find_all("img")
            for img in images:
                src = img.get("src") or img.get("data-src")
                if src and ("product" in src.lower() or "listing" in src.lower() or "item" in src.lower()):
                    img_url = src
                    break
        
        # Strategy 4: Take the first reasonable image
        if not img_url and images:
            for img in images:
                src = img.get("src") or img.get("data-src")
                if src and not src.endswith((".svg", ".gif")) and "logo" not in src.lower() and "icon" not in src.lower():
                    img_url = src
                    break
        
        if not img_url:
            logger.warning(f"No image found on listing page: {listing_url}")
            return None
        
        # Handle relative URLs
        if img_url.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(listing_url)
            img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
        
        # Download the image
        img_response = requests.get(img_url, headers=headers, timeout=15)
        img_response.raise_for_status()
        
        # Generate a filename from the URL
        import hashlib
        url_hash = hashlib.md5(listing_url.encode()).hexdigest()[:12]
        
        # Determine file extension
        content_type = img_response.headers.get("content-type", "")
        ext = ".jpg"
        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"
        
        filename = f"listing_{url_hash}{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)
        
        # Save and optimize the image
        img = Image.open(BytesIO(img_response.content))
        img = img.convert("RGB")  # Ensure JPEG compatibility
        img.save(filepath, "JPEG", quality=85, optimize=True)
        
        logger.info(f"Downloaded listing image: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Error downloading listing image from {listing_url}: {e}")
        return None


def get_unsplash_image(search_term, unsplash_access_key):
    """
    Download an image from Unsplash API based on a search term.
    Search query format: "[CATEGORY] South Africa"
    
    Args:
        search_term: Search query (e.g., "tent South Africa").
        unsplash_access_key: Unsplash API access key.
    
    Returns:
        str: Local file path to the downloaded image, or None if failed.
    """
    ensure_images_dir()
    
    try:
        # Append "South Africa" if not already present
        if "south africa" not in search_term.lower():
            query = f"{search_term} South Africa"
        else:
            query = search_term
        
        url = "https://api.unsplash.com/search/photos"
        params = {
            "query": query,
            "per_page": 1,
            "orientation": "landscape",
        }
        headers = {
            "Authorization": f"Client-ID {unsplash_access_key}",
            "Accept-Version": "v1",
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        results = data.get("results", [])
        
        if not results:
            logger.warning(f"No Unsplash results for query: {query}")
            return None
        
        # Get the first result's image URL (regular size)
        image_url = results[0]["urls"].get("regular") or results[0]["urls"].get("small")
        
        if not image_url:
            logger.warning(f"No image URL in Unsplash result for: {query}")
            return None
        
        # Download the image
        img_response = requests.get(image_url, timeout=15)
        img_response.raise_for_status()
        
        # Generate filename
        import hashlib
        term_hash = hashlib.md5(search_term.encode()).hexdigest()[:12]
        filename = f"unsplash_{term_hash}.jpg"
        filepath = os.path.join(IMAGES_DIR, filename)
        
        # Save and optimize
        img = Image.open(BytesIO(img_response.content))
        img = img.convert("RGB")
        img.save(filepath, "JPEG", quality=85, optimize=True)
        
        logger.info(f"Downloaded Unsplash image for '{search_term}': {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Error downloading Unsplash image for '{search_term}': {e}")
        return None


def cleanup_images():
    """
    Delete all files in the /images folder after posting to save space.
    """
    ensure_images_dir()
    
    try:
        count = 0
        for filename in os.listdir(IMAGES_DIR):
            filepath = os.path.join(IMAGES_DIR, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
                count += 1
                logger.info(f"Deleted: {filepath}")
        
        logger.info(f"Cleanup complete: removed {count} files from /images")
        return count
        
    except Exception as e:
        logger.error(f"Error cleaning up images: {e}")
        return 0