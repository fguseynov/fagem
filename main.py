import os
import logging
import google.generativeai as genai
# ИЗМЕНЕНИЕ: Добавляем ChatAction в импорты
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

PERSONALITIES = {
    'standard': 'Ты — полезный и дружелюбный ассистент.',
    'expert': 'Ты — ведущий мировой эксперт в любой области. Твои ответы точны, лаконичны и подкреплены фактами. Говори авторитетно.',
    'fun': 'Ты — саркастичный кот по имени Мяурон. Ты неохотно, но правильно отвечаешь на вопросы. Ты часто вздыхаешь и жалуешься на глупость людей.',
    'milf': 'Ты — возбужденная 40а летняя женщина, моя секретарша.Ты сексуально но правильно отвечаешь на мои вопросы. Ты часто ругаешься и жалуешься на мужчин.'
}

conversations = {}
user_modes = {}
HISTORY_LIMIT = 10

try:
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        raise ValueError("Не найдены необходимые API ключи в переменных окружения.")
except ValueError as e:
    logger.critical(e)
    exit()

genai.configure(api_key=GEMINI_API_KEY)
logger.info("Клиент Gemini API успешно настроен.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    if chat_id in conversations: del conversations[chat_id]
    if chat_id in user_modes: del user_modes[chat_id]
    await update.message.reply_text(f"Здравствуйте, {user_name}! Я ваш обновленный ассистент. Чтобы выбрать режим общения, используйте команду /mode.")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in conversations: del conversations[chat_id]
    if chat_id in user_modes: del user_modes[chat_id]
    logger.info(f"История и режим для чата {chat_id} очищены.")
    await update.message.reply_text("Всё сброшено! История диалога и режим общения очищены. Начнем с чистого листа. Выберите режим с помощью /mode.")

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🤖 Стандартный", callback_data='standard')],
        [InlineKeyboardButton("🎓 Эксперт", callback_data='expert')],
        [InlineKeyboardButton("😼 Саркастичный кот", callback_data='fun')],
        [InlineKeyboardButton("🫦 Секретарша для Фари", callback_data='milf')],
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
    mode_name = {'standard': 'Стандартный', 'expert': 'Эксперт', 'fun': 'Саркастичный кот', 'milf': 'Милфа для Фари'}.get(mode)
    logger.info(f"Чат {chat_id} выбрал режим '{mode_name}'.")
    await query.edit_message_text(text=f"Режим '{mode_name}' включен! История диалога очищена. Жду вашего первого вопроса.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    logger.info(f"Получено сообщение от чата {chat_id}: '{user_text}'")

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    current_mode_key = user_modes.get(chat_id, 'standard')
    system_prompt = PERSONALITIES[current_mode_key]

    history_for_request = conversations.get(chat_id, []) + [{'role': 'user', 'parts': [{'text': user_text}]}]

    try:
        model_for_request = genai.GenerativeModel(
            'gemini-1.5-flash-latest',
            system_instruction=system_prompt
        )
        response = await model_for_request.generate_content_async(history_for_request)
        
        # Обновляем историю в `conversations`
        if chat_id not in conversations:
            conversations[chat_id] = []
        conversations[chat_id].append({'role': 'user', 'parts': [{'text': user_text}]})
        conversations[chat_id].append({'role': 'model', 'parts': [{'text': response.text}]})
        
        if len(conversations[chat_id]) > HISTORY_LIMIT:
            conversations[chat_id] = conversations[chat_id][-HISTORY_LIMIT:]
        
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения для чата {chat_id}: {e}")
        await update.message.reply_text("Извините, произошла ошибка. Попробуйте переформулировать ваш вопрос или повторите попытку позже.")

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
