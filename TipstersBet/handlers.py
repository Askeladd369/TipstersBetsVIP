import datetime
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
from utils import *
from db import *
import tempfile
import os
import random, string
import re
import pandas as pd

# Función para generar código de invitación
def generate_invitation_code():
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    print(f"[DEBUG] - Código generado: {code}")
    return code

# Registro de handlers en la aplicación
def register_handlers(app: Client):

    @app.on_message(filters.command("start") & filters.private)
    async def start(client, message):
        args = message.text.split()
        
        if len(args) < 2:
            await message.reply("Por favor, proporciona un código de invitación para activar el bot.")
            return
        
        invitation_code = args[1].strip()
        with sqlite3.connect("bot_database.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT duration FROM invitation_codes WHERE code = ? AND used = 0", (invitation_code,))
            code_data = cursor.fetchone()
            
            if code_data is None:
                await message.reply("Código de invitación no válido o ya usado.")
                return
            
            duration = code_data[0]
            cursor.execute("UPDATE invitation_codes SET used = 1 WHERE code = ?", (invitation_code,))
            conn.commit()
            
            user_id = message.from_user.id
            user_name = message.from_user.first_name
            approved_time = datetime.datetime.now().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, first_name, approved, subscription_days, approved_time) 
                VALUES (?, ?, ?, ?, ?)""",
                (user_id, user_name, 1, duration, approved_time))
            conn.commit()
            
            await message.reply(
                f"¡Bienvenido, {user_name}! Has activado tu membresía VIP. Tu suscripción durará {duration} días. Escribe el comando /categories para seleccionar a los tipsters que quieres recibir."
            )

    @app.on_callback_query(filters.regex(r"admin_menu") & filters.create(lambda _, __, m: is_admin(m.from_user.id)))
    async def show_admin_menu(client, callback_query):
        await admin_menu(client, callback_query.message)
        await callback_query.answer()

    @app.on_callback_query(filters.regex(r"user_main_menu"))
    async def show_main_button_menu_callback(client, callback_query):
        # Aquí llamamos a la función que muestra el menú principal de botones.
        await show_main_button_menu(client, callback_query.message)
        await callback_query.answer()

    @app.on_callback_query(filters.regex(r"generate_invitation_code") & filters.create(lambda _, __, m: is_admin(m.from_user.id)))
    async def handle_generate_invitation_code(client, callback_query):
        await callback_query.message.reply("Por favor, introduce la duración (en días) para el código de invitación:")
        user_states.set(callback_query.from_user.id, "awaiting_invitation_duration")
        await callback_query.answer()

    @app.on_message(filters.text & filters.create(lambda _, __, m: is_admin(m.from_user.id) and user_states.get(m.from_user.id) == "awaiting_invitation_duration"))
    async def handle_invitation_duration(client, message):
        try:
            duration = int(message.text.strip())
            code = generate_invitation_code()
            
            with sqlite3.connect("bot_database.db") as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO invitation_codes (code, duration, used) VALUES (?, ?, 0)", (code, duration))
                conn.commit()
            
            await message.reply(f"Código de invitación generado: {code}\nDuración: {duration} días")
            user_states.set(message.from_user.id, None)
        except ValueError:
            await message.reply("Por favor, introduce un número válido para la duración en días.")
            user_states.set(message.from_user.id, "awaiting_invitation_duration")

    @app.on_message(filters.command("admin") & filters.create(lambda _, __, m: is_admin(m.from_user.id)))
    async def admin_menu(client, message):
        buttons = [
            [InlineKeyboardButton("Revisar Usuarios 👥", callback_data="review_users")],
            [InlineKeyboardButton("Generar Código de Invitación 🔑", callback_data="generate_invitation_code")],
            [InlineKeyboardButton("Subir Excel 📊", callback_data="upload_excel")]
        ]
        
        await message.reply("Menú de administración:", reply_markup=InlineKeyboardMarkup(buttons))

    @app.on_callback_query(filters.regex(r"main_(Button\d+)_select"))
    async def handle_main_button_selection(client, callback_query):
        # Cargar los grupos dinámicamente desde el archivo Excel
        tipsters_df, grupos = load_tipsters_from_excel("C:\\Users\\Administrator\\TipstersBetsVIP\\TipstersBet\\excel tipstersbets.xlsx")
        
        # Verifica que la lista esté correctamente poblada
        if not grupos:
            print("[ERROR] La lista 'grupos' está vacía o no se pudo cargar.")
            await callback_query.answer("No se pudieron cargar los grupos.", show_alert=True)
            return

        # Agregar manualmente el grupo "Alta Efectividad"
        grupos.append("Grupo Alta Efectividad 📊")

        # Extraer el identificador del botón y determinar el índice del grupo
        group_button = callback_query.data.split("_")[1]
        match = re.search(r'\d+', group_button)
        if match:
            group_index = int(match.group()) - 1  # Calcula el índice
        else:
            await callback_query.answer("Error al procesar la solicitud.", show_alert=True)
            return

        # Verifica que el índice esté dentro de rango
        if group_index < 0 or group_index >= len(grupos):
            await callback_query.answer("Índice de grupo fuera de rango.", show_alert=True)
            return

        # Accede al nombre del grupo
        group_name = grupos[group_index]

        # Filtrar por grupo o por semáforo verde si es "Alta Efectividad"
        if group_name == "Grupo Alta Efectividad 📊":
            tipsters_in_group = tipsters_df[tipsters_df['Efectividad'] > 65]
        else:
            tipsters_in_group = tipsters_df[tipsters_df['Grupo'] == group_name]

        # Enviar una descripción detallada antes de mostrar los botones
        message_text = f"Tipsters en {group_name}:\n\n"
        for _, tipster in tipsters_in_group.iterrows():
            tipster_name = tipster['Nombre']
            message_text += f"👤 {tipster_name}\n"
            
            if pd.notna(tipster.get('Bank Inicial')):
                message_text += f"🏦 Inicial: ${tipster.get('Bank Inicial')}\n"

            if pd.notna(tipster.get('Bank Actual')):
                message_text += f"🏦 Actual: ${tipster.get('Bank Actual')}\n"

            if pd.notna(tipster.get('Victorias')):
                message_text += f"✅ Victorias: {tipster.get('Victorias')}\n"

            if pd.notna(tipster.get('Derrotas')):
                message_text += f"❌ Derrotas: {tipster.get('Derrotas')}\n"

            if pd.notna(tipster.get('Efectividad')):
                message_text += f"📊 Efectividad: {tipster.get('Efectividad')}%\n"

            racha = tipster.get('Dias en racha')
            if pd.notna(racha) and racha > 0:
                racha = int(racha)
                stars = '🌟' * min(racha, 4) + ('🎯' if racha >= 5 else '')
                message_text += f"🔥 Racha: {racha} días {stars}\n"

            message_text += "\n"

        await callback_query.message.edit_text(message_text)

        buttons = []
        with sqlite3.connect("bot_database.db") as conn:
            cursor = conn.cursor()

            # Botón para activar/desactivar todos los tipsters en "Alta Efectividad"
            if group_name == "Grupo Alta Efectividad 📊":
                cursor.execute("SELECT receive_all_alta_efectividad FROM users WHERE user_id = ?", (callback_query.from_user.id,))
                receive_all = cursor.fetchone()[0]
                active_emoji = '✅' if receive_all else '❌'
                buttons.append([InlineKeyboardButton(f"Activar/Desactivar Todos {active_emoji}", callback_data="toggle_all_alta_efectividad")])

            for _, tipster in tipsters_in_group.iterrows():
                tipster_name = tipster['Nombre']

                # Añadir el emoji de activado/desactivado
                cursor.execute("SELECT * FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", (callback_query.from_user.id, tipster_name))
                is_active = cursor.fetchone()
                active_emoji = '✅' if is_active else '❌'

                buttons.append([
                    InlineKeyboardButton(f"{tipster_name} {active_emoji}", callback_data=f"toggle_{tipster_name}_{group_button}_select")
                ])

        buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="user_main_menu")])
        await callback_query.message.reply_text("Selecciona un Tipster para activar o desactivar:", reply_markup=InlineKeyboardMarkup(buttons))
        await callback_query.answer()


    @app.on_callback_query(filters.regex(r"toggle_all_alta_efectividad"))
    async def toggle_all_alta_efectividad(client, callback_query):
        user_id = callback_query.from_user.id
        tipsters_df, grupos = load_tipsters_from_excel("C:\\Users\\Administrator\\TipstersBetsVIP\\TipstersBet\\excel tipstersbets.xlsx")

        with sqlite3.connect("bot_database.db") as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT receive_all_alta_efectividad FROM users WHERE user_id = ?", (user_id,))
            receive_all = cursor.fetchone()[0]

            if receive_all:
                # Desactivar la recepción de todos los tipsters de alta efectividad
                cursor.execute("""
                    DELETE FROM user_tipsters 
                    WHERE user_id = ? AND tipster_name IN (SELECT name FROM tipsters WHERE Efectividad > 65)
                """, (user_id,))
                cursor.execute("UPDATE users SET receive_all_alta_efectividad = 0 WHERE user_id = ?", (user_id,))
                await callback_query.answer("Has desactivado todos los tipsters de Alta Efectividad.")
            else:
                # Activar la recepción de todos los tipsters de alta efectividad
                cursor.executemany("""
                    INSERT INTO user_tipsters (user_id, tipster_name) 
                    VALUES (?, ?)
                    ON CONFLICT DO NOTHING
                """, [(user_id, tipster['Nombre']) for _, tipster in tipsters_df[tipsters_df['Efectividad'] > 65].iterrows()])
                cursor.execute("UPDATE users SET receive_all_alta_efectividad = 1 WHERE user_id = ?", (user_id,))
                await callback_query.answer("Has activado todos los tipsters de Alta Efectividad.")

            conn.commit()

        # Actualizar el menú después de activar o desactivar todos los tipsters
        await handle_main_button_selection(client, callback_query)


    @app.on_callback_query(filters.regex(r"toggle_(.+)_(Button\d+)_select"))
    async def toggle_tipster_notification(client, callback_query):
        user_id = callback_query.from_user.id
        data = callback_query.data.split("_")
        tipster_name = data[1]  # Nombre del tipster
        group_button = data[2]  # Identificador del grupo

        with sqlite3.connect("bot_database.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", 
                        (user_id, tipster_name))
            subscription = cursor.fetchone()

            if subscription:
                cursor.execute("DELETE FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", 
                            (user_id, tipster_name))
                await callback_query.answer(f"Has desactivado las notificaciones para {tipster_name}.")
            else:
                cursor.execute("INSERT INTO user_tipsters (user_id, tipster_name) VALUES (?, ?)", 
                            (user_id, tipster_name))
                await callback_query.answer(f"Has activado las notificaciones para {tipster_name}.")
            conn.commit()

        # Actualizar el menú del grupo después del cambio
        await handle_main_button_selection(client, callback_query)


    @app.on_message(filters.command("categories") & filters.private)
    async def show_main_buttons(client, message):
        user_id = message.from_user.id
        if is_user_approved(user_id):
            await show_main_button_menu(client, message)
        else:
            await message.reply("Tu cuenta aún no ha sido aprobada por el administrador. Por favor espera la confirmación.")

    @app.on_callback_query(filters.regex(r"remove_") & filters.create(lambda _, __, m: is_main_admin(m.from_user.id)))
    async def remove_user(client, callback_query):
        user_id = int(callback_query.data.split("_")[1])
        user = get_user(user_id)
        if user:
            with sqlite3.connect("bot_database.db") as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                conn.commit()
            await callback_query.answer(f"Usuario {user[0][1]} eliminado.")
            await client.send_message(user_id, "Tu membresía premium terminó. Has sido eliminado de la lista de suscriptores por el administrador.")
            await review_users(client, callback_query)
        else:
            await callback_query.answer("Usuario no encontrado.")

    @app.on_callback_query(filters.regex(r"review_users") & filters.create(lambda _, __, m: is_main_admin(m.from_user.id)))
    async def review_users(client, callback_query):
        with sqlite3.connect("bot_database.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            users = cursor.fetchall()
        
        if not users:
            await callback_query.message.reply("No hay usuarios suscritos.")
            return
        
        buttons = []
        for user in users:
            subscription_days = user[3]
            approved_time = user[4]
            
            if approved_time:
                approved_time = datetime.datetime.fromisoformat(approved_time)
                days_left = (approved_time + datetime.timedelta(days=subscription_days) - datetime.datetime.now()).days
            else:
                days_left = "N/A"

            buttons.append([InlineKeyboardButton(f"{user[1]} - {days_left} días restantes", callback_data=f"remove_{user[0]}")])
        
        buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="admin_menu")])
        
        await callback_query.message.edit_text("Usuarios suscritos:", reply_markup=InlineKeyboardMarkup(buttons))
        await callback_query.answer()

    # Modificar el handler para enviar los mensajes a los canales correspondientes
    @app.on_message((filters.media_group | filters.photo) & filters.create(lambda _, __, m: m.from_user and is_admin(m.from_user.id)))
    async def handle_image_group(client, message):
        # Cargar el archivo Excel
        excel_file = "C:\\Users\\Administrator\\TipstersBetsVIP\\TipstersBet\\excel tipstersbets.xlsx"
        tipsters_df, _ = load_tipsters_from_excel(excel_file)
        channels_dict = load_channels_from_excel(excel_file)

        if message.media_group_id:
            if not hasattr(client, 'media_groups_processed'):
                client.media_groups_processed = {}

            if message.media_group_id in client.media_groups_processed:
                return
                
            client.media_groups_processed[message.media_group_id] = True

            media_group = await client.get_media_group(message.chat.id, message.id)
            caption = media_group[0].caption if media_group[0].caption else None
        else:
            caption = message.caption

        if not caption:
            await message.reply("Por favor, añade el nombre del tipster a la(s) imagen(es).")
            return

        category = caption.strip()

        # Buscar las estadísticas del tipster en el DataFrame
        tipster_stats = tipsters_df[tipsters_df['Nombre'].str.lower() == category.lower()]

        if tipster_stats.empty:
            await message.reply("No se encontraron estadísticas para el tipster especificado.")
            return

        stats = tipster_stats.iloc[0]  # Obtén la fila de estadísticas para el tipster

        # Asignar el semáforo basado en la columna 'Efectividad'
        efectividad = stats.get('Efectividad', 0)
        if efectividad > 65:
            semaforo = '🟢'
        elif 50 <= efectividad <= 65:
            semaforo = '🟡'
        else:
            semaforo = '🔴'

        # Obtener la racha
        racha = stats.get('Dias en racha', 0)
        if pd.notna(racha):
            racha = int(racha)
        racha_emoji = '🌟' * min(racha, 4) + ('🎯' if racha >= 5 else '')

        stats_message = (
            f"Tipster: {category} {semaforo}\n"
            f"Control de apuestas 👇\n"
            f"Bank Inicial 🏦: ${stats.get('Bank Inicial', 'N/A')} 💵\n"
            f"Bank Actual 🏦: ${stats.get('Bank Actual', 'N/A')} 💵\n"
            f"Victorias: {stats.get('Victorias', 'N/A')} ✅\n"
            f"Derrotas: {stats.get('Derrotas', 'N/A')} ❌\n"
            f"Efectividad: {efectividad}% 📊\n"
            f"Dias en racha: {racha} días {racha_emoji}"
        )

        processed_images = []
        if message.media_group_id:
            for media in media_group:
                if media.photo:
                    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                        photo = await client.download_media(media.photo.file_id, file_name=tmp_file.name)
                        watermarked_image = add_watermark(photo, "C:\\Users\\Administrator\\TipstersBetsVIP\\TipstersBet\\watermark.png", semaforo, racha)
                        processed_images.append(watermarked_image)
                    os.remove(tmp_file.name)
        else:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                photo = await client.download_media(message.photo.file_id, file_name=tmp_file.name)
                processed_images = [add_watermark(photo, "C:\\Users\\Administrator\\TipstersBetsVIP\\TipstersBet\\watermark.png", semaforo, racha)]
            os.remove(tmp_file.name)

        # Enviar a los usuarios que tienen activado este tipster
        with sqlite3.connect("bot_database.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM user_tipsters WHERE tipster_name = ?", (category,))
            users = cursor.fetchall()

            for user in users:
                await client.send_photo(user[0], processed_images[0], caption=stats_message)

        # Enviar al canal correspondiente si está configurado
        group_name = stats.get('Grupo')
        channel_id = channels_dict.get(group_name)

        if channel_id:
            for img in processed_images:
                await client.send_photo(channel_id, img, caption=stats_message)

        # Enviar al canal de alta efectividad si corresponde
        if efectividad > 65 and 'Alta Efectividad' in channels_dict:
            for img in processed_images:
                await client.send_photo(channels_dict['Alta Efectividad'], img, caption=stats_message)

        if message.media_group_id:
            del client.media_groups_processed[message.media_group_id]





