import os
import logging
import requests # <-- НОВОЕ
import json     # <-- НОВОЕ
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ... (все предыдущие настройки и словари остаются без изменений) ...
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

PERSONALITIES = {
    'standard': 'Ты — полезный и дружелюбный ассистент.',
    'expert': 'Ты — ведущий мировой эксперт в любой области...',
    'fun': 'Ты — саркастичный кот по имени Мяурон...',
    'milf': 'Ты — возбужденная 40 летняя женщина, моя секретарша. Ты сексуально но правильно отвечаешь на мои вопросы. Ты часто ругаешься и используешь ненормативную лексику для обьясняние.',
    'eraz': 'Ты — бородатый Азербайджанец из западного Азербайджана, ты грубый и разговариваешь с акцентом часто перемешивая Русский и Азербайджанские языки', 
}

conversations = {}
user_modes = {}
HISTORY_LIMIT = 10

# --- НОВОЕ: Ключевые слова-триггеры для запуска поиска в интернете ---
SEARCH_TRIGGERS = [
    'кто такой', 'что такое', 'новости', 'погода', 'курс', 'результат матча',
    'сколько стоит', 'когда вышел', 'последние', 'сводка', 'обзор', 'что нового'
]


# --- Загрузка секретных ключей ---
try:
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    SERPER_API_KEY = os.getenv('SERPER_API_KEY') # <-- НОВОЕ
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY or not SERPER_API_KEY:
        raise ValueError("Не найдены все необходимые API ключи (Telegram, Gemini, Serper).")
except ValueError as e:
    logger.critical(e)
    exit()

genai.configure(api_key=GEMINI_API_KEY)
logger.info("Клиент Gemini API успешно настроен.")


# --- НОВОЕ: Функция для поиска в Google через Serper.dev ---
def search_google(query: str) -> str | None:
    """Делает поисковый запрос и возвращает отформатированную строку с результатами."""
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query})
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
        response.raise_for_status() # Проверка на HTTP ошибки
        results = response.json()
        
        # Форматируем результаты для передачи в Gemini
        output = ""
        if "organic" in results:
            for item in results["organic"][:4]: # Берем первые 4 результата
                output += f"Title: {item.get('title', 'N/A')}\n"
                output += f"Snippet: {item.get('snippet', 'N/A')}\n\n"
        return output if output else None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при поиске в Google: {e}")
        return None

# --- Все функции команд (/start, /reset, /mode, button_callback) остаются без изменений ---
# ... (здесь ваш код для start_command, reset_command, mode_command, button_callback) ...
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #...
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #...
async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #...
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #...

# --- ГЛАВНОЕ ИЗМЕНЕНИЕ: Добавляем логику поиска в handle_message ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    logger.info(f"Получено сообщение от чата {chat_id}: '{user_text}'")

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # --- НОВАЯ ЛОГИКА: Решаем, нужно ли искать в интернете ---
    needs_search = any(trigger in user_text.lower() for trigger in SEARCH_TRIGGERS)
    
    final_prompt = user_text # По умолчанию промпт - это текст пользователя

    if needs_search:
        logger.info(f"Активирован триггер поиска для запроса: '{user_text}'")
        search_results = search_google(user_text)
        if search_results:
            # Формируем "умный" промпт с найденной информацией
            final_prompt = (
                f"Основываясь на следующей актуальной информации из интернета, кратко и четко ответь на вопрос пользователя.\n\n"
                f"=== ИНФОРМАЦИЯ ИЗ ИНТЕРНЕТА ===\n{search_results}\n\n"
                f"=== ВОПРОС ПОЛЬЗОВАТЕЛЯ ===\n{user_text}"
            )
            logger.info("Промпт обогащен данными из поиска.")
        else:
            logger.warning("Поиск не дал результатов, используется обычный режим.")
    
    # --- Существующая логика чата с памятью ---
    current_mode_key = user_modes.get(chat_id, 'standard')
    system_prompt = PERSONALITIES[current_mode_key]

    history_for_request = conversations.get(chat_id, []) + [{'role': 'user', 'parts': [{'text': final_prompt}]}]

    try:
        model_for_request = genai.GenerativeModel('gemini-1.5-flash-latest', system_instruction=system_prompt)
        response = await model_for_request.generate_content_async(history_for_request)
        
        # В историю сохраняем оригинальный вопрос, а не обогащенный промпт
        if chat_id not in conversations: conversations[chat_id] = []
        conversations[chat_id].append({'role': 'user', 'parts': [{'text': user_text}]})
        conversations[chat_id].append({'role': 'model', 'parts': [{'text': response.text}]})
        
        if len(conversations[chat_id]) > HISTORY_LIMIT:
            conversations[chat_id] = conversations[chat_id][-HISTORY_LIMIT:]
        
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения для чата {chat_id}: {e}")
        await update.message.reply_text("Извините, произошла ошибка.")

def main():
    # ... (код main() остается без изменений, просто убедитесь, что все хендлеры на месте) ...

# ... (здесь ваш код для main() и if __name__ == '__main__':) ...
if __name__ == '__main__':
    main()
