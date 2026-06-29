from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import NoReturn

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings
from app.exceptions import EmailDeliveryError
from app.services.email_service import send_resend_test_email


async def send_email(to_email: str) -> str:
    settings = Settings()
    return await send_resend_test_email(to_email=to_email, settings=settings)


def main() -> NoReturn:
    parser = argparse.ArgumentParser(description="Send the Resend Hello World test email.")
    parser.add_argument(
        "--to",
        required=True,
        help="Recipient email address for the test message.",
    )
    args = parser.parse_args()

    try:
        message_id = asyncio.run(send_email(to_email=str(args.to)))
    except ValidationError as exc:
        print(f"settings invalid: {exc}")
        raise SystemExit(2) from exc
    except EmailDeliveryError as exc:
        print(f"resend send failed: {exc.code}: {exc.message}")
        raise SystemExit(1) from exc

    print(f"resend: ok: message_id={message_id}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
