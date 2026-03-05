# Yuhdash

Portfolio analytics dashboard for [Yuh](https://www.yuh.com) — the Swiss investment app. Upload your transaction CSV and get a full breakdown of your P&L, fees, asset allocation, and performance history.

---

## Features

- **Multi-format CSV support** — works with both the standard Yuh export and the crypto transactions format
- **P&L breakdown** — realized vs unrealized gains per asset, with and without fees
- **Trading console UI** — color-coded table (green/red) for instant performance reading
- **Asset details** — per-asset metrics: avg buy price, current price, cost basis, value, and P&L %
- **Interactive charts** — portfolio composition, P&L by asset, performance %, and value evolution over time
- **Date range filter** — analyze any time window within your transaction history
- **Live price lookup** — fetches current prices via Yahoo Finance (yfinance) as fallback for assets in your CSV
- **Supports ETFs, stocks, and crypto** — auto-detects asset type with appropriate icons

## Screenshots

> Upload your CSV → get instant analytics

| Section | Description |
|---|---|
| Portfolio Overview | Portfolio value, Unrealized P&L, Gross P&L, NET P&L |
| Secondary stats | Total invested, assets held, realized P&L, fees paid |
| Breakdown table | Per-asset table with color-coded P&L columns |
| Asset Details | Expandable cards with cost basis, prices, and P&L % deltas |
| Charts | Composition (donut), P&L bars, performance %, timeline |

## Running locally

```bash
# Clone the repo
git clone https://github.com/cripsisxyz/yuhdash.git
cd yuhdash

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
streamlit run app.py
```

App opens at `http://localhost:8501`

## Requirements

```
streamlit>=1.31.0
pandas>=2.0.0
plotly>=5.18.0
yfinance>=0.2.40
requests>=2.31.0
```

## CSV format

### Standard Yuh export

Download from the Yuh app under **Transactions → Export CSV**.

Expected columns:

| Column | Description |
|---|---|
| `ACTIVITY TYPE` | `INVEST_ORDER_EXECUTED`, `INVEST_RECURRING_ORDER_EXECUTED`, `INVEST_SELL_EXECUTED` |
| `ACTIVITY NAME` | Asset description (e.g. `7.2737x Silver (Swisscanto Silver)`) |
| `DEBIT` | Amount debited (purchase cost) |
| `CREDIT` | Amount credited (sale proceeds) |
| `FEES/COMMISSION` | Brokerage fee |
| `BUY/SELL` | `BUY` or `SELL` |
| `QUANTITY` | Number of units |
| `ASSET` | Ticker symbol (e.g. `EQQQ`, `CSSMI`, `BTC`) |
| `PRICE PER UNIT` | Execution price |
| `DATE` | Transaction date |

### Crypto transactions format

Also supported — uses the Yuh crypto CSV columns (`Transaction type`, `Asset`, `Eur (amount)`, etc.). The app auto-detects the format on upload.

## How P&L is calculated

- **Realized P&L** — calculated on each SELL using the average cost basis of prior BUYs
- **Unrealized P&L** — `(last known price × current quantity) − cost basis`
- **Gross P&L** — realized + unrealized
- **NET P&L** — gross P&L minus all fees paid
- **Current price** — taken from the last transaction price in your CSV; falls back to Yahoo Finance via `yfinance`

## Tech stack

- [Streamlit](https://streamlit.io) — UI framework
- [Pandas](https://pandas.pydata.org) — data processing
- [Plotly](https://plotly.com/python) — interactive charts
- [yfinance](https://github.com/ranaroussi/yfinance) — live price fallback

## License

MIT
