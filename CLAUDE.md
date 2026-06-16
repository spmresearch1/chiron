# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core Purpose

This codebase contains tools for extracting and analyzing biotechnology/pharmaceutical pipeline data from regulatory filings and clinical trial registries.

## Key Scripts and Their Usage

### 1. biotech_pipeline_extractor.py
Extracts R&D/clinical pipeline information from company 10-K filings via FNTK Pro API.

```bash
# Fetch pipeline for a single ticker
python3 biotech_pipeline_extractor.py MRNA

# Multiple tickers
python3 biotech_pipeline_extractor.py MRNA REGN
```

Output: Creates timestamped .txt files (e.g., `MRNA_2026-05-22.txt`) with extracted pipeline data.

### 2. groq_parse_test.py
Parses extracted pipeline text using Groq AI to structure data into JSON format with molecule names, indications, and trial details.

```bash
# Parse pipeline for a ticker (fetches and parses)
python3 groq_parse_test.py --ticker MRNA
```

### 3. scripts/ctgov_studies.py
Queries ClinicalTrials.gov v2 API to track clinical trials by sponsor, collaborator, or search terms.

```bash
# Single study lookup
python3 scripts/ctgov_studies.py NCT06018753

# Search by sponsor
python3 scripts/ctgov_studies.py --mode sponsor "Tempus AI"

# Save and diff snapshots
python3 scripts/ctgov_studies.py --mode sponsor "Company Name" --save-snapshot snapshots/
python3 scripts/ctgov_studies.py --mode sponsor "Company Name" --diff snapshots/previous_snapshot.json
```

## Environment Configuration

Required API keys in `.env`:
- `API_KEY`: FNTK Pro API key for accessing 10-K filings
- `GROQ_KEY`: Groq API key for AI-powered text parsing

## Data Flow

1. **Extract**: Use `biotech_pipeline_extractor.py` to fetch pipeline data from 10-K filings
2. **Parse**: Use `groq_parse_test.py` to structure extracted text into JSON
3. **Track**: Use `ctgov_studies.py` to monitor clinical trial updates and changes

## Output Files

- Pipeline extracts: Root directory as `{TICKER}_{DATE}.txt`
- Clinical trial snapshots: `snapshots/` directory as JSON files