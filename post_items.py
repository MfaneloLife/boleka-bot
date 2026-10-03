"""
post_items.py - Post unposted "Item" records to Facebook via the Meta Graph API.

Queries the Neon PostgreSQL "Item" table (quoted for Prisma compatibility) for
items where is_posted_to_social is false, generates a national South Africa
post for each, publishes via the Meta Graph API, then updates
is_posted_to_social = true (and stores the post id/url).

Business rules enforced:
  - Pricing: rental items show a '/day' suffix; direct-sale items omit it.
  - Audience: single national South Africa market (no city/township targeting).

Usage:
    python post_items.py            # process up to DEFAULT_LIMIT unposted items
    python post_items.py --limit 3  # process up to 3 unposted items
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from ai import generate_post, format_price_display
from db import get_unposted_items, get_item_images, mark_item_posted
from images import (
    download_image_from_url,
    get_unsplash_image,
    enhance_image,
    cleanup_images,
)
from social import post_to_fb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("post_items")

DEFAULT_LIMIT = 5


def post_item(item, api_key):
    """Generate + publish one Item, then mark it posted in the database."""
    item_id = item.get("id")
    title = (item.get("title") or "Check this listing").strip()
    item_type = (item.get("itemType") or "SELLING").strip().upper()
    price = item.get("price")
    rental_price = item.get("rentalPrice")

    # Enforce pricing rules: '/day' suffix only for rental rates.
    price_display = format_price_display(item_type, price, rental_price)
    logger.info(f"Posting item {item_id}: {title} | {price_display}")

    post = generate_post(
        post_type="B",
        category_or_item=title,
        price=price,
        price_display=price_display,
        api_key=api_key,
    )
    caption = post.get("full_caption") or post.get("primary_text") or ""

    image_path = None

    # 1) Prefer the item's own image stored in the DB (Cloudflare R2 URLs).
    try:
        for image in get_item_images(item_id):
            if image.get("url"):
                image_path = download_image_from_url(image["url"])
                if image_path:
                    break
    except Exception as e:
        logger.warning(f"Could not load DB images for item {item_id}: {e}")

    # 2) Fall back to Unsplash.
    if not image_path:
        unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
        if unsplash_key:
            search_term = " ".join(title.split()[:2]) if title else "product"
            image_path = get_unsplash_image(search_term, unsplash_key)

    if not image_path:
        logger.error(f"No image available for item {item_id}; skipping.")
        return {"success": False, "message": "No image available"}

    image_path = enhance_image(image_path)

    result = post_to_fb(image_path, caption)

    if result["success"]:
        try:
            mark_item_posted(item_id, result.get("post_id"))
            logger.info(f"✅ Posted and marked item {item_id}: {result.get('post_id')}")
        except Exception as e:
            logger.error(
                f"Posted item {item_id} but failed to mark it as posted: {e}"
            )
    else:
        logger.error(f"❌ Failed to post item {item_id}: {result.get('message')}")

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Maximum number of unposted items to process (default: {DEFAULT_LIMIT})",
    )
    args = parser.parse_args()

    api_key = os.getenv("DEEPSEEK_API_KEY")

    try:
        items = get_unposted_items(limit=args.limit)
    except Exception as e:
        logger.error(f"Failed to query the database: {e}")
        sys.exit(1)

    if not items:
        logger.info("No unposted items found. Nothing to do.")
        return

    logger.info(f"Found {len(items)} unposted item(s).")

    succeeded = 0
    failed = 0
    for item in items:
        try:
            result = post_item(item, api_key)
            if result["success"]:
                succeeded += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Unexpected error posting item {item.get('id')}: {e}")
            failed += 1
        finally:
            cleanup_images()

    logger.info(f"Done. {succeeded} posted, {failed} failed.")


if __name__ == "__main__":
    main()
