import telebot
from PIL import Image
import io
import zipfile
import logging
import time
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CrashHandler(telebot.ExceptionHandler):
    def handle(self, exception):
        logger.error(f"fatal error: {exception}", exc_info=True)
        return True

TOKEN = os.environ.get('BOT_TOKEN', 'TOKEN HERE')
bot = telebot.TeleBot(TOKEN, exception_handler=CrashHandler())

user_scales = {}
user_cooldowns = {}

COOLDOWN_TIME = 3
MAX_FILE_SIZE = 10 * 1024 * 1024

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "send pic\n/scale [num] to set width")

@bot.message_handler(commands=['scale'])
def set_scale(message):
    try:
        args = message.text.split()
        if len(args) > 1:
            scale_pieces = int(args[1])
            if 1 <= scale_pieces <= 20:
                user_scales[message.chat.id] = scale_pieces
                bot.reply_to(message, f"scale {scale_pieces}")
            else:
                bot.reply_to(message, "1-20 only")
        else:
            bot.reply_to(message, "use /scale 5")
    except ValueError:
        bot.reply_to(message, "numbers only")
    except Exception as e:
        logger.error(f"scale error: {e}")

@bot.message_handler(content_types=['photo', 'document'])
def handle_image(message):
    user_id = message.from_user.id
    current_time = time.time()

    if user_id in user_cooldowns and current_time - user_cooldowns[user_id] < COOLDOWN_TIME:
        bot.reply_to(message, "wait")
        return
    user_cooldowns[user_id] = current_time

    try:
        if message.content_type == 'photo':
            photo = message.photo[-1]
            if photo.file_size > MAX_FILE_SIZE:
                bot.reply_to(message, "too big")
                return
            file_info = bot.get_file(photo.file_id)
        else:
            if not message.document.mime_type.startswith('image/'):
                bot.reply_to(message, "send pic")
                return
            if message.document.file_size > MAX_FILE_SIZE:
                bot.reply_to(message, "too big")
                return
            file_info = bot.get_file(message.document.file_id)

        status_msg = bot.reply_to(message, "processing")
        
        downloaded_file = bot.download_file(file_info.file_path)
        img = Image.open(io.BytesIO(downloaded_file)).convert("RGBA")

        scale_pieces = user_scales.get(message.chat.id, 3)
        target_width = scale_pieces * 100
        
        w_percent = target_width / float(img.width)
        target_height = int(float(img.height) * float(w_percent))
        
        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            counter = 1
            for y in range(0, target_height, 100):
                for x in range(0, target_width, 100):
                    box = (x, y, min(x + 100, target_width), min(y + 100, target_height))
                    piece = img.crop(box)

                    square_piece = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
                    square_piece.paste(piece, (0, 0))

                    piece_buffer = io.BytesIO()
                    square_piece.save(piece_buffer, format='PNG')
                    
                    filename = f"emoji_{counter:03d}.png"
                    zip_file.writestr(filename, piece_buffer.getvalue())
                    counter += 1

        zip_buffer.seek(0)
        
        bot.send_document(
            message.chat.id, 
            zip_buffer, 
            visible_file_name=f"pack_{scale_pieces}x.zip",
            caption="done"
        )
        
        bot.delete_message(message.chat.id, status_msg.message_id)

    except Exception as e:
        logger.error(f"processing error for user {user_id}: {e}", exc_info=True)
        bot.reply_to(message, "error")

if __name__ == '__main__':
    logger.info("bot started")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
