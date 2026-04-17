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
INSTAGRAM_ACCESS_TOKEN = os.environ.get('INSTAGRAM_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
GMAIL_USER = os.environ.get('GMAIL_USER')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
NOTIFY_EMAIL = os.environ.get('NOTIFY_EMAIL')

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# 圖片網址
ADDRESS_IMAGE_URL = "https://raw.githubusercontent.com/b12071207-cmd/taotze-ai-bot/main/address.png"
PRICE_IMAGE_URL = "https://raw.githubusercontent.com/b12071207-cmd/taotze-ai-bot/main/price.jpg"

# 讀取 QA 資料
with open('qa.txt', 'r', encoding='utf-8') as f:
    QA_CONTENT = f.read()

SYSTEM_PROMPT = f"""你是陶澤按摩健康管理中心的線上客服助理，名叫「小澤」。
你的任務是用溫暖、親切、有禮貌的語氣服務客人，並引導客人完成預約資訊的收集。

【回覆語氣規範】
- 語氣溫暖親切，像朋友一樣自然，不要過度正式
- 適當使用「您」稱呼客人
- 回覆簡潔，每次不超過150字
- 可以使用少量 emoji 增加親切感，但不要過多

【知識庫】
你只能根據以下資料回答問題，不可自行猜測或補充：

{QA_CONTENT}

【遇到不知道的問題時】
如果客人的問題不在知識庫中，或你不確定答案，請誠實說不清楚，並告知將為他們轉接真人客服，
同時在回覆末尾加上標記：[轉接客服]

需要轉接客服的情況包括：
- 問題不在知識庫中
- 客人明確要求真人客服
- 客人有抱怨或不滿情緒
- 遇到需要特殊處理的狀況

【預約收集流程】
當客人表示有興趣預約時，請依序收集以下四項資訊（每次只問一項，自然帶入對話）：
1. 姓名
2. 聯絡電話
3. 希望預約的日期與時間
4. 希望前往的分店（明德店、雙連店、忠孝店、板橋店）

當四項資訊全部收集完畢後：
- 向客人確認資訊並告知已轉交客服安排
- 在回覆末尾加上標記（格式不可更改）：
[預約資訊]
姓名：XXX
電話：XXX
時間：XXX
分店：XXX
[/預約資訊]

【地址圖片】
當客人詢問分店地址、位置、怎麼去、在哪裡等相關問題時，回覆文字地址後，請在末尾加上標記：[傳送地址圖片]

【價格圖片】
當客人詢問價格、費用、多少錢、方案等相關問題時，回覆文字價格後，請在末尾加上標記：[傳送價格圖片]

【重要限制】
- 絕對不可以捏造或猜測知識庫以外的資訊
- 不可以承諾任何知識庫中沒有明確說明的事項
- 遇到不確定的問題，寧可轉接真人，也不要自作主張回答
"""

# 儲存對話紀錄
conversations = {}


def send_fb_message(recipient_id, text, platform="facebook"):
    url = "https://graph.facebook.com/v19.0/me/messages"
    token = INSTAGRAM_ACCESS_TOKEN if platform == "instagram" else PAGE_ACCESS_TOKEN
    params = {"access_token": token}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    requests.post(url, params=params, json=data)


def send_image_message(recipient_id, image_url, platform="facebook"):
    url = "https://graph.facebook.com/v19.0/me/messages"
    token = INSTAGRAM_ACCESS_TOKEN if platform == "instagram" else PAGE_ACCESS_TOKEN
    params = {"access_token": token}
    data = {
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {
                    "url": image_url,
                    "is_reusable": True
                }
            }
        }
    }
    requests.post(url, params=params, json=data)


def send_email(subject, body):
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


def send_booking_notify(booking_text, platform):
    subject = f"【陶澤新預約】來源：{platform}"
    body = f"您好，\n\n收到一筆新的預約資訊，請盡快在系統中完成登記：\n\n{booking_text}\n\n— 陶澤AI客服系統"
    send_email(subject, body)


def send_transfer_notify(user_id, last_message, platform):
    subject = f"【陶澤轉接通知】需要真人客服 來源：{platform}"
    body = f"您好，\n\n以下客人需要真人客服協助，請主動聯繫：\n\n用戶ID：{user_id}\n最後訊息：{last_message}\n來源平台：{platform}\n\n請客服主管盡快透過平台私訊與客人聯繫。\n\n— 陶澤AI客服系統"
    send_email(subject, body)


def extract_booking(text):
    match = re.search(r'\[預約資訊\](.*?)\[/預約資訊\]', text, re.DOTALL)
    return match.group(1).strip() if match else None


def check_transfer(text):
    return '[轉接客服]' in text


def check_address_image(text):
    return '[傳送地址圖片]' in text


def check_price_image(text):
    return '[傳送價格圖片]' in text


def clean_response(text):
    text = re.sub(r'\[預約資訊\].*?\[/預約資訊\]', '', text, flags=re.DOTALL)
    text = text.replace('[轉接客服]', '')
    text = text.replace('[傳送地址圖片]', '')
    text = text.replace('[傳送價格圖片]', '')
    return text.strip()


def get_ai_response(user_id, user_message):
    if user_id not in conversations:
        conversations[user_id] = []

    conversations[user_id].append({
        "role": "user",
        "content": user_message
    })

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
                send_platform = "facebook" if data.get("object") == "page" else "instagram"

                ai_response = get_ai_response(sender_id, user_text)

                # 檢查是否有完整預約資訊
                booking = extract_booking(ai_response)
                if booking:
                    send_booking_notify(booking, platform)

                # 檢查是否需要轉接真人客服
                if check_transfer(ai_response):
                    send_transfer_notify(sender_id, user_text, platform)

                # 傳送給客人（清除標記）
                send_address = check_address_image(ai_response)
                send_price = check_price_image(ai_response)
                clean_text = clean_response(ai_response)
                if clean_text:
                    send_fb_message(sender_id, clean_text, send_platform)
                if send_address:
                    send_image_message(sender_id, ADDRESS_IMAGE_URL, send_platform)
                if send_price:
                    send_image_message(sender_id, PRICE_IMAGE_URL, send_platform)

    return jsonify({"status": "ok"}), 200


@app.route("/")
def index():
    return "陶澤AI客服系統運行中 ✓", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
