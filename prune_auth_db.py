import json
from datetime import datetime, timezone

DB_PATH = "auth_db.json"

def parse_iso_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)

def main():
    now = datetime.now(timezone.utc)

    with open(DB_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)

    users = db.get("users", [])
    if not isinstance(users, list):
        users = []

    kept = []
    removed = 0

    for u in users:
        if not isinstance(u, dict):
            continue

        exp = u.get("expires_at", None)
        enabled = u.get("enabled", True)

        # безлимит
        if exp is None:
            kept.append(u)
            continue

        # отключённых можно НЕ удалять (оставляем)
        # если хочешь удалять отключённых — убери этот блок
        if not enabled:
            kept.append(u)
            continue

        try:
            exp_dt = parse_iso_utc(exp)
        except Exception:
            # если дата кривая — оставим, чтобы не потерять запись
            kept.append(u)
            continue

        if exp_dt > now:
            kept.append(u)
        else:
            removed += 1

    db["users"] = kept

    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    print(f"Pruned expired: {removed}")

if __name__ == "__main__":
    main()