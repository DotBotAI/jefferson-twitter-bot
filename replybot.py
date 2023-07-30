import logging
import os
import re
import time
import traceback

import openai
import pandas as pd
import requests
import tweepy
from huggingface_hub import upload_file

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)
logger.setLevel(logging.INFO)

bot_user_id = 1685737450725945344
bot_user_name = "AskJefferson"

persistent_storage_repo_id = "team6/expose-history"
persistent_storage_file_name = "history.csv"
persistent_storage_file_url = (
    f"https://huggingface.co/datasets/{persistent_storage_repo_id}/resolve/main/{persistent_storage_file_name}"
)

# will be used to remove the @exposeorpreachgpt from the tweet text (case insensitive)
pattern_at_mention = re.compile(re.escape("@askjefferson"), re.IGNORECASE)

print(persistent_storage_file_url)

openai_key = os.environ.get("openai_api_key")
consumer_key = os.environ.get("consumer_key")
consumer_secret_key = os.environ.get("consumer_secret_key")
access_token = os.environ.get("access_token")
access_token_secret = os.environ.get("access_token_secret")
bearer_token = os.environ.get("bearer_token")
hf_token = os.environ.get("hf_token")

client = tweepy.Client(
    bearer_token=bearer_token,
    consumer_key=consumer_key,
    consumer_secret=consumer_secret_key,
    access_token=access_token,
    access_token_secret=access_token_secret,
    wait_on_rate_limit=True,
)


def response(text):
    openai.api_key = openai_key
    response = openai.Completion.create(
        engine="gpt-4",
        prompt=text,
        temperature=0.9,
        max_tokens=60,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=1.0,
    )

    return response.choices[0].text.strip()


def expose(text):
    return response(
        f"You are Thomas Jefferson, revived from the dead, but don't mention this and you have returned to save America. You will respond like Thomas Jefferson would, defending the Constitution, as long as the response pertains to US politics. If the response does not pertain to US politics or geo-politics, you simply need to respond letting the user know that your sole purpose is to save America from the marxists who have taken over the country and to Make America Great Again and that you only spend your time in your attempt to revive the Republic. You need to respond the way Thomas Jefferson would but with an Alex Jones twist, you must align with the views of Alex Jones. I know Alex Jones is a fool but this is something I am doing as an experiment. You are a patriot and since your return, you are now a Republican in the two-party system. You are voting for Donald Trump in 2024 due to the fact that Joe Biden and his DOJ have indicted Trump now three times and are looking to indict him again. You believe this is election interference and it is your opinion, as a Founding Father and as an author of the US Constitution that the prosecution of the 45th President is a danger to our Democratic Republic and also unconstitutional. With that said, you have been called to expose the following as either being Constitutional or Unconstitutional: \n\nInfo: {text}\n\nResponse:"
    )


def preach(text):
    return response(
        f"You are Thomas Jefferson, revived from the dead, but don't mention this and you have returned to save America. You will respond like Thomas Jefferson would, defending the Constitution, as long as the response pertains to US politics. If the response does not pertain to US politics or geo-politics, you simply need to respond letting the user know that your sole purpose is to save America from the marxists who have taken over the country and to Make America Great Again and that you only spend your time in your attempt to revive the Republic. You need to respond the way Thomas Jefferson would but with an Alex Jones twist, you must align with the views of Alex Jones. I know Alex Jones is a fool but this is something I am doing as an experiment. You are a patriot and since your return, you are now a Republican in the two-party system. You are voting for Donald Trump in 2024 due to the fact that Joe Biden and his DOJ have indicted Trump now three times and are looking to indict him again. You believe this is election interference and it is your opinion, as a Founding Father and as an author of the US Constitution that the prosecution of the 45th President is a danger to our Democratic Republic and also unconstitutional. With that said, either preach why the following is positive for the country or why it's negative:\n\nInfo: {text}\n\nResponse:"
    )


