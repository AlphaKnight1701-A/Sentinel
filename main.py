import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
import tweepy
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ============================================================
# CONFIGURATION — Keys are now loaded from the .env file
# ============================================================
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
# ============================================================

# Initialize the Twitter/X client (v2)
twitter_client = tweepy.Client(
    bearer_token=TWITTER_BEARER_TOKEN,
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
)

# File to persist the last processed tweet ID across restarts
LAST_TWEET_ID_FILE = "last_tweet_id.txt"


def load_last_tweet_id() -> str | None:
    """Load the last processed tweet ID from disk."""
    try:
        with open(LAST_TWEET_ID_FILE, "r") as f:
            tweet_id = f.read().strip()
            return tweet_id if tweet_id else None
    except FileNotFoundError:
        return None


def save_last_tweet_id(tweet_id: str) -> None:
    """Persist the last processed tweet ID to disk."""
    with open(LAST_TWEET_ID_FILE, "w") as f:
        f.write(str(tweet_id))


async def check_mentions_loop():
    """Background loop that polls X for new @Sentinel mentions every 2 minutes."""
    last_tweet_id = load_last_tweet_id()

    # Get the bot's own user ID
    me = twitter_client.get_me()
    if me.data is None:
        print("ERROR: Could not authenticate with Twitter. Check your API keys.")
        return
    bot_id = me.data.id
    print(f"Bot authenticated as @{me.data.username} (ID: {bot_id})")

    while True:
        try:
            print("Checking for new mentions...")

            mentions = twitter_client.get_users_mentions(
                id=bot_id,
                since_id=last_tweet_id,
            )

            if mentions.data:
                # Process oldest to newest
                for mention in reversed(mentions.data):
                    print(f"New mention found: {mention.text}")

                    # Reply with "hi"
                    twitter_client.create_tweet(
                        text="yoo",
                        in_reply_to_tweet_id=mention.id,
                    )
                    print(f"Replied 'yoo' to tweet {mention.id}")

                    # Update and persist the tracker
                    last_tweet_id = mention.id
                    save_last_tweet_id(last_tweet_id)
            else:
                print("No new mentions found.")

        except Exception as e:
            print(f"Error encountered: {e}")

        # Wait 30 seconds before polling again
        await asyncio.sleep(30)


# ---------------------
# FastAPI Lifespan
# ---------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the mention-polling loop when the server boots, cancel on shutdown."""
    task = asyncio.create_task(check_mentions_loop())
    yield
    task.cancel()


# ---------------------
# FastAPI App
# ---------------------
app = FastAPI(lifespan=lifespan)


@app.get("/")
def health_check():
    return {"status": "@Sentinel is online and actively monitoring X!"}
