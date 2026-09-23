import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.core.config import settings
from backend.services.auth_service import get_user_by_id

async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            print("Attempting to get user...")
            # Use the UUID of testagent@example.com which we created, or we can just fetch the first user
            from sqlalchemy import select
            from backend.db.models.user import User
            user_row = await db.scalar(select(User).limit(1))
            if not user_row:
                print("No users found.")
                return
            print("Found user:", user_row.id)
            user = await get_user_by_id(db, str(user_row.id))
            print("Successfully loaded user:", user.id)
            for m in user.workspaces:
                print(m.workspace.name)
        except Exception as e:
            print("Error getting user!")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
