"""
app.py - E-BOLEKA Marketplace Bot v2.0
Main Flask application with scheduler, web dashboard, and post orchestration.

Posts 3 times per day (08:00, 13:00, 18:00 SAST) directly to the E-BOLEKA
Facebook Page using Meta Graph API system user credentials.

Content rules:
  - National South Africa audience (single market - no city segmentation).
  - Every post follows the high-converting ad framework:
      Primary Text (hook + pain point + solution)
      Headline (bold CTA / value highlight)
      Description (clarifying subtext)
      OFFER (incentive / discount / direct action)
"""

import os
import sys
import time
import json
import random
import logging
import threading
from datetime import datetime, timedelta, date
from pathlib import Path

# Load environment variables FIRST
from dotenv import load_dotenv
load_dotenv()

# Flask imports
from flask import Flask, render_template, request, jsonify

# Scheduling
import schedule

# Import local modules
from scraper import get_empty_categories, get_new_listings
from ai import generate_post, MARKET
from images import get_listing_image, get_unsplash_image, cleanup_images, enhance_image
from social import post_to_fb

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "boleka-default-secret-2024")

# Paths
BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs.txt"
IMAGES_DIR = BASE_DIR / "images"
HISTORY_FILE = BASE_DIR / "posted_history.json"
STATE_FILE = BASE_DIR / "bot_state.json"

IMAGES_DIR.mkdir(exist_ok=True)

# Dedup window: don't repeat the same category/item for 3 days.
DEDUP_DAYS = 3

# Single national market - no city/township segmentation.
MARKET_NAME = MARKET  # "South Africa"

# Posting frequency: exactly 3 posts per day.
MAX_POSTS_PER_DAY = 3

# Scheduler times (SAST = UTC+2)
SCHEDULE_TIMES = ["08:00", "13:00", "18:00"]

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------

def setup_logging():
    """Configure logging to both file and console."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(LOGS_DIR, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()

# ---------------------------------------------------------------------------
# Persistent Post History (avoids repeating content across days)
# ---------------------------------------------------------------------------

def _load_history():
    """Load posted history, cleaning entries older than DEDUP_DAYS."""
    if not HISTORY_FILE.exists():
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cutoff = (datetime.now() - timedelta(days=DEDUP_DAYS)).strftime("%Y-%m-%d")
        cleaned = {k: v for k, v in data.items() if v >= cutoff}
        if len(cleaned) != len(data):
            _save_history(cleaned)
            logger.info(f"Cleaned {len(data) - len(cleaned)} expired history entries (>{DEDUP_DAYS} days).")
        return cleaned
    except Exception as e:
        logger.error(f"Error loading post history: {e}")
        return {}


def _save_history(history):
    """Save post history to posted_history.json."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving post history: {e}")


def is_already_posted(key, post_type):
    """
    Check if a category/item has already been posted within DEDUP_DAYS.

    For Type B, "key" is the listing title. For Type A, "key" is the category.
    Returns True = skip, False = safe to post.
    """
    history = _load_history()
    lookup = f"{key}|||{post_type}"
    already = lookup in history
    if already:
        logger.info(f"⏭️  Skipping already-posted: {key} | Type {post_type} (posted {history[lookup]})")
    return already


def mark_as_posted(key, post_type):
    """Record that a category/item was posted today."""
    history = _load_history()
    today_str = datetime.now().strftime("%Y-%m-%d")
    lookup = f"{key}|||{post_type}"
    history[lookup] = today_str
    _save_history(history)
    logger.info(f"📝 Marked as posted: {key} | Type {post_type}")


# ---------------------------------------------------------------------------
# State Persistence (survives Render sleep cycles)
# ---------------------------------------------------------------------------

