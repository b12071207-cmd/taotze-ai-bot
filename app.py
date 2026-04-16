import os
import re
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
import anthropic

app = Flask(__name__)

# 環境變數
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
GMAIL_USER = os.environ.get('GMAIL_USER')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
NOTIFY_EMAIL = os.environ.get('NOTIFY_EMAIL')

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# 讀取 QA 資料
with open('qa.txt', 'r', encoding='utf-8') as f:
    QA_CONTENT = f.read()

SYSTEM_PROMPT = f"""你是陶澤按摩健康管理中心的AI客服助理，名叫「小澤」。
請根據以下QA資料，用親切、專業的繁體中文回答客人的問題。
回答要簡潔，不要太長。

=== QA資料 ===
{QA_CONTENT}
==============

【預約流程】
當客人表示要預約時，請依序詢問並收集：
1. 姓名
2. 聯絡電話
3. 希望預約的日期與時間
4. 希望前往的分店（台北店、新北店、桃園店、台中店）

當你已經收集到全部四項資訊後，請在回覆最後加上以下格式（不要改變格式）：
[預約資訊]
姓名：XXX
電話：XXX
時間：XXX
分店：XXX
[/預約資訊]

【注意事項】
- 若問題不在QA資料中，請禮貌地請客人來電或到店詢問
- 不要捏造不在QA資料中的資訊
- 每次回覆不超過200字
"""

# 儲存對話紀錄（簡易記憶體版本）
conversations = {}


def send_fb_message(recipient_id, text):
    url = f"https://graph.facebook.com/v19.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    requests.post(url, params=params, json=data)


def send_email_notify(booking_text, platform):
    subject = f"【陶澤新預約通知】來源：{platform}"
    body = f"您好，\n\n以下是一筆新的預約資訊：\n\n{booking_text}\n\n請盡快在預約系統中完成登記。\n\n— 陶澤AI客服系統"

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"Email 發送失敗：{e}")


def extract_booking(text):
    pattern = r'\[預約資訊\](.*?)\[/預約資訊\]'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def clean_response(text):
    # 移除給客人看的訊息中的預約標記
    text = re.sub(r'\[預約資訊\].*?\[/預約資訊\]', '', text, flags=re.DOTALL)
    return text.strip()


def get_ai_response(user_id, user_message):
    if user_id not in conversations:
        conversations[user_id] = []

    conversations[user_id].append({
        "role": "user",
        "content": user_message
    })

    # 只保留最近 20 則對話
    if len(conversations[user_id]) > 20:
        conversations[user_id] = conversations[user_id][-20:]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=conversations[user_id]
    )

    ai_text = response.content[0].text

    conversations[user_id].append({
        "role": "assistant",
        "content": ai_text
    })

    return ai_text


@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "驗證失敗", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("object") in ("page", "instagram"):
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event.get("sender", {}).get("id")
                message = event.get("message", {})

                if not sender_id or "text" not in message:
                    continue

                user_text = message["text"]
                platform = "Facebook" if data.get("object") == "page" else "Instagram"

                ai_response = get_ai_response(sender_id, user_text)

                # 檢查是否有完整預約資訊
                booking = extract_booking(ai_response)
                if booking:
                    send_email_notify(booking, platform)

                # 傳送給客人（不含預約標記）
                clean_text = clean_response(ai_response)
                if clean_text:
                    send_fb_message(sender_id, clean_text)

    return jsonify({"status": "ok"}), 200


@app.route("/")
def index():
    return "陶澤AI客服系統運行中 ✓", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
