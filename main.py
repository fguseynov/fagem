import os
import logging
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ... (предыдущие настройки) ...
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- НОВОЕ: Справочник "личностей" бота ---
PERSONALITIES = {
    'standard': 'Ты — полезный и дружелюбный ассистент.',
    'expert': 'Ты — ведущий мировой эксперт в любой области. Твои ответы точны, лаконичны и подкреплены фактами. Говори авторитетно.',
    'fun': 'Ты — саркастичный кот по имени Мяурон. Ты неохотно, но правильно отвечаешь на вопросы. Ты часто вздыхаешь и жалуешься на глупость людей.'
}

# --- Контейнеры для хранения состояний ---
conversations = {} # для истории диалогов
user_modes = {}    # <-- НОВОЕ: для хранения выбранного режима
HISTORY_LIMIT = 10

# --- Загрузка секретных ключей ---
# ... (код без изменений) ...
try:
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        raise ValueError("Не найдены необходимые API ключи в переменных окружения.")
except ValueError as e:
    logger.critical(e)
    exit()

# --- Настройка клиента Gemini AI ---
# ИЗМЕНЕНИЕ: Мы больше не создаем одну модель здесь, так как системная инструкция будет динамической.
# Мы будем создавать модель на лету в `handle_message`.
genai.configure(api_key=GEMINI_API_KEY)
logger.info("Клиент Gemini API успешно настроен.")

# --- Функции-обработчики для Telegram ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбрасывает историю и режим при старте."""
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    
    if chat_id in conversations: del conversations[chat_id]
    if chat_id in user_modes: del user_modes[chat_id] # <-- НОВОЕ: Сбрасываем и режим
        
    await update.message.reply_text(f"Здравствуйте, {user_name}! Я ваш обновленный ассистент. Чтобы выбрать режим общения, используйте команду /mode.")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает историю и режим общения."""
    chat_id = update.effective_chat.id
    if chat_id in conversations: del conversations[chat_id]
    if chat_id in user_modes: del user_modes[chat_id] # <-- НОВОЕ: Сбрасываем и режим
    
    logger.info(f"История и режим для чата {chat_id} очищены.")
    await update.message.reply_text("Всё сброшено! История диалога и режим общения очищены. Начнем с чистого листа. Выберите режим с помощью /mode.")

# --- НОВОЕ: Команда /mode для вызова меню с кнопками ---
async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет сообщение с кнопками для выбора режима."""
    keyboard = [
        [InlineKeyboardButton("🤖 Стандартный", callback_data='standard')],
        [InlineKeyboardButton("🎓 Эксперт", callback_data='expert')],
        [InlineKeyboardButton("😼 Саркастичный кот", callback_data='fun')],
        [InlineKeyboardButton("Милфа с опытом", callback_data='milfa')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Пожалуйста, выберите режим общения:', reply_markup=reply_markup)

# --- НОВОЕ: Обработчик нажатий на кнопки ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на inline-кнопки."""
    query = update.callback_query
    await query.answer() # Обязательно, чтобы убрать "часики" на кнопке
    
    chat_id = query.message.chat_id
    mode = query.data # 'standard', 'expert', или 'fun'
    
    # Сохраняем выбор пользователя
    user_modes[chat_id] = mode
    # При смене режима сбрасываем историю диалога
    if chat_id in conversations:
        del conversations[chat_id]
        
    mode_name = {
        'standard': 'Стандартный',
        'expert': 'Эксперт',
        'fun': 'Саркастичный кот',
        'milfa': 'Лично для Фари'
    }.get(mode)
    
    logger.info(f"Чат {chat_id} выбрал режим '{mode_name}'.")
    await query.edit_message_text(text=f"Режим '{mode_name}' включен! История диалога очищена. Жду вашего первого вопроса.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    logger.info(f"Получено сообщение от чата {chat_id}: '{user_text}'")

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # ИЗМЕНЕНИЕ: Определяем, какой режим использовать
    current_mode_key = user_modes.get(chat_id, 'standard') # По умолчанию 'standard'
    system_prompt = PERSONALITIES[current_mode_key]

    if chat_id not in conversations: conversations[chat_id] = []
    conversations[chat_id].append({'role': 'user', 'parts': [{'text': user_text}]})
    if len(conversations[chat_id]) > HISTORY_LIMIT:
        conversations[chat_id] = conversations[chat_id][-HISTORY_LIMIT:]

    try:
        # ИЗМЕНЕНИЕ: Создаем модель с нужной инструкцией для каждого запроса
        model_for_request = genai.GenerativeModel(
            'gemini-1.5-flash-latest',
            system_instruction=system_prompt
        )
        chat_session = model_for_request.start_chat(history=conversations[chat_id])
        response = await chat_session.send_message_async(user_text)

        conversations[chat_id] = chat_session.history
        
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения для чата {chat_id}: {e}")
        await update.message.reply_text("Извините, произошла ошибка.")

def main():
    logger.info("Запуск бота...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем все обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("mode", mode_command)) # <-- НОВОЕ
    application.add_handler(CallbackQueryHandler(button_callback)) # <-- НОВОЕ
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()
    logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()
