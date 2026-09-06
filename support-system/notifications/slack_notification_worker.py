import os
import json
import redis
import requests
import time
from dotenv import load_dotenv

load_dotenv(override=True)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

def main():
    if not SLACK_WEBHOOK_URL:
        print("ERROR: Missing SLACK_WEBHOOK_URL env variable")
        return 

    print("Notification worker started. Waiting for HITL approval requests...")

    while True:
        try:
            #brpop blocks until an item is available in 'operator_notifications'
            #It returns a tuple: (queue_name, message_data)
            result = redis_client.brpop("operator_notifications", timeout=5)

            if result:
                queue_name, message_data = result
                notification = json.loads(message_data)
                
                #format the message for slack
                send_slack_notification(notification)

        except Exception as e:
            print(f"[Worker] Error processing notification: {e}")
            time.sleep(5)

def send_slack_notification(notification: dict):
    """
    Formats the notificaion dictionary and sends an HTTP POST to slack.
    """
    if not SLACK_WEBHOOK_URL:
        print("ERROR: SLACK_WEBHOOK_URL is not configured.")
        return

    session_id = notification.get("session_id", "Unkown")
    risk_level = notification.get("risk_level", "Medium").upper()
    checkpoint_id = notification.get("checkpoint_id", "Unkown")

    #slack formatting block
    slack_payload = {
        "text": f":rotating_light: *HITL Approval Required* :rotating_light:\n"
                f"Risk Level: {risk_level}\n"
                f"Session ID: `{session_id}`\n"
                f"Checkpoint_id: `{checkpoint_id}`\n\n"
                f"Please review this action in the dashboard."
    }

    #send the HTTP to slack
    response = requests.post(
        SLACK_WEBHOOK_URL,
        json = slack_payload,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        print(f"Failed to send slack notification: {response.status_code} {response.text}")
    else:
        print(f"Sucessfully sent Slack notification for session: {session_id}")

if __name__ == "__main__":
    main()

#Run this script in the background: uv run python support-system/notifications/slack_notification_worker.py
#This will run indefinitely, monitoring the operator_notifications queue. 
#The script is blocking, so it should run in a separate terminal or as a background service.
#You can stop it with Ctrl+C.