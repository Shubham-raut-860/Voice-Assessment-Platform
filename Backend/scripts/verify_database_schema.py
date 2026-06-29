from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db.engine import create_engine, dispose_database


EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "alembic_version",
        "users",
        "assessments",
        "assessment_sessions",
        "assessment_reports",
        "webhook_events",
    }
)
EXPECTED_ENUMS: frozenset[str] = frozenset(
    {
        "user_role",
        "assessment_status",
        "assessment_session_status",
        "assessment_report_pass_fail",
        "assessment_report_generation_status",
    }
)
EXPECTED_REVISION = "20260530_0001"


@dataclass(frozen=True)
class SchemaCheckResult:
    name: str
    ok: bool
    detail: str


async def collect_schema_checks(settings: Settings) -> list[SchemaCheckResult]:
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            revision_result = await connection.execute(text("select version_num from alembic_version"))
            revision = revision_result.scalar_one_or_none()

            table_result = await connection.execute(
                text(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = 'public'
                    """
                )
            )
            tables = {str(row[0]) for row in table_result.fetchall()}

            enum_result = await connection.execute(
                text(
                    """
                    select typname
                    from pg_type
                    where typnamespace = 'public'::regnamespace
                    """
                )
            )
            enums = {str(row[0]) for row in enum_result.fetchall()}

            extension_result = await connection.execute(
                text("select exists(select 1 from pg_extension where extname = 'pgcrypto')")
            )
            pgcrypto_enabled = bool(extension_result.scalar_one())
    finally:
        await dispose_database(engine)

    missing_tables = sorted(EXPECTED_TABLES - tables)
    missing_enums = sorted(EXPECTED_ENUMS - enums)
    return [
        SchemaCheckResult(
            name="alembic_revision",
            ok=revision == EXPECTED_REVISION,
            detail=str(revision),
        ),
        SchemaCheckResult(
            name="tables",
            ok=not missing_tables,
            detail="all_present" if not missing_tables else f"missing:{','.join(missing_tables)}",
        ),
        SchemaCheckResult(
            name="enums",
            ok=not missing_enums,
            detail="all_present" if not missing_enums else f"missing:{','.join(missing_enums)}",
        ),
        SchemaCheckResult(
            name="pgcrypto",
            ok=pgcrypto_enabled,
            detail="enabled" if pgcrypto_enabled else "missing",
        ),
    ]


def main() -> NoReturn:
    try:
        settings = Settings()
        results = asyncio.run(collect_schema_checks(settings))
    except ValidationError as exc:
        print(f"settings: failed: {exc}")
        raise SystemExit(2) from exc
    except SQLAlchemyError as exc:
        print(f"database: failed: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    for result in results:
        status = "ok" if result.ok else "failed"
        print(f"{result.name}: {status}: {result.detail}")

    if all(result.ok for result in results):
        print("database_schema: ok")
        raise SystemExit(0)

    print("database_schema: failed")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
