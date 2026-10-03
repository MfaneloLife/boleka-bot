"""
db.py - Neon PostgreSQL connection helpers (psycopg2).

The database is managed by a Next.js Prisma app. Prisma preserves the exact
model/field casing, so the table must be referenced as the quoted identifier
"Item", and camelCase columns (e.g. "itemType", "rentalPrice") must be quoted
too. snake_case columns (e.g. is_posted_to_social) can be used unquoted.

Connects via the DATABASE_URL environment variable using psycopg2.
"""

import os
import logging

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def _ensure_ssl(url):
    """Append sslmode=require when missing (Neon requires an SSL connection)."""
    if not url:
        return url
    if "sslmode=" in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}sslmode=require"


def get_connection():
    """Open a new psycopg2 connection using DATABASE_URL."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to your .env before running."
        )
    return psycopg2.connect(_ensure_ssl(url))


# Columns we care about on the Item table. CamelCase columns need quoting
# because Prisma preserves field casing in the actual PostgreSQL column names.
_ITEM_COLUMNS = (
    "id",
    "title",
    "description",
    "category",
    "condition",
    "tags",
    "quantity",
    "lat",
    "lng",
    "address",
    '"itemType"',
    "price",
    '"rentalPrice"',
    '"allowCollection"',
    '"allowDelivery"',
    '"deliveryFee"',
    '"isActive"',
    '"userId"',
    "is_posted_to_social",
    '"social_post_url"',
    '"createdAt"',
    '"updatedAt"',
)


def get_unposted_items(limit=None):
    """
    Query the "Item" table for items not yet posted to social media.

    Only active items whose is_posted_to_social is false are returned, ordered
    oldest-first so the earliest listings go out first.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            query = (
                f"SELECT {', '.join(_ITEM_COLUMNS)} "
                'FROM "Item" '
                "WHERE is_posted_to_social = false AND \"isActive\" = true "
                'ORDER BY "createdAt" ASC'
            )
            params = []
            if limit is not None:
                query += " LIMIT %s"
                params.append(int(limit))
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_item_images(item_id):
    """
    Return the image URLs for an item, ordered by the stored image order.

    Images live in the "ItemImage" table (stored as Cloudflare R2 URLs).
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                'SELECT id, url, "order" FROM "ItemImage" '
                'WHERE "itemId" = %s ORDER BY "order" ASC',
                (item_id,),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def mark_item_posted(item_id, post_url=None):
    """
    Set is_posted_to_social = true for an item after a successful post.

    Also stores the post id/url in social_post_url when provided and bumps
    updatedAt so the Next.js app sees the change.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE "Item" '
                "SET is_posted_to_social = true, "
                '"social_post_url" = COALESCE(%s, "social_post_url"), '
                '"updatedAt" = NOW() '
                "WHERE id = %s",
                (post_url, item_id),
            )
        conn.commit()
        logger.info(f"Marked item {item_id} as posted to social.")
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to mark item {item_id} as posted: {e}")
        raise
    finally:
        conn.close()
