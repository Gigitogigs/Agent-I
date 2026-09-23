import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.core.config import settings
from backend.services.auth_service import register_user

async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            print("Attempting to register user...")
            user = await register_user(db, email="debug@example.com", full_name="Debug User", password="password123")
            print("Successfully registered:", user.id)
        except Exception as e:
            print("Error registering user!")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
