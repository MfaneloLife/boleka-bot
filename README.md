# 🇿🇦 E-BOLEKA Marketplace Bot v2.0

Automated social media bot that promotes **eboleka.co.za** listings across South Africa.
Posts **3 times per day** directly to the **E-BOLEKA Facebook Page** using Meta Graph API
system user credentials.

---

## 🎯 Mission

1. **Get more users to list items for FREE** on eboleka.co.za across South Africa
2. **Advertise items already available** on eboleka.co.za nationally

---

## 🎯 National Targeting (single market)

Every post targets a **national South Africa audience** as one market. Posts are **not**
segmented by individual cities or townships.

- **3 posts per day** consistently

---

## ⏰ Schedule (SAST)

Runs automatically **3 times per day**:
- 08:00
- 13:00
- 18:00

---

## 🧠 High-Converting Post Structure

Every generated post follows this proven ad layout:

- **Primary Text** — a hook that highlights a pain point and introduces the solution immediately
- **Headline** — a bold, punchy call-to-action or value highlight
- **Description** — a short clarifying subtext expanding the benefit

And the **4 pillars** of every post:

1. **High-contrast visuals** (auto-enhanced before publishing) or clean product layouts
2. **A clear value proposition** showing instant utility
3. **Before/after or side-by-side comparison** where relevant
4. **An OFFER** — a clear incentive, discount or direct action prompt

---

## 📁 Project Structure

```
boleka-bot/
├── app.py              # Main Flask app + scheduler + dashboard
├── scraper.py          # Scrapes eboleka.co.za for listings & categories
├── ai.py               # DeepSeek AI post generator (SA tone, emojis, hashtags)
├── social.py           # Facebook Graph API poster
├── images.py           # Image handler (eboleka + Unsplash)
├── templates/
│   └── dashboard.html  # Clean mobile-friendly web dashboard
├── images/             # Downloaded images (cleaned after posting)
├── requirements.txt    # Python dependencies
├── Procfile            # Render.com process definition
├── .env.example        # Environment variables template
└── README.md           # This file
```

---

## 🚀 Deploy to Render.com (Free Tier)

### Step 1: Fork/Clone This Repository

Push this code to a **GitHub repository**.

### Step 2: Create a Render.com Account

