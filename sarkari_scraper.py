import requests
from bs4 import BeautifulSoup
import schedule
import time
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import redis
from flask import Flask, jsonify

# Flask app for health check API
app = Flask(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL")  # Your Redis URL
r = redis.from_url(REDIS_URL)  # Connecting to Redis

# Msg91 SMTP Settings
SMTP_SERVER = "smtp.mailer91.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("SENDER_EMAIL")  # Access from environment variable
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")  # Access from environment variable
EMAIL_FROM = "noreply-splitpe@shivamkmr.com"
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")  # Access from environment variable

def fetch_post_data():
    url = "https://www.sarkariresult.com/"  # Sarkari Results URL
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch data: {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    post_section = soup.find("div", id="post")
    if not post_section:
        print("No post section found on the page.")
        return None

    posts = []
    for ul in post_section.find_all("ul"):
        for li in ul.find_all("li"):
            link = li.find("a")
            if link:
                posts.append({
                    "title": link.text.strip(),
                    "url": link["href"].strip()
                })

    return posts

def load_previous_data_from_redis():
    # Get the previous data from Redis
    previous_data = r.get("sarkari_results_data")
    if previous_data:
        return json.loads(previous_data)
    return []

def save_current_data_to_redis(data):
    # Save the current data to Redis
    r.set("sarkari_results_data", json.dumps(data))

def scrape_additional_data(post_url):
    response = requests.get(post_url)
    if response.status_code != 200:
        print(f"Failed to fetch URL {post_url}: {response.status_code}")
        return None

    # Return the full HTML of the page
    return response.text

def send_email(subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("Email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")

def compare_and_report_differences(new_data, old_data):
    old_set = {json.dumps(item) for item in old_data}
    new_set = {json.dumps(item) for item in new_data}

    added = [json.loads(item) for item in new_set - old_set]
    removed = [json.loads(item) for item in old_set - new_set]

    if added:
        print("New Posts Added:")
        email_body = "New posts added:\n\n"
        for post in added:
            email_body += f"- {post['title']} ({post['url']})\n"
            # additional_data = scrape_additional_data(post['url'])
            # if additional_data:
            #     # Append the HTML data to the email body
            #     email_body += f"Additional Data:\n{additional_data}\n\n"
            
        send_email("New Posts Found", email_body)

    if removed:
        print("\nPosts Removed:")
        for post in removed:
            print(f"- {post['title']} ({post['url']})")

    if not added and not removed:
        print("No changes detected.")

def scrape_and_check():
    print("Fetching data...")
    new_data = fetch_post_data()
    if new_data is None:
        print("Skipping this run due to fetch failure.")
        return

    old_data = load_previous_data_from_redis()
    compare_and_report_differences(new_data, old_data)
    save_current_data_to_redis(new_data)

# Schedule the job to run every 5 seconds
schedule.every(5).seconds.do(scrape_and_check)

# Health check API
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "The service is running."}), 200

# Run the Flask app in a separate thread to allow the scheduler to run concurrently
if __name__ == "__main__":
    import threading

    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(1)

    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    # Run the Flask app for health check API
    app.run(host='0.0.0.0', port=5000)
