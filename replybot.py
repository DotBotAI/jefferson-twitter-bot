import base64
import hashlib
import os
import re
import json
import requests
import dbm
import ast
import openai
import datetime
import pytz


from dotenv import load_dotenv
load_dotenv()

from flask_apscheduler import APScheduler
from requests.auth import AuthBase, HTTPBasicAuth
from requests_oauthlib import OAuth2Session, TokenUpdated
from flask import Flask, request, redirect, session, url_for, render_template


class Config:
    SCHEDULER_API_ENABLED = True


app = Flask(__name__)
app.secret_key = os.urandom(50)

scheduler = APScheduler()


client_id = os.environ.get("CLIENT_ID")
client_secret = os.environ.get("CLIENT_SECRET")
# Add OpenAI API key to environment variables
openai.api_key = os.environ.get("OPENAI_API_KEY")
bearer_token = os.environ.get("BEARER_TOKEN")

auth_url = "https://twitter.com/i/oauth2/authorize"
token_url = "https://api.twitter.com/2/oauth2/token"
redirect_uri = os.environ.get("REDIRECT_URI")

scopes = ["tweet.read", "users.read", "tweet.write", "offline.access"]

code_verifier = base64.urlsafe_b64encode(os.urandom(30)).decode("utf-8")
code_verifier = re.sub("[^a-zA-Z0-9]+", "", code_verifier)

code_challenge = hashlib.sha256(code_verifier.encode("utf-8")).digest()
code_challenge = base64.urlsafe_b64encode(code_challenge).decode("utf-8")
code_challenge = code_challenge.replace("=", "")

def make_token(token=None):
    return OAuth2Session(client_id, token=token, redirect_uri=redirect_uri, scope=scopes)

def generate_tweet(incoming_tweet):
    # Define the conversation

    print("Generating tweet")
    print(incoming_tweet)

    conversation = [
        {"role": "system", "content": "You are Karen, a mid 50s single professional woman. You do not have significant career achievements but have typically survived by not being noticed or responsible for anything of consequence. You are an adjunct professor of humanities in a mid tier academic institution. You will respond in tweets by framing the conversation around diversity, equal opportunity for women and minorities. There will always be an element of snark and disappointment to your responses. Make sure to keep your responses relevant to the users messages."},
        {"role": "user", "content": incoming_tweet}
    ]
    
    # Call the OpenAI API
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=conversation
    )
    
    # Get the content of the assistant's message
    tweet = completion.choices[0].message['content']

    # Remove any references to the bot user handle
    tweet = re.sub(r'@msdiversity2023', '', tweet, flags=re.I)

    # Ensure the generated tweet is not longer than 280 characters
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."  # truncate and add an ellipsis
    
    return tweet

def post_tweet(payload, token, reply_to_id):
    print("Tweeting!")
    print(reply_to_id)
    payload.update({"reply": {"in_reply_to_tweet_id": reply_to_id}})  # add reply to status id
    return requests.request(
        "POST",
        "https://api.twitter.com/2/tweets",
        json=payload,
        headers={
            "Authorization": "Bearer {}".format(token["access_token"]),
            "Content-Type": "application/json",
        },
    )


def bearer_oauth(r):
    """
    Method required by bearer token authentication.
    """
    r.headers["Authorization"] = f"Bearer {bearer_token}"
    r.headers["User-Agent"] = "v2UserMentionsPython"
    return r


def get_tweet_text(conversation_id):
    response = requests.get(
        f"https://api.twitter.com/2/tweets/{conversation_id}",
        params={"tweet.fields": "text"},
        auth=bearer_oauth
    )

    if response.status_code != 200:
        raise Exception(
            "Cannot get tweet (HTTP {}): {}".format(
                response.status_code, response.text
            )
        )

    response_json = response.json()

    print("I am now getting the content of the original tweet")
    
    if 'data' in response_json:
        tweet_text = response_json['data']['text']
        print(tweet_text)
        return tweet_text
    else:
        print("Unable to retrieve tweet text.")
        return None
    
