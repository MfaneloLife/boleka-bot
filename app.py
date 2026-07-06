"""
app.py - Boleka SA Marketplace Bot v1.0
Main Flask application with scheduler, web dashboard, and post orchestration.
Runs 4 times per day (8:00, 12:00, 16:00, 20:00 SAST) posting to Facebook.
Instagram auto-syncs via Meta Account Center.

NEW v1.0.1:
- Persistent post history (posted_history.json) with 3-day dedup
- State save/restore to survive Render sleep cycles
- Randomized category selection to avoid repeating same content
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
from ai import generate_post
from images import get_listing_image, get_unsplash_image, cleanup_images
from social import post_to_fb

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Flask app
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "boleka-default-secret-2024")

# Paths
BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs.txt"
IMAGES_DIR = BASE_DIR / "images"
HISTORY_FILE = BASE_DIR / "posted_history.json"
STATE_FILE = BASE_DIR / "bot_state.json"

# Ensure images directory exists
IMAGES_DIR.mkdir(exist_ok=True)

# Dedup window: don't repeat same category/item in same city for 3 days
DEDUP_DAYS = 3

# South African cities (9-city rotation)
CITIES = [
    "Johannesburg",
    "Pretoria",
    "Cape Town",
    "Durban",
    "Bloemfontein",
    "Port Elizabeth",
    "East London",
    "Polokwane",
    "Rustenburg",
]

# Post limits
MAX_POSTS_PER_CITY_PER_DAY = 2
MAX_POSTS_PER_DAY = 20

# Scheduler times (SAST = UTC+2)
SCHEDULE_TIMES = ["08:00", "12:00", "16:00", "20:00"]

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
    """
    Load the post history from posted_history.json.
    Returns dict: {"city|||key|||post_type": "2026-07-15"}
    Auto-expires entries older than DEDUP_DAYS.
    """
    if not HISTORY_FILE.exists():
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Clean expired entries
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


def is_already_posted(city, key, post_type):
    """
    Check if a category/item has already been posted in the same city
    within the last DEDUP_DAYS days.

    For Type B, "key" is the listing title.
    For Type A, "key" is the category name.

    Returns True = skip, False = safe to post.
    """
    history = _load_history()
    lookup = f"{city}|||{key}|||{post_type}"
    already = lookup in history
    if already:
        logger.info(f"⏭️  Skipping already-posted: {city} | {key} | Type {post_type} (posted {history[lookup]})")
    return already


def mark_as_posted(city, key, post_type):
    """Record that a category/item was posted for a city today."""
    history = _load_history()
    today_str = datetime.now().strftime("%Y-%m-%d")
    lookup = f"{city}|||{key}|||{post_type}"
    history[lookup] = today_str
    _save_history(history)
    logger.info(f"📝 Marked as posted: {city} | {key} | Type {post_type}")


# ---------------------------------------------------------------------------
# State Persistence (survives Render sleep cycles)
# ---------------------------------------------------------------------------

def _save_state():
    """Save city_post_count and posts_today to bot_state.json."""
    try:
        data = {
            "posts_today": state.posts_today,
            "city_post_count": state.city_post_count,
            "last_run": state.last_run.isoformat() if state.last_run else None,
            "saved_at": datetime.now().isoformat(),
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving bot state: {e}")


def _load_state():
    """
    Load state from bot_state.json on startup.
    Resets daily counters if the saved date is not today.
    """
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
            logger.info(f"State from {saved_date} is stale. Resetting daily counters.")
            state.reset_daily_counts()
        else:
            state.posts_today = data.get("posts_today", 0)
            saved_counts = data.get("city_post_count", {})
            for city in CITIES:
                state.city_post_count[city] = saved_counts.get(city, 0)
            logger.info(f"Restored state: {state.posts_today} posts today, counts: {state.city_post_count}")

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
        self.city_post_count = {city: 0 for city in CITIES}
        self.current_city_index = 0

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
        """Reset daily post counters at midnight."""
        self.posts_today = 0
        self.city_post_count = {city: 0 for city in CITIES}
        _save_state()
        logger.info("Daily post counters reset for new day.")


state = BotState()

# ---------------------------------------------------------------------------
# Post Orchestration Logic
# ---------------------------------------------------------------------------

def log_to_file(timestamp, city, platform, message):
    """Log a post event to logs.txt."""
    with open(LOGS_DIR, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {city} | {platform} | {message}\n")


def _pick_unposted_category(empty_categories, city):
    """
    From the list of empty categories, pick one that hasn't been posted
    in the last DEDUP_DAYS days for this city. Falls back to the first
    available if all have been posted recently.

    Returns the chosen category dict, or None if the list is empty.
    """
    if not empty_categories:
        return None

    # Shuffle so we don't always pick the same order
    shuffled = random.sample(empty_categories, len(empty_categories))

    for cat_info in shuffled:
        cat_name = cat_info["category"]
        if not is_already_posted(city, cat_name, "A"):
            logger.info(f"Selected unposted category for {city}: {cat_name}")
            return cat_info

    # All categories have been posted within DEDUP_DAYS — pick a random one
    fallback = random.choice(empty_categories)
    logger.info(f"All categories recently posted for {city}. Falling back to random: {fallback['category']}")
    return fallback


def _pick_unposted_listing(listings, city):
    """
    From the list of listings, pick one whose title hasn't been posted
    in the last DEDUP_DAYS days for this city.

    Returns the chosen listing dict, or None if the list is empty.
    """
    if not listings:
        return None

    shuffled = random.sample(listings, len(listings))

    for listing in shuffled:
        title = listing["title"]
        # Type B dedup by listing title (titles may vary slightly so exact match only)
        if not is_already_posted(city, title, "B"):
            logger.info(f"Selected unposted listing for {city}: {title}")
            return listing

    # All were posted recently — pick a random one anyway
    fallback = random.choice(listings)
    logger.info(f"All listings recently posted for {city}. Falling back to random: {fallback['title']}")
    return fallback


def create_type_a_post(city, category_info, api_key):
    """
    Create a Type A post: Call to list items in an empty category.
    Records category in posted history on success.
    """
    category_name = category_info["category"]
    count = category_info.get("count", 0)

    state.add_log(f"Creating Type A post for {city}: {category_name} ({count} listings)")

    caption = generate_post(post_type="A", city=city, category_or_item=category_name, api_key=api_key)

    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
    image_path = None
    image_source = "Unsplash"

    if unsplash_key:
        image_path = get_unsplash_image(category_name, unsplash_key)

    if not image_path:
        state.add_log(f"No Unsplash image found for '{category_name}', trying fallback...", "WARNING")
        if unsplash_key:
            image_path = get_unsplash_image("marketplace items", unsplash_key)

    if not image_path:
        state.add_log("No image available. Skipping post.", "ERROR")
        return {"success": False, "message": "No image available"}

    final_caption = caption
    if image_source == "Unsplash":
        final_caption += "\n\n📷 Photo: Unsplash"

    result = post_to_fb(image_path, final_caption)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if result["success"] else "FAILED"
    log_to_file(timestamp, city, "Facebook",
                f"Type A: {category_name} | {status} | {result.get('post_id', 'N/A')}")

    if result["success"]:
        state.posts_today += 1
        state.city_post_count[city] = state.city_post_count.get(city, 0) + 1
        mark_as_posted(city, category_name, "A")
        _save_state()
        state.add_log(f"✅ Posted Type A for {city}: {category_name} (Post ID: {result.get('post_id')})")
    else:
        state.add_log(f"❌ Failed Type A for {city}: {category_name} - {result.get('message')}", "ERROR")

    return result


def create_type_b_post(city, listing, api_key):
    """
    Create a Type B post: Promote a new listing from eboleka.
    Records listing title in posted history on success.
    """
    title = listing["title"]
    price = listing.get("price", "0")
    url = listing.get("url", "")

    state.add_log(f"Creating Type B post for {city}: {title} (R{price})")

    caption = generate_post(post_type="B", city=city, category_or_item=title, price=price, api_key=api_key)

    image_path = None
    image_source = "eboleka.co.za"

    if url:
        image_path = get_listing_image(url)

    if not image_path:
        unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
        if unsplash_key:
            search_term = " ".join(title.split()[:2]) if title else "product"
            image_path = get_unsplash_image(search_term, unsplash_key)
            image_source = "Unsplash"

    if not image_path:
        state.add_log("No image available. Skipping post.", "ERROR")
        return {"success": False, "message": "No image available"}

    final_caption = caption
    if image_source == "Unsplash":
        final_caption += "\n\n📷 Photo: Unsplash"

    result = post_to_fb(image_path, final_caption)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if result["success"] else "FAILED"
    log_to_file(timestamp, city, "Facebook",
                f"Type B: {title} (R{price}) | {status} | {result.get('post_id', 'N/A')}")

    if result["success"]:
        state.posts_today += 1
        state.city_post_count[city] = state.city_post_count.get(city, 0) + 1
        mark_as_posted(city, title, "B")
        _save_state()
        state.add_log(f"✅ Posted Type B for {city}: {title} (Post ID: {result.get('post_id')})")
    else:
        state.add_log(f"❌ Failed Type B for {city}: {title} - {result.get('message')}", "ERROR")

    return result


def get_next_city():
    """
    Get the next city in rotation, respecting daily limits.
    Skips cities that have reached their daily max (2 posts).
    """
    for _ in range(len(CITIES)):
        city = CITIES[state.current_city_index]
        state.current_city_index = (state.current_city_index + 1) % len(CITIES)
        if state.city_post_count.get(city, 0) < MAX_POSTS_PER_CITY_PER_DAY:
            return city

    logger.warning("All cities have reached their daily post limit.")
    return None


def run_bot_cycle():
    """
    Main bot cycle: Run a full posting round.
    Alternates between Type A (call to list) and Type B (new listing) posts.
    Uses dedup to avoid repeating the same category/item within DEDUP_DAYS.
    Respects daily limits: max 2 per city, max 20 total.
    """
    if state.is_running:
        logger.warning("Bot cycle already running. Skipping this round.")
        return

    state.is_running = True
    start_time = datetime.now()

    try:
        state.add_log(f"🚀 Starting bot cycle at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # Reset daily counts if it's a new day
        today = datetime.now().date()
        if state.last_run:
            last_date = state.last_run.date()
            if today > last_date:
                state.reset_daily_counts()

        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        posts_created = 0
        post_round = 0
        skipped_categories = 0  # Track how many we skipped due to dedup

        while posts_created < MAX_POSTS_PER_DAY:
            city = get_next_city()
            if not city:
                state.add_log("No more cities available (all at daily limit).")
                break

            if post_round % 2 == 0:
                # --- Type A: Call to list items ---
                empty_categories = get_empty_categories(city)

                if empty_categories:
                    # Pick an unposted category (with dedup check)
                    category_info = _pick_unposted_category(empty_categories, city)
                    if category_info:
                        result = create_type_a_post(city, category_info, deepseek_key)
                        if result.get("success"):
                            posts_created += 1
                        else:
                            skipped_categories += 1
                    else:
                        skipped_categories += 1
                        state.add_log(f"No unposted categories available for {city}.", "WARNING")
                else:
                    state.add_log(f"No empty categories found for {city}, trying Type B instead.")
                    listings = get_new_listings(city)
                    if listings:
                        listing = _pick_unposted_listing(listings, city)
                        if listing:
                            result = create_type_b_post(city, listing, deepseek_key)
                            if result.get("success"):
                                posts_created += 1
            else:
                # --- Type B: Promote new listings ---
                listings = get_new_listings(city)

                if listings:
                    listing = _pick_unposted_listing(listings, city)
                    if listing:
                        result = create_type_b_post(city, listing, deepseek_key)
                        if result.get("success"):
                            posts_created += 1
                    else:
                        skipped_categories += 1
                else:
                    state.add_log(f"No new listings found for {city}, trying Type A instead.")
                    empty_categories = get_empty_categories(city)
                    if empty_categories:
                        category_info = _pick_unposted_category(empty_categories, city)
                        if category_info:
                            result = create_type_a_post(city, category_info, deepseek_key)
                            if result.get("success"):
                                posts_created += 1

            post_round += 1

            if skipped_categories >= 9:
                state.add_log("Too many dedup skips. All 9-city categories likely posted within 3 days.", "WARNING")
                break

            if posts_created < MAX_POSTS_PER_DAY and post_round < len(CITIES) * 2:
                time.sleep(2)

        cleanup_images()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        state.last_run = end_time
        _save_state()
        state.add_log(f"✅ Bot cycle complete. {posts_created} posts in {duration:.1f}s "
                      f"(skipped {skipped_categories} duplicates)")

    except Exception as e:
        logger.error(f"Bot cycle crashed: {e}", exc_info=True)
        state.add_log(f"❌ Bot cycle error: {e}", "ERROR")
    finally:
        state.is_running = False


def scheduled_job():
    """Wrapper for scheduler to run the bot cycle."""
    logger.info("Scheduled job triggered.")
    run_bot_cycle()
    _update_next_run()


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
def dashboard():
    """Main dashboard page."""
    return render_template(
        "dashboard.html",
        cities=CITIES,
        last_run=state.last_run.strftime("%Y-%m-%d %H:%M:%S") if state.last_run else "Never",
        next_run=state.next_run.strftime("%Y-%m-%d %H:%M:%S") if state.next_run else "Not set",
        is_running=state.is_running,
        posts_today=state.posts_today,
        city_post_count=state.city_post_count,
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
        "city_post_count": state.city_post_count,
        "max_per_city": MAX_POSTS_PER_CITY_PER_DAY,
        "cities": CITIES,
        "current_city_index": state.current_city_index,
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
    """Trigger an immediate bot cycle."""
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
    """Test post for a specific city."""
    if state.is_running:
        return jsonify({
            "success": False,
            "message": "Bot cycle is already running. Please wait."
        }), 409

    city = request.form.get("city", "").strip()

    if city not in CITIES:
        return jsonify({
            "success": False,
            "message": f"Invalid city: {city}. Valid cities: {', '.join(CITIES)}"
        }), 400

    def do_test_post():
        state.is_running = True
        try:
            state.add_log(f"🧪 Test post initiated for {city}...")
            deepseek_key = os.getenv("DEEPSEEK_API_KEY")

            listings = get_new_listings(city)
            if listings:
                result = create_type_b_post(city, listings[0], deepseek_key)
            else:
                empty_categories = get_empty_categories(city)
                if empty_categories:
                    result = create_type_a_post(city, empty_categories[0], deepseek_key)
                else:
                    state.add_log("No listings or categories found for test post.", "ERROR")
                    result = {"success": False, "message": "No content available"}

            cleanup_images()

            if result.get("success"):
                state.add_log(f"✅ Test post successful for {city}! Posted to Facebook. Instagram will auto-sync.")
            else:
                state.add_log(f"❌ Test post failed: {result.get('message')}", "ERROR")
        except Exception as e:
            state.add_log(f"❌ Test post error: {e}", "ERROR")
        finally:
            state.is_running = False

    thread = threading.Thread(target=do_test_post, daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "message": f"Test post initiated for {city}. Posted to Facebook. Instagram will auto-sync."
    })


@app.route("/api/logs/clear", methods=["POST"])
def api_clear_logs():
    """Clear in-memory logs (file logs preserved)."""
    state.run_logs = []
    state.add_log("📝 Dashboard logs cleared.")
    return jsonify({"success": True, "message": "Logs cleared."})


@app.route("/api/reset-daily", methods=["POST"])
def api_reset_daily():
    """Manually reset daily post counters."""
    state.reset_daily_counts()
    state.add_log("🔄 Daily post counters manually reset.")
    return jsonify({"success": True, "message": "Daily counts reset."})


# ---------------------------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Verify required environment variables
    required_vars = [
        "DEEPSEEK_API_KEY",
        "FB_PAGE_ACCESS_TOKEN",
        "FB_PAGE_ID",
        "UNSPLASH_ACCESS_KEY",
    ]

    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        logger.warning(f"Missing environment variables: {', '.join(missing)}")
        logger.warning("The bot will run but some features may not work.")
        logger.warning("Copy .env.example to .env and fill in your values.")

    # Restore state from previous run (survives Render sleep)
    _load_state()

    logger.info("=" * 60)
    logger.info("Boleka SA Marketplace Bot v1.0 Starting...")
    logger.info(f"Cities: {', '.join(CITIES)}")
    logger.info(f"Schedule: {', '.join(SCHEDULE_TIMES)} SAST daily")
    logger.info(f"Max posts/day: {MAX_POSTS_PER_DAY} | Max per city: {MAX_POSTS_PER_CITY_PER_DAY}")
    logger.info(f"Dedup: {DEDUP_DAYS} days | Platform: Facebook (Instagram auto-sync)")
    logger.info("=" * 60)

    start_scheduler()
    _update_next_run()

    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    logger.info(f"Starting Flask dashboard on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=debug)