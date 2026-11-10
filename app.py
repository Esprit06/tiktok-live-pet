import os
import threading
import time
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, CommentEvent, LikeEvent
from TikTokLive.client.errors import UserOfflineError

app = Flask(__name__, static_folder='static', template_folder='templates')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 📋 ข้อมูล 10 ร่างวิวัฒนาการ (รองรับทั้งภาพ .png และวิดีโอ .mp4)
stages_info = {
    1: ("ไข่ภูติป่า (รอฟัก)", "/static/images/stage1.png"),
    2: ("ภูติน้อยจิ๋วปีกกุด", "/static/images/stage2.png"),
    3: ("ภูติเวทมนตร์เรืองแสง", "/static/images/stage3.png"),
    4: ("ราชันภูติพฤกษา", "/static/images/stage4.png"),
    5: ("พฤกษามังกรน้อย", "/static/images/stage5.png"),
    6: ("เทพภูติแห่งแสงอาทิตย์", "/static/images/stage6.png"),
    7: ("จอมเวทย์พฤกษาโบราณ", "/static/images/stage7.png"),
    8: ("มหาพฤกษาพิทักษ์ไพร", "/static/images/stage8.png"),
    9: ("ภูติตำนานแห่งสรวงสวรรค์", "/static/images/stage9.png"),
    10: ("พระเจ้าแห่งอาณาจักรภูติ", "/static/images/stage10.png")
}

# 🏆 ระบบเก็บคะแนนผู้สนับสนุน (Top Supporters)
supporters_score = {}

def get_top_supporters():
    sorted_supporters = sorted(supporters_score.items(), key=lambda x: x[1], reverse=True)[:3]
    return [{"name": name, "score": score} for name, score in sorted_supporters]

# 🐾 สถานะสัตว์เลี้ยงเริ่มต้น
pet_state = {
    "name": "ภูติน้อยจิ๋ว",
    "stage": 1,
    "stage_name": stages_info[1][0],
    "exp": 0,
    "max_exp": 100,
    "hunger": 80,
    "health": 100,
    "status": "ไข่ใบนี้กำลังรอพลังจากทุกคนอยู่...",
    "image_url": stages_info[1][1],
    "top_supporters": []
}

TIKTOK_HANDLE = "metech_merao"
client: TikTokLiveClient = TikTokLiveClient(unique_id=TIKTOK_HANDLE)

add_exp_lock = threading.Lock()

# 🔄 ระบบ Idle 24/7: อาหารลดช้าลงตามร่าง + ระบบลดขั้นเมื่อหิว
def background_idle_engine():
    global pet_state
    while True:
        time.sleep(10)
        with add_exp_lock:
            if pet_state["stage"] <= 3:
                drain_amount = 3
            elif pet_state["stage"] <= 7:
                drain_amount = 2
            else:
                drain_amount = 1

            if pet_state["hunger"] > drain_amount:
                pet_state["hunger"] -= drain_amount
            else:
                pet_state["hunger"] = 0
                if pet_state["stage"] > 1:
                    pet_state["stage"] -= 1
                    current_stage = pet_state["stage"]
                    pet_state["stage_name"] = stages_info[current_stage][0]
                    pet_state["image_url"] = stages_info[current_stage][1]
                    pet_state["hunger"] = 50
                    pet_state["status"] = f"⚠️ หิวโซเกินไป! ถอยหลังลงสู่ร่างที่ {current_stage}!"
                else:
                    pet_state["status"] = "🥚 หิวจัดจนกลายสภาพกลับเป็นไข่เหมือนเดิม!"
        
        socketio.emit('update_pet', pet_state)

def add_exp_and_feed(amount, feed_hunger, user, action_type, gift_value=0):
    global pet_state
    with add_exp_lock:
        pet_state["exp"] += amount
        pet_state["hunger"] = min(100, pet_state["hunger"] + feed_hunger)
        pet_state["status"] = f"{user} {action_type}!"
        
        if gift_value > 0:
            if user not in supporters_score:
                supporters_score[user] = 0
            supporters_score[user] += gift_value
            
        pet_state["top_supporters"] = get_top_supporters()
        
        if pet_state["exp"] >= pet_state["max_exp"] and pet_state["stage"] < 10:
            pet_state["stage"] += 1
            pet_state["exp"] = 0
            pet_state["max_exp"] += 150
            
            current_stage = pet_state["stage"]
            pet_state["stage_name"] = stages_info[current_stage][0]
            pet_state["image_url"] = stages_info[current_stage][1]
            pet_state["status"] = f"🎉 วิวัฒนาการขึ้นสู่ร่างที่ {current_stage}: {pet_state['stage_name']}!"

