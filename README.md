# Fast Dolphin · Lead Finder

Internal tool for finding LATAM contract leads on Dice.com. Searches for jobs posted in the last 3 days matching Latin America keywords (Mexico, Brazil, Colombia, Argentina, Chile, Panama, etc.) with Contract or Third Party employment types.

## Access

Live app: `https://<your-org>.github.io/dice-leads`

Only `@fastdolphin.com` email addresses can log in.

## How to use

1. Sign in with your Fast Dolphin email.
2. Click **"Pull fresh leads"** — the app queries Dice.com for the latest jobs.
3. Browse, sort, and filter the results table.
4. Click **"Export CSV"** to download leads for outreach.

Results are cached locally so you can refresh the page without re-running the scrape.

## Setup (one-time, for admins)

### 1. Create the repo

```bash
gh repo create fastdolphin/dice-leads --private
cd dice-leads
git init
git remote add origin git@github.com:fastdolphin/dice-leads.git
```

### 2. Push the code

```bash
git add .
git commit -m "Initial commit"
git push -u origin main
```

### 3. Enable GitHub Pages

- Go to **Settings → Pages** in the repo
- Under **Source**, select **GitHub Actions**
- The first push will trigger a deploy automatically

### 4. Update the homepage URL

In `package.json`, update the `homepage` field:
```json
"homepage": "https://fastdolphin.github.io/dice-leads"
```

## Keywords tracked

Mexico · Brazil · Colombia · Argentina · Chile · Latin America · Spanish · LATAM · Bolivia · Peru · Costa Rica · Panama · Ecuador · Portuguese · Maquiladora · Corp to Corp

## Employment types targeted

Contract · Third Party · Corp to Corp · C2C

## Tech stack

- React 18 (Create React App)
- GitHub Pages (free hosting)
- No backend — runs entirely in the browser
- Results cached in localStorage between sessions
