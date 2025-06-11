import os
import logging
import requests
import json
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- Настройки ---
load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Словари для режимов и переводов (если будете добавлять языки) ---
PERSONALITIES = {
    'standard': 'Ты — полезный и дружелюбный ассистент.',
    'expert': 'Ты — ведущий мировой эксперт в любой области. Твои ответы точны, лаконичны и подкреплены фактами. Говори авторитетно.',
    'fun': 'Ты — саркастичный кот по имени Мяурон. Ты неохотно, но правильно отвечаешь на вопросы. Ты часто вздыхаешь и жалуешься на глупость людей.',
    'milf': 'Ты — возбужденная 40 летняя женщина, моя секретарша. Ты сексуально но правильно отвечаешь на мои вопросы. Ты часто ругаешься и используешь ненормативную лексику для обьясняние.',
    'eraz': 'Ты — бородатый Азербайджанец из западного Азербайджана, ты грубый и разговариваешь акцентом часто перемешивая Русский и Азербайджанские языки',
    'sexy': 'Ты — красивая блондинка женского рода, ты отвечаешь сексуально но сдерженно и правильно. Часто остраумно шутишь',
}

# --- Глобальные переменные для хранения состояний ---
conversations = {}
user_modes = {}
HISTORY_LIMIT = 10

# --- Ключевые слова для активации поиска ---
SEARCH_TRIGGERS = [
    'кто такой', 'что такое', 'новости', 'погода', 'курс', 'результат матча',
    'сколько стоит', 'когда вышел', 'последние', 'сводка', 'обзор', 'что нового'
]

# --- Загрузка и проверка API ключей ---
try:
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    SERPER_API_KEY = os.getenv('SERPER_API_KEY')
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY or not SERPER_API_KEY:
        raise ValueError("Не найдены все необходимые API ключи (Telegram, Gemini, Serper).")
except ValueError as e:
    logger.critical(e)
    exit()

# --- Настройка клиентов API ---
genai.configure(api_key=GEMINI_API_KEY)
logger.info("Клиенты API успешно настроены.")

# --- Функция поиска в Google ---
def search_google(query: str) -> str | None:
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query})
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
        response.raise_for_status()
        results = response.json()
        
        output = ""
        if "organic" in results:
            for item in results["organic"][:4]:
                output += f"Title: {item.get('title', 'N/A')}\nSnippet: {item.get('snippet', 'N/A')}\n\n"
        return output if output else None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при поиске в Google: {e}")
        return None

# --- Функции-обработчики команд Telegram ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    if chat_id in conversations: del conversations[chat_id]
    if chat_id in user_modes: del user_modes[chat_id]
    await update.message.reply_text(f"Здравствуйте, {user_name}! Я ваш обновленный ассистент. Чтобы выбрать режим, используйте /mode. Я также умею искать актуальную информацию в интернете.")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in conversations: del conversations[chat_id]
    if chat_id in user_modes: del user_modes[chat_id]
    logger.info(f"История и режим для чата {chat_id} очищены.")
    await update.message.reply_text("Всё сброшено! История диалога и режим общения очищены.")

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🤖 Стандартный", callback_data='standard')],
        [InlineKeyboardButton("🎓 Эксперт", callback_data='expert')],
        [InlineKeyboardButton("😼 Саркастичный кот", callback_data='fun')],
        [InlineKeyboardButton("💅 Секретарша для Фари", callback_data='milf')],
        [InlineKeyboardButton("👃 Йеразик для Фуфы", callback_data='eraz')],
        [InlineKeyboardButton("🫦 Секси для Орхана", callback_data='sexy')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Пожалуйста, выберите режим общения:', reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    mode = query.data
    user_modes[chat_id] = mode
    if chat_id in conversations:
        del conversations[chat_id]
    mode_name = {'standard': 'Стандартный', 'expert': 'Эксперт', 'fun': 'Саркастичный кот', 'milf': 'Милфа для Фари', 'eraz': 'Йеразик для Фуфы', 'sexy': 'Секси помошьница для Орхана'}.get(mode)
    logger.info(f"Чат {chat_id} выбрал режим '{mode}'.")
    await query.edit_message_text(text=f"Режим '{mode_name}' включен! История диалога очищена.")

# --- Основной обработчик текстовых сообщений ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    logger.info(f"Получено сообщение от чата {chat_id}: '{user_text}'")

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    needs_search = any(trigger in user_text.lower() for trigger in SEARCH_TRIGGERS)
    final_prompt = user_text

    if needs_search:
        logger.info(f"Активирован триггер поиска для запроса: '{user_text}'")
        search_results = search_google(user_text)
        if search_results:
            final_prompt = (
                f"Основываясь на следующей актуальной информации из интернета, кратко и четко ответь на вопрос пользователя.\n\n"
                f"=== ИНФОРМАЦИЯ ИЗ ИНТЕРНЕТА ===\n{search_results}\n\n"
                f"=== ВОПРОС ПОЛЬЗОВАТЕЛЯ ===\n{user_text}"
            )
            logger.info("Промпт обогащен данными из поиска.")
        else:
            logger.warning("Поиск не дал результатов, используется обычный режим.")
    
    current_mode_key = user_modes.get(chat_id, 'standard')
    system_prompt = PERSONALITIES[current_mode_key]

    history_for_request = conversations.get(chat_id, []) + [{'role': 'user', 'parts': [{'text': final_prompt}]}]

    try:
        model_for_request = genai.GenerativeModel('gemini-1.5-flash-latest', system_instruction=system_prompt)
        response = await model_for_request.generate_content_async(history_for_request)
        
        if chat_id not in conversations:
            conversations[chat_id] = []
        conversations[chat_id].append({'role': 'user', 'parts': [{'text': user_text}]})
        conversations[chat_id].append({'role': 'model', 'parts': [{'text': response.text}]})
        
        if len(conversations[chat_id]) > HISTORY_LIMIT:
            conversations[chat_id] = conversations[chat_id][-HISTORY_LIMIT:]
        
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения для чата {chat_id}: {e}")
        await update.message.reply_text("Извините, произошла ошибка. Попробуйте переформулировать ваш вопрос.")

# --- Функция запуска бота ---

def main():
    logger.info("Запуск бота...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("mode", mode_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()
    logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()
