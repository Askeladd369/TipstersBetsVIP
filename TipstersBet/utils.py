import pandas as pd
import logging
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import config
import pyrogram

# Función para cargar los tipsters desde un archivo Exce


def load_tipsters_from_excel(excel_file):
    try:
        # Cargar el archivo Excel en un DataFrame
        df = pd.read_excel(excel_file)
        
        # Verificar que la columna 'Grupo' existe
        if 'Grupo' not in df.columns:
            print("[ERROR] La columna 'Grupo' no existe en el archivo Excel.")
            return pd.DataFrame(), []
        
        # Obtener la lista única de grupos
        grupos = df['Grupo'].unique().tolist()
        
        return df, grupos
    except Exception as e:
        print(f"Error al cargar el archivo Excel: {e}")
        return pd.DataFrame(), []  # Retornar un DataFrame vacío y una lista vacía en caso de error

# Función para cargar los canales desde la hoja "Channels"
def load_channels_from_excel(excel_file):
    try:
        channels_df = pd.read_excel(excel_file, sheet_name='Channels')
        channels_dict = pd.Series(channels_df.Canal_ID.values, index=channels_df.Grupo).to_dict()
        return channels_dict
    except Exception as e:
        logging.error(f"Error al cargar la hoja de canales: {e}")
        return {}

def load_groups_from_excel(excel_file):
    try:
        # Cargar el archivo Excel en un DataFrame de Pandas
        df = pd.read_excel(excel_file)
        
        # Asumiendo que la columna 'Grupo' contiene los nombres de los grupos
        grupos = df['Grupo'].unique().tolist()
        
        return grupos
    except Exception as e:
        print(f"Error al cargar el archivo Excel: {e}")
        return []



# Función para verificar si el usuario es administrador
def is_admin(user_id):
    return user_id in {config.admin_id, config.admin_id2, config.bot_id}

# Función para verificar si el usuario es el administrador principal
def is_main_admin(user_id):
    return user_id == config.admin_id

# Clase para manejar los estados de los usuarios
class UserState:
    def __init__(self):
        self.states = {}
    
    def set(self, user_id, state):
        self.states[user_id] = state
    
    def get(self, user_id):
        return self.states.get(user_id)

user_states = UserState()

# Función para mostrar el menú principal
async def show_main_button_menu(client, message):
    df = load_tipsters_from_excel("C:\\Users\\saidd\\OneDrive\\Escritorio\\Bot de Telegram pruebas\\Bot separado 2\\excel ejemplo.xlsx")
    grupos = load_groups_from_excel("C:\\Users\\saidd\\OneDrive\\Escritorio\\Bot de Telegram pruebas\\Bot separado 2\\excel ejemplo.xlsx")

    if "Grupo Alta Efectividad 📊" not in grupos:
        grupos.append("Grupo Alta Efectividad 📊")

    buttons = []
    for i, grupo in enumerate(grupos):
        buttons.append([InlineKeyboardButton(grupo, callback_data=f"main_Button{i+1}_select")])

    try:
        await message.edit_text("Selecciona un Grupo de tipsters:", reply_markup=InlineKeyboardMarkup(buttons))
    except pyrogram.errors.MessageIdInvalid:
        await message.reply("Selecciona un Grupo de tipsters:", reply_markup=InlineKeyboardMarkup(buttons))

# Función para manejar la selección de botones principales
def get_tipsters_by_group(df, group_name):
    return df[df['Grupo'] == group_name]

# Función para agregar marca de agua a la imagen
def add_watermark(input_image_path, watermark_image_path, semaphore, stars):
    from PIL import Image, ImageDraw
    import io

    base_image = Image.open(input_image_path).convert("RGBA")
    watermark = Image.open(watermark_image_path).convert("RGBA")

    width_ratio = base_image.width / watermark.width
    height_ratio = base_image.height / watermark.height
    scale = min(width_ratio, height_ratio)

    new_size = (int(watermark.width * scale), int(watermark.height * scale))
    watermark = watermark.resize(new_size, Image.LANCZOS)

    position = ((base_image.width - watermark.width) // 2, (base_image.height - watermark.height) // 2)
    transparent = Image.new('RGBA', base_image.size, (0, 0, 0, 0))
    transparent.paste(base_image, (0, 0))
    transparent.paste(watermark, position, mask=watermark)
    
    draw = ImageDraw.Draw(transparent)
    text = f"{semaphore} {'🌟' * min(stars, 4)}{'🎯' if stars == 5 else ''}"
    text_position = (10, 10)
    draw.text(text_position, text, fill=(255, 255, 255, 128))

    output = io.BytesIO()
    transparent.convert("RGB").save(output, format="JPEG")
    output.seek(0)

    return output

def get_user(user_id):
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()  # Asegurarse de devolver una fila completa, no un valor individual

# Función para verificar si un usuario está aprobado
def is_user_approved(user_id):
    user = get_user(user_id)
    return user and user[2] == 1  # Acceder directamente al tercer elemento que representa la aprobación


   
