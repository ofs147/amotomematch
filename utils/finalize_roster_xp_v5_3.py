"""Integrity-gated Roster XP Final Write and master-status synchronization."""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from utils.bulk_expansion_v3 import bulk_final_write, load_bulk_final_write_inputs


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def execute_roster_xp_final_write(*, data_dir: Path, approved_path: Path,
                                  draft_path: Path, qa_path: Path) -> dict[str, int]:
    approved_ids, draft, qa = load_bulk_final_write_inputs(
        approved_path=approved_path, draft_path=draft_path, qa_path=qa_path)
    blocked = {cid for cid, status in qa["statuses"].items() if status == "BLOCKED"}
    if approved_ids & blocked:
        raise ValueError("Approved IDs contain BLOCKED characters")

    character_path = data_dir / "characters_v2_candidate.csv"
    metadata_path = data_dir / "characters_v2_candidate_metadata.csv"
    master_path = data_dir / "characters_master.csv"
    appearance_path = data_dir / "character_game_appearances.csv"
    games_path = data_dir / "games_master.csv"

    before = _read_csv(character_path)
    if approved_ids & {row["character_id"] for row in before}:
        raise ValueError("Approved IDs already exist in the XP database")
    master = _read_csv(master_path)
    master_by_id = {row["character_id"]: row for row in master}
    if not approved_ids <= set(master_by_id):
        raise ValueError("Approved IDs missing from characters_master")
    appearances = _read_csv(appearance_path)
    appeared = {row["character_id"] for row in appearances}
    if not approved_ids <= appeared:
        raise ValueError("Approved IDs missing character_game_appearances")
    game_ids = {row["game_id"] for row in _read_csv(games_path)}
    if any(row["game_id"] not in game_ids for row in appearances if row["character_id"] in approved_ids):
        raise ValueError("Approved appearance references an unknown game_id")

    tier_by_id = {item["character_id"]: item["annotation_tier"] for item in draft["characters"]}
    for cid in approved_ids:
        master_by_id[cid]["xp_annotation_status"] = (
            "reviewed_lite" if tier_by_id[cid] == "B" else
            "candidate_only" if tier_by_id[cid] == "C" else
            "human_reviewed_gold"
        )

    # Prepare the master replacement before mutating either production XP file.
    fields = list(master[0])
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", delete=False,
                                     dir=master_path.parent) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(master)
        master_temp = Path(handle.name)

    written = bulk_final_write(
        approved_ids=approved_ids, draft=draft, qa=qa,
        character_path=character_path, metadata_path=metadata_path)
    if written != len(approved_ids):
        master_temp.unlink(missing_ok=True)
        raise RuntimeError(f"Expected {len(approved_ids)} writes, got {written}")
    master_temp.replace(master_path)
    after = _read_csv(character_path)
    return {"before": len(before), "written": written, "after": len(after), "master": len(master)}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    xp_dir = root / "data" / "xp_annotation"
    print(execute_roster_xp_final_write(
        data_dir=root / "data",
        approved_path=xp_dir / "roster_xp_v5_3_batch_01_approved_ids.json",
        draft_path=xp_dir / "roster_xp_v5_3_batch_01_draft.json",
        qa_path=xp_dir / "roster_xp_v5_3_batch_01_qa.json",
    ))
