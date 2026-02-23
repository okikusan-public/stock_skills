"""Note manager -- dual-write to JSON files and Neo4j (KIK-397, KIK-429).

Notes are investment memos (thesis, observation, concern, review, target)
attached to specific stocks or to categories (portfolio, market, general).
The JSON file is the master; Neo4j is a view.
"""

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional


_NOTES_DIR = "data/notes"
_VALID_TYPES = {"thesis", "observation", "concern", "review", "target", "lesson", "journal"}
_VALID_CATEGORIES = {"stock", "portfolio", "market", "general"}


def _notes_dir(base_dir: str = _NOTES_DIR) -> Path:
    d = Path(base_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_note(
    symbol: Optional[str] = None,
    note_type: str = "observation",
    content: str = "",
    source: str = "",
    category: Optional[str] = None,
    base_dir: str = _NOTES_DIR,
) -> dict:
    """Save a note to JSON file and Neo4j.

    Parameters
    ----------
    symbol : str, optional
        Stock ticker (e.g., "7203.T"). If provided, category is set to "stock".
    note_type : str
        One of: thesis, observation, concern, review, target, lesson.
    content : str
        The note text.
    source : str
        Where this note came from (e.g., "manual", "health-check", "report").
    category : str, optional
        Note category: "stock", "portfolio", "market", "general".
        Auto-set to "stock" when symbol is provided.
        Defaults to "general" when neither symbol nor category is given.
    base_dir : str
        Notes directory.

    Returns
    -------
    dict
        The saved note record.
    """
    if note_type not in _VALID_TYPES:
        raise ValueError(f"Invalid note type: {note_type}. Must be one of {_VALID_TYPES}")

    # Resolve category
    if symbol:
        resolved_category = "stock"
    elif category and category in _VALID_CATEGORIES:
        resolved_category = category
    elif note_type == "journal" and not category:
        resolved_category = "general"
    else:
        resolved_category = "general"

    if resolved_category != "stock" and category and category not in _VALID_CATEGORIES:
        raise ValueError(f"Invalid category: {category}. Must be one of {_VALID_CATEGORIES}")

    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")

    # Build ID and filename based on symbol or category
    if symbol:
        note_id = f"note_{today}_{symbol}_{uuid.uuid4().hex[:8]}"
        safe_symbol = symbol.replace(".", "_").replace("/", "_")
        filename = f"{today}_{safe_symbol}_{note_type}.json"
    else:
        note_id = f"note_{today}_{resolved_category}_{uuid.uuid4().hex[:8]}"
        filename = f"{today}_{resolved_category}_{note_type}.json"

    note = {
        "id": note_id,
        "date": today,
        "timestamp": now,
        "symbol": symbol or "",
        "category": resolved_category,
        "type": note_type,
        "content": content,
        "source": source,
    }

    # KIK-473: journal type auto-detects symbols from content
    detected_symbols: list[str] = []
    if note_type == "journal" and not symbol and content:
        try:
            from src.core.ticker_utils import extract_all_symbols
            detected_symbols = extract_all_symbols(content)[:3]
        except Exception:
            pass
        if detected_symbols:
            note["detected_symbols"] = detected_symbols

    # 1. Write to JSON file (master)
    d = _notes_dir(base_dir)
    path = d / filename

    # Append to existing file if same date/symbol-or-category/type, else create new
    existing = []
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            existing = data if isinstance(data, list) else [data]
        except (json.JSONDecodeError, OSError):
            existing = []

    existing.append(note)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    # 2. Write to Neo4j (view) -- graceful degradation
    try:
        from src.data.graph_store import merge_note
        from src.data.history_store import _build_embedding
        sem_summary, emb = _build_embedding(
            "note", symbol=symbol or "", note_type=note_type, content=content,
        )
        merge_note(
            note_id=note_id,
            note_date=today,
            note_type=note_type,
            content=content,
            symbol=symbol or None,
            source=source,
            category=resolved_category,
            semantic_summary=sem_summary,
            embedding=emb,
        )
        # KIK-473: Create ABOUT relationships for detected symbols in journal notes
        if detected_symbols:
            from src.data.graph_store import _get_mode, _get_driver
            if _get_mode() != "off":
                driver = _get_driver()
                if driver is not None:
                    with driver.session() as session:
                        for ds in detected_symbols:
                            session.run(
                                "MATCH (n:Note {id: $note_id}) "
                                "MERGE (s:Stock {symbol: $symbol}) "
                                "MERGE (n)-[:ABOUT]->(s)",
                                note_id=note_id, symbol=ds,
                            )
    except Exception:
        pass  # Neo4j unavailable, JSON is the master

    # KIK-434: AI graph linking (graceful degradation)
    try:
        from src.data.graph_linker import link_note
        if detected_symbols:
            for ds in detected_symbols:
                link_note(note_id, ds, note_type, content)
        else:
            link_note(note_id, symbol, note_type, content)
    except Exception:
        pass

    return note


def load_notes(
    symbol: Optional[str] = None,
    note_type: Optional[str] = None,
    category: Optional[str] = None,
    base_dir: str = _NOTES_DIR,
) -> list[dict]:
    """Load notes from JSON files.

    Parameters
    ----------
    symbol : str, optional
        Filter by stock symbol.
    note_type : str, optional
        Filter by note type.
    category : str, optional
        Filter by category ("stock", "portfolio", "market", "general").
    base_dir : str
        Notes directory.

    Returns
    -------
    list[dict]
        Notes sorted by date descending.
    """
    d = Path(base_dir)
    if not d.exists():
        return []

    all_notes = []
    for fp in d.glob("*.json"):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            notes = data if isinstance(data, list) else [data]
            all_notes.extend(notes)
        except (json.JSONDecodeError, OSError):
            continue

    # Filter
    if symbol:
        all_notes = [n for n in all_notes if n.get("symbol") == symbol]
    if note_type:
        all_notes = [n for n in all_notes if n.get("type") == note_type]
    if category:
        all_notes = [n for n in all_notes if n.get("category") == category]

    # Sort by date descending
    all_notes.sort(key=lambda n: n.get("date", ""), reverse=True)
    return all_notes


def delete_note(
    note_id: str,
    base_dir: str = _NOTES_DIR,
) -> bool:
    """Delete a note by ID from JSON files.

    Returns True if found and deleted.
    """
    d = Path(base_dir)
    if not d.exists():
        return False

    found = False
    for fp in d.glob("*.json"):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            notes = data if isinstance(data, list) else [data]
            filtered = [n for n in notes if n.get("id") != note_id]
            if len(filtered) < len(notes):
                if filtered:
                    with open(fp, "w", encoding="utf-8") as f:
                        json.dump(filtered, f, ensure_ascii=False, indent=2)
                else:
                    fp.unlink()
                found = True
                break
        except (json.JSONDecodeError, OSError):
            continue

    # Delete from Neo4j (view) -- graceful degradation
    try:
        from src.data.graph_store import _get_mode, _get_driver
        if _get_mode() != "off":
            driver = _get_driver()
            if driver is not None:
                driver.execute_query(
                    "MATCH (n:Note {id: $nid}) DETACH DELETE n",
                    nid=note_id, database_="neo4j",
                )
    except Exception:
        pass

    return found
