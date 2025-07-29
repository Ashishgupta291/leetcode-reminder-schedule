from dotenv import load_dotenv
import requests
import psycopg2
import os
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import ssl

load_dotenv()

# Email config from environment
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

# DB URL from environment
DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DB_URL, sslmode='require')

def get_today_challenge_title():
    url = "https://leetcode.com/graphql"
    payload = {
        "operationName": "questionOfToday",
        "query": """
        query questionOfToday {
          activeDailyCodingChallengeQuestion {
            question {
              title
              titleSlug
            }
          }
        }
        """,
        "variables": {}
    }
    headers = {"Content-Type": "application/json"}
    res = requests.post(url, json=payload, headers=headers)
    return res.json()['data']['activeDailyCodingChallengeQuestion']['question']['titleSlug']

def has_solved_today(username, today_slug):
    url = "https://leetcode.com/graphql"
    payload = {
        "operationName": "recentAcSubmissions",
        "variables": {"username": username, "limit": 20},
        "query": """
        query recentAcSubmissions($username: String!, $limit: Int!) {
          recentAcSubmissionList(username: $username, limit: $limit) {
            titleSlug
            timestamp
          }
        }
        """
    }
    res = requests.post(url, json=payload)
    subs = res.json()['data']['recentAcSubmissionList']
    today = datetime.utcnow().date()
    for sub in subs:
        sub_date = datetime.utcfromtimestamp(int(sub['timestamp'])).date()
        if sub_date == today and sub['titleSlug'] == today_slug:
            return True
    return False

def send_reminder_email(recipient_email, username):
    subject = "⏰ LeetCode Daily Challenge Reminder"
    body = f"""
    <html>
    <body>
      <p>Hi {username},</p>
      <p>You haven’t completed today’s LeetCode daily challenge yet.</p>
      <p><a href='https://leetcode.com/problemset/all/'>Go solve it now »</a></p>
    </body>
    </html>
    """
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = SENDER_EMAIL
    message["To"] = recipient_email
    message.attach(MIMEText(body, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_email, message.as_string())

def check_all_users():
    now = datetime.utcnow().time().replace(second=0, microsecond=0)
    five_min_ago = (datetime.utcnow() - timedelta(minutes=5)).time().replace(second=0, microsecond=0)

    try:
        conn = get_connection()
        c = conn.cursor()

        if five_min_ago <= now:
            # Normal case: same day
            c.execute("""
                SELECT u.email, s.leetcode_username
                FROM schedules s
                JOIN users u ON s.user_id = u.id
                WHERE s.utc_time BETWEEN %s AND %s
            """, (five_min_ago, now))
        else:
            # Wrap-around midnight case: split the range
            c.execute("""
                SELECT u.email, s.leetcode_username
                FROM schedules s
                JOIN users u ON s.user_id = u.id
                WHERE s.utc_time >= %s OR s.utc_time <= %s
            """, (five_min_ago, now))

        users = c.fetchall()

        today_slug = get_today_challenge_title()

        for email, username in users:
            try:
                if not has_solved_today(username, today_slug):
                    send_reminder_email(email, username)
                    print(f"📩 Sent reminder to {username}")
                else:
                    print(f"✅ {username} already solved today’s challenge.")
            except Exception as e:
                print(f"❌ Error processing {username}: {e}")

    except Exception as db_err:
        print(f"❌ DB error: {db_err}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    check_all_users()  # ← Only run once per GitHub Action trigger
