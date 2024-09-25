import datetime
import asyncio
import sqlite3
import logging
import tempfile
import os
import random, string
import re
import pandas as pd
from pyrogram import Client, filters
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
        
        if len(args) < 2:
            await message.reply("Por favor, proporciona un código de invitación para activar el bot.")
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
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, first_name, approved, subscription_days, approved_time) 
                VALUES (?, ?, ?, ?, ?)""",
                (user_id, user_name, 1, duration, approved_time))
            conn.commit()
        
        await message.reply(
            f"¡Bienvenido, {user_name}! Has activado tu membresía VIP. Tu suscripción durará {duration} días. Escribe el comando /categories para seleccionar a los tipsters que quieres recibir."
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
        await callback_query.message.reply("Por favor, introduce la duración (en días) para el código de invitación:")
        user_states.set(callback_query.from_user.id, "awaiting_invitation_duration")
        await callback_query.answer()

    @app.on_message(filters.text & admin_only() & filters.create(lambda _, __, m: user_states.get(m.from_user.id) == "awaiting_invitation_duration"))
    async def handle_invitation_duration(client, message):
        try:
            duration = int(message.text.strip())
            code = generate_invitation_code()
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO invitation_codes (code, duration, used) VALUES (?, ?, 0)", (code, duration))
                conn.commit()
            await message.reply(f"Código de invitación generado: {code}\nDuración: {duration} días")
            user_states.set(message.from_user.id, None)
        except ValueError:
            await message.reply("Por favor, introduce un número válido para la duración en días.")
            user_states.set(message.from_user.id, "awaiting_invitation_duration")

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
                cursor.execute("DELETE FROM user_tipsters WHERE user_id = ? AND tipster_name IN (SELECT Nombre FROM tipsters WHERE Efectividad > 65)", (user_id,))
                cursor.execute("UPDATE users SET receive_all_alta_efectividad = 0 WHERE user_id = ?", (user_id,))
                await callback_query.answer("Has desactivado todos los tipsters de Alta Efectividad.")
            else:
                cursor.executemany("INSERT INTO user_tipsters (user_id, tipster_name) VALUES (?, ?) ON CONFLICT DO NOTHING", [(user_id, tipster['Nombre']) for _, tipster in tipsters_df[tipsters_df['Efectividad'] > 65].iterrows()])
                cursor.execute("UPDATE users SET receive_all_alta_efectividad = 1 WHERE user_id = ?", (user_id,))
                await callback_query.answer("Has activado todos los tipsters de Alta Efectividad.")
            conn.commit()

        await update_tipster_buttons(client, callback_query)

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

        # Actualizar los botones en el mensaje
        await callback_query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
        await callback_query.answer("Botones actualizados.")

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
        victorias = stats.get('Victorias', None)
        derrotas = stats.get('Derrotas', None)
        efectividad = stats.get('Efectividad', None)
        racha = stats.get('Dias en racha', 0)

        # Verificar si las estadísticas son NaN y manejar el caso
        victorias = 0 if pd.isna(victorias) else int(victorias)
        derrotas = 0 if pd.isna(derrotas) else int(derrotas)
        bank_inicial = 0.0 if pd.isna(bank_inicial) else bank_inicial
        bank_actual = 0.0 if pd.isna(bank_actual) else bank_actual
        racha = 0 if pd.isna(racha) else int(racha)

        # Asignar semáforo
        semaforo = '🟢' if efectividad > 65 else '🟡' if 50 <= efectividad <= 65 else '🔴'

        # Procesar racha
        racha_emoji = '🌟' * min(racha, 4) + ('🎯' if racha >= 5 else '')

        # Crear el mensaje de estadísticas
        stats_message = f"Tipster: {tipster_name} {semaforo}\n"
        stats_message += f"🏦Bank Inicial: ${bank_inicial:.2f}💵\n🏦Bank Actual: ${bank_actual:.2f}💵\n"
        stats_message += f"✅Victorias: {victorias}\n❌Derrotas: {derrotas}\n📊Efectividad: {efectividad}%\nRacha: {racha} días {racha_emoji}"

        # Crear una lista para agrupar todas las imágenes procesadas
        media_group = []

        # Verificar si el mensaje contiene una imagen (foto) o es un media group
        if message.media_group_id:
            # Obtener todas las imágenes del media group
            media_group_content = await client.get_media_group(message.chat.id, message.id)

            # Procesar cada imagen
            for idx, media in enumerate(media_group_content):
                if media.photo:
                    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                        photo = await client.download_media(media.photo.file_id, file_name=tmp_file.name)
                        watermarked_image = add_watermark(photo, config.watermark_path, racha_emoji, racha)

                        # Si es la primera imagen, agregar el caption
                        media_group.append(InputMediaPhoto(watermarked_image, caption=stats_message if idx == 0 else None))

                    os.remove(tmp_file.name)
        elif message.photo:
            # Procesar una sola imagen
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                photo = await client.download_media(message.photo.file_id, file_name=tmp_file.name)
                watermarked_image = add_watermark(photo, config.watermark_path, racha_emoji, racha)

                # Crear el InputMediaPhoto para una sola imagen con el caption
                media_group.append(InputMediaPhoto(watermarked_image, caption=stats_message))

            os.remove(tmp_file.name)

        if not media_group:
            await message.reply("No se encontraron fotos en el mensaje.")
            return

        # Enviar las imágenes a los usuarios suscritos como un grupo de medios
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM user_tipsters WHERE tipster_name = ?", (tipster_name,))
            users = cursor.fetchall()

            for user in users:
                await client.send_media_group(user[0], media_group)

        # Obtener el nombre del grupo desde las estadísticas del tipster
        group_name = stats.get('Grupo', '').strip()

        # Buscar el ID del canal correspondiente desde el diccionario de canales
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
        if efectividad > 65:
            await client.send_media_group(config.channel_alta_efectividad, media_group)

            
    # Handler para grupos de imágenes
    @app.on_message((filters.media_group | filters.photo) & admin_only())
    async def handle_image_group(client, message):
        excel_file = config.excel_path
        tipsters_df, _ = load_tipsters_from_excel(excel_file)
        channels_dict = load_channels_from_excel(excel_file)

        # Manejar correctamente el grupo de medios
        if message.media_group_id:
            if not hasattr(client, 'media_groups_processed'):
                client.media_groups_processed = {}

            if message.media_group_id in client.media_groups_processed:
                return

            client.media_groups_processed[message.media_group_id] = True

            # Obtener todo el grupo de medios
            media_group_content = await client.get_media_group(message.chat.id, message.id)
            # Tomar el caption de la primera imagen del grupo
            caption = media_group_content[0].caption if media_group_content[0].caption else None
        else:
            caption = message.caption

        # Verificar si el caption existe
        if not caption:
            await message.reply("Por favor, añade el nombre del tipster a la(s) imagen(es).")
            return

        # Tomar el nombre del tipster desde el caption
        category = caption.strip()

        # Buscar estadísticas del tipster
        tipster_stats = tipsters_df[tipsters_df['Nombre'].str.lower() == category.lower()]

        if tipster_stats.empty:
            await message.reply(f"No se encontraron estadísticas para el tipster '{category}'.")
            return

        stats = tipster_stats.iloc[0]  # Obtén las estadísticas

        # Crear el mensaje de estadísticas
        efectividad = stats.get('Efectividad', 0)
        semaforo = '🟢' if efectividad > 65 else '🟡' if 50 <= efectividad <= 65 else '🔴'
        bank_inicial = stats.get('Bank Inicial', 0)
        bank_actual = stats.get('Bank Actual', 0)
        victorias = stats.get('Victorias', 0)
        derrotas = stats.get('Derrotas', 0)
        racha = stats.get('Dias en racha', 0) if not pd.isna(stats.get('Dias en racha', 0)) else 0

        racha_emoji = '🌟' * min(racha, 4) + ('🎯' if racha >= 5 else '') if racha else ''
        stats_message = f"Tipster: {category} {semaforo}\n 🏦Bank Inicial: ${bank_inicial:.2f}💵\n"
        stats_message += f"🏦Bank Actual: ${bank_actual:.2f}💵\n ✅Victorias: {victorias}\n"
        stats_message += f"❌Derrotas: {derrotas}\n📊Efectividad: {efectividad}%\nRacha: {racha} días {racha_emoji}"

        # Lista para agrupar todas las imágenes procesadas
        media_group = []

        # Procesar imágenes según si es un grupo de medios o una sola foto
        if message.media_group_id:
            for media in media_group_content:
                if media.photo:
                    with tempfile.NamedTemporaryFile() as tmp_file:
                        photo = await client.download_media(media.photo.file_id, file_name=tmp_file.name)
                        watermarked_image = add_watermark(photo, config.watermark_path, semaforo, racha)
                        media_group.append(InputMediaPhoto(watermarked_image, caption=stats_message if len(media_group) == 0 else None))
        else:
            with tempfile.NamedTemporaryFile() as tmp_file:
                photo = await client.download_media(message.photo.file_id, file_name=tmp_file.name)
                watermarked_image = add_watermark(photo, config.watermark_path, semaforo, racha)
                media_group.append(InputMediaPhoto(watermarked_image, caption=stats_message))

        if not media_group:
            await message.reply("No se encontraron fotos en el mensaje.")
            return

        # Enviar el grupo de medios a los usuarios suscritos
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM user_tipsters WHERE tipster_name = ?", (category,))
            users = cursor.fetchall()

            for user in users:
                await client.send_media_group(user[0], media_group)

        # Enviar al canal correspondiente
        group_name = stats.get('Grupo', '').lower()
        channel_id = channels_dict.get(group_name)
        if channel_id:
            await client.send_media_group(channel_id, media_group)

        # Enviar al canal de alta efectividad si corresponde
        if efectividad > 65 and 'alta efectividad' in channels_dict:
            await client.send_media_group(channels_dict['alta efectividad'], media_group)

        # Limpiar el registro de media group procesado
        if message.media_group_id:
            del client.media_groups_processed[message.media_group_id]


    @app.on_message(filters.channel & filters.chat(config.CANAL_PRIVADO_ID))
    async def handle_channel_images(client, message):
        # Manejar correctamente el grupo de medios
        if message.media_group_id:
            if not hasattr(client, 'media_groups_processed'):
                client.media_groups_processed = {}

            # Evitar procesar el grupo de medios más de una vez
            if message.media_group_id in client.media_groups_processed:
                return

            client.media_groups_processed[message.media_group_id] = True

            # Obtener todo el grupo de medios
            media_group = await client.get_media_group(message.chat.id, message.id)

            # Tomar el caption de la primera imagen (se aplicará a todas las imágenes del grupo)
            caption = media_group[0].caption if media_group[0].caption else None
            if not caption:
                await message.reply("No se detectó nombre de tipster en las imágenes.")
                return

            # Cargar las estadísticas de los tipsters y el diccionario de canales una sola vez
            tipsters_df, _ = load_tipsters_from_excel(config.excel_path)
            channels_dict = load_channels_from_excel(config.excel_path)

            # Lista para almacenar todas las imágenes procesadas
            processed_media_group = []

            # Procesar todas las imágenes del grupo de medios
            for media in media_group:
                # Aquí deberías procesar cada imagen (por ejemplo, añadir la marca de agua)
                # Agrega la imagen procesada a la lista
                processed_media_group.append(media)

            # Llamar a la función una sola vez para todo el grupo de medios procesado
            await process_image_and_send(client, message, caption.strip(), tipsters_df, channels_dict)

        else:
            # Procesar una sola imagen si no es un grupo de medios
            caption = message.caption
            if not caption:
                await message.reply("No se detectó nombre de tipster en la imagen.")
                return

            # Cargar las estadísticas de los tipsters y el diccionario de canales
            tipsters_df, _ = load_tipsters_from_excel(config.excel_path)
            channels_dict = load_channels_from_excel(config.excel_path)

            # Procesar la imagen
            await process_image_and_send(client, message, caption.strip(), tipsters_df, channels_dict)

        # Limpiar el registro del media group para evitar duplicados
        if message.media_group_id and message.media_group_id in client.media_groups_processed:
            del client.media_groups_processed[message.media_group_id]




    @app.on_callback_query(filters.regex(r"review_users") & admin_only())
    async def review_users(client, callback_query):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            users = cursor.fetchall()

        if not users:
            await callback_query.message.reply("No hay usuarios suscritos.")
            return

        buttons = []
        for user in users:
            user_id = user[0]
            first_name = user[1]
            subscription_days = user[3]
            approved_time = user[4]

            if approved_time:
                approved_time = datetime.datetime.fromisoformat(approved_time)
                days_left = (approved_time + datetime.timedelta(days=subscription_days) - datetime.datetime.now()).days
            else:
                days_left = "N/A"

            buttons.append([InlineKeyboardButton(f"{first_name} - {days_left} días restantes", callback_data=f"remove_{user_id}")])

        buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="admin_menu")])
        
        # Editar el texto del mensaje actual con los nuevos botones de usuarios
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


