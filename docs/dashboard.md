# Dashboard

```bash
form4clean dashboard          # opens http://127.0.0.1:8765
form4clean dashboard --port 9000 --no-browser
```

The dashboard is served by the same local process as the API. There are no accounts; it binds to
127.0.0.1 so only your computer can reach it.

## Pages

| Page | What it shows |
|---|---|
| Overview | 12-month purchase and sale totals, share of sales under 10b5-1 plans, monthly purchases and sales, most active insiders, latest filings |
| Price Chart | Daily prices with insider markers, filters, and a panel listing the filings behind any marker |
| Transactions | Sortable, filterable table with column filters, column chooser, resizable columns, expandable rows and CSV/Parquet export |
| Data Quality | Pipeline counts, status distribution, missing values, every issue with its explanation and affected records, amendment links |
| Export | Filtered or full cleaned data, raw rows, the quality report or the manifest, as CSV, Parquet or JSON, optionally point-in-time |
| Settings | SEC contact email, request rate, price provider and key |

The filter bar is shared by the chart and the table, and filtering happens on the server, so
the markers, the table and any export always contain the same records.

## Chart markers

| Colour | Shape | Group |
|---|---|---|
| Green | arrow up | Purchase (P) |
| Red | arrow down | Sale (S) |
| Blue | circle | Derivative exercise or conversion |
| Purple | circle | Equity compensation (A) |
| Orange | square | Other (tax withholding, gifts, everything else) |

* Transactions of the same group on the same day are combined into one marker labelled with the
  code and count (`S×12`). Clicking it lists every underlying transaction.
* **Disclosure date (default)** plots each transaction on `disclosure_session_date`: the first
  regular session in which its filing was public. A filing accepted at 4:45 p.m. appears on the
  next day's candle, not the day of the trade.
* **Transaction date** plots the trade date, with a reminder that investors did not know about
  the trade until the filing date.
* Dates that fall on weekends or holidays move to the next session. Transactions outside the
  price history are not plotted, and the legend says how many.

## Price data

The SEC does not publish stock prices. Choose a provider in Settings:

| Provider | Cost | Notes |
|---|---|---|
| None (default) | Free | No price chart. Everything else works. |
| Tiingo | Free API key from [tiingo.com](https://www.tiingo.com) | End-of-day prices, cached locally for 12 hours |
| Yahoo Finance (optional) | Free, no key. Install with `pip install "form4clean[yfinance]"` | Uses Yahoo's unofficial feed through the community [yfinance](https://github.com/ranaroussi/yfinance) package. Not installed by default, and can break or be throttled when Yahoo changes its site. Prices are adjusted for splits. Cached locally for 12 hours |
| CSV | Free | Daily bars from `~/.form4clean/prices/TICKER.csv` (`date,open,high,low,close,volume`). Historical-data downloads from Nasdaq.com work as-is. |

Tiingo prices are used unadjusted, so chart prices line up with the per-share prices insiders
reported at the time; after a stock split the chart shows the jump. Yahoo adjusts every price
for splits, so before a split the chart sits below the prices insiders reported. CSV prices are drawn
exactly as they are in the file.

The chart states the provider and that data is end-of-day. If prices are missing or the provider
fails, the page says so; it never draws placeholder prices. To add a provider, subclass
`PriceProvider` in `src/form4clean/market_data/providers.py`.

The charting library is [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts)
(Apache 2.0), used only for drawing.

## Developing the frontend

```bash
cd frontend
npm install
npm run dev        # Vite on http://localhost:5173, proxies /api to port 8765
form4clean dashboard --no-browser   # in another terminal
npm test           # Vitest
npm run build      # writes ../src/form4clean/api/static
```
