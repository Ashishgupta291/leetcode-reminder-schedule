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

# Email config
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

# DB URL
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
    try:
        subs = res.json().get('data', {}).get('recentAcSubmissionList', [])
        if subs is None:  # in case data is null
            return False
    except Exception as e:
        print(f"Error for user {username}: {e}")
        return False
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
    today_date = datetime.utcnow().date()
    current_time = datetime.utcnow().time().replace(second=0, microsecond=0)

    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT s.id, u.email, s.leetcode_username
            FROM schedules s
            JOIN users u ON s.user_id = u.id
            WHERE (s.last_execution_date IS NULL OR s.last_execution_date < %s)
              AND s.utc_time <= %s;
        """, (today_date, current_time))

        users = c.fetchall()
        today_slug = get_today_challenge_title()

        for schedule_id, email, username in users:
            try:
                if not has_solved_today(username, today_slug):
                    send_reminder_email(email, username)
                    print(f"📩 Sent reminder to {username}")
                else:
                    print(f"✅ {username} already solved today’s challenge.")
                
                # Update last_execution_date regardless of email sent or not
                c.execute("""
                    UPDATE schedules
                    SET last_execution_date = %s
                    WHERE id = %s;
                """, (today_date, schedule_id))
                conn.commit()

            except Exception as e:
                print(f"❌ Error processing {username}: {e}")

    except Exception as db_err:
        print(f"❌ DB error: {db_err}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_all_users()

