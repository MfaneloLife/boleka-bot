"""
social.py - Facebook Graph API poster for E-BOLEKA Marketplace Bot v2.0

Schedules posts on the E-BOLEKA Facebook Page using Meta Graph API system
user credentials. Posts are scheduled with a future `scheduled_publish_time`
so they reliably appear in Meta Business Suite -> Planner -> Scheduled, where
the owner can review, edit, reschedule, or manually publish each one.

Why scheduled instead of published=false drafts:
  Meta's Graph API `published=false` creates an "unpublished page post" that
  is meant for ad creative (dark posts). It does NOT surface in the Meta
  Business Suite "Drafts" tab, which is only populated by content drafted
  inside Meta Business Suite itself. Scheduling a post into the future makes
  it show up in the content Planner, giving the owner a reliable place to
  review and publish manually (or edit/reschedule/delete).

To attach the image we use a two-step process:
  1) Upload the photo as an unpublished asset (/{page-id}/photos,
     published=false) to get a photo ID.
  2) Create a scheduled feed post (/{page-id}/feed) with that photo attached
     via `attached_media`.
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

# How far in the future to schedule each post (in days). The posts appear in
# Meta Business Suite -> Planner -> Scheduled for manual review. If the owner
# does nothing, the post auto-publishes after this many days. Override with
# the POST_SCHEDULE_DAYS environment variable.
try:
    SCHEDULE_LEAD_DAYS = int(os.getenv("POST_SCHEDULE_DAYS", "7"))
except (TypeError, ValueError):
    SCHEDULE_LEAD_DAYS = 7


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
    Schedule a photo + caption post on the E-BOLEKA Facebook Page.

    The post is created on /{page-id}/feed with a future `scheduled_publish_time`
    so it appears in Meta Business Suite -> Planner -> Scheduled, ready for the
    owner to review and publish manually (or edit/reschedule/delete).

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
        # Step 2: schedule a feed post with the photo attached. The future
        # publish time makes it show in Meta Business Suite -> Planner ->
        # Scheduled for manual review.
        # ------------------------------------------------------------------
        publish_time = int(time.time()) + (SCHEDULE_LEAD_DAYS * 86400)
        feed_url = f"{GRAPH_API_BASE}/{pid}/feed"
        feed_data = {
            "message": caption,
            "access_token": token,
            "scheduled_publish_time": str(publish_time),
            "attached_media": json.dumps([{"media_fbid": photo_id}]),
        }
        feed_response = requests.post(feed_url, data=feed_data, timeout=60)
        feed_response.raise_for_status()
        feed_result = feed_response.json()
        post_id = feed_result.get("id") or feed_result.get("post_id")

        success_msg = (
            f"Successfully scheduled post on E-BOLEKA Facebook Page {pid}. "
            f"Post ID: {post_id}. Review it in Meta Business Suite -> Planner -> Scheduled."
        )
        logger.info(success_msg)
        return {"success": True, "message": success_msg, "post_id": post_id}

    except requests.HTTPError as e:
        detail = _extract_error_detail(e.response) if e.response is not None else str(e)
        error_msg = f"Facebook Graph API error: {detail or e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}

    except Exception as e:
        error_msg = f"Unexpected error scheduling Facebook post: {e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "post_id": None}


def post_to_facebook_with_retry(image_path, caption, max_retries=2):
    """Schedule a Facebook post with automatic retry on failure."""
    result = {"success": False, "message": "No attempts made", "post_id": None}

    for attempt in range(1, max_retries + 1):
        result = post_to_fb(image_path, caption)

        if result["success"]:
            return result

        logger.warning(
            f"Facebook schedule attempt {attempt}/{max_retries} failed: {result['message']}"
        )
        if attempt < max_retries:
            wait_seconds = attempt * 5
            logger.info(f"Retrying in {wait_seconds} seconds...")
            time.sleep(wait_seconds)

    logger.error(f"All {max_retries} Facebook schedule attempts failed.")
    return result