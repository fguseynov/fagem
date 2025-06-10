import os
import logging
import google.generativeai as genai
from dotenv import load_dotenv 
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
load_dotenv()

# Настройка логирования для отладки на хостинге
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Загрузка секретных ключей из окружения ---
# Это безопасный способ, который работает на любом хостинге.
try:
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        raise ValueError("Не найдены необходимые API ключи в переменных окружения.")
except ValueError as e:
    logger.critical(e)
    # Если ключей нет, бот не сможет запуститься.
    exit()

# --- Настройка клиента Gemini AI ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    logger.info("Модель Gemini успешно настроена.")
except Exception as e:
    logger.critical(f"Ошибка при настройке модели Gemini: {e}")
    exit()

# --- Функции-обработчики для Telegram ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение при команде /start."""
    user_name = update.effective_user.first_name
    await update.message.reply_text(f"Здравствуйте, {user_name}! Я ваш персональный ассистент. Просто задайте мне любой вопрос.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения от пользователя."""
    user_text = update.message.text
    chat_id = update.effective_chat.id
    logger.info(f"Получено сообщение от чата {chat_id}: '{user_text}'")

    # Показываем пользователю, что мы "печатаем"
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        # Отправляем текст в Gemini и получаем ответ
        response = await model.generate_content_async(user_text)
        
        # Отправляем ответ пользователю
        await update.message.reply_text(response.text)
        logger.info(f"Ответ для чата {chat_id} успешно отправлен.")

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения для чата {chat_id}: {e}")
        await update.message.reply_text("Извините, произошла ошибка. Попробуйте переформулировать ваш вопрос или повторите попытку позже.")

def main():
    """Основная функция для запуска бота."""
    logger.info("Запуск бота...")
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики команд и сообщений
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем бота (режим polling)
    application.run_polling()
    logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()