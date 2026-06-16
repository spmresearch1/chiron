#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Biotech Pipeline Extractor
-------------------------
Asks for a ticker and retrieves the company's biotech/pharma pipeline as presented
in the most recent 10-K, using the FNTK Pro API.

Environment:
  Create a .env file next to this script with:
    API_KEY="your_api_key_here"
  You may also set FNTK_BASE (default: https://fntkpro.com)

Usage:
  pip install requests python-dotenv
  python biotech_pipeline_extractor.py [TICKER ...]

Examples:
  python biotech_pipeline_extractor.py MRNA
  python biotech_pipeline_extractor.py MRNA REGN
  python biotech_pipeline_extractor.py "MRNA,REGN"
  python biotech_pipeline_extractor.py  # Will prompt for ticker
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    # Optional dependency. Script works without it if env vars are already set.
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs) -> bool:  # type: ignore
        return False

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

# Load environment variables
load_dotenv()

DEFAULT_BASE = os.getenv("FNTK_BASE", "https://fntkpro.com")
DEFAULT_KEY = os.getenv("API_KEY", "").strip()
TIMEOUT = 180

PIPELINE_QUESTION = """From the company's most recent 10-K filing, extract the R&D / clinical / product pipeline exactly as presented in the filing.

Please preserve the original structure and presentation:
- If the pipeline is shown as a table, reproduce the table with aligned columns.
- If the pipeline is shown as bullet points or by platform/modality/phase, reproduce that structure.
- Include the molecule/candidate/program names and their associated indications (and phase/status if shown).

IMPORTANT:
- Molecule or program names often appear in the format ABC-1234 or ABC - 1234.
- Preserve molecule names EXACTLY as written in the filing, including hyphens, spaces, or numbering.
- Do NOT normalize, rename, or paraphrase molecule identifiers.
- If a molecule name includes a dash, number, or code, reproduce it verbatim.

Do not convert the output into JSON or any other schema. Just return the pipeline as presented. If no pipeline is provided in the 10-K, say "No pipeline presented in the 10-K.".
"""


def ask_10k_question(base: str, ticker: str, question: str, api_key: str) -> str:
    """
    Ask a question about a company's 10-K filing.

    Args:
        base: Base URL for the API
        ticker: Stock ticker symbol
        question: Question to ask
        api_key: API key for authentication

    Returns:
        Response text from the API
    """
    if requests is None:  # pragma: no cover
        raise RuntimeError("Missing dependency: requests (install with `pip install requests`).")

    url = f"{base}/ask-10k-question"
    payload = {"ticker": ticker.upper(), "question": question, "api_key": api_key}

    try:
        response = requests.post(url, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "") if isinstance(data, dict) else ""
    except requests.exceptions.Timeout:
        return "[ERROR] Request timed out"
    except requests.exceptions.RequestException as e:
        return f"[ERROR] Request failed: {e}"
    except Exception as e:
        return f"[ERROR] Unexpected error: {e}"


def get_pipeline(ticker: str) -> str:
    """
    Fetch the biotech/pharma pipeline for `ticker` from the most recent 10-K, save it to a
    local .txt file (like `main()` does), and return the extracted text.

    This function is intended for importing into other scripts (no prompts, no sys.exit).
    """
    api_key = DEFAULT_KEY
    if not api_key:
        raise ValueError("No API key provided. Set API_KEY in .env or environment variable.")

    t = (ticker or "").strip().upper()
    if not t:
        raise ValueError("Ticker symbol is required.")

    request_date = datetime.now().date().isoformat()
    out_dir = Path.cwd()

    result = ask_10k_question(DEFAULT_BASE, t, PIPELINE_QUESTION, api_key)

    # Save response to local .txt file named after ticker + request date.
    safe_ticker = "".join(ch for ch in t if ch.isalnum() or ch in ("-", "_", "."))
    if not safe_ticker:
        safe_ticker = "TICKER"

    base_name = f"{safe_ticker}_{request_date}.txt"
    out_path = out_dir / base_name
    if out_path.exists():
        # Avoid overwriting prior runs from the same day.
        ts = datetime.now().strftime("%H%M%S")
        out_path = out_dir / f"{safe_ticker}_{request_date}_{ts}.txt"

    out_path.write_text(result + ("\n" if not result.endswith("\n") else ""), encoding="utf-8")
    return result


def main() -> None:
    """Main function to run the application."""
    parser = argparse.ArgumentParser(
        description="Extract biotech/pharma pipeline as presented in the most recent 10-K filing"
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        help="Ticker symbol(s), e.g. MRNA or MRNA REGN (comma-separated also supported)",
    )
    args = parser.parse_args()

    # Get API key
    api_key = DEFAULT_KEY
    if not api_key:
        print("ERROR: No API key provided. Set API_KEY in .env or environment variable.")
        sys.exit(1)

    # Get tickers from command line or user input
    if args.tickers:
        raw = " ".join(args.tickers)
    else:
        raw = input("Enter ticker symbol(s) (comma or space separated): ").strip()

    tickers = [t.strip().upper() for t in raw.replace(",", " ").split() if t.strip()]
    if not tickers:
        print("ERROR: At least one ticker symbol is required.")
        sys.exit(1)

    for i, ticker in enumerate(tickers, start=1):
        print(f"\n[{i}/{len(tickers)}] Fetching pipeline for {ticker} from most recent 10-K...")
        print("=" * 80)
        result = get_pipeline(ticker)
        print(result)

        print("=" * 80)


if __name__ == "__main__":
    main()

