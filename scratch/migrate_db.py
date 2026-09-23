import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from backend.core.config import settings
from sqlalchemy import text

async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        print("Running alter table...")
        try:
            await conn.execute(text("ALTER TABLE workspace_members ADD COLUMN status VARCHAR NOT NULL DEFAULT 'active';"))
            print("Successfully added status column.")
        except Exception as e:
            print("Error altering table, it might already exist or another error occurred:", e)
            
if __name__ == "__main__":
    asyncio.run(main())