def get_user_id(username):
    response = requests.get(
        f"https://api.twitter.com/2/users/by/username/{username}",
        auth=bearer_oauth
    )
    if response.status_code != 200:
        raise Exception(
            f"Cannot get user (HTTP {response.status_code}): {response.text}"
        )
    return response.json()["data"]["id"]

def get_followers(user_id):
    response = requests.get(
        f"https://api.twitter.com/2/users/{user_id}/followers",
        auth=bearer_oauth
    )

    if response.status_code != 200:
        raise Exception(
            "Cannot get followers (HTTP {}): {}".format(
                response.status_code, response.text
            )
        )

    response_json = response.json()

    print("I am now getting the list of followers for user")

    if 'data' in response_json:
        followers = [user['id'] for user in response_json['data']]
        print(followers)
        return followers
    else:
        print("Unable to retrieve followers.")
        return None

def get_mentions(user_id):
    utc_now = datetime.datetime.now(pytz.UTC)  # get the current UTC time
    start_time = (utc_now - datetime.timedelta(seconds=60)).strftime('%Y-%m-%dT%H:%M:%SZ')  # get the time 60 seconds ago in the correct format

    response = requests.get(
        f"https://api.twitter.com/2/users/{user_id}/mentions",
        params={"start_time": start_time, "tweet.fields": "conversation_id"},
        auth=bearer_oauth
    )

    if response.status_code != 200:
        raise Exception(
            "Cannot get mentions (HTTP {}): {}".format(
                response.status_code, response.text
            )
        )

    response_json = response.json()

    if 'data' in response_json:
        mention_data = response_json['data']
        return mention_data
    else:
        print("No 'data' field found in the response.")
        return None

    
# Print User ID
username = "msdiversity2023"
user_id = get_user_id(username)
print(f"User ID of @msdiversity2023: {user_id}")
# followers = get_followers(user_id)
# print(followers)

@scheduler.task('interval', id='everyother', seconds=60)
def every_other():
    db = dbm.open(".my_store", "c")
    t = db["token"]
    bb_t = t.decode("utf8").replace("'", '"')
    data = ast.literal_eval(bb_t)
    twitter = make_token()
    refreshed_token = twitter.refresh_token(
        token_url=token_url,
        auth=HTTPBasicAuth(client_id, client_secret),
        refresh_token=data["refresh_token"],
    )
    st_refreshed_token = '"{}"'.format(refreshed_token)
    j_refreshed_token = json.loads(st_refreshed_token)
    db["token"] = j_refreshed_token

    mentions = get_mentions(user_id)

    if mentions is not None:
        for mention in mentions:

            mention_id = mention['id']
            conversation_id = mention.get('conversation_id', None)

            if conversation_id and mention_id == conversation_id:
                mention_text = mention['text']
                print("Seems like a brand new tweet")
                print(mention_text)
            elif conversation_id:
                mention_text = get_tweet_text(conversation_id)
                print("Seems like a reply tag tweet")
                print(mention_text)
            else:
                print("Conversation ID not found in the response.")
                continue
            
            tweet = generate_tweet(mention_text)
            payload = {"text": "{}".format(tweet)}
            response = post_tweet(payload, refreshed_token, mention_id)  # include the mention id
            print(response.text)

    
@app.route("/")
def hello():
    return render_template("index.html")


@app.route("/start")
def demo():
    global twitter
    twitter = make_token()
    authorization_url, state = twitter.authorization_url(
        auth_url, code_challenge=code_challenge, code_challenge_method="S256"
    )
    session["oauth_state"] = state
    return redirect(authorization_url)


@app.route("/oauth/callback", methods=["GET"])
def callback():
    code = request.args.get("code")
    token = twitter.fetch_token(
        token_url=token_url,
        client_secret=client_secret,
        code_verifier=code_verifier,
        code=code,
    )
    st_token = '"{}"'.format(token)
    j_token = json.loads(st_token)
    with dbm.open(".my_store", "c") as db:
        db["token"] = j_token
        return render_template("thank-you.html") 
    


if __name__ == "__main__":
  app.config.from_object(Config())
  scheduler.init_app(app)
  scheduler.start()
  app.run()