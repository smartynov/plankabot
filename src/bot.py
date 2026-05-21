import os
import logging
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from plankapy import Planka, PasswordAuth

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Planka client
planka = Planka(
    url=os.getenv('PLANKA_URL'),
    auth=PasswordAuth(
        os.getenv('PLANKA_EMAIL'),
        os.getenv('PLANKA_PASSWORD')
    )
)

async def get_list_id():
    """Get the list ID to use for new cards."""
    # First try to get from environment
    list_id = os.getenv('PLANKA_LIST_ID')
    if list_id:
        return list_id
    
    # If not set, get the first list from the board
    try:
        board_id = os.getenv('PLANKA_BOARD_ID')
        async with planka as client:
            lists = await client.boards.get_lists(board_id)
            if not lists:
                raise ValueError("No lists found in the board")
            return lists[0].id
    except Exception as e:
        logger.error(f"Error getting list ID: {e}")
        raise

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and create Planka cards."""
    try:
        # Get message text (either caption or text)
        message_text = update.message.caption or update.message.text or "No text provided"
        
        # Split title and description
        lines = message_text.split('\n', 1)
        title = lines[0].split('.', 1)[0].strip()
        description = lines[1].strip() if len(lines) > 1 else ""
        
        # If first line doesn't end with a period, try to find the first sentence
        if '.' in lines[0] and not title.endswith('.'):
            title = lines[0].split('.')[0].strip()
            remaining_text = message_text[len(title)+1:].strip()
            description = remaining_text if remaining_text else description

        # Get list ID
        list_id = await get_list_id()

        async with planka as client:
            # Create card
            card = await client.cards.create(
                board_id=os.getenv('PLANKA_BOARD_ID'),
                list_id=list_id,
                name=title,
                description=description
            )

            # Handle file or photo attachment
            if update.message.document or update.message.photo:
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    try:
                        if update.message.document:
                            file = await update.message.document.get_file()
                            await file.download_to_drive(tmp_file.name)
                        elif update.message.photo:
                            photo = update.message.photo[-1]  # Get the largest photo size
                            file = await photo.get_file()
                            await file.download_to_drive(tmp_file.name)

                        # Upload attachment
                        try:
                            await client.cards.add_attachment(
                                card_id=card.id,
                                file_path=tmp_file.name
                            )
                        except Exception as e:
                            logger.error(f"Error uploading attachment: {e}")
                            await update.message.reply_text(
                                "⚠️ Card created, but there was an error uploading the attachment."
                            )
                    finally:
                        # Clean up temporary file
                        try:
                            os.unlink(tmp_file.name)
                        except OSError:
                            pass

            # Get direct card URL
            card_url = f"{os.getenv('PLANKA_URL')}/boards/{os.getenv('PLANKA_BOARD_ID')}/cards/{card.id}"
            
            await update.message.reply_text(
                f"✅ Created card: {title}\n"
                f"🔗 Link: {card_url}"
            )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing message: {error_msg}")
        if "list_id" in error_msg.lower():
            await update.message.reply_text(
                "❌ Error: Could not find a valid list in the board. "
                "Please check your PLANKA_LIST_ID setting."
            )
        else:
            await update.message.reply_text(
                "❌ Sorry, there was an error creating the card. Please try again later."
            )

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    # Add message handler
    application.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        handle_message
    ))

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 