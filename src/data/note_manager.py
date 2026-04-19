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
_VALID_TYPES = {"thesis", "observation", "concern", "review", "target", "lesson", "journal", "exit-rule"}
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
    trigger: Optional[str] = None,
    expected_action: Optional[str] = None,
    stop_loss: Optional[str] = None,
    take_profit: Optional[str] = None,
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
    trigger : str, optional
        What triggered this lesson (KIK-534). Only stored for type="lesson".
    expected_action : str, optional
        What action should be taken next time (KIK-534). Only stored for type="lesson".

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

    # KIK-534: lesson-specific fields
    if note_type == "lesson":
        if trigger:
            note["trigger"] = trigger
        if expected_action:
            note["expected_action"] = expected_action

    # KIK-566: exit-rule specific fields
    if note_type == "exit-rule":
        if stop_loss:
            note["stop_loss"] = stop_loss
        if take_profit:
            note["take_profit"] = take_profit

    # KIK-564: Lesson conflict detection (before save)
    lesson_conflicts: list[dict] = []
    if note_type == "lesson":
        try:
            lesson_conflicts = check_lesson_conflicts(note, base_dir=base_dir)
        except Exception:
            pass  # graceful degradation

    # KIK-473: journal type auto-detects symbols from content
    detected_symbols: list[str] = []
    if note_type == "journal" and not symbol and content:
        try:
            from src.data.ticker_utils import extract_all_symbols
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
        from src.data.history import _build_embedding
        sem_summary, emb = _build_embedding(
            "note", symbol=symbol or "", note_type=note_type, content=content,
            trigger=note.get("trigger", ""),
            expected_action=note.get("expected_action", ""),
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
        from src.data.graph_store.linker import link_note
        if detected_symbols:
            for ds in detected_symbols:
                link_note(note_id, ds, note_type, content)
        else:
            link_note(note_id, symbol, note_type, content)
    except Exception:
        pass

    # KIK-571: Lesson community classification
    if note_type == "lesson":
        try:
            from src.data.lesson_community import classify_lesson, merge_lesson_community
            community = classify_lesson(content, trigger or "")
            merge_lesson_community(note_id, community)
            note["_lesson_community"] = community
        except Exception:
            pass  # graceful degradation

    # KIK-564: Attach conflicts to return value
    if lesson_conflicts:
        note["_conflicts"] = lesson_conflicts

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


# ---------------------------------------------------------------------------
# Lesson conflict detection (KIK-564)
# ---------------------------------------------------------------------------

def check_lesson_conflicts(
    new_lesson: dict,
    base_dir: str = _NOTES_DIR,
    similarity_threshold: float = 0.5,
) -> list[dict]:
    """Check if a new lesson conflicts with existing lessons (KIK-564/570).

    Delegates to lesson_conflict.find_conflicts() for unified detection.
    """
    existing = load_notes(note_type="lesson", base_dir=base_dir)
    if not existing:
        return []
    try:
        from src.data.lesson_conflict import find_conflicts
        return find_conflicts(new_lesson, existing, similarity_threshold)
    except ImportError:
        return []


# Backward-compatible aliases (used by auto_context and tests)
def _keyword_similarity(text_a: str, text_b: str) -> float:
    """CJK-aware keyword similarity (KIK-570 delegates to lesson_conflict)."""
    try:
        from src.data.lesson_conflict import keyword_similarity
        return keyword_similarity(text_a, text_b)
    except ImportError:
        # Fallback: space-split only
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)


def _embedding_similarity(text_a: str, text_b: str) -> Optional[float]:
    """Cosine similarity via TEI (KIK-570 delegates to lesson_conflict)."""
    try:
        from src.data.lesson_conflict import embedding_similarity
        return embedding_similarity(text_a, text_b)
    except ImportError:
        return None


def get_exit_rules(
    symbol: Optional[str] = None,
    base_dir: str = _NOTES_DIR,
) -> list[dict]:
    """Load exit-rule notes, optionally filtered by symbol (KIK-566).

    Returns list of exit-rule notes sorted by date descending.
    Each note has stop_loss and/or take_profit fields.
    """
    return load_notes(note_type="exit-rule", symbol=symbol, base_dir=base_dir)


def check_exit_rule(
    symbol: str,
    pnl_pct: float,
    base_dir: str = _NOTES_DIR,
) -> Optional[dict]:
    """Check if a position has hit any exit-rule threshold (KIK-566).

    Parameters
    ----------
    symbol : str
        Ticker symbol.
    pnl_pct : float
        Current P&L percentage (e.g., -15.0 means -15%).

    Returns
    -------
    Optional[dict]
        {type: "stop_loss"|"take_profit", threshold: str, reason: str}
        or None if no threshold hit.
    """
    rules = get_exit_rules(symbol=symbol, base_dir=base_dir)
    if not rules:
        return None

    # Use the most recent rule
    rule = rules[0]
    reason = (rule.get("content") or "")[:100]

    # Check stop_loss
    sl = rule.get("stop_loss", "")
    if sl:
        sl_val = _parse_threshold(sl)
        if sl_val is not None and pnl_pct <= sl_val:
            return {"type": "stop_loss", "threshold": sl, "reason": reason}

    # Check take_profit
    tp = rule.get("take_profit", "")
    if tp:
        tp_val = _parse_threshold(tp)
        if tp_val is not None and pnl_pct >= tp_val:
            return {"type": "take_profit", "threshold": tp, "reason": reason}

    return None


def _parse_threshold(value: str) -> Optional[float]:
    """Parse a threshold string like '-15%' or '+20%' into a float."""
    if not value:
        return None
    s = value.strip().replace("%", "").replace("％", "")
    try:
        return float(s)
    except ValueError:
        return None


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
