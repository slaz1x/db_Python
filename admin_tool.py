import argparse
from datetime import timezone, timedelta
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))

DB_PATH = "auth_db.json"

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без 0/O/I/1

def now_msk():
    return datetime.now(MSK)

def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()

def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)

def gen_code() -> str:
    def chunk(n=4):
        return "".join(secrets.choice(ALPHABET) for _ in range(n))
    return f"{chunk()}-{chunk()}"

def calc_expires(plan: str):
    plan = plan.lower().strip()
    if plan in ("life", "lifetime", "forever", "inf"):
        return None
    if plan.endswith("d"):
        days = int(plan[:-1])
        return now_msk() + timedelta(days=days)
    raise ValueError("plan must be 3d/7d/30d or life")

def load_db(path: str) -> dict:
    if not os.path.exists(path):
        return {"version": 1, "users": []}
    with open(path, "r", encoding="utf-8") as f:
        db = json.load(f)
    if "users" not in db or not isinstance(db["users"], list):
        db["users"] = []
    if "version" not in db:
        db["version"] = 1
    return db

def save_db(path: str, db: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def upsert_user(db: dict, hwid: str, plan: str, code: str | None, enabled: bool, note: str | None):
    issued = now_msk()
    exp_dt = calc_expires(plan)
    exp_iso = iso(exp_dt) if exp_dt else None
    if code is None:
        code = gen_code()

    users = db["users"]
    for u in users:
        if u.get("hwid") == hwid:
            u["code"] = code
            u["plan"] = plan
            u["issued_at"] = iso(issued)
            u["expires_at"] = exp_iso
            u["enabled"] = bool(enabled)
            if note is not None:
                u["note"] = note
            return code, exp_iso, True

    rec = {
        "hwid": hwid,
        "code": code,
        "plan": plan,
        "issued_at": iso(issued),
        "expires_at": exp_iso,
        "enabled": bool(enabled),
    }
    if note is not None:
        rec["note"] = note
    users.append(rec)
    return code, exp_iso, False

def remove_users(db: dict, hwid: str | None, code: str | None) -> int:
    users = db["users"]
    before = len(users)
    kept = []
    for u in users:
        if hwid and u.get("hwid") == hwid:
            continue
        if code and str(u.get("code", "")).strip() == code.strip():
            continue
        kept.append(u)
    db["users"] = kept
    return before - len(kept)

def prune_expired(db: dict) -> int:
    users = db["users"]
    now = now_utc()
    kept = []
    removed = 0

    for u in users:
        exp = u.get("expires_at", None)
        if exp is None:
            kept.append(u)  # life
            continue
        try:
            exp_dt = parse_iso(exp)
        except Exception:
            kept.append(u)
            continue
        if exp_dt > now:
            kept.append(u)
        else:
            removed += 1

    db["users"] = kept
    return removed

def cmd_add(args):
    db = load_db(DB_PATH)
    code, expires_at, updated = upsert_user(
        db=db,
        hwid=args.hwid.strip(),
        plan=args.plan.strip(),
        code=(args.code.strip() if args.code else None),
        enabled=(not args.disable),
        note=args.note,
    )
    save_db(DB_PATH, db)
    print(("UPDATED" if updated else "ADDED") + f": hwid={args.hwid} code={code} expires_at={expires_at}")

def cmd_remove(args):
    db = load_db(DB_PATH)
    removed = remove_users(db, hwid=args.hwid, code=args.code)
    save_db(DB_PATH, db)
    print(f"Removed: {removed}")

def cmd_list(args):
    db = load_db(DB_PATH)
    users = db.get("users", [])
    print(f"Users: {len(users)}")
    for u in users:
        print(
            f"hwid={u.get('hwid')} code={u.get('code')} plan={u.get('plan')} "
            f"expires_at={u.get('expires_at')} enabled={u.get('enabled', True)}"
        )

def cmd_prune(args):
    db = load_db(DB_PATH)
    removed = prune_expired(db)
    save_db(DB_PATH, db)
    print(f"Pruned expired: {removed}")

def main():
    ap = argparse.ArgumentParser(prog="admin_tool.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="add/update user")
    p_add.add_argument("--hwid", required=True)
    p_add.add_argument("--plan", required=True, help="3d / 7d / 30d / life")
    p_add.add_argument("--code", default=None, help="optional custom code")
    p_add.add_argument("--disable", action="store_true", help="set enabled=false")
    p_add.add_argument("--note", default=None)
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser("remove", help="remove user")
    p_rm.add_argument("--hwid", default=None)
    p_rm.add_argument("--code", default=None)
    p_rm.set_defaults(func=cmd_remove)

    p_ls = sub.add_parser("list", help="list users")
    p_ls.set_defaults(func=cmd_list)

    p_pr = sub.add_parser("prune", help="remove expired users locally")
    p_pr.set_defaults(func=cmd_prune)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()