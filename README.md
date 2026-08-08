# Daily Stock Value Tracker Data

Fetches standardized daily quotes for mainland China, Hong Kong and US indices,
gold, copper, crude oil, Muyuan Foods and Zijin Mining. Mainland indices use
AKShare first (including the two A-share stocks) and automatically fall back to
yfinance. A future Tushare adapter can use the same loader boundary without
changing the JSON schema; keep its token in GitHub Actions Secrets, never in the
repository or output.

## Run locally

```bash
python -m pip install -r requirements.txt
python fetch_market.py
```

Output: `data/latest.json`.

## Cloud schedule and public URL

GitHub Actions runs at 07:10 Asia/Shanghai each Monday-Friday and can also be
started from **Actions > Daily market data > Run workflow**. In repository
settings, select **Pages > Source > GitHub Actions** once.

After deployment, the JSON URL is:

```text
https://<github-user>.github.io/<repository>/latest.json
```

No tokens, usernames, email addresses or other personal data are written into
the JSON. Tushare can be added later as another loader; it is intentionally not
enabled because it requires a private API token.
