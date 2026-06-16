#!/usr/bin/env python3
"""Query ClinicalTrials.gov v2 API with rich field modules and multiple search strategies.

Supports three search modes for tracking trial constellations:
  sponsor  — query.spons  (all trials sponsored by an entity)
  term     — query.term   (full-text search across protocol text)
  collab   — AREA[CollaboratorFullName] search
  nctid    — single study lookup by NCT ID (returns full protocolSection)

Pagination is automatic — all matching studies are fetched.
Snapshots can be saved and diffed to surface quarterly changes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://clinicaltrials.gov/api/v2/studies"

# The search endpoint requires top-level section names (not individual modules).
# "protocolSection" returns all modules: identification, status, sponsor/collaborators,
# description, conditions, design, eligibility, outcomes, contacts/locations, arms/interventions.
FIELDS_DEFAULT = "protocolSection"

PAGE_SIZE_DEFAULT = 50


def _ssl_context(insecure: bool) -> ssl.SSLContext | None:
    if not insecure:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch_json(url: str, context: ssl.SSLContext | None) -> dict:
    with urllib.request.urlopen(url, context=context) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_all_pages(url: str, context: ssl.SSLContext | None) -> list[dict]:
    """Paginate through all results, following nextPageToken."""
    studies: list[dict] = []
    page_url = url
    while page_url:
        data = _fetch_json(page_url, context)
        studies.extend(data.get("studies", []))
        token = data.get("nextPageToken")
        if token:
            sep = "&" if "?" in url else "?"
            page_url = f"{url}{sep}pageToken={urllib.parse.quote(token)}"
        else:
            page_url = ""
    return studies


def _build_search_url(params: list[tuple[str, str]], fields: str, page_size: int) -> str:
    all_params = params + [
        ("fields", fields),
        ("pageSize", str(page_size)),
    ]
    return f"{API_BASE}?{urllib.parse.urlencode(all_params)}"


def search_by_sponsor(sponsor: str, fields: str, page_size: int) -> str:
    return _build_search_url([("query.spons", sponsor)], fields, page_size)


def search_by_term(term: str, fields: str, page_size: int) -> str:
    return _build_search_url([("query.term", term)], fields, page_size)


def search_by_collaborator(name: str, fields: str, page_size: int) -> str:
    term = f'AREA[CollaboratorFullName]{name}'
    return _build_search_url([("query.term", term)], fields, page_size)


def fetch_single_study(nct_id: str, context: ssl.SSLContext | None) -> dict:
    url = f"{API_BASE}/{urllib.parse.quote(nct_id)}?fields=protocolSection"
    return _fetch_json(url, context)


# ---------------------------------------------------------------------------
# Snapshot diffing
# ---------------------------------------------------------------------------

def _nct_id_from_study(study: dict) -> str:
    """Extract NCT ID from a study object."""
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    return ident.get("nctId", "unknown")


def _study_summary(study: dict) -> dict:
    """Extract a comparable summary from a study for diffing."""
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    sponsor = proto.get("sponsorCollaboratorsModule", {})
    locations = proto.get("contactsLocationsModule", {})
    site_list = locations.get("locations", [])
    collabs = sponsor.get("collaborators", [])
    return {
        "nctId": ident.get("nctId", ""),
        "briefTitle": ident.get("briefTitle", ""),
        "overallStatus": status.get("overallStatus", ""),
        "phase": (proto.get("designModule", {}).get("phases") or [""])[0] if proto.get("designModule", {}).get("phases") else "",
        "leadSponsor": sponsor.get("leadSponsor", {}).get("name", ""),
        "collaborators": [c.get("name", "") for c in collabs],
        "siteCount": len(site_list),
    }


def save_snapshot(studies: list[dict], snapshot_dir: str, label: str) -> str:
    path = Path(snapshot_dir)
    path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = path / f"{label}_{ts}.json"
    with open(fname, "w") as f:
        json.dump(studies, f, indent=2, ensure_ascii=False)
    return str(fname)


def diff_snapshots(old_path: str, new_studies: list[dict]) -> dict:
    """Compare new studies against a saved snapshot. Returns a diff summary."""
    with open(old_path) as f:
        old_studies = json.load(f)

    old_by_id = {_nct_id_from_study(s): _study_summary(s) for s in old_studies}
    new_by_id = {_nct_id_from_study(s): _study_summary(s) for s in new_studies}

    added = [new_by_id[k] for k in new_by_id if k not in old_by_id]
    removed = [old_by_id[k] for k in old_by_id if k not in new_by_id]

    changed = []
    for nct_id in set(old_by_id) & set(new_by_id):
        old_s, new_s = old_by_id[nct_id], new_by_id[nct_id]
        diffs = {k: {"old": old_s[k], "new": new_s[k]} for k in old_s if old_s[k] != new_s[k]}
        if diffs:
            changed.append({"nctId": nct_id, "changes": diffs})

    return {"added": added, "removed": removed, "changed": changed}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_stdin_prompt(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Query ClinicalTrials.gov v2 API with rich field modules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
search modes:
  sponsor   query.spons search (e.g. --mode sponsor "Tempus AI")
  term      query.term full-text (e.g. --mode term "Tempus xT OR Tempus xF")
  collab    AREA[CollaboratorFullName] (e.g. --mode collab "Tempus")
  nctid     single study by NCT ID (e.g. --mode nctid NCT06018753)
""",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Search query or NCT ID. If omitted, you'll be prompted.",
    )
    parser.add_argument(
        "--mode",
        choices=["sponsor", "term", "collab", "nctid"],
        default="term",
        help="Search mode (default: term).",
    )
    parser.add_argument(
        "--fields",
        default=os.environ.get("CTGOV_FIELDS", FIELDS_DEFAULT),
        help="Comma-separated field modules (env: CTGOV_FIELDS).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=int(os.environ.get("CTGOV_PAGE_SIZE", str(PAGE_SIZE_DEFAULT))),
        help=f"Results per page (env: CTGOV_PAGE_SIZE). Default: {PAGE_SIZE_DEFAULT}.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw JSON (no pretty formatting).",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification (not recommended).",
    )
    parser.add_argument(
        "--save-snapshot",
        metavar="DIR",
        help="Save results as a timestamped snapshot in DIR.",
    )
    parser.add_argument(
        "--diff",
        metavar="SNAPSHOT_FILE",
        help="Diff current results against a previous snapshot file.",
    )
    parser.add_argument(
        "--label",
        default="ctgov",
        help="Label prefix for snapshot filenames (default: ctgov).",
    )

    args = parser.parse_args(argv)

    query = (args.query or "").strip()
    if not query:
        query = _read_stdin_prompt("query: ").strip()
    if not query:
        print("Error: query is required.", file=sys.stderr)
        return 2

    context = _ssl_context(args.insecure)

    # Auto-detect NCT IDs so --mode nctid isn't required
    mode = args.mode
    if mode == "term" and re.fullmatch(r"NCT\d+", query, re.IGNORECASE):
        mode = "nctid"

    try:
        if mode == "nctid":
            data = fetch_single_study(query, context)
            studies = [data]
        else:
            if mode == "sponsor":
                url = search_by_sponsor(query, args.fields, args.page_size)
            elif mode == "collab":
                url = search_by_collaborator(query, args.fields, args.page_size)
            else:
                url = search_by_term(query, args.fields, args.page_size)
            studies = _fetch_all_pages(url, context)
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1

    # Diff against previous snapshot if requested
    if args.diff:
        try:
            diff_result = diff_snapshots(args.diff, studies)
            output = {
                "totalCurrent": len(studies),
                "diff": diff_result,
            }
        except Exception as e:
            print(f"Diff failed: {e}", file=sys.stderr)
            return 1
    else:
        output = {"totalStudies": len(studies), "studies": studies}

    # Save snapshot if requested
    if args.save_snapshot:
        snap_path = save_snapshot(studies, args.save_snapshot, args.label)
        print(f"Snapshot saved: {snap_path}", file=sys.stderr)

    # Output
    if args.raw:
        sys.stdout.write(json.dumps(output, ensure_ascii=False))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(json.dumps(output, indent=2, ensure_ascii=False))
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
