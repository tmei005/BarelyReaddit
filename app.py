from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS  # Import CORS
import praw
import datetime
import time
from textblob import TextBlob
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

import pandas as pd
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from rake_nltk import Rake
from nltk.stem import WordNetLemmatizer

from collections import Counter

app = Flask(__name__, static_folder='client/src')
CORS(app)

load_dotenv()

# Initialize Reddit API
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT")
)

# Initialize Gemini API
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

fetch_called = False

def summarize(text, type, topic):
    """
    Summarizes the given message
    """

    if type == "post":
        system_instruction=["Summarize the following inputted message directly within 2-3 sentences without mentioning the person who posted the message. Don't use filler phrases such as 'the following summarizes,' 'one user shared,' 'the next shared their,' or 'another user discussed.' Focus on the main points and experiences mentioned."]
    elif type == "topic":
        # make it better
        system_instruction = f"Briefly define the topic based on popular definitions and examples: {topic}. Then, summarize all the Reddit posts given of what the user should expect to see within 2 sentences."

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
        system_instruction=system_instruction),
        contents=[text]
    )
    return response.text

# Get popularity trend
def get_topic_popularity(topic):
    """
    Fetch post count for a given topic over the last 14 days 
    and calculate percentage change from the previous week.
    """
    end_time = time.time()
    one_week_ago = end_time - (7 * 24 * 60 * 60)
    two_weeks_ago = one_week_ago - (7 * 24 * 60 * 60)

    curr_count = 0
    last_count = 0
    for submission in reddit.subreddit("all").search(topic, sort="new"):  # Adjust limit as needed
        if one_week_ago <= submission.created_utc <= end_time:
            curr_count += 1
        elif two_weeks_ago <= submission.created_utc <= one_week_ago:
            last_count += 1
        else:
            break
    # Calculate percentage change
    if last_count > 0:
        popularity_change = ((curr_count - last_count) / last_count) * 100
    else:
        popularity_change = 0  # Avoid division by zero
    return popularity_change

def fetch_reddit_user_info(username, limit=20):
    """
    
    """
    comments = []
    subreddits = {}

    user = reddit.redditor(username)
    username = user.name
    icon_url = reddit.redditor(username).icon_img

    aggregate_polarity = 0
    aggregate_subjectivity = 0

    # Adds it in order of latest -> oldest
    for comment in user.comments.new(limit=limit):
        message = TextBlob(comment.body)

        # Retrieves the comment's polarity and subjectivity
        polarity = message.sentiment.polarity
        subjectivity = message.sentiment.subjectivity

        aggregate_polarity += polarity
        aggregate_subjectivity += subjectivity
        
        
        if comment.subreddit.display_name in subreddits:
            subreddits[comment.subreddit.display_name] += 1
        else:
            subreddits[comment.subreddit.display_name] = 1

        # Stores polarity and subjectivity of each user's comment
        comment_data = {
            "polarity": polarity,
            "subjectivity": subjectivity,
        }
        comments.append(comment_data)
    
    # Retrieves the user's top 3 most frequently subreddits they've commented on
    top_subreddits = Counter(subreddits)
    if(not top_subreddits):
        top_3_subreddits = []
    else:
        top_3_subreddits = top_subreddits.most_common(3) 
    
    # Calculates the average polarity and subjectivity of the user's comments
    user_average_polarity = aggregate_polarity/len(comments)
    user_average_subjectivity = aggregate_subjectivity/len(comments)

    return username, icon_url, top_3_subreddits, user_average_polarity, user_average_subjectivity

# Get posts
def fetch_post_info(topic, sort='hot'):
    """
    Fetch Reddit posts based on a topic.
    """
    global fetch_called

    topic_posts = []
    topic_summary = ""

    aggregate_polarity = 0
    aggregate_subjectivity = 0
    popularity_change = get_topic_popularity(topic)

    image_extensions = [".jpeg", ".png"]

    # TODO: check if the post is solely image based 
    index = 0
    for submission in reddit.subreddit('all').search(topic, sort):
        if index == 5:
            break
        if(submission.selftext != ""):
            title = submission.title
            full_text = title + " " + submission.selftext
            topic_summary += f"{index}. {full_text}"
            url = submission.url
            op = fetch_reddit_user_info(submission.author.name)

            message = TextBlob(full_text)

            polarity = message.sentiment.polarity
            subjectivity = message.sentiment.subjectivity

            summary = summarize(full_text, "post", topic)

            aggregate_polarity += polarity
            aggregate_subjectivity += subjectivity
            
            # Stores post data to dictionary
            post_data = {
                "subreddit": submission.subreddit.display_name,
                "op": op,
                "title": title,
                "url": url,
                "summary": summary,
                "polarity": polarity,
                "subjectivity": subjectivity
            }
            topic_posts.append(post_data)
            index+=1


    topic_summary = summarize(topic_summary, "topic", topic)

    fetch_called = True

    # Calculates the average polarity and subjectivity of the user's comments
    aggregate_polarity = aggregate_polarity/len(topic_posts)
    aggregate_subjectivity = aggregate_subjectivity/len(topic_posts)
    return topic_summary, topic_posts, aggregate_polarity, aggregate_subjectivity

# Serve the static files (HTML, CSS, JS)
@app.route('/')
def index():
    return send_from_directory('client/src', 'index.html')

@app.route('/src/<path:path>')
def static_file(path):
    return send_from_directory('client/src', path)

@app.route('/reset', methods=['POST'])
def reset_fetch():
    global fetch_called
    fetch_called = False

@app.route('/analyze', methods=['GET'])
def analyze():
    sort = 'hot'
    topic = request.args.get('topic')
    sort = request.args.get('sort')
    if not topic:
        return jsonify({"error": "Please provide a topic"}), 400
    sort = request.args.get('sort')
    popularity_change = get_topic_popularity(topic)
    if sort != 'hot':
        summary, posts, aggregate_polarity, aggregate_subjectivity = fetch_post_info(topic, sort)
    else:
        summary, posts, aggregate_polarity, aggregate_subjectivity = fetch_post_info(topic)
    return jsonify({
        'topic': topic,
        'sort': sort,
        'popularity_change':popularity_change,
        'posts': posts,
        'topic_summary': summary,
        'aggregate_polarity': aggregate_polarity,
        'aggregate_subjectivity': aggregate_subjectivity
    })

if __name__ == '__main__':
    app.run(debug=True)