import datetime
import asyncio
import sqlite3
import logging
import tempfile
import os
import random, string
import re
import pandas as pd
from pyrogram import Client, filters,errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from utils import *
from db import *

# Función para obtener la conexión a la base de datos
def get_db_connection():
    return sqlite3.connect("bot_database.db")

# Función para generar botones inline
def create_menu_button(label, callback_data):
    return InlineKeyboardButton(label, callback_data=callback_data)

def create_menu(buttons):
    return InlineKeyboardMarkup([[create_menu_button(label, callback_data)] for label, callback_data in buttons])

# Función para generar códigos de invitación
def generate_invitation_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

# Validación para administradores
def admin_only():
    async def func(_, __, message):
        if message.from_user is None:
            return False
        
        return is_admin(message.from_user.id)
    return filters.create(func)

# Función para manejar los estados de invitación
def get_invitation_code(invitation_code):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT duration FROM invitation_codes WHERE code = ? AND used = 0", (invitation_code,))
        return cursor.fetchone()

def update_invitation_code_used(invitation_code):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE invitation_codes SET used = 1 WHERE code = ?", (invitation_code,))
        conn.commit()

# Función para generar botones de tipsters
def generate_tipster_buttons(tipsters_in_group, user_id, group_button, conn):
    buttons = []
    cursor = conn.cursor()

    for _, tipster in tipsters_in_group.iterrows():
        tipster_name = tipster['Nombre']
        cursor.execute("SELECT * FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", (user_id, tipster_name))
        is_active = cursor.fetchone()
        active_emoji = '✅' if is_active else '❌'
        buttons.append([InlineKeyboardButton(f"{tipster_name} {active_emoji}", callback_data=f"toggle_{tipster_name}_{group_button}_select")])

    return buttons

