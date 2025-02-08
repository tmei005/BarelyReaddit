from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS  # Import CORS
import praw
from textblob import TextBlob
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

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

# TODO : Include overarching topic summary
def summarize(text, type, image=None):
    """
    Summarizes the given message
    """

    if type == "post":
        system_instruction="Provide a concise summary of the post and focus on key points and main ideas:"
    elif type == "topic":
        system_instruction="Provide a concise summary of the list of posts provided and focus on key points and main ideas that correlate to the overarching topic:"

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
        system_instruction=["Summarize the following inputted message:"]),
        contents=[text]
    )
    return response.text
    
def fetch_post_info(topic, sort='hot', limit=5):
    """
    Fetch Reddit posts based on a topic.
    """
    posts_info = []

    aggregate_polarity = 0
    aggregate_subjectivity = 0

    image_extensions = [".jpeg", ".png"]

    # TODO: check if the post has an image or not, find a way to analyze it and include it in the summary
    for submission in reddit.subreddit('all').search(topic, sort, limit=limit):
        title = submission.title
        full_text = title + " " + submission.selftext
        url = submission.url

        message = TextBlob(full_text)

        polarity = message.sentiment.polarity
        subjectivity = message.sentiment.subjectivity

        # has_media_metadata = False
        # if hasattr(submission, 'media_metadata'):
        #     has_media_metadata = True

        # # specifically for content posts
        # if(submission.selftext == ""):
        #     if has_media_metadata:
        #         for image_data in submission.media_metadata:
        #             image_url = image_data["s"]["u"]  
        #             print(f"Image URL: {image_url}") 
        #     # summary = summarize(full_text)
        # else:

        # CASES: gallery (slideshow of photos), external link to a news article
        # photo image, or video

        summary = summarize(full_text, "post")
        # print(summary)

        aggregate_polarity += polarity
        aggregate_subjectivity += subjectivity
        
        post_data = {
            "title": title,
            "url": url,
            "summary": summary,
            "polarity": polarity,
            "subjectivity": subjectivity
        }

        posts_info.append(post_data)

    aggregate_polarity = aggregate_polarity/len(posts_info)
    aggregate_subjectivity = aggregate_subjectivity/len(posts_info)
    return posts_info, aggregate_polarity, aggregate_subjectivity

print(fetch_post_info("pikachu", "new"))

def fetch_reddit_user_info(username, limit=20):
    user_info = []
    user = reddit.redditor(username)

    aggregate_polarity = 0
    aggregate_subjectivity = 0

    # Does it in order of latest -> oldest
    for comment in user.comments.new(limit=limit):
        message = TextBlob(comment.body)
        polarity = message.sentiment.polarity
        subjectivity = message.sentiment.subjectivity

        aggregate_polarity += polarity
        aggregate_subjectivity += subjectivity
        
        comment_data = {
            "polarity": polarity,
            "subjectivity": subjectivity

        }
        user_info.append(comment_data)

    aggregate_polarity = aggregate_polarity/len(user_info)
    aggregate_subjectivity = aggregate_subjectivity/len(user_info)

    return user_info, aggregate_polarity, aggregate_subjectivity

# test case:
# print(fetch_reddit_user_info("segcymf"))


# Serve the static files (HTML, CSS, JS)
@app.route('/')
def index():
    return send_from_directory('client/src', 'index.html')

@app.route('/src/<path:path>')
def static_file(path):
    return send_from_directory('client/src', path)

@app.route('/analyze', methods=['GET'])
def analyze():
    sort = 'hot'
    topic = request.args.get('topic')
    sort = request.args.get('sort')
    if not topic:
        return jsonify({"error": "Please provide a topic"}), 400
    sort = request.args.get('sort')
    if sort != 'hot':
        posts, aggregate_polarity, aggregate_subjectivity = fetch_post_info(topic, sort)
    else:
        posts, aggregate_polarity, aggregate_subjectivity = fetch_post_info(topic)
    
    return jsonify({
        'topic': topic,
        'sort': sort,
        'posts': posts,
        'aggregate_polarity': aggregate_polarity,
        'aggregate_subjectivity': aggregate_subjectivity
    })

if __name__ == '__main__':
    app.run(debug=True)