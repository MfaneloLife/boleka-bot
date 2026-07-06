"""
social.py - Social Media Poster for Boleka SA Marketplace Bot v1.0
Posts ONLY to Facebook Page. Instagram is linked and will auto-sync.
Uses facebook-sdk library for posting images with captions.
"""

import os
import logging
import facebook

# Configure logging
logger = logging.getLogger(__name__)


def post_to_fb(image_path, caption, page_access_token=None, page_id=None):
    """
    Post an image with caption to a Facebook Page.
    Instagram is linked via Meta Account Center and will auto-sync.
    
    Args:
        image_path: Local file path to the image to post.
        caption: The caption text (including hashtags).
        page_access_token: Facebook Page access token (or reads from env).
        page_id: Facebook Page ID (or reads from env).
    
    Returns:
        dict: {"success": True/False, "message": "...", "post_id": "..."}
    """
    # Get credentials from parameters or environment
    if not page_access_token:
        page_access_token = os.getenv("FB_PAGE_ACCESS_TOKEN")
    if not page_id:
        page_id = os.getenv("FB_PAGE_ID")
    
    # Validate credentials
    if not page_access_token or not page_id:
        error_msg = "Facebook credentials not configured. Missing FB_PAGE_ACCESS_TOKEN or FB_PAGE_ID."
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}
    
    # Validate image exists
    if not image_path or not os.path.exists(image_path):
        error_msg = f"Image file not found: {image_path}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}
    
    try:
        # Initialize Facebook Graph API
        graph = facebook.GraphAPI(access_token=page_access_token, version="18.0")
        
        # Post photo to the Facebook Page
        # Using put_photo which uploads a photo with a message
        with open(image_path, "rb") as image_file:
            post_result = graph.put_photo(
                image=image_file,
                message=caption,
            )
        
        # Extract post ID from the result
        post_id = post_result.get("post_id") or post_result.get("id", "unknown")
        
        success_msg = (
            f"Successfully posted to Facebook Page {page_id}. "
            f"Post ID: {post_id}. Instagram will auto-sync if linked in Account Center."
        )
        logger.info(success_msg)
        
        return {
            "success": True,
            "message": success_msg,
            "post_id": post_id,
        }
        
    except facebook.GraphAPIError as e:
        error_msg = f"Facebook Graph API error: {e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}
        
    except Exception as e:
        error_msg = f"Unexpected error posting to Facebook: {e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}


def post_to_facebook_with_retry(image_path, caption, max_retries=2):
    """
    Post to Facebook with automatic retry on failure.
    
    Args:
        image_path: Local file path to the image.
        caption: The caption text.
        max_retries: Maximum number of retry attempts.
    
    Returns:
        dict: {"success": True/False, "message": "...", "post_id": "..."}
    """
    for attempt in range(1, max_retries + 1):
        result = post_to_fb(image_path, caption)
        
        if result["success"]:
            return result
        
        logger.warning(f"Facebook post attempt {attempt}/{max_retries} failed: {result['message']}")
        
        if attempt < max_retries:
            import time
            wait_seconds = attempt * 5  # Exponential-ish backoff
            logger.info(f"Retrying in {wait_seconds} seconds...")
            time.sleep(wait_seconds)
    
    logger.error(f"All {max_retries} Facebook post attempts failed.")
    return result  # Return the last failure result