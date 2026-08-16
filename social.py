"""
social.py - Facebook Graph API poster for E-BOLEKA Marketplace Bot v2.0

Posts directly to the E-BOLEKA Facebook Page using Meta Graph API
system user credentials (a long-lived System User Access Token). Uses the
raw Graph API via `requests` so we target the Page explicitly and keep
full control over the API version.

All posts are created as UNPUBLISHED (draft) so they are only visible to the
Page admin, never to the public. The owner reviews and publishes each one
manually.
"""

import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

# Graph API version (override with GRAPH_API_VERSION if needed).
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def _get_credentials(page_access_token=None, page_id=None):
    """Resolve the access token and Page ID from args or environment."""
    token = page_access_token
    if not token:
        # Preferred credential: Meta Business Manager system user token.
        # Legacy page token is kept as a fallback for backwards compatibility.
        token = (
            os.getenv("FB_SYSTEM_USER_ACCESS_TOKEN")
            or os.getenv("META_SYSTEM_USER_TOKEN")
            or os.getenv("FB_PAGE_ACCESS_TOKEN")
        )

    pid = page_id
    if not pid:
        pid = os.getenv("FB_PAGE_ID")

    return token, pid


def post_to_fb(image_path, caption, page_access_token=None, page_id=None):
    """
    Create a DRAFT photo + caption on the E-BOLEKA Facebook Page.

    Uses the Meta Graph API system user credentials and POSTs to
    `/{page-id}/photos` with `published=false` so the content is saved as an
    unpublished draft (visible only to the Page admin), never shown publicly.
    The owner then reviews and publishes it manually.

    Args:
        image_path: Local file path to the image to post.
        caption: Full caption (primary text + headline + description + offer).
        page_access_token: Optional token override (defaults to env).
        page_id: Optional Page ID override (defaults to env).

    Returns:
        dict: {"success": bool, "message": str, "post_id": str|None}
    """
    token, pid = _get_credentials(page_access_token, page_id)

    if not token or not pid:
        error_msg = (
            "Facebook credentials not configured. Missing system user token "
            "(FB_SYSTEM_USER_ACCESS_TOKEN / META_SYSTEM_USER_TOKEN) or FB_PAGE_ID."
        )
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}

    if not image_path or not os.path.exists(image_path):
        error_msg = f"Image file not found: {image_path}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}

    url = f"{GRAPH_API_BASE}/{pid}/photos"

    try:
        with open(image_path, "rb") as image_file:
            files = {"source": (os.path.basename(image_path), image_file, "image/jpeg")}
            data = {
                "message": caption,
                "access_token": token,
                "published": "false",
            }
            response = requests.post(url, data=data, files=files, timeout=60)

        response.raise_for_status()
        result = response.json()
        post_id = result.get("post_id") or result.get("id")

        success_msg = (
            f"Successfully created DRAFT on E-BOLEKA Facebook Page {pid}. "
            f"Draft ID: {post_id}. Awaiting manual review/publish."
        )
        logger.info(success_msg)
        return {"success": True, "message": success_msg, "post_id": post_id}

    except requests.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("error", {}).get("message", "")
        except Exception:
            detail = str(e)
        error_msg = f"Facebook Graph API error: {detail or e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}

    except Exception as e:
        error_msg = f"Unexpected error posting to Facebook: {e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}


def post_to_facebook_with_retry(image_path, caption, max_retries=2):
    """Post to Facebook with automatic retry on failure."""
    result = {"success": False, "message": "No attempts made", "post_id": None}

    for attempt in range(1, max_retries + 1):
        result = post_to_fb(image_path, caption)

        if result["success"]:
            return result

        logger.warning(
            f"Facebook post attempt {attempt}/{max_retries} failed: {result['message']}"
        )
        if attempt < max_retries:
            wait_seconds = attempt * 5
            logger.info(f"Retrying in {wait_seconds} seconds...")
            time.sleep(wait_seconds)

    logger.error(f"All {max_retries} Facebook post attempts failed.")
    return result