Go to [render.com](https://render.com) and sign up (free). Connect your GitHub account.

### Step 3: Create a New Web Service

1. Click **"New +"** → **"Web Service"**
2. Select your GitHub repository
3. Configure:
   - **Name**: `boleka-bot` (or any name you like)
   - **Runtime**: `Python 3`
   - **Region**: `Frankfurt` (closest to South Africa)
   - **Branch**: `main` (or your default branch)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Choose **Free** instance type

### Step 4: Set Environment Variables

In your Render dashboard, go to **Environment** and add these variables:

| Variable | Description | Where to Get It |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek AI API key | [platform.deepseek.com](https://platform.deepseek.com) |
| `FB_SYSTEM_USER_ACCESS_TOKEN` | Meta Business Manager System User Access Token | Meta Business Manager → System Users |
| `FB_PAGE_ID` | E-BOLEKA Facebook Page ID | Facebook Page → About |
| `UNSPLASH_ACCESS_KEY` | Unsplash API key | [unsplash.com/developers](https://unsplash.com/developers) |
| `FLASK_SECRET` | Random string for Flask sessions | Generate any random string |

### Step 5: Deploy

Click **"Create Web Service"**. Render will build and deploy your app.

> ⚠️ **Important**: Render Free tier services **spin down after 15 minutes of inactivity**. The scheduler runs in a background thread and will only work while the service is active. For the scheduler to run reliably 24/7, consider using a **Cron Job** service (see below) or upgrade to a paid Render plan.

### Step 6: Keep the Scheduler Alive (Free Tier)

Since Render free tier sleeps after inactivity, use an **external cron job** to ping your dashboard every 5 minutes:

1. Go to [cron-job.org](https://cron-job.org) (free)
2. Create a cron job that pings: `https://your-app-name.onrender.com/`
3. Set interval to **every 5 minutes**
4. This keeps the service awake so the scheduler runs on time

---

## 🔗 Facebook + Instagram Auto-Sync Setup

1. Go to [Meta Business Suite](https://business.facebook.com/)
2. Navigate to **Settings** → **Linked Accounts** → **Instagram**
3. Link your Instagram professional account to your Facebook Page
4. Enable **auto-share** from Facebook to Instagram
5. **No IG username/password needed** — posts appear automatically on Instagram

---

## 🔑 Getting API Keys

### DeepSeek API Key
1. Go to [platform.deepseek.com](https://platform.deepseek.com)
2. Sign up / log in
3. Go to **API Keys** → **Create new key**
4. Copy the key (starts with `sk-`)

### Meta System User Access Token
1. Go to [business.facebook.com](https://business.facebook.com) → **Business settings** → **System users**
2. Create a System User and assign it the **Admin** role on your Facebook app
3. Add the System User to the **E-BOLEKA Page** with `pages_manage_posts` and `pages_read_engagement`
4. In **System users**, generate a **long-lived access token**
5. Copy it into `FB_SYSTEM_USER_ACCESS_TOKEN`

### Facebook Page ID
1. Go to your Facebook Page
2. Click **About** → **Page Transparency**
3. Copy the **Page ID** number

### Unsplash API Access Key
1. Go to [unsplash.com/developers](https://unsplash.com/developers)
2. Register a new application
3. Copy the **Access Key** (not Secret Key)

---

## 🖥️ Local Development

### Prerequisites
- Python 3.10+
- pip

### Setup

```bash
# Clone the repo
cd boleka-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Edit .env with your actual API keys
nano .env

# Run the bot
python app.py
```

Visit **http://localhost:5000** for the dashboard.

### Running with Gunicorn (production-like)

```bash
gunicorn app:app --bind 0.0.0.0:5000
```

---

## 📊 Web Dashboard

The dashboard at `/` shows:
- Posts today counter
- Last run / Next run times
- City-by-city post counts
- **Run Now** button to trigger a manual cycle
- **Test Post** dropdown to test a post for any city
- Live scrolling logs
- Mobile-friendly dark theme

---

## 📝 Post Types

### Type A — Call to List
Asks people **across South Africa** who have a specific category of items to list them FREE on E-BOLEKA.
> "🔥 STOP LETTING YOUR STUFF COLLECT DUST — EARN TODAY. Still storing tents you barely use while cash is tight? List FREE on E-BOLEKA and turn clutter into income in minutes. 🎁 List FREE today — no fees and you keep 100% of your earnings."

### Type B — New Listing Promotion
Promotes a newly scraped listing from eboleka.co.za to a national audience.
> "🔥 HOT FIND — GRAB IT BEFORE IT'S GONE. Tired of endless searching and overpaying? We just found it for you on E-BOLEKA. 🎁 DM now to secure it — first come, first served."

---

## 🧹 Logs

All actions are logged to `logs.txt` in the format:
```
2024-01-15 08:00:05 | Johannesburg | Facebook | Type A: Tents | SUCCESS | 12345_67890
```

The dashboard also shows live in-memory logs (last 200 entries).

---

## ⚠️ Rate Limits

- **Exactly 3 posts per day** — one per scheduled slot (08:00, 13:00, 18:00 SAST)
- **3-day dedup** — the same category/item is not repeated within 3 days

---

## 🛠️ Tech Stack

- **Python 3.10+** — Core language
- **Flask** — Web dashboard & API
- **schedule** — Job scheduling
- **requests + BeautifulSoup4** — Web scraping eboleka.co.za
- **OpenAI SDK** — DeepSeek AI integration
- **requests** — Facebook Graph API posting (Meta system user credentials)
- **Pillow** — Image optimization
- **python-dotenv** — Environment variable management
- **gunicorn** — WSGI production server

---

## 📄 License

MIT — Use freely for your marketplace.

---

## 🤝 Support

For issues, check the logs on your Render dashboard or the web dashboard at `/`.

---

Made with ❤️ for South African hustlers 🇿🇦