import logging
import asyncio
from pyrogram import Client
import config
from db import init_db
from handlers import register_handlers

# Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Inicialización de la base de datos
init_db()

# Inicializa el cliente de Pyrogram
app = Client("my_bot", api_id=config.api_id, api_hash=config.api_hash, bot_token=config.bot_token)

# Registrar los manejadores de eventos
register_handlers(app)

if __name__ == "__main__":
    app.run()
