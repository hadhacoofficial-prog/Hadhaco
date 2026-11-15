"""Create dev accounts for k6 load testing.

Usage: python scripts/setup_k6_accounts.py

Creates (or resets the password of):
  - Admin user:  admin@hadha.co / Admin123!@#
  - Customer:    customer@hadha.co / Customer123!@#
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password

ADMIN_EMAIL = "admin@hadha.co"
ADMIN_PASSWORD = "Admin123!@#"
CUSTOMER_EMAIL = "customer@hadha.co"
CUSTOMER_PASSWORD = "Customer123!@#"


async def ensure_account(email: str, password: str, role: str) -> None:
    """Create the profile if missing, then (re)set a verified password credential."""
    password_hash = await hash_password(password)
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                text("SELECT id FROM profiles WHERE email = :email"), {"email": email}
            )
        ).first()
        if row:
            user_id = row[0]
            print(f"  Profile {email} already exists (user_id={user_id})")
        else:
            user_id = uuid.uuid4()
            await session.execute(
                text(
                    "INSERT INTO profiles (id, email, role, is_active, is_verified, full_name) "
                    "VALUES (:uid, :email, :role, true, true, :name)"
                ),
                {
                    "uid": user_id,
                    "email": email,
                    "role": role,
                    "name": email.split("@")[0].title(),
                },
            )
            print(f"  Profile {email} created (role={role}, user_id={user_id})")
        await session.execute(
            text(
                "INSERT INTO user_credentials "
                "(user_id, password_hash, email_verified_at, password_changed_at) "
                "VALUES (:uid, :hash, now(), now()) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "password_hash = EXCLUDED.password_hash, "
                "email_verified_at = COALESCE(user_credentials.email_verified_at, now()), "
                "password_changed_at = now()"
            ),
            {"uid": user_id, "hash": password_hash},
        )
        await session.commit()


async def main() -> None:
    print("--- Ensuring accounts ---")
    await ensure_account(ADMIN_EMAIL, ADMIN_PASSWORD, "admin")
    await ensure_account(CUSTOMER_EMAIL, CUSTOMER_PASSWORD, "customer")

    print("\n--- Credentials for k6 ---")
    print(f"  DEV_EMAIL={ADMIN_EMAIL}")
    print(f"  DEV_PASSWORD={ADMIN_PASSWORD}")
    print(f"  CUSTOMER_EMAIL={CUSTOMER_EMAIL}")
    print(f"  CUSTOMER_PASSWORD={CUSTOMER_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