# Registro de handlers en la aplicación
def register_handlers(app: Client):

    @app.on_message(filters.command("start") & filters.private)
    async def start(client, message):
        args = message.text.split()
        gif_path = "C:\\Users\\Administrator\\TipstersBetsVIP\\TipstersBet\\familia.gif"
        info_text = (
            "📊 **¿Cómo funciona el grupo VIP?**\n\n"
            "Con el objetivo de ayudarte a identificar a los tipsters más rentables, contamos con un sistema de *semáforos* que acompañan al nombre de cada tipster:\n"
            "- Semáforo verde 🟢: Efectividad superior al **70%**.\n"
            "- Semáforo amarillo 🟡: Efectividad entre **50% y 70%**.\n"
            "- Semáforo rojo 🔴: Efectividad menor al **50%**.\n\n"
            "La efectividad es un indicador clave de la precisión y habilidad de los tipsters en sus pronósticos.\n\n"
            
            "Además, también evaluamos el *rendimiento a corto plazo* con nuestro sistema de **estrellas** ⭐️:\n"
            "- Cada estrella indica los días consecutivos de ganancias de un tipster. Si el tipster mantiene una racha positiva, subirá en el ranking con más estrellas ⭐️⭐️, indicando que es confiable seguir sus recomendaciones.\n"
            "- Por otro lado, si los resultados son negativos, el tipster descenderá en el ranking, lo que nos permite aprovechar las rachas positivas y evitar las negativas.\n\n"
            
            "💎 *Grupo Exclusivo 'Alta Efectividad'*\n"
            "Este grupo está reservado para los tipsters con un historial de aciertos superior al **70%**. Aquí solo compartimos las apuestas de los tipsters más precisos.\n\n"
            
            "🔥 De esta manera, garantizamos que sigas las recomendaciones de los expertos que contribuirán significativamente al crecimiento de tu bank.\n\n"
            
            "**Modalidades para recibir nuestras apuestas:**\n"
            "- A través de este bot, usando el comando /categories para activar a los tipsters que quieres recibir.\n"
            "- Uniéndote a nuestros grupos, donde organizamos a los tipsters por categorías.\n\n"
            
            "🔗 **Enlaces de acceso a nuestros grupos:**\n"
            "🇲🇽 **Grupo de Nacionales**: [Unirse](https://t.me/+Z9fj5SmR8GdlYjhh)\n"
            "🇺🇸 **Grupo de Americanos**: [Unirse](https://t.me/+xgtawqeOAhE2NDgx)\n"
            "⭐️ **Grupo de Stakes 10 y garantizados**: [Unirse](https://t.me/+WOF58ybazGAwODUx)\n"
            "💎 **Grupo de Alta Efectividad**: [Unirse](https://t.me/+vHF5R3P9eMQ2MTQx)\n"
            "👑 **Los Rey App**: [Unirse](https://t.me/+o4REb6_EYiY1YWUx)\n\n"
            "🎰 **Grupo Extranjeros**: [Unirse](https://t.me/+BifOpvJrK_M0NWIx)\n"
            "🪜 **Grupo de Retos escalera**: [Unirse](https://t.me/+xMODO227vbk3NzUx)\n"
            
            "_Nota_: Si recibes el mensaje de “límite excedido” de Telegram, simplemente espera un momento y vuelve a solicitar el acceso haciendo clic en el enlace. Serás aceptado por un administrador en breves. 👨‍💻"
        )

        if len(args) < 2:
            await message.reply("Por favor, proporciona un código de invitación para activar el bot de la siguiente manera:\n /start (codigo de invitacion)")
            return

        invitation_code = args[1].strip()
        code_data = get_invitation_code(invitation_code)

        if code_data is None:
            await message.reply("Código de invitación no válido o ya usado.")
            return

        duration = code_data[0]
        update_invitation_code_used(invitation_code)

        user_id = message.from_user.id
        user_name = message.from_user.first_name
        approved_time = datetime.datetime.now().isoformat()

        # Insertar o actualizar la información del usuario en la base de datos
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, first_name, approved, subscription_days, approved_time) 
                VALUES (?, ?, ?, ?, ?)""",
                (user_id, user_name, 1, duration, approved_time))
            conn.commit()

        # Desbanear al usuario del canal privado para permitir su acceso
        try:
            # Cargar los canales desde el archivo Excel
            channels_dict = load_channels_from_excel(config.excel_path)  # Ruta correcta al archivo Excel

            # Desbanear al usuario de todos los canales a los que tiene acceso
            for channel_id in channels_dict.values():
                await client.unban_chat_member(chat_id=channel_id, user_id=user_id)
                logging.info(f"Usuario con ID {user_id} ha sido desbaneado del canal {channel_id}.")
        except errors.UserNotParticipant:
            logging.info(f"El usuario {user_id} no estaba previamente baneado de los canales.")
        except Exception as e:
            logging.error(f"Error al intentar desbanear al usuario {user_id} de los canales: {e}")
            await message.reply(f"Error al desbanear al usuario: {e}")

        # Enviar el GIF como bienvenida
        try:
            await client.send_animation(
                chat_id=message.chat.id,
                animation=gif_path,
                caption=f"Bienvenido a la familia {user_name}! 🎉"
            )
        except Exception as e:
            await message.reply(f"Error al enviar el GIF de bienvenida: {e}")

        # Enviar el mensaje de bienvenida adicional
        await message.reply(
            f"Has activado tu membresía VIP. Tu suscripción durará {duration} días.\n {info_text}" 
        )

    @app.on_callback_query(filters.regex(r"admin_menu") & admin_only())
    async def show_admin_menu(client, callback_query):
        buttons = [
            ("Revisar Usuarios 👥", "review_users"),
            ("Generar Código de Invitación 🔑", "generate_invitation_code"),
            ("Subir Excel 📊", "upload_excel")
        ]
        await callback_query.message.edit_text("Menú de administración:", reply_markup=create_menu(buttons))
        await callback_query.answer()

    @app.on_callback_query(filters.regex(r"user_main_menu"))
    async def show_main_button_menu_callback(client, callback_query):
        await show_main_button_menu(client, callback_query.message)
        await callback_query.answer()

    @app.on_callback_query(filters.regex(r"generate_invitation_code") & admin_only())
    async def handle_generate_invitation_code(client, callback_query):
        await callback_query.message.reply("Por favor, introduce la duración (en días) y la cantidad de códigos que deseas generar (en el formato: duración,cantidad):")
        user_states.set(callback_query.from_user.id, "awaiting_invitation_duration_and_quantity")
        await callback_query.answer()

    @app.on_message(filters.text & admin_only() & filters.create(lambda _, __, m: user_states.get(m.from_user.id) == "awaiting_invitation_duration_and_quantity"))
    async def handle_invitation_duration_and_quantity(client, message):
        try:
            # Parsear la entrada del usuario, que debe tener el formato "duración,cantidad"
            duration, quantity = map(int, message.text.strip().split(","))
            
            codes = [generate_invitation_code() for _ in range(quantity)]
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                for code in codes:
                    cursor.execute("INSERT INTO invitation_codes (code, duration, used) VALUES (?, ?, 0)", (code, duration))
                conn.commit()
            
            codes_text = "\n".join([f"Envia mensaje a este bot @Tipstersbetsbot con tu código de activación de la siguiente manera: \n\n/start {code} \n\n " for code in codes])
            await message.reply(f"{codes_text}")
            user_states.set(message.from_user.id, None)
        except ValueError:
            await message.reply("Por favor, introduce un formato válido: duración,cantidad. Por ejemplo: 30,5")
            user_states.set(message.from_user.id, "awaiting_invitation_duration_and_quantity")
        
    @app.on_message(filters.command("admin") & admin_only())
    async def admin_menu(client, message):
        buttons = [
            ("Revisar Usuarios 👥", "review_users"),
            ("Generar Código de Invitación 🔑", "generate_invitation_code"),
            ("Subir Excel 📊", "upload_excel")
        ]
        await message.reply("Menú de administración:", reply_markup=create_menu(buttons))

    @app.on_callback_query(filters.regex(r"main_(Button\d+)_select"))
    async def handle_main_button_selection(client, callback_query):
        # Cargar los grupos dinámicamente desde el archivo Excel
        tipsters_df, grupos = load_tipsters_from_excel(config.excel_path)
        
        # Verificar que la lista de grupos esté correctamente poblada
        if not grupos:
            await callback_query.answer("No se pudieron cargar los grupos.", show_alert=True)
            return

        # Agregar manualmente el grupo "Alta Efectividad"
        grupos.append("Grupo Alta Efectividad 📊")

        # Extraer el identificador del botón y determinar el índice del grupo
        group_button = callback_query.data.split("_")[1]
        match = re.search(r'\d+', group_button)
        group_index = int(match.group()) - 1 if match else -1

        # Verificar que el índice esté dentro del rango
        if group_index < 0 or group_index >= len(grupos):
            await callback_query.answer("Índice de grupo fuera de rango.", show_alert=True)
            return

        # Acceder al nombre del grupo
        group_name = grupos[group_index]

        # Filtrar por grupo o por semáforo verde si es "Alta Efectividad"
        if group_name == "Grupo Alta Efectividad 📊":
            tipsters_in_group = tipsters_df[tipsters_df['Efectividad'] > 65]
        else:
            tipsters_in_group = tipsters_df[tipsters_df['Grupo'] == group_name]

        # Crear botones con solo el nombre del tipster
        buttons = []
        with get_db_connection() as conn:
            cursor = conn.cursor()

            for _, tipster in tipsters_in_group.iterrows():
                tipster_name = tipster['Nombre']

                # Añadir el emoji de activado/desactivado
                cursor.execute("SELECT * FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", (callback_query.from_user.id, tipster_name))
                is_active = cursor.fetchone()
                active_emoji = '✅' if is_active else '❌'

                # Formato del botón: solo el nombre del tipster y el emoji de estado
                button_text = f"{tipster_name} {active_emoji}"

                # El botón sigue permitiendo activar/desactivar el tipster
                buttons.append([InlineKeyboardButton(button_text, callback_data=f"toggle_{tipster_name}_{group_button}_select")])

        # Añadir el botón de "Volver"
        buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="user_main_menu")])

        # Editar los botones en el mensaje
        await callback_query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))

    @app.on_callback_query(filters.regex(r"toggle_all_alta_efectividad"))
    async def toggle_all_alta_efectividad(client, callback_query):
        user_id = callback_query.from_user.id
        tipsters_df, _ = load_tipsters_from_excel(config.excel_path)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT receive_all_alta_efectividad FROM users WHERE user_id = ?", (user_id,))
            receive_all = cursor.fetchone()[0]
            
            if receive_all:
                # Desactivar todos los tipsters de Alta Efectividad
                cursor.execute("""
                    DELETE FROM user_tipsters WHERE user_id = ? AND tipster_name IN (
                        SELECT Nombre FROM tipsters WHERE Efectividad > 65
                    )""", (user_id,))
                cursor.execute("UPDATE users SET receive_all_alta_efectividad = 0 WHERE user_id = ?", (user_id,))
                await callback_query.answer("Has desactivado todos los tipsters de Alta Efectividad.")
            else:
                # Activar todos los tipsters de Alta Efectividad
                cursor.executemany("""
                    INSERT INTO user_tipsters (user_id, tipster_name) VALUES (?, ?) ON CONFLICT DO NOTHING
                """, [(user_id, tipster['Nombre']) for _, tipster in tipsters_df[tipsters_df['Efectividad'] > 65].iterrows()])
                cursor.execute("UPDATE users SET receive_all_alta_efectividad = 1 WHERE user_id = ?", (user_id,))
                await callback_query.answer("Has activado todos los tipsters de Alta Efectividad.")
            conn.commit()

        # Actualizar los botones inmediatamente para reflejar el cambio en la interfaz
        await update_tipster_buttons(client, callback_query)

    async def update_tipster_buttons(client, callback_query):
        # Recargar los grupos y los tipsters del Excel
        tipsters_df, grupos = load_tipsters_from_excel(config.excel_path)
        
        # Extraer el identificador del botón y determinar el índice del grupo
        group_button = callback_query.data.split("_")[2]
        match = re.search(r'\d+', group_button)
        group_index = int(match.group()) - 1 if match else -1

        # Verificar que el índice esté dentro del rango
        if group_index < 0 or group_index >= len(grupos):
            await callback_query.answer("Índice de grupo fuera de rango.", show_alert=True)
            return

        # Acceder al nombre del grupo
        group_name = grupos[group_index]
        
        # Filtrar por grupo o por "Alta Efectividad"
        if group_name == "Grupo Alta Efectividad 📊":
            tipsters_in_group = tipsters_df[tipsters_df['Efectividad'] > 65]
        else:
            tipsters_in_group = tipsters_df[tipsters_df['Grupo'] == group_name]

        # Crear los botones actualizados
        buttons = []
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for _, tipster in tipsters_in_group.iterrows():
                tipster_name = tipster['Nombre']

                # Verificar el estado del tipster
                cursor.execute("SELECT * FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", (callback_query.from_user.id, tipster_name))
                is_active = cursor.fetchone()
                active_emoji = '✅' if is_active else '❌'

                # Crear el botón con el nombre del tipster y el emoji de estado
                button_text = f"{tipster_name} {active_emoji}"
                buttons.append([InlineKeyboardButton(button_text, callback_data=f"toggle_{tipster_name}_{group_button}_select")])

        # Añadir el botón de "Volver"
        buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="user_main_menu")])

        # Actualizar los botones en el mensaje sin recargar la interfaz completa
        await callback_query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
        await callback_query.answer("Botones actualizados.")

    @app.on_callback_query(filters.regex(r"toggle_(.+)_(Button\d+)_select"))
    async def toggle_tipster_notification(client, callback_query):
        user_id = callback_query.from_user.id
        data = callback_query.data.split("_")
        tipster_name = data[1]  # Nombre del tipster
        group_button = data[2]  # Identificador del grupo

        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar si el tipster ya está activado para el usuario
            cursor.execute("SELECT * FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", (user_id, tipster_name))
            subscription = cursor.fetchone()
            
            if subscription:
                # Si está activado, desactivarlo
                cursor.execute("DELETE FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", (user_id, tipster_name))
                conn.commit()
                await callback_query.answer(f"Has desactivado las notificaciones para {tipster_name}.")
            else:
                # Si no está activado, activarlo
                cursor.execute("INSERT INTO user_tipsters (user_id, tipster_name) VALUES (?, ?)", (user_id, tipster_name))
                conn.commit()
                await callback_query.answer(f"Has activado las notificaciones para {tipster_name}.")

        # Sincronización instantánea: Actualizar botones con el nuevo estado
        await update_tipster_buttons(client, callback_query)

    @app.on_message(filters.command("categories") & filters.private)
    async def show_main_buttons(client, message):
        user_id = message.from_user.id
        if is_user_approved(user_id):
            await show_main_button_menu(client, message)
        else:
            await message.reply("Tu cuenta aún no ha sido aprobada por el administrador. Por favor espera la confirmación.")

    # Función para procesar imágenes y enviar a usuarios/canales
    async def process_image_and_send(client, message, tipster_name, tipsters_df, channels_dict):
        # Buscar las estadísticas del tipster en el DataFrame (Hoja 1)
        tipster_stats = tipsters_df[tipsters_df['Nombre'].str.lower() == tipster_name.lower()]

        if tipster_stats.empty:
            await message.reply(f"No se encontraron estadísticas para el tipster '{tipster_name}'.")
            return

        stats = tipster_stats.iloc[0]

        # Obtener estadísticas
        bank_inicial = stats.get('Bank Inicial', None)
        bank_actual = stats.get('Bank Actual', None)
        manejo_bank = stats.get('Manejo de Bank', None)
        utilidad_unidades = stats.get('Utilidad en unidades', None)
        victorias = stats.get('Victorias', None)
        derrotas = stats.get('Derrotas', None)
        efectividad = stats.get('Efectividad', None)
        racha = stats.get('Dias en racha', 0)
        record_futbol = stats.get('Futbol', None)
        record_basquetball = stats.get('Basquetball', None)
        record_americano =stats.get('Americano', None)
        record_tenis=stats.get('Tenis', None)
        record_mma =stats.get('MMA', None)
        record_esports= stats.get('Esports', None)
        record_pingpong= stats.get('PingPong', None)
        record_beisbol = stats.get('Beisbol', None)
        record_hockey= stats.get('Hockey', None)

        # Verificar si las estadísticas son NaN y manejar el caso
        victorias = None if pd.isna(victorias) else int(victorias)
        derrotas = None if pd.isna(derrotas) else int(derrotas)
        bank_inicial = None if pd.isna(bank_inicial) else bank_inicial
        bank_actual = None if pd.isna(bank_actual) else bank_actual
        manejo_bank = None if pd.isna(manejo_bank) else manejo_bank
        utilidad_unidades = None if pd.isna(utilidad_unidades) else utilidad_unidades
        efectividad = None if pd.isna(efectividad) else efectividad
        racha = 0 if pd.isna(racha) else int(racha)
        record_futbol = None if pd.isna(record_futbol) else record_futbol
        record_basquetball = None if pd.isna(record_basquetball) else record_basquetball
        record_americano = None if pd.isna(record_americano) else record_americano
        record_tenis= None if pd.isna(record_tenis) else record_tenis
        record_mma = None if pd.isna(record_mma) else record_mma
        record_esports= None if pd.isna(record_esports) else record_esports
        record_pingpong= None if pd.isna(record_pingpong) else record_pingpong
        record_beisbol =None if pd.isna(record_beisbol) else record_beisbol
        record_hockey=None if pd.isna(record_hockey) else record_hockey

        # Asignar semáforo
        semaforo = '🟢' if efectividad and efectividad > 65 else '🟡' if efectividad and 50 <= efectividad <= 65 else '🔴'

        # Procesar racha
        racha_emoji = '🌟' * min(racha, 4) + ('🎯' if racha >= 5 else '')

        # Crear el mensaje de estadísticas condicionalmente
        if racha > 0:
            stats_message = f"🎫 {tipster_name} {racha_emoji}\n"
        else:
            stats_message = f"🎫 {tipster_name}\n"

        if bank_inicial is not None:
            stats_message += f"🏦 Bank Inicial: ${bank_inicial:.2f} 💵\n"

        if bank_actual is not None:
            # Formatear el mensaje de bank actual con el símbolo correspondiente
            simbolo = "+" if bank_actual > 0 else ""
            
            # Mostrar el valor de bank_actual tal como está, añadiendo el símbolo si es positivo
            stats_message += f"💰 Balance: {simbolo}${bank_actual:.2f} 💵\n"

        
        if efectividad is not None:
            stats_message += f"{semaforo} Efectividad: {int(efectividad)}%\n"

        if manejo_bank is not None:
            stats_message += f"🧾 Gestion de bank: {manejo_bank}\n"

        if utilidad_unidades is not None:
            stats_message += f"💎 Utilidad en unidades (Bank de 100U): {utilidad_unidades:.2f}\n"

        if victorias is not None or derrotas is not None:
            stats_message += "📊 Record: "
            
            if victorias is not None and victorias > 0:
                stats_message += f"{victorias} ✅"
            else:
                stats_message += "0 ✅"
            
            stats_message += " - "  # Agregar el separador entre victorias y derrotas
            
            if derrotas is not None and derrotas > 0:
                stats_message += f"{derrotas} ❌"
            else:
                stats_message += "0 ❌"
            
            stats_message += "\n"  # Nueva línea al final del mensaje de récord

        if record_futbol is not None:
            stats_message += f"⚽️ Record Futbol: ✅{record_futbol}❌\n"
        
        if record_basquetball is not None:
            stats_message += f"🏀 Record Basquetball: ✅{record_basquetball}❌\n"

        if record_americano is not None:
            stats_message += f"🏈 Record Americano: ✅{record_americano}❌\n"

        if record_beisbol is not None:
            stats_message += f"⚾️ Record Beisbol: ✅{record_beisbol}❌\n"

        if record_tenis is not None:
            stats_message += f"🎾 Record Tenis: ✅{record_tenis}❌\n"

        if record_mma is not None:
            stats_message += f"🥊 Record MMA: ✅{record_mma}❌\n"

        if record_esports is not None:
            stats_message += f"🎮 Record Esports: ✅{record_esports}❌\n"
        
        if record_pingpong is not None:
            stats_message += f"🏓 Record PingPong: ✅{record_pingpong}❌\n"

        if record_hockey is not None:
            stats_message += f"🏒 Record Hockey: ✅{record_hockey}❌\n"

        # Crear una lista para agrupar todas las imágenes procesadas
        media_group = []

        # Procesar las imágenes y añadirles la marca de agua
        if message.media_group_id:
            media_group_content = await client.get_media_group(message.chat.id, message.id)

            for idx, media in enumerate(media_group_content):
                if media.photo:
                    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                        photo = await client.download_media(media.photo.file_id, file_name=tmp_file.name)
                        watermarked_image = add_watermark(photo, config.watermark_path, racha_emoji, racha)
                        media_group.append(InputMediaPhoto(watermarked_image, caption=stats_message if idx == 0 else None))
                    os.remove(tmp_file.name)
        elif message.photo:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                photo = await client.download_media(message.photo.file_id, file_name=tmp_file.name)
                watermarked_image = add_watermark(photo, config.watermark_path, racha_emoji, racha)
                media_group.append(InputMediaPhoto(watermarked_image, caption=stats_message))
            os.remove(tmp_file.name)

        if not media_group:
            await message.reply("No se encontraron fotos en el mensaje.")
            return

        # Enviar las imágenes a los usuarios suscritos
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM user_tipsters WHERE tipster_name = ?", (tipster_name,))
            users = cursor.fetchall()

            for user in users:
                try:
                    await client.send_media_group(user[0], media_group)
                except errors.UserIsBlocked:
                    logging.info(f"El usuario {user[0]} ha bloqueado al bot y no se le enviarán las imágenes.")
                except Exception as e:
                    logging.error(f"Error al enviar imágenes al usuario {user[0]}: {e}")

        # Obtener el nombre del grupo desde las estadísticas del tipster
        group_name = stats.get('Grupo', '').strip()
        channel_id = channels_dict.get(group_name)

        if not channel_id:
            await message.reply(f"No se encontró un canal correspondiente para el grupo: {group_name}")
            return

        # Enviar imágenes al canal como un grupo de medios
        try:
            await client.send_media_group(channel_id, media_group)
        except Exception as e:
            await message.reply(f"Error al enviar las imágenes al canal {channel_id}: {e}")

        # Enviar al canal de alta efectividad si corresponde
        if efectividad and efectividad > 65:
            try:
                await client.send_media_group(config.channel_alta_efectividad, media_group)
            except Exception as e:
                logging.error(f"Error al enviar al canal de alta efectividad: {e}")
        
    @app.on_message((filters.media_group | filters.photo) & (filters.chat(config.CANAL_PRIVADO_ID) | admin_only()))
    async def handle_images(client, message):
        excel_file = config.excel_path
        tipsters_df, _ = load_tipsters_from_excel(excel_file)
        channels_dict = load_channels_from_excel(excel_file)

        # Verificar si es un grupo de medios o una sola imagen
        if message.media_group_id:
            if not hasattr(client, 'media_groups_processed'):
                client.media_groups_processed = {}

            # Evitar procesar el grupo de medios más de una vez
            if message.media_group_id in client.media_groups_processed:
                return
            client.media_groups_processed[message.media_group_id] = True

            # Obtener todo el grupo de medios
            media_group_content = await client.get_media_group(message.chat.id, message.id)

            # Usar el caption de la primera imagen del grupo
            caption = media_group_content[0].caption if media_group_content[0].caption else None
        else:
            # Procesar una sola imagen
            caption = message.caption

        # Verificar si se proporcionó un nombre de tipster en el caption
        if not caption:
            await message.reply("Por favor, añade el nombre del tipster a la(s) imagen(es).")
            return

        # Pasar el procesamiento de las imágenes y el envío a `process_image_and_send`
        tipster_name = caption.strip()
        await process_image_and_send(client, message, tipster_name, tipsters_df, channels_dict)

        # Limpiar el registro del media group para evitar duplicados
        if message.media_group_id:
            del client.media_groups_processed[message.media_group_id]

    @app.on_callback_query(filters.regex(r"review_users") & admin_only())
    async def review_users(client, callback_query):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, first_name, subscription_days, approved_time FROM users")
            users = cursor.fetchall()

        if not users:
            await callback_query.message.reply("No hay usuarios suscritos.")
            return

        # Crear una lista de botones para cada usuario
        buttons = []
        for user in users:
            user_id = user[0]
            first_name = user[1]
            subscription_days = user[2]
            approved_time = user[3]

            if approved_time:
                approved_time = datetime.datetime.fromisoformat(approved_time)
                days_left = (approved_time + datetime.timedelta(days=subscription_days) - datetime.datetime.now()).days
            else:
                days_left = "N/A"

            buttons.append([InlineKeyboardButton(f"{first_name} - {days_left} días restantes", callback_data=f"remove_{user_id}")])

        buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="admin_menu")])

        # Enviar el mensaje con los botones de los usuarios
        await callback_query.message.edit_text("Usuarios suscritos:", reply_markup=InlineKeyboardMarkup(buttons))
        await callback_query.answer()

    @app.on_callback_query(filters.regex(r"upload_excel") & admin_only())
    async def prompt_upload_excel(client, callback_query):
        await callback_query.message.reply("Por favor, sube el archivo Excel que contiene los datos de los tipsters.")
        user_states.set(callback_query.from_user.id, "awaiting_excel_upload")
        await callback_query.answer()

    @app.on_message(filters.document & admin_only() & filters.create(lambda _, __, m: user_states.get(m.from_user.id) == "awaiting_excel_upload"))
    async def handle_excel_upload(client, message):
        if message.document.mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':  # Asegúrate de que es un archivo .xlsx
            # Descargar el archivo Excel subido por el usuario
            file_path = await client.download_media(message.document)

            try:
                # Ruta al archivo Excel existente en la carpeta del código
                excel_destino = config.excel_path  # Cambia esto a la ruta real del archivo Excel que quieres reemplazar
                
                # Reemplazar el archivo Excel existente con el nuevo archivo
                os.replace(file_path, excel_destino)

                # Procesar el archivo Excel para verificar que se subió correctamente (opcional)
                tipsters_df, grupos = load_tipsters_from_excel(excel_destino)

                await message.reply("¡Archivo Excel subido y procesado correctamente!")
            except Exception as e:
                await message.reply(f"Error al procesar el archivo Excel: {e}")
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)  # Eliminar el archivo temporal si no se movió correctamente
        else:
            await message.reply("Por favor, sube un archivo válido en formato .xlsx.")

        user_states.set(message.from_user.id, None)

    @app.on_chat_join_request()
    async def approve_join_request(client, join_request):
        # Este handler escucha cada vez que hay una solicitud para unirse a un canal/grupo
        try:
            await client.approve_chat_join_request(join_request.chat.id, join_request.from_user.id)
            print(f"Solicitud de {join_request.from_user.first_name} aprobada para el canal/grupo {join_request.chat.title}")
        except Exception as e:
            print(f"Error al aprobar la solicitud de {join_request.from_user.first_name}: {e}")

    @app.on_callback_query(filters.regex(r"remove_(\d+)") & admin_only())
    async def remove_user_callback(client, callback_query):
        user_id = int(callback_query.data.split("_")[1])
        
        # Cargar los canales desde el archivo Excel
        channels_dict = load_channels_from_excel(config.excel_path)  # Ruta correcta al archivo Excel
        
        # Eliminar al usuario de los canales especificados en el Excel
        for group_name, channel_id in channels_dict.items():
            try:
                # Usar ban_chat_member para eliminar al usuario del canal
                await client.ban_chat_member(channel_id, user_id)
                logging.info(f"Usuario {user_id} removido del canal {channel_id} ({group_name})")
            except Exception as e:
                logging.error(f"Error al eliminar al usuario {user_id} del canal {channel_id}: {e}")

        # Ahora eliminamos al usuario del bot (de la base de datos)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()

        await callback_query.answer(f"Usuario {user_id} eliminado del bot y de los canales.")

# Función para eliminar usuarios de los canales cuando expira su suscripción
async def check_and_remove_expired_users(client: Client):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, first_name, subscription_days, approved_time FROM users WHERE approved = 1")
        users = cursor.fetchall()

    # Recorremos cada usuario y verificamos si su suscripción ha caducado
    for user in users:
        user_id = user[0]
        approved_time = datetime.datetime.fromisoformat(user[3])
        subscription_days = user[2]

        # Calcular la fecha de vencimiento
        expiration_date = approved_time + datetime.timedelta(days=subscription_days)
        days_left = (expiration_date - datetime.datetime.now()).days

        if days_left <= 0:
            # Si la membresía ha expirado, eliminar al usuario de los canales
            await remove_user_from_channels(client, user_id)
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET approved = 0 WHERE user_id = ?", (user_id,))
                conn.commit()

# Función para eliminar al usuario de los canales
async def remove_user_from_channels(client: Client, user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id FROM user_channels WHERE user_id = ?", (user_id,))
        channels = cursor.fetchall()

    for channel in channels:
        channel_id = channel[0]
        try:
            # Usar ban_chat_member para eliminar al usuario del canal
            await client.ban_chat_member(channel_id, user_id)
            logging.info(f"Usuario {user_id} removido del canal {channel_id}")
            
            # Desbanear inmediatamente después de eliminar para permitir futuras reintegraciones
            await unban_user_from_channel(client, user_id, channel_id)
        except Exception as e:
            logging.error(f"Error al eliminar o desbanear al usuario {user_id} del canal {channel_id}: {e}")

# Tarea para ejecutar la verificación de membresías expiradas periódicamente
async def membership_check_loop(client: Client):
    while True:
        await check_and_remove_expired_users(client)
        await asyncio.sleep(86400)  # Esperar 24 horas entre verificaciones

async def unban_user_from_channel(client: Client, user_id: int, channel_id: int):
    try:
        await client.unban_chat_member(chat_id=channel_id, user_id=user_id)
        logging.info(f"Usuario con ID {user_id} ha sido desbaneado del canal {channel_id}.")
    except errors.UserNotParticipant:
        logging.info(f"El usuario {user_id} no estaba previamente baneado del canal {channel_id}.")
    except Exception as e:
        logging.error(f"Error al intentar desbanear al usuario {user_id} del canal {channel_id}: {e}")