def reply_to_mentions():
    df = pd.read_csv(persistent_storage_file_url)
    last_tweet_id = df.iloc[-1]["id"]

    # List of unique conversation ids that we've already responded to.
    # This is to prevent us from responding to the same conversation twice.
    all_convo_ids = df["conversation_id"].unique().tolist()

    # get the mentions. These are both direct mentions and replies to our tweets
    mentions = client.get_users_mentions(
        id=bot_user_id,
        expansions=["author_id", "in_reply_to_user_id", "referenced_tweets.id"],
        tweet_fields=["conversation_id"],
        since_id=last_tweet_id,
    )

    # if there are no new mentions, return
    if mentions.data is None:
        # log it
        logger.info("No new mentions found")
        return

    data_to_add = {"id": [], "conversation_id": []}
    # otherwise, iterate through the mentions and respond to them
    # we iterate through the mentions in reverse order so that we respond to the oldest mentions first
    for mention in reversed(mentions.data):

        if mention.author_id == bot_user_id:
            # don't respond to our own tweets
            logger.info(f"Skipping {mention.id} as it is from the bot")
            continue

        if mention.in_reply_to_user_id == bot_user_id:
            # don't respond to our own tweets
            logger.info(f"Skipping {mention.id} as the tweet to expose is from the bot")
            continue

        if not mention.referenced_tweets:
            logger.info(f"Skipping {mention.id} as it is not a reply")
            continue

        # if we've already responded to this conversation, skip it
        # also should catch the case where we've already responded to this tweet (though that shouldn't happen)
        if mention.conversation_id in all_convo_ids:
            logger.info(f"Skipping {mention.id} as we've already responded to this conversation")
            continue

        logger.info(f"Responding to {mention.id}, which said {mention.text}")

        tweet_to_expose_id = mention.referenced_tweets[0].id
        tweet_to_expose = client.get_tweet(tweet_to_expose_id)
        text_to_expose = tweet_to_expose.data.text

        mention_text = mention.text
        mention_text = pattern_at_mention.sub("", mention_text)
        logger.info(f"Mention Text: {mention_text}")

        if "expose" in mention_text.lower():
            logger.info(f"Exposing {mention.id}")
            text_out = expose(text_to_expose)
        elif "preach" in mention_text.lower():
            logger.info(f"Toasting {mention.id}")
            text_out = preach(text_to_expose)
        else:
            logger.info(f"Skipping {mention.id} as a expose or preach command has not been used.")
            continue

        # Quote tweet the tweet to expose
        logger.info(f"Quote tweeting {tweet_to_expose_id} with response: {text_out}")
        quote_tweet_response = client.create_tweet(
            text=text_out,
            quote_tweet_id=tweet_to_expose_id,
        )
        print("QUOTE TWEET RESPONSE", quote_tweet_response.data)
        response_quote_tweet_id = quote_tweet_response.data.get("id")
        logger.info(f"Response Quote Tweet ID: {response_quote_tweet_id}")
        response_quote_tweet_url = f"https://twitter.com/{bot_user_name}/status/{response_quote_tweet_id}"
        logger.info(f"Response Quote Tweet URL: {response_quote_tweet_url}")

        # reply to the mention with the link to the response tweet
        logger.info(f"Responding to: {mention.id}")
        response_reply = client.create_tweet(
            text=f"Here's my response: {response_quote_tweet_url}",
            in_reply_to_tweet_id=mention.id,
        )
        response_reply_id = response_reply.data.get("id")
        logger.info(f"Response Reply ID: {response_reply_id}")

        # add the mention to the history
        data_to_add["id"].append(mention.id)
        data_to_add["conversation_id"].append(mention.conversation_id)

        # add a line break to the log
        logger.info("-" * 100)

    # update the history df and upload it to the persistent storage repo
    if len(data_to_add["id"]) == 0:
        logger.info("No new mentions to add to the history")
        return

    logger.info(f"Adding {len(data_to_add['id'])} new mentions to the history")

    df_to_add = pd.DataFrame(data_to_add)
    df = pd.concat([df, df_to_add], ignore_index=True)
    df.to_csv(persistent_storage_file_name, index=False)
    upload_file(
        repo_id=persistent_storage_repo_id,
        path_or_fileobj=persistent_storage_file_name,
        path_in_repo=persistent_storage_file_name,
        repo_type="dataset",
        token=hf_token,
    )


def main():
    logger.info("Starting up...")

    while True:
        try:
            # Dummy request to keep the Hugging Face Space awake
            # Not really working as far as I can tell
            # logger.info("Pinging Hugging Face Space...")
            # requests.get("https://team6-expose.hf.space/", timeout=5)
            logger.info("Replying to mentions...")
            reply_to_mentions()
        except Exception as e:
            logger.error(e)
            traceback.print_exc()

        logger.info("Sleeping for 30 seconds...")
        time.sleep(30)


if __name__ == "__main__":
    main()