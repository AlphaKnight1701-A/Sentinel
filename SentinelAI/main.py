import asyncio
import os
import random
import string
from contextlib import asynccontextmanager
from fastapi import FastAPI
import tweepy
from dotenv import load_dotenv
from google import genai

# Load environment variables from .env file
load_dotenv()

# Configure Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    client = genai.Client(api_key=GOOGLE_API_KEY)
else:
    client = None

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

            # Include expansions and fields to get text, author, and media of the mention itself
            mentions = twitter_client.get_users_mentions(
                id=bot_id,
                since_id=last_tweet_id,
                expansions=['referenced_tweets.id', 'author_id', 'attachments.media_keys'],
                user_fields=['name', 'username'],
                tweet_fields=['referenced_tweets', 'text', 'author_id', 'attachments'],
                media_fields=['url', 'preview_image_url'],
                max_results=5 
            )

            import httpx

            if mentions.data:
                # Need to map includes if any media or users came back directly with the mention
                mention_users = {u.id: u for u in mentions.includes.get('users', [])} if 'users' in mentions.includes else {}
                
                # Process oldest to newest
                for mention in reversed(mentions.data):
                    print(f"New mention found: {mention.text}")

                    # Determine what to analyze: the tweet being replied to, or the mention itself
                    user_question = mention.text
                    parent_tweet_text = mention.text
                    parent_tweet_author_username = mention_users.get(mention.author_id).username if mention.author_id in mention_users else "unknown"
                    parent_tweet_author_name = mention_users.get(mention.author_id).name if mention.author_id in mention_users else "Unknown"
                    media_urls = []

                    parent_id = getattr(mention, 'referenced_tweets', None)
                    
                    if parent_id and len(parent_id) > 0:
                        for ref in parent_id:
                            if ref.type == 'replied_to':
                                # Fetch the parent tweet with all attachments and author info
                                parent_tweet = twitter_client.get_tweet(
                                    ref.id, 
                                    expansions=['author_id', 'attachments.media_keys'],
                                    tweet_fields=['text', 'author_id', 'attachments'],
                                    user_fields=['name', 'username'],
                                    media_fields=['url', 'preview_image_url', 'type']
                                )
                                
                                if parent_tweet.data:
                                    parent_tweet_text = parent_tweet.data.text
                                    
                                    # Extract Author of the parent tweet
                                    if 'users' in parent_tweet.includes:
                                        p_author = next((u for u in parent_tweet.includes['users'] if u.id == parent_tweet.data.author_id), None)
                                        if p_author:
                                            parent_tweet_author_name = p_author.name
                                            parent_tweet_author_username = p_author.username
                                            
                                    # Extract Media from the parent tweet
                                    if 'media' in parent_tweet.includes:
                                        for m in parent_tweet.includes['media']:
                                            if m.type == 'photo' or m.type == 'animated_gif':
                                                media_urls.append(m.url)
                                            elif m.type == 'video':
                                                if m.preview_image_url:
                                                    media_urls.append(m.preview_image_url)
                                break

                    # If no media in the parent, check the mention itself (just in case they quote tweeted without replying, or just attached an image)
                    if not media_urls and getattr(mention, 'attachments', None):
                        if 'media' in mentions.includes:
                            for m_key in mention.attachments.get('media_keys', []):
                                m = next((media for media in mentions.includes['media'] if media.media_key == m_key), None)
                                if m:
                                    if m.type == 'photo' or m.type == 'animated_gif':
                                        media_urls.append(m.url)
                                    elif m.type == 'video' and hasattr(m, 'preview_image_url'):
                                        media_urls.append(m.preview_image_url)

                    # Send data to localhost:8000/live-feed
                    print(f"Calling backend /live-feed for {parent_tweet_author_username} with {len(media_urls)} media items")
                    try:
                        with httpx.Client(timeout=60.0) as client:
                            payload = {
                                "content_type": "post",
                                "post_text": parent_tweet_text,
                                "profile_username": parent_tweet_author_username,
                                "profile_display_name": parent_tweet_author_name,
                                "media_urls": media_urls
                            }
                            # Send image_url if exactly one, else send list in media_urls
                            if len(media_urls) > 0:
                                payload["image_url"] = media_urls[0]

                            response = client.post("http://127.0.0.1:8000/live-feed", json=payload)
                            response.raise_for_status()
                            live_feed_data = response.json()
                            
                    except Exception as e:
                        print(f"Error calling backend: {e}")
                        live_feed_data = {
                            "error": "Backend analysis failed or timed out.",
                            "reasoning_summary": "I was unable to reach the Sentinel backend to analyze this media. Please try again later."
                        }

                    # Generate Gemini analysis
                    analysis = "I'm sorry, I couldn't analyze this tweet right now because my AI brain (Gemini) isn't configured."
                    if model:
                        try:
                            # Strip out the bot's username from the user question so it doesn't get confused
                            clean_question = user_question.replace(f"@{me.data.username}", "").strip()
                            if not clean_question:
                                clean_question = "What is the analysis of this post?"

                            prompt = (
                                f"You are Sentinel, an elite AI Trust & Safety bot. A user on X (Twitter) just tagged you and asked: '{clean_question}'.\n\n"
                                f"Here is the context of the tweet they are referring to:\n"
                                f"Author: {parent_tweet_author_name} (@{parent_tweet_author_username})\n"
                                f"Text: '{parent_tweet_text}'\n"
                                f"Media Count: {len(media_urls)}\n\n"
                                f"Here is the forensic analysis generated by the Sentinel Backend:\n"
                                f"Risk Level: {live_feed_data.get('risk_level', 'unknown')}\n"
                                f"Trust Score: {live_feed_data.get('trust_score', 'unknown')}/100\n"
                                f"AI Generated Score: {live_feed_data.get('ai_generated_score', 'unknown')}/100\n"
                                f"Reasoning: {live_feed_data.get('reasoning_summary', 'No summary provided')}\n\n"
                                f"Task: Write a short, highly professional but approachable tweet replying to the user's question using the provided forensic analysis. "
                                f"Do NOT just regurgitate the stats. Synthesize a direct answer to their question. "
                                f"Keep it extremely concise (under 240 characters) because this is a Twitter reply. "
                                f"Do not use hashtags."
                            )
                            gemini_response = client.models.generate_content(
                                model='gemini-2.5-flash-lite',
                                contents=prompt
                            )
                            analysis = gemini_response.text.strip()
                            
                            # X has character limits (280). Gemini responses can be long.
                            # We'll truncate to ~250 to leave room for the unique suffix.
                            if len(analysis) > 250:
                                analysis = analysis[:247] + "..."

                            # Deduplication helper: always add a random suffix to avoid Twitter's 403 Forbidden
                            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
                            analysis = f"{analysis}\n\n[Ref: {suffix}]"
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


if __name__ == "__main__":
    print("Starting Sentinel Twitter Bot...")
    try:
        asyncio.run(check_mentions_loop())
    except KeyboardInterrupt:
        print("\nShutting down bot...")
