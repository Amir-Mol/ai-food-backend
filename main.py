from dotenv import load_dotenv

# Load environment variables from .env file at the very beginning
# This MUST be the first thing to run.
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from api import auth, profile, recommendations, history, ai
from database import db # Import the shared db instance
from api import recipes

# Create a global Prisma client instance
# This client will be used throughout your application to interact with the database.


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect to the database when the application starts up
    print("Connecting to database...")
    await db.connect() # Use the shared db instance
    print("Database connected.")
    yield
    # Disconnect from the database when the application shuts down
    print("Disconnecting from database...")
    await db.disconnect() # Use the shared db instance
    print("Database disconnected.")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Hello World"}

# Include the authentication router
app.include_router(auth.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(recommendations.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(recipes.router, prefix="/api")