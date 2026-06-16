import os
import sys
import argparse
from pathlib import Path

from groq import Groq


def _load_dotenv(dotenv_path: Path) -> None:
    """
    Minimal .env loader (no external deps).
    """
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key in os.environ:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        os.environ[key] = value


def _find_dotenv() -> Path | None:
    candidates = [
        Path(__file__).resolve().parent / ".env",
        Path.cwd() / ".env",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def _prompt_for_txt_path() -> str:
    """
    Prompt user for a .txt file path and return its full contents.
    """
    while True:
        path_str = input("Enter path to .txt file (drag & drop works): ").strip().strip("'").strip('"')

        if not path_str:
            print("Empty path. Try again.", file=sys.stderr)
            continue

        path = Path(path_str).expanduser()
        if not path.exists() or not path.is_file():
            print("File not found. Try again.", file=sys.stderr)
            continue

        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Failed to read file: {e}", file=sys.stderr)


SYSTEM_PROMPT = (
    "You are a data extraction engine.\n"
    "You MUST output ONLY valid JSON matching the schema below.\n\n"
    "SCHEMA (required):\n"
    "{\n"

    '  "rows": [\n'
    "    {\n"
    '      "molecule": string | null,\n'
    '      "indication": string,\n'
    '      "study": string,\n'
    '      "treatment_population": string,\n'
    '      "regimen": string | null\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "EXTRACTION RULES:\n"
    "1) Each row must be self-contained. Do NOT assume a shared or parent molecule.\n"
    "2) Populate the molecule field ONLY if the molecule is explicitly stated or clearly implied for that row.\n"
    "3) Section headers (e.g. “X Trials”, “X Program”, “X Study”) apply ONLY to rows directly under that header.\n"
    "4) Do NOT propagate molecule names across unrelated rows.\n"
    "5) Preserve exact spelling and punctuation of molecule names.\n"
    "6) If a molecule cannot be confidently assigned to a row, set molecule=null.\n"
    "7) Extract regimen text even if it appears as bullets or prose outside a table.\n"
    "8) Output ONLY JSON. No explanations. No comments.\n"
)



def main() -> int:
    dotenv = _find_dotenv()
    if dotenv:
        _load_dotenv(dotenv)

    parser = argparse.ArgumentParser(
        description="Run Groq extraction against a fetched 10-K pipeline (prompts for ticker)."
    )
    parser.add_argument(
        "--ticker",
        help="If provided, fetch pipeline text for this ticker using biotech_pipeline_extractor.get_pipeline() and send it to Groq.",
    )
    args = parser.parse_args()

    api_key = os.getenv("GROQ_KEY")
    if not api_key:
        print("Missing GROQ_KEY in environment or .env file.", file=sys.stderr)
        return 2

    ticker = args.ticker
    if not ticker:
        ticker = input("Enter ticker symbol: ").strip()

    try:
        # Lazy import to avoid forcing extractor deps / import-time side effects unless needed.
        from biotech_pipeline_extractor import get_pipeline  # type: ignore
    except Exception as e:
        print(f"Failed to import get_pipeline from biotech_pipeline_extractor.py: {e}", file=sys.stderr)
        return 2

    try:
        user_content = get_pipeline(ticker)
    except Exception as e:
        print(f"Failed to fetch pipeline for {ticker}: {e}", file=sys.stderr)
        return 2

    if not user_content.strip():
        print("File is empty.", file=sys.stderr)
        return 2

    client = Groq(api_key=api_key)

    completion = client.chat.completions.create(
        model="qwen/qwen3-32b",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                # JSON anchor to match Playground behavior
                "role": "assistant",
                "content": '{ "molecule": null, "source_title": null, "rows": [] }',
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        temperature=1,
        top_p=1,
        max_completion_tokens=8192,
        stream=False,
    )

    print(completion.choices[0].message.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
