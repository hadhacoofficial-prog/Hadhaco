"""Create dev accounts for k6 load testing.

Usage: python scripts/setup_k6_accounts.py

Creates:
  - Admin user:  admin@hadha.co / Admin123!@#
  - Customer:    customer@hadha.co / Customer123!@#
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal

ADMIN_EMAIL = "admin@hadha.co"
ADMIN_PASSWORD = "Admin123!@#"
CUSTOMER_EMAIL = "customer@hadha.co"
CUSTOMER_PASSWORD = "Customer123!@#"


async def create_supabase_user(email: str, password: str) -> str | None:
    """Create or update a user in Supabase Auth via the admin API."""
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    # Try to list users and find existing by email
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{settings.SUPABASE_URL}/auth/v1/admin/users",
            headers=headers,
        )
    if resp.status_code == 200:
        users = resp.json().get("users", [])
        for u in users:
            if u.get("email") == email:
                uid = u["id"]
                print(f"  Supabase {email}: already exists (user_id={uid})")
                # Update password
                async with httpx.AsyncClient(timeout=15) as client:
                    await client.put(
                        f"{settings.SUPABASE_URL}/auth/v1/admin/users/{uid}",
                        headers=headers,
                        json={"password": password},
                    )
                return uid

    # Create new
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.SUPABASE_URL}/auth/v1/admin/users",
            headers=headers,
            json={"email": email, "password": password, "email_confirm": True},
        )
    print(f"  Supabase {email}: HTTP {resp.status_code}")
    if resp.status_code in (200, 201):
        data = resp.json()
        uid = data.get("id", "")
        print(f"    user_id={uid}")
        return uid
    else:
        print(f"    body={resp.text[:300]}")
        return None


async def ensure_profile(user_id: str, email: str, role: str) -> None:
    """Insert the profile row if it does not exist."""
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            text("SELECT id FROM profiles WHERE id = :uid"), {"uid": user_id}
        )
        if existing.first():
            print(f"  Profile {email} already exists — skipping")
            return
        await session.execute(
            text(
                "INSERT INTO profiles (id, email, role, is_active, full_name) "
                "VALUES (:uid, :email, :role, true, :name)"
            ),
            {
                "uid": user_id,
                "email": email,
                "role": role,
                "name": email.split("@")[0].title(),
            },
        )
        await session.commit()
        print(f"  Profile {email} created (role={role})")


async def main() -> None:
    print("--- Creating Supabase auth users ---")
    admin_id = await create_supabase_user(ADMIN_EMAIL, ADMIN_PASSWORD)
    customer_id = await create_supabase_user(CUSTOMER_EMAIL, CUSTOMER_PASSWORD)

    if not admin_id or not customer_id:
        print("\nERROR: Could not create both users. Aborting.")
        return

    print("\n--- Ensuring profile rows ---")
    await ensure_profile(admin_id, ADMIN_EMAIL, "admin")
    await ensure_profile(customer_id, CUSTOMER_EMAIL, "customer")

    print("\n--- Credentials for k6 ---")
    print(f"  DEV_EMAIL={ADMIN_EMAIL}")
    print(f"  DEV_PASSWORD={ADMIN_PASSWORD}")
    print(f"  CUSTOMER_EMAIL={CUSTOMER_EMAIL}")
    print(f"  CUSTOMER_PASSWORD={CUSTOMER_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
