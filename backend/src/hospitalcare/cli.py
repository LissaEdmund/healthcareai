"""Command-line entry point: `uv run hcai <command>`."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .config import get_settings
from .db import check_health, get_conn, migrate


def cmd_init_db(args) -> int:
    with get_conn() as conn:
        applied = migrate(conn)
    print(f"Database: {get_settings().database_path}")
    print(f"Applied migrations: {applied or 'none (already up to date)'}")
    return 0


def cmd_seed(args) -> int:
    from .seed import seed

    settings = get_settings()
    if args.reset:
        removed = 0
        for path in (settings.database_path, settings.checkpoint_path):
            for suffix in ("", "-wal", "-shm"):
                p = path.with_name(path.name + suffix)
                if p.exists():
                    p.unlink()
                    removed += 1
        if removed:
            print("Removed the existing local synthetic database and workflow checkpoints.")
    with get_conn() as conn:
        migrate(conn)
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            print("Database already seeded. Use --reset to recreate it.")
            return 1
        counts = seed(conn)
    print(f"Seeded SYNTHETIC data: {counts}. Demo accounts use HCAI_DEMO_PASSWORD.")
    return 0


def cmd_check(args) -> int:
    from .llm import model_status
    from .mcp_clients import McpToolError, ReadOnlyFilesystemClient

    settings = get_settings()
    ok = True
    for problem in settings.validate_for_runtime():
        print(f"[FAIL] config: {problem}")
        ok = False
    db_ok, db_detail = check_health()
    print(f"[{'OK' if db_ok else 'FAIL'}] database: {db_detail}")
    ok &= db_ok
    model = model_status()
    print(f"[{'OK' if model['available'] else 'WARN'}] local model {model['model']}: {model['detail']}")
    try:
        listing = asyncio.run(ReadOnlyFilesystemClient().call("list_directory", "protocols"))
        print(f"[OK] filesystem MCP: {listing.get('content', '')[:120]}")
    except McpToolError as exc:
        print(f"[FAIL] filesystem MCP: {exc}")
        ok = False
    print(f"Demo mode: {settings.demo_mode}  Facility: {settings.facility_code}")
    return 0 if ok else 1


def cmd_serve(args) -> int:
    import uvicorn

    settings = get_settings()
    problems = settings.validate_for_runtime()
    if problems:
        for p in problems:
            print(f"Configuration error: {p}", file=sys.stderr)
        return 2
    uvicorn.run("hospitalcare.api.app:app", host=settings.api_host, port=settings.api_port, reload=args.reload)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="hcai", description="HospitalCare AI (synthetic-data prototype)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="apply database migrations").set_defaults(func=cmd_init_db)
    p_seed = sub.add_parser("seed", help="load synthetic demonstration data")
    p_seed.add_argument("--reset", action="store_true", help="delete the local database and checkpoints first")
    p_seed.set_defaults(func=cmd_seed)
    sub.add_parser("check", help="verify configuration, database, model and filesystem MCP").set_defaults(func=cmd_check)
    p_serve = sub.add_parser("serve", help="start the API server")
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=cmd_serve)
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
