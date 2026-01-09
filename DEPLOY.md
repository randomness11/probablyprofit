# Deploy to GitHub

Your probablyprofit repository is ready to deploy! Follow these steps:

## Option 1: Using GitHub CLI (Recommended)

```bash
# Install GitHub CLI if you haven't (macOS)
brew install gh

# Login to GitHub
gh auth login

# Create repository and push
gh repo create probablyprofit --public --source=. --remote=origin --push

# Done! Your repo is now at https://github.com/YOUR_USERNAME/probablyprofit
```

## Option 2: Using GitHub Web Interface

### Step 1: Create Repository on GitHub

1. Go to https://github.com/new
2. Repository name: `probablyprofit`
3. Description: `AI-powered trading bot framework for Polymarket`
4. Set to **Public**
5. **Do NOT** initialize with README (we already have one)
6. Click "Create repository"

### Step 2: Push Your Code

```bash
# Add GitHub as remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/probablyprofit.git

# Push to GitHub
git branch -M main
git push -u origin main
```

## After Pushing

Your repository will be live at: `https://github.com/YOUR_USERNAME/probablyprofit`

### Recommended Next Steps

1. **Add repository description** on GitHub:
   - "AI-powered trading bot framework for Polymarket - inspired by a16z"

2. **Add topics** to help people discover your repo:
   - `polymarket`
   - `trading-bot`
   - `ai`
   - `claude`
   - `prediction-markets`
   - `crypto`
   - `a16z`
   - `python`

3. **Enable GitHub Actions** (optional):
   - Can add automated testing later

4. **Star your own repo** ⭐ to get started!

## Share It

Once deployed, share your repo:

```markdown
🚀 Just launched probablyprofit - an AI-powered framework for building Polymarket trading bots!

Define your trading strategy in natural language, and let Claude handle the decision-making.

✨ Features:
- Natural language strategy prompts
- Built-in risk management
- News & social signal integration
- Backtesting engine
- 3 working example bots

Check it out: https://github.com/YOUR_USERNAME/probablyprofit

Built with @AnthropicAI Claude 💙
```

---

**Note**: Make sure to update the repository URLs in `pyproject.toml` after creating the repo with your actual GitHub username!