def _save_state():
    """Save posts_today and last_run to bot_state.json."""
    try:
        data = {
            "posts_today": state.posts_today,
            "last_run": state.last_run.isoformat() if state.last_run else None,
            "saved_at": datetime.now().isoformat(),
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving bot state: {e}")


def _load_state():
    """Load state from bot_state.json on startup. Resets daily counter if stale."""
    if not STATE_FILE.exists():
        logger.info("No saved state file found. Starting fresh.")
        return
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        saved_at = data.get("saved_at", "")
        saved_date = saved_at[:10] if saved_at else ""
        today_str = datetime.now().strftime("%Y-%m-%d")

        if saved_date != today_str:
            logger.info(f"State from {saved_date} is stale. Resetting daily counter.")
            state.reset_daily_counts()
        else:
            state.posts_today = data.get("posts_today", 0)
            logger.info(f"Restored state: {state.posts_today} posts today")

        if data.get("last_run"):
            try:
                state.last_run = datetime.fromisoformat(data["last_run"])
            except (ValueError, TypeError):
                pass

    except Exception as e:
        logger.error(f"Error loading bot state: {e}")


# ---------------------------------------------------------------------------
# Global State (in-memory for dashboard)
# ---------------------------------------------------------------------------

class BotState:
    """Simple in-memory state tracker for the dashboard."""
    def __init__(self):
        self.last_run = None
        self.next_run = None
        self.is_running = False
        self.run_logs = []
        self.posts_today = 0

    def add_log(self, message, level="INFO"):
        """Add a log entry for the dashboard."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.run_logs.append((timestamp, message))
        if len(self.run_logs) > 200:
            self.run_logs = self.run_logs[-200:]
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)

    def reset_daily_counts(self):
        """Reset the daily post counter at midnight."""
        self.posts_today = 0
        _save_state()
        logger.info("Daily post counter reset for new day.")


state = BotState()

# ---------------------------------------------------------------------------
# Post Orchestration Logic
# ---------------------------------------------------------------------------

def log_to_file(timestamp, market, platform, message):
    """Log a post event to logs.txt."""
    with open(LOGS_DIR, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {market} | {platform} | {message}\n")


def _pick_unposted_category(empty_categories):
    """Pick a category not posted within DEDUP_DAYS (national market)."""
    if not empty_categories:
        return None

    shuffled = random.sample(empty_categories, len(empty_categories))

    for cat_info in shuffled:
        cat_name = cat_info["category"]
        if not is_already_posted(cat_name, "A"):
            logger.info(f"Selected unposted category: {cat_name}")
            return cat_info

    fallback = random.choice(empty_categories)
    logger.info(f"All categories recently posted. Falling back to random: {fallback['category']}")
    return fallback


def _pick_unposted_listing(listings):
    """Pick a listing not posted within DEDUP_DAYS (national market)."""
    if not listings:
        return None

    shuffled = random.sample(listings, len(listings))

    for listing in shuffled:
        title = listing["title"]
        if not is_already_posted(title, "B"):
            logger.info(f"Selected unposted listing: {title}")
            return listing

    fallback = random.choice(listings)
    logger.info(f"All listings recently posted. Falling back to random: {fallback['title']}")
    return fallback


def create_type_a_post(market, category_info, api_key):
    """Create a Type A post: Call to list items in an empty category (national)."""
    category_name = category_info["category"]
    count = category_info.get("count", 0)

    state.add_log(f"Creating Type A post (national): {category_name} ({count} listings)")

    post = generate_post(post_type="A", category_or_item=category_name, api_key=api_key)
    caption = post.get("full_caption") or post.get("primary_text") or ""

    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
    image_path = None

    if unsplash_key:
        image_path = get_unsplash_image(category_name, unsplash_key)

    if not image_path:
        state.add_log(f"No Unsplash image found for '{category_name}', trying fallback...", "WARNING")
        if unsplash_key:
            image_path = get_unsplash_image("marketplace items", unsplash_key)

    if not image_path:
        state.add_log("No image available. Skipping post.", "ERROR")
        return {"success": False, "message": "No image available"}

    # Pillar 1: ensure high-contrast visuals before publishing.
    image_path = enhance_image(image_path)

    result = post_to_fb(image_path, caption)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if result["success"] else "FAILED"
    log_to_file(timestamp, market, "Facebook",
                f"Type A: {category_name} | {status} | {result.get('post_id', 'N/A')}")

    if result["success"]:
        state.posts_today += 1
        mark_as_posted(category_name, "A")
        _save_state()
        state.add_log(f"✅ Posted Type A (national): {category_name} (Post ID: {result.get('post_id')})")
    else:
        state.add_log(f"❌ Failed Type A: {category_name} - {result.get('message')}", "ERROR")

    return result


def create_type_b_post(market, listing, api_key):
    """Create a Type B post: Promote a new listing from eboleka (national)."""
    title = listing["title"]
    price = listing.get("price", "0")
    url = listing.get("url", "")

    state.add_log(f"Creating Type B post (national): {title} (R{price})")

    post = generate_post(post_type="B", category_or_item=title, price=price, api_key=api_key)
    caption = post.get("full_caption") or post.get("primary_text") or ""

    image_path = None

    if url:
        image_path = get_listing_image(url)

    if not image_path:
        unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
        if unsplash_key:
            search_term = " ".join(title.split()[:2]) if title else "product"
            image_path = get_unsplash_image(search_term, unsplash_key)

    if not image_path:
        state.add_log("No image available. Skipping post.", "ERROR")
        return {"success": False, "message": "No image available"}

    # Pillar 1: ensure high-contrast visuals before publishing.
    image_path = enhance_image(image_path)

    result = post_to_fb(image_path, caption)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if result["success"] else "FAILED"
    log_to_file(timestamp, market, "Facebook",
                f"Type B: {title} (R{price}) | {status} | {result.get('post_id', 'N/A')}")

    if result["success"]:
        state.posts_today += 1
        mark_as_posted(title, "B")
        _save_state()
        state.add_log(f"✅ Posted Type B (national): {title} (Post ID: {result.get('post_id')})")
    else:
        state.add_log(f"❌ Failed Type B: {title} - {result.get('message')}", "ERROR")

    return result


def _create_type_a_attempt(market, api_key):
    """Fetch categories and attempt one Type A post."""
    empty_categories = get_empty_categories(market)
    category_info = _pick_unposted_category(empty_categories)
    if not category_info:
        state.add_log("No unposted categories available for Type A.", "WARNING")
        return {"success": False, "message": "No categories available"}
    return create_type_a_post(market, category_info, api_key)


def _create_type_b_attempt(market, api_key):
    """Fetch listings and attempt one Type B post."""
    listings = get_new_listings(market)
    listing = _pick_unposted_listing(listings)
    if not listing:
        state.add_log("No unposted listings available for Type B.", "WARNING")
        return {"success": False, "message": "No listings available"}
    return create_type_b_post(market, listing, api_key)


def run_bot_cycle():
    """
    Main bot cycle: creates exactly ONE post per run.
    The scheduler triggers this 3 times a day (3 posts/day total).
    Alternates Type A / Type B, falling back to the other type if needed.
    """
    if state.is_running:
        logger.warning("Bot cycle already running. Skipping this round.")
        return

    state.is_running = True
    start_time = datetime.now()

    try:
        state.add_log(f"🚀 Starting posting cycle at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # Reset the daily counter if it's a new day.
        if state.last_run and start_time.date() > state.last_run.date():
            state.reset_daily_counts()

        if state.posts_today >= MAX_POSTS_PER_DAY:
            state.add_log(f"✅ Daily limit reached ({MAX_POSTS_PER_DAY} posts). Waiting for the next day.")
            state.last_run = start_time
            _save_state()
            return

        deepseek_key = os.getenv("DEEPSEEK_API_KEY")

        # Alternate post types across the 3 daily slots.
        primary_type = "A" if state.posts_today % 2 == 0 else "B"

        if primary_type == "B":
            result = _create_type_b_attempt(MARKET_NAME, deepseek_key)
            if not (result and result.get("success")):
                state.add_log("Type B unavailable, falling back to Type A.")
                result = _create_type_a_attempt(MARKET_NAME, deepseek_key)
        else:
            result = _create_type_a_attempt(MARKET_NAME, deepseek_key)
            if not (result and result.get("success")):
                state.add_log("Type A unavailable, falling back to Type B.")
                result = _create_type_b_attempt(MARKET_NAME, deepseek_key)

        cleanup_images()

        if result and result.get("success"):
            state.add_log(f"✅ Cycle complete: 1 post created. Total today: {state.posts_today}/{MAX_POSTS_PER_DAY}")
        else:
            msg = result.get("message") if result else "No content available"
            state.add_log(f"❌ Cycle failed to post: {msg}", "ERROR")

    except Exception as e:
        logger.error(f"Bot cycle crashed: {e}", exc_info=True)
        state.add_log(f"❌ Bot cycle error: {e}", "ERROR")
    finally:
        state.last_run = datetime.now()
        _save_state()
        _update_next_run()
        state.is_running = False


def scheduled_job():
    """Wrapper for scheduler to run the bot cycle."""
    logger.info("Scheduled job triggered.")
    run_bot_cycle()


def _update_next_run():
    """Calculate and update the next scheduled run time."""
    now = datetime.now()
    today = now.date()

    for time_str in SCHEDULE_TIMES:
        hour, minute = map(int, time_str.split(":"))
        scheduled = datetime(today.year, today.month, today.day, hour, minute)
        if scheduled > now:
            state.next_run = scheduled
            return

    hour, minute = map(int, SCHEDULE_TIMES[0].split(":"))
    state.next_run = datetime(today.year, today.month, today.day, hour, minute) + timedelta(days=1)


def start_scheduler():
    """Configure and start the schedule background thread."""
    for time_str in SCHEDULE_TIMES:
        schedule.every().day.at(time_str).do(scheduled_job)
        logger.info(f"Scheduled job for {time_str} SAST daily.")

    _update_next_run()

    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(30)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True, name="scheduler")
    scheduler_thread.start()
    logger.info("Scheduler started in background thread.")

# ---------------------------------------------------------------------------
# Flask Routes - Web Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Lightweight keep-alive / health-check endpoint.

    External ping services (e.g. cron-job.org) hit the root URL every few
    minutes to keep the Render free tier awake. Return a tiny plain-text
    response instead of the full dashboard HTML so we never trip their
    output-size limits.
    """
    return "Bot is active", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/dashboard")
def dashboard():
    """Main dashboard page."""
    return render_template(
        "dashboard.html",
        market=MARKET_NAME,
        schedule_times=SCHEDULE_TIMES,
        max_posts_per_day=MAX_POSTS_PER_DAY,
        last_run=state.last_run.strftime("%Y-%m-%d %H:%M:%S") if state.last_run else "Never",
        next_run=state.next_run.strftime("%Y-%m-%d %H:%M:%S") if state.next_run else "Not set",
        is_running=state.is_running,
        posts_today=state.posts_today,
        logs=state.run_logs[-50:],
    )


@app.route("/api/status")
def api_status():
    """Return bot status as JSON."""
    return jsonify({
        "last_run": state.last_run.isoformat() if state.last_run else None,
        "next_run": state.next_run.isoformat() if state.next_run else None,
        "is_running": state.is_running,
        "posts_today": state.posts_today,
        "max_posts_today": MAX_POSTS_PER_DAY,
        "market": MARKET_NAME,
        "schedule_times": SCHEDULE_TIMES,
    })


@app.route("/api/logs")
def api_logs():
    """Return recent log entries as JSON."""
    return jsonify({
        "logs": [
            {"timestamp": ts, "message": msg}
            for ts, msg in state.run_logs[-100:]
        ]
    })


@app.route("/api/run", methods=["POST"])
def api_run_now():
    """Trigger an immediate bot cycle (creates one post)."""
    if state.is_running:
        return jsonify({
            "success": False,
            "message": "Bot cycle is already running. Please wait."
        }), 409

    thread = threading.Thread(target=run_bot_cycle, daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "message": "Bot cycle started. Check logs for progress."
    })