@client.on(CommentEvent)
async def on_comment(event: CommentEvent):
    user = event.user.nickname
    text = event.comment.strip().lower()
    
    if text in ["!status", "!สเตตัส", "!level"]:
        status_msg = f"📊 [{pet_state['stage_name']}] EXP: {pet_state['exp']}/{pet_state['max_exp']} | ความอิ่ม: {pet_state['hunger']}%"
        socketio.emit('live_event', {'user': "System", 'text': f"🤖 บอทตอบ {user}: {status_msg}"})
        
    elif text in ["!help", "!วิธีเล่น", "!กติกา"]:
        help_msg = "💡 กติกา: พิมพ์คอมเมนต์เพื่อเพิ่ม EXP / ส่งของขวัญเพื่อเร่งวิวัฒนาการและฟื้นฟูความอิ่ม!"
        socketio.emit('live_event', {'user': "System", 'text': f"🤖 บอทตอบ {user}: {help_msg}"})
        
    else:
        add_exp_and_feed(2, 1, user, f"พิมพ์คอมเมนต์: '{event.comment}'")
        socketio.emit('live_event', {'user': user, 'text': f"💬 {user}: {event.comment}"})

@client.on(GiftEvent)
async def on_gift(event: GiftEvent):
    user = event.user.nickname
    gift_name = event.gift.name
    count = event.gift.repeat_count
    diamonds = event.gift.diamond_count * count
    add_exp_and_feed(diamonds * 2, 25, user, f"ส่งของขวัญ {gift_name} x{count}", gift_value=diamonds)
    socketio.emit('live_event', {'user': user, 'text': f"🎁 {user} ส่ง {gift_name}"})

@app.route("/simulate/comment")
def simulate_comment():
    add_exp_and_feed(10, 10, "ผู้ชมจำลอง", "ช่วยกันพิมพ์ปลุกภูติ")
    socketio.emit('update_pet', pet_state)
    socketio.emit('live_event', {'user': 'ผู้ชมจำลอง', 'text': '💬 ผู้ชมจำลอง: สู้ๆ นะภูติน้อย!'})
    return jsonify({"status": "OK"})

@app.route("/simulate/gift")
def simulate_gift():
    add_exp_and_feed(100, 40, "สายเปย์จำลอง", "ส่งมาลัยทองคำ", gift_value=50)
    socketio.emit('update_pet', pet_state)
    socketio.emit('live_event', {'user': 'สายเปย์จำลอง', 'text': '🎁 สายเปย์จำลอง ส่งมาลัยทองคำ!'})
    return jsonify({"status": "OK"})

@app.route("/simulate/status")
def simulate_status():
    status_msg = f"📊 [{pet_state['stage_name']}] EXP: {pet_state['exp']}/{pet_state['max_exp']} | ความอิ่ม: {pet_state['hunger']}%"
    socketio.emit('live_event', {'user': "System", 'text': f"🤖 บอทตอบ ผู้ชมจำลอง: {status_msg}"})
    return jsonify({"status": "OK"})

@app.route("/simulate/help")
def simulate_help():
    help_msg = "💡 กติกา: พิมพ์คอมเมนต์เพื่อเพิ่ม EXP / ส่งของขวัญเพื่อเร่งวิวัฒนาการและฟื้นฟูความอิ่ม!"
    socketio.emit('live_event', {'user': "System", 'text': f"🤖 บอทตอบ ผู้ชมจำลอง: {help_msg}"})
    return jsonify({"status": "OK"})

@app.route("/")
def index():
    pet_state["top_supporters"] = get_top_supporters()
    return render_template("index.html", pet=pet_state)

def run_tiktok_client():
    try:
        client.run()
    except UserOfflineError:
        pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    threading.Thread(target=background_idle_engine, daemon=True).start()
    threading.Thread(target=run_tiktok_client, daemon=True).start()
    print(f"🚀 Advanced 10-Stage Idle Pet Server Running on port {port}")
    socketio.run(app, host='0.0.0.0', port=port)