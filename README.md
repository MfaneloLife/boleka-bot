# 🇿🇦 Boleka SA Marketplace Bot v1.0

Automated social media bot that promotes **eboleka.co.za** listings across South Africa.
Posts to **Facebook Pages** — Instagram auto-syncs via Meta Account Center.

---

## 🎯 Mission

1. **Get more users to list items for FREE** on eboleka.co.za across South Africa
2. **Advertise items already available** on eboleka.co.za by city

---

## 🏙️ 9-City Rotation

Johannesburg → Pretoria → Cape Town → Durban → Bloemfontein → Port Elizabeth → East London → Polokwane → Rustenburg

- Max **2 posts per city per day**
- Max **20 posts total per day**

---

## ⏰ Schedule (SAST)

Runs automatically **4 times per day**:
- 08:00
- 12:00
- 16:00
- 20:00

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
| `FB_PAGE_ACCESS_TOKEN` | Facebook Page access token | Facebook Developer Console |
| `FB_PAGE_ID` | Facebook Page ID | Facebook Page → About |
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

### Facebook Page Access Token
1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Create a new app (type: **Business**)
3. Add **Facebook Login** and **Pages API** products
4. Go to **Graph API Explorer**
5. Select your app and **Page Access Token**
6. Grant permissions: `pages_manage_posts`, `pages_read_engagement`
7. Generate token and copy it

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
Asks people in a city who have a specific category of items to list them FREE on Boleka.co.za.
> "📢 Who in Johannesburg has Tents & Camping Gear to rent or sell? 💰 List it for FREE on Boleka.co.za and make money this week! 🚀"

### Type B — New Listing Promotion
Promotes a newly scraped listing from eboleka.co.za.
> "🆕 NEW in Cape Town! 🔥 DJ Sound System for R2,500 on Boleka.co.za. DM to buy! 🏃‍♂️💨"

---

## 🧹 Logs

All actions are logged to `logs.txt` in the format:
```
2024-01-15 08:00:05 | Johannesburg | Facebook | Type A: Tents | SUCCESS | 12345_67890
```

The dashboard also shows live in-memory logs (last 200 entries).

---

## ⚠️ Rate Limits

- **Max 2 posts per city per day** — prevents spamming
- **Max 20 posts total per day** — stays within Facebook API limits
- **2-second delay between posts** — avoids rate limiting

---

## 🛠️ Tech Stack

- **Python 3.10+** — Core language
- **Flask** — Web dashboard & API
- **schedule** — Job scheduling
- **requests + BeautifulSoup4** — Web scraping eboleka.co.za
- **OpenAI SDK** — DeepSeek AI integration
- **facebook-sdk** — Facebook Graph API posting
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