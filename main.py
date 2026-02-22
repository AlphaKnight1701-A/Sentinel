import asyncio
import os
import random
import string
from contextlib import asynccontextmanager
from fastapi import FastAPI
import tweepy
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv()

# Configure Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
else:
    model = None

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
    print(f"IMPORTANT: Make sure you are tagging @{me.data.username} in your tweets!")

    while True:
        try:
            print(f"Checking for new mentions since ID: {last_tweet_id}...")

            mentions = twitter_client.get_users_mentions(
                id=bot_id,
                since_id=last_tweet_id,
                tweet_fields=['referenced_tweets', 'text'],
                max_results=5 # Fetch a few to be sure
            )

            if mentions.data:
                # Process oldest to newest
                for mention in reversed(mentions.data):
                    print(f"New mention found: {mention.text}")

                    # Determine what to analyze: the tweet being replied to, or the mention itself
                    tweet_to_analyze = mention.text
                    parent_id = getattr(mention, 'referenced_tweets', None)
                    
                    if parent_id and len(parent_id) > 0:
                        for ref in parent_id:
                            if ref.type == 'replied_to':
                                parent_tweet = twitter_client.get_tweet(ref.id, tweet_fields=['text'])
                                if parent_tweet.data:
                                    tweet_to_analyze = parent_tweet.data.text
                                break

                    # Generate Gemini analysis
                    analysis = "I'm sorry, I couldn't analyze this tweet right now because my AI brain (Gemini) isn't configured."
                    if model:
                        try:
                            prompt = (
                                f"Analyze the following tweet/post: '{tweet_to_analyze}'. "
                                "Summarize it briefly and evaluate how likely it is to be 'real' or 'fake' news. "
                                "Respond in a natural, conversational tone like a person would, being concise and helpful."
                            )
                            response = model.generate_content(prompt)
                            analysis = response.text.strip()
                            
                            # X has character limits (280). Gemini responses can be long.
                            # We'll truncate to ~250 to leave room for the unique suffix.
                            if len(analysis) > 250:
                                analysis = analysis[:247] + "..."

                            # Deduplication helper: always add a random suffix to avoid Twitter's 403 Forbidden
                            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
                            analysis = f"{analysis} \n\n[Ref: {suffix}]"
                        except Exception as ai_err:
                            print(f"Gemini error: {ai_err}")
                            analysis = f"Hmm, I ran into a bit of trouble with my AI processing for that one! [err_{random.randint(100,999)}]"

                    # Reply with Gemini's analysis
                    try:
                        twitter_client.create_tweet(
                            text=analysis,
                            in_reply_to_tweet_id=mention.id,
                        )
                        print(f"Replied with Gemini analysis to tweet {mention.id}")
                    except Exception as tweet_err:
                        print(f"Failed to create tweet {mention.id}: {tweet_err}")

                    # ALWAYS update and persist the tracker so we don't get stuck in a loop on a bad tweet
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
