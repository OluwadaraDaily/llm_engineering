---
title: Paper Equity Trading Dashboard
emoji: chart_with_upwards_trend
colorFrom: gray
colorTo: blue
sdk: gradio
sdk_version: 5.47.2
app_file: app.py
pinned: false
license: mit
---

# Paper Equity Trading Dashboard

This folder is ready to upload to a Hugging Face Gradio Space.

## Deploy

1. Create a free Hugging Face account.
2. Create a new Space at `https://huggingface.co/new-space`.
3. Choose:
   - SDK: `Gradio`
   - Hardware: free CPU is enough for testing
   - Visibility: private while testing, public when ready
4. Upload the files in this folder:
   - `app.py`
   - `requirements.txt`
   - `README.md`
5. In the Space settings, add these as **Secrets**:
   - `APCA_API_KEY_ID`
   - `APCA_API_SECRET_KEY`
   - `OPENAI_API_KEY`
6. Add these optional **Variables** or **Secrets**:
   - `APCA_API_BASE_URL=https://paper-api.alpaca.markets`
   - `APCA_DATA_BASE_URL=https://data.alpaca.markets`
   - `OPENAI_MODEL=gpt-5-mini`
   - `ALLOW_LIVE_TRADING=false`
   - `APP_USERNAME=<username>`
   - `APP_PASSWORD=<password>`

Set `APP_USERNAME` and `APP_PASSWORD` to put a basic password screen in front of the app.

## Safety Notes

- Use Alpaca paper-trading credentials for public testing.
- Do not add live Alpaca keys to a public Space.
- Keep `ALLOW_LIVE_TRADING=false` unless you intentionally modify and audit the app for live trading.
- The app can submit paper orders, including from the agentic trading tab when explicitly enabled.

## Update From Notebook

The deployed `app.py` was generated from `../buy_sell_equities.ipynb`, but notebook-only test cells were intentionally skipped. If you update the notebook, regenerate `app.py` from the reusable setup/function/UI cells and keep immediate API smoke-test calls out of the import path.
