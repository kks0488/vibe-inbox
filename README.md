# 📧 Gmail Organizer

**AI-powered Gmail organization tool** - Google Gemini AI **reads your email content** and classifies them automatically.

[한국어 문서 (Korean)](README.ko.md)

## ✨ Features

- 🤖 **Content-based AI Classification**: Analyzes **email body content**, not just sender
- 🏷️ **Auto Labeling**: Automatically applies Gmail labels based on classification
- 📦 **Smart Archiving**: Archives marketing/promotional emails (even from trusted domains!)
- 🛡️ **Trusted Sender Management**: Whitelist support for important senders
- 📊 **Statistics & Summary**: Detailed classification statistics
- ⏰ **Auto Scheduler**: Background execution via systemd service

## 📂 Classification Categories (4)

| Category | Description | Examples | Action |
|----------|-------------|----------|--------|
| 📌 **IMPORTANT** | Directly relevant to me | Payment confirmations, password resets, shipping notifications, replies to my posts | Keep |
| 📧 **NORMAL** | General service notifications | GitHub PRs, Slack alerts, monthly reports | Keep |
| 📰 **INFO** | Mass marketing/newsletters | Discount promos, follow suggestions, trend reports | **Archive** |
| 🚫 **SPAM** | Malicious/scam emails only | Phishing, cold sales, unknown ads | Spam folder |

### Key Differentiator

```
❌ Traditional: Email from Google → Always important
✅ This tool:   Google payment alert → Important / Google promo → Archive
```

| Email Example | Traditional | Gmail Organizer |
|---------------|-------------|-----------------|
| LinkedIn comment notification | Important | ✅ Important |
| LinkedIn "follow this person" | Important | 📦 Archive |
| Steam wishlist sale | Normal | 📦 Archive |
| Coupang payment complete | Normal | ✅ Important |

---

## 🚀 Installation

### 1. Requirements

- Python 3.9+
- Google Cloud Account
- Gemini API Key

### 2. Install Dependencies

```bash
cd gmail-organizer
pip install -r requirements.txt
```

### 3. Google Cloud Setup (Gmail API)

Gmail API requires OAuth 2.0 authentication.

#### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one

#### Step 2: Enable Gmail API

1. Navigate to "APIs & Services" → "Library"
2. Search for "Gmail API"
3. Click "Enable"

#### Step 3: Configure OAuth Consent Screen

1. Go to "APIs & Services" → "OAuth consent screen"
2. Select "External" (for testing)
3. Enter app name and email
4. Add scopes:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`
   - `https://www.googleapis.com/auth/gmail.labels`
5. Add your email as a test user

#### Step 4: Create OAuth 2.0 Client ID

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: "Desktop app"
4. Enter a name and click "Create"
5. Click **Download JSON**
6. Rename the downloaded file to `credentials.json`
7. Place `credentials.json` in the project folder

### 4. Gemini API Key Setup

1. Get an API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create `.env` file:

```bash
cp env_example.txt .env
```

3. Edit `.env` file:

```
GEMINI_API_KEY=your_api_key_here
GMAIL_CREDENTIALS_PATH=credentials.json
```

---

## 📖 Usage

### Interactive Menu (Recommended)

```bash
python main.py
```

### CLI Commands

```bash
# Check status
python main.py status

# Gmail authentication
python main.py auth

# Analyze emails (classify only, no changes)
python main.py analyze -n 50

# Organize emails (classify + apply labels)
python main.py organize -n 30

# Analyze with specific query
python main.py analyze -q "is:unread"

# Auto organize (no confirmation)
python main.py organize -n 50 -y

# Logout
python main.py logout
```

### Example: First Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the program
python main.py

# 3. Select "4. Gmail Authentication" from menu
# 4. Login to your Google account in browser
# 5. Check connection with "1. Check Status"
# 6. Test with "2. Analyze Emails"
# 7. Start organizing with "3. Organize Emails"
```

---

## 🔧 Configuration

Customize settings in `config.py`:

```python
# Change AI model
GEMINI_MODEL = "gemini-1.5-flash"  # Fast model
# GEMINI_MODEL = "gemini-1.5-pro"  # More accurate model

