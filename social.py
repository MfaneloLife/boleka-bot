"""
social.py - Facebook Graph API poster for E-BOLEKA Marketplace Bot v2.0

Creates DRAFT posts on the E-BOLEKA Facebook Page using Meta Graph API
system user credentials. Drafts are saved as unpublished Page posts that
appear under Meta Business Suite -> Content/Planner -> Drafts (classic Page
"Publishing Tools -> Drafts") so the owner can review and publish manually.

Why /feed instead of /photos:
  Posting a photo directly to /{page-id}/photos with published=false creates a
  hidden "unpublished photo" that only surfaces in Ads Manager, not in the
  Page's normal draft queue. To make drafts visible in Meta Business Suite,
  we first upload the photo as an unpublished asset, then attach it to a draft
  post on /{page-id}/feed (published=false), which is the documented way to
  create a draft that shows in the Page's content planner.
"""

import os
import time
import json
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


def _extract_error_detail(response):
    """Pull a human-readable error message out of a Graph API error response."""
    try:
        return response.json().get("error", {}).get("message", response.text)
    except Exception:
        return response.text


def post_to_fb(image_path, caption, page_access_token=None, page_id=None):
    """
    Create a DRAFT photo + caption on the E-BOLEKA Facebook Page.

    The draft is created on the /{page-id}/feed endpoint with published=false
    so it shows up in Meta Business Suite -> Planner -> Drafts, ready for the
    owner to review and publish manually. The photo is attached via a
    two-step process (unpublished photo upload -> feed draft with
    attached_media).

    Args:
        image_path: Local file path to the image to post.
        caption: Full caption (headline + primary text + description + offer).
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

    try:
        # ------------------------------------------------------------------
        # Step 1: upload the photo as an UNPUBLISHED asset so it is not shown
        # publicly on the Page. This returns a photo ID we can attach below.
        # ------------------------------------------------------------------
        photo_url = f"{GRAPH_API_BASE}/{pid}/photos"
        with open(image_path, "rb") as image_file:
            photo_files = {
                "source": (os.path.basename(image_path), image_file, "image/jpeg")
            }
            photo_data = {
                "access_token": token,
                "published": "false",
            }
            photo_response = requests.post(photo_url, data=photo_data, files=photo_files, timeout=60)

        photo_response.raise_for_status()
        photo_result = photo_response.json()
        photo_id = photo_result.get("id")

        if not photo_id:
            error_msg = f"Facebook did not return a photo ID: {photo_response.text}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "post_id": None}

        # ------------------------------------------------------------------
        # Step 2: create a DRAFT feed post with the photo attached. This is the
        # step that makes the draft visible in Meta Business Suite's Drafts.
        # ------------------------------------------------------------------
        feed_url = f"{GRAPH_API_BASE}/{pid}/feed"
        feed_data = {
            "message": caption,
            "access_token": token,
            "published": "false",
            "attached_media": json.dumps([{"media_fbid": photo_id}]),
        }
        feed_response = requests.post(feed_url, data=feed_data, timeout=60)
        feed_response.raise_for_status()
        feed_result = feed_response.json()
        post_id = feed_result.get("id") or feed_result.get("post_id")

        success_msg = (
            f"Successfully created DRAFT on E-BOLEKA Facebook Page {pid}. "
            f"Draft ID: {post_id}. Review and publish it in Meta Business Suite -> Drafts."
        )
        logger.info(success_msg)
        return {"success": True, "message": success_msg, "post_id": post_id}

    except requests.HTTPError as e:
        detail = _extract_error_detail(e.response) if e.response is not None else str(e)
        error_msg = f"Facebook Graph API error: {detail or e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}

    except Exception as e:
        error_msg = f"Unexpected error creating Facebook draft: {e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}


def post_to_facebook_with_retry(image_path, caption, max_retries=2):
    """Create a Facebook draft with automatic retry on failure."""
    result = {"success": False, "message": "No attempts made", "post_id": None}

    for attempt in range(1, max_retries + 1):
        result = post_to_fb(image_path, caption)

        if result["success"]:
            return result

        logger.warning(
            f"Facebook draft attempt {attempt}/{max_retries} failed: {result['message']}"
        )
        if attempt < max_retries:
            wait_seconds = attempt * 5
            logger.info(f"Retrying in {wait_seconds} seconds...")
            time.sleep(wait_seconds)

    logger.error(f"All {max_retries} Facebook draft attempts failed.")
    return result