@app.route("/api/test-post", methods=["POST"])
def api_test_post():
    """Test post for the national South Africa market."""
    if state.is_running:
        return jsonify({
            "success": False,
            "message": "Bot cycle is already running. Please wait."
        }), 409

    def do_test_post():
        state.is_running = True
        try:
            state.add_log(f"🧪 Test post initiated for national {MARKET_NAME}...")
            deepseek_key = os.getenv("DEEPSEEK_API_KEY")

            result = _create_type_b_attempt(MARKET_NAME, deepseek_key)
            if not (result and result.get("success")):
                state.add_log("Type B unavailable for test, trying Type A.")
                result = _create_type_a_attempt(MARKET_NAME, deepseek_key)

            cleanup_images()

            if result and result.get("success"):
                state.add_log(f"✅ Test post successful for national {MARKET_NAME}! Posted to E-BOLEKA Facebook Page.")
            else:
                msg = result.get("message") if result else "No content available"
                state.add_log(f"❌ Test post failed: {msg}", "ERROR")
        except Exception as e:
            state.add_log(f"❌ Test post error: {e}", "ERROR")
        finally:
            state.is_running = False

    thread = threading.Thread(target=do_test_post, daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "message": f"Test post initiated for national {MARKET_NAME}."
    })


@app.route("/api/logs/clear", methods=["POST"])
def api_clear_logs():
    """Clear in-memory logs (file logs preserved)."""
    state.run_logs = []
    state.add_log("📝 Dashboard logs cleared.")
    return jsonify({"success": True, "message": "Logs cleared."})