# Adjust batch size
DEFAULT_BATCH_SIZE = 50

# Max email content length
MAX_EMAIL_CONTENT_LENGTH = 2000

# Modify category actions
EMAIL_CATEGORIES = {
    "SPAM": {
        "action": "spam"  # Options: "spam", "archive", "keep"
    }
}
```

---

## ⚠️ Important Notes

### Security

- **Never hardcode passwords in the code**
- Add `credentials.json` and `token.json` to `.gitignore`
- Manage API keys via environment variables

### API Usage

- Gemini API has free quota limits (requests per minute)
- Processing many emails at once may hit API limits
- Adjust batch size to manage usage

### Gmail API

- Only high-confidence spam emails are moved to spam folder
- Labels are created with "AI/" prefix
- Delete functionality is disabled for safety

---

## 📁 Project Structure

```
gmail-organizer/
├── main.py              # Main executable
├── config.py            # Configuration
├── auth.py              # Gmail OAuth authentication
├── gmail_client.py      # Gmail API client
├── ai_classifier.py     # Gemini AI classifier
├── scheduler.py         # Auto scheduler
├── requirements.txt     # Dependencies
├── README.md            # This file
├── README.ko.md         # Korean documentation
├── env_example.txt      # Environment variable example
├── credentials.json     # OAuth credentials (add manually)
└── token.json           # Auth token (auto-generated)
```

---

## 🖥️ Ubuntu Server Deployment

### 1. Transfer Project Files

```bash
# Transfer from local to Ubuntu server
scp -r /path/to/gmail-organizer username@your-server:/home/username/
```

### 2. Run Install Script

```bash
# SSH connection
ssh username@your-server

# Run install script
cd ~/gmail-organizer
chmod +x install_ubuntu.sh
./install_ubuntu.sh
```

### 3. Authentication Setup (Important!)

⚠️ **OAuth authentication requires a browser.** Two options:

**Option A: Authenticate locally, then copy token.json (Recommended)**
```bash
# After completing authentication on local PC
scp token.json username@your-server:/home/username/gmail-organizer/
scp credentials.json username@your-server:/home/username/gmail-organizer/
scp .env username@your-server:/home/username/gmail-organizer/
```

**Option B: Use SSH port forwarding**
```bash
# SSH with port forwarding from local
ssh -L 8080:localhost:8080 username@your-server

# Run authentication on server
cd ~/gmail-organizer
source venv/bin/activate
python main.py auth
# Access the displayed URL in browser
```

### 4. Start Service

```bash
# Start service
sudo systemctl start gmail-organizer

# Enable auto-start on boot
sudo systemctl enable gmail-organizer

# Check status
sudo systemctl status gmail-organizer
```

### 5. Monitor Logs

```bash
# Real-time log monitoring
tail -f ~/gmail-organizer/logs/scheduler.log

# Service log
journalctl -u gmail-organizer -f
```

### 6. Scheduler Options

```bash
# Direct execution (for testing)
cd ~/gmail-organizer
source venv/bin/activate

# Default (60 min interval, auto organize)
python scheduler.py

# Custom options
python scheduler.py --interval 60 --batch-size 100  # 1 hour interval, 100 emails
python scheduler.py --analyze-only  # Analysis only (no organizing)
```

---

## 🐳 Docker

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f
```

---

## 🐛 Troubleshooting

### "credentials.json file not found"

- Create an OAuth client ID in Google Cloud Console and download the JSON file
- Make sure the file is named exactly `credentials.json`

### "Gemini API key required"

- Check that `GEMINI_API_KEY` is set in your `.env` file
- Verify the API key is valid

### "Token expired"

- Re-authenticate with `python main.py auth`
- Or delete `token.json` and authenticate again

### "API limit exceeded"

- Wait a moment and try again
- Reduce `DEFAULT_BATCH_SIZE` in `config.py`

---

## 📄 License

MIT License

---

## 🤝 Contributing

Bug reports, feature suggestions, and PRs are welcome!