@app.route("/api/reset-daily", methods=["POST"])
def api_reset_daily():
    """Manually reset the daily post counter."""
    state.reset_daily_counts()
    state.add_log("🔄 Daily post counter manually reset.")
    return jsonify({"success": True, "message": "Daily count reset."})


# ---------------------------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------------------------

_WSGI_SCHEDULER_STARTED = False


def _start_wsgi_scheduler():
    """Start the scheduler on module import (works under gunicorn too)."""
    global _WSGI_SCHEDULER_STARTED
    if _WSGI_SCHEDULER_STARTED:
        return
    _WSGI_SCHEDULER_STARTED = True

    _load_state()
    start_scheduler()
    _update_next_run()

    logger.info("=" * 60)
    logger.info("E-BOLEKA Marketplace Bot v2.0 Starting...")
    logger.info(f"Market: {MARKET_NAME} (national - single market, no city segmentation)")
    logger.info(f"Schedule: {', '.join(SCHEDULE_TIMES)} SAST daily")
    logger.info(f"Max posts/day: {MAX_POSTS_PER_DAY}")
    logger.info(f"Dedup: {DEDUP_DAYS} days | Platform: Facebook Page (Meta system user)")
    logger.info("=" * 60)


_start_wsgi_scheduler()


if __name__ == "__main__":
    # Verify required environment variables.
    token_vars = ["FB_SYSTEM_USER_ACCESS_TOKEN", "META_SYSTEM_USER_TOKEN", "FB_PAGE_ACCESS_TOKEN"]
    has_token = any(os.getenv(v) for v in token_vars)

    missing = []
    if not has_token:
        missing.append("FB_SYSTEM_USER_ACCESS_TOKEN (or META_SYSTEM_USER_TOKEN)")
    if not os.getenv("FB_PAGE_ID"):
        missing.append("FB_PAGE_ID")

    if missing:
        logger.warning(f"Missing environment variables: {', '.join(missing)}")
        logger.warning("The bot will run but posting may fail until these are set.")
        logger.warning("Copy .env.example to .env and fill in your values.")

    # The scheduler is already running (started on import above).
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    logger.info(f"Starting Flask dashboard on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=debug)
