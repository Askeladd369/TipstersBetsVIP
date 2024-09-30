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

#Funcion para dividir los botones de tipsters
def split_message(text, max_chars=4096):
    """Divide un mensaje en partes más pequeñas si excede el límite de caracteres permitido."""
    return [text[i:i+max_chars] for i in range(0, len(text), max_chars)]

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
    #callback admin menu
    @app.on_callback_query(filters.regex(r"admin_menu") & filters.create(lambda _, __, m: is_admin(m.from_user.id)))
    async def show_admin_menu(client, callback_query):
        await admin_menu(client, callback_query.message)
        await callback_query.answer()
    #callback menu user
    @app.on_callback_query(filters.regex(r"user_main_menu"))
    async def show_main_button_menu_callback(client, callback_query):
        # Aquí llamamos a la función que muestra el menú principal de botones.
        await show_main_button_menu(client, callback_query.message)
        await callback_query.answer()
    #handler codigo de invitacion
    @app.on_callback_query(filters.regex(r"generate_invitation_code") & filters.create(lambda _, __, m: is_admin(m.from_user.id)))
    async def handle_generate_invitation_code(client, callback_query):
        await callback_query.message.reply("Por favor, introduce la duración (en días) para el código de invitación:")
        user_states.set(callback_query.from_user.id, "awaiting_invitation_duration")
        await callback_query.answer()
    #handler duracion del codigo de invitacion
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
    #Menu de admin
    @app.on_message(filters.command("admin") & filters.create(lambda _, __, m: is_admin(m.from_user.id)))
    async def admin_menu(client, message):
        buttons = [
            [InlineKeyboardButton("Revisar Usuarios 👥", callback_data="review_users")],
            [InlineKeyboardButton("Generar Código de Invitación 🔑", callback_data="generate_invitation_code")],
            [InlineKeyboardButton("Subir Excel 📊", callback_data="upload_excel")]
        ]
        
        await message.reply("Menú de administración:", reply_markup=InlineKeyboardMarkup(buttons))

    #carga los botones del excel
    @app.on_callback_query(filters.regex(r"main_(Button\d+)_select"))
    async def handle_main_button_selection(client, callback_query):
        # Cargar los grupos dinámicamente desde el archivo Excel
        tipsters_df, grupos = load_tipsters_from_excel(config.excel_path)
        
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

        # Dividir el mensaje si es muy largo
        message_parts = split_message(message_text)

        # Enviar las partes del mensaje, una tras otra
        for part in message_parts:
            await callback_query.message.reply_text(part)

        # Construir los botones para activar/desactivar tipsters
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
        await callback_query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
        await callback_query.answer("Botones actualizados.")

    @app.on_callback_query(filters.regex(r"toggle_all_alta_efectividad"))
    async def toggle_all_alta_efectividad(client, callback_query):
        user_id = callback_query.from_user.id
        tipsters_df, grupos = load_tipsters_from_excel(config.excel_path)

        with sqlite3.connect("bot_database.db") as conn:
            cursor = conn.cursor()
            
            # Verificar el estado actual de "Alta Efectividad"
            cursor.execute("SELECT receive_all_alta_efectividad FROM users WHERE user_id = ?", (user_id,))
            receive_all = cursor.fetchone()[0]
            
            if receive_all:
                # Desactivar todos los tipsters de alta efectividad
                cursor.execute("""
                    DELETE FROM user_tipsters 
                    WHERE user_id = ? AND tipster_name IN (SELECT Nombre FROM tipsters WHERE Efectividad > 65)
                """, (user_id,))
                print(f"[DEBUG] Desactivando todos los tipsters de alta efectividad para el usuario {user_id}.")
                cursor.execute("UPDATE users SET receive_all_alta_efectividad = 0 WHERE user_id = ?", (user_id,))
                conn.commit()
                print(f"[DEBUG] Estado de 'receive_all_alta_efectividad' actualizado a 0 para el usuario {user_id}.")
                await callback_query.answer("Has desactivado todos los tipsters de Alta Efectividad.")
            else:
                # Activar todos los tipsters de alta efectividad
                cursor.executemany("""
                    INSERT INTO user_tipsters (user_id, tipster_name) 
                    VALUES (?, ?)
                    ON CONFLICT DO NOTHING
                """, [(user_id, tipster['Nombre']) for _, tipster in tipsters_df[tipsters_df['Efectividad'] > 65].iterrows()])
                print(f"[DEBUG] Activando todos los tipsters de alta efectividad para el usuario {user_id}.")
                cursor.execute("UPDATE users SET receive_all_alta_efectividad = 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                print(f"[DEBUG] Estado de 'receive_all_alta_efectividad' actualizado a 1 para el usuario {user_id}.")
                await callback_query.answer("Has activado todos los tipsters de Alta Efectividad.")

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
            
            # Verificar si el tipster ya está activado para el usuario
            cursor.execute("SELECT * FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", (user_id, tipster_name))
            subscription = cursor.fetchone()
            
            if subscription:
                # Si está activado, desactivarlo
                cursor.execute("DELETE FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", (user_id, tipster_name))
                print(f"[DEBUG] Desactivando notificaciones para {tipster_name} del usuario {user_id}.")
                conn.commit()
                
                # Verificar que se haya realizado el cambio
                cursor.execute("SELECT * FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", (user_id, tipster_name))
                if cursor.fetchone() is None:
                    print(f"[DEBUG] {tipster_name} desactivado correctamente para el usuario {user_id}.")
                else:
                    print(f"[ERROR] No se pudo desactivar {tipster_name} para el usuario {user_id}.")
                await callback_query.answer(f"Has desactivado las notificaciones para {tipster_name}.")
            else:
                # Si no está activado, activarlo
                cursor.execute("INSERT INTO user_tipsters (user_id, tipster_name) VALUES (?, ?)", (user_id, tipster_name))
                print(f"[DEBUG] Activando notificaciones para {tipster_name} del usuario {user_id}.")
                conn.commit()
                
                # Verificar que se haya realizado el cambio
                cursor.execute("SELECT * FROM user_tipsters WHERE user_id = ? AND tipster_name = ?", (user_id, tipster_name))
                if cursor.fetchone():
                    print(f"[DEBUG] {tipster_name} activado correctamente para el usuario {user_id}.")
                else:
                    print(f"[ERROR] No se pudo activar {tipster_name} para el usuario {user_id}.")
                await callback_query.answer(f"Has activado las notificaciones para {tipster_name}.")

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

    async def process_image_and_send(client, message, tipster_name, tipsters_df, channels_dict):
        tipster_stats = tipsters_df[tipsters_df['Nombre'].str.lower() == tipster_name.lower()]

        if tipster_stats.empty:
            await message.reply(f"No se encontraron estadísticas para el tipster '{tipster_name}'.")
            return

        stats = tipster_stats.iloc[0]

        # Obtener estadísticas (evitando NaN)
        bank_inicial = stats.get('Bank Inicial', None)
        bank_actual = stats.get('Bank Actual', None)
        victorias = stats.get('Victorias', None)
        derrotas = stats.get('Derrotas', None)
        efectividad = stats.get('Efectividad', None)
        racha = stats.get('Dias en racha', 0)

        # Asignar el semáforo basado en la columna 'Efectividad'
        if efectividad > 65:
            semaforo = '🟢'
        elif 50 <= efectividad <= 65:
            semaforo = '🟡'
        else:
            semaforo = '🔴'

        # Procesar racha
        if pd.isna(racha) or not isinstance(racha, (int, float)):
            racha = 0
        else:
            racha = int(racha)

        racha_emoji = '🌟' * min(racha, 4) + ('🎯' if racha >= 5 else '')

        # Crear el mensaje
        stats_message = f"Tipster: {tipster_name}{semaforo}\n Control de apuestas👇\n"
        if bank_inicial is not None:
            stats_message += f"Bank Inicial 🏦: ${int(bank_inicial):.2f} 💵\n"
        if bank_actual is not None:
            stats_message += f"Bank Actual 🏦: ${int(bank_actual):.2f} 💵\n"
        if victorias is not None:
            stats_message += f"Victorias: {int(victorias)} ✅\n"
        if derrotas is not None:
            stats_message += f"Derrotas: {int(derrotas)} ❌\n"
        if efectividad is not None:
            stats_message += f"Efectividad: {int(efectividad)}% 📊\n"
        if racha:
            stats_message += f"Racha: {int(racha)} días {racha_emoji}"

        # Procesar la imagen y agregar la marca de agua
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            photo = await client.download_media(message.photo.file_id, file_name=tmp_file.name)
            watermarked_image = add_watermark(photo, config.watermark_path, racha_emoji, racha)

        # Enviar a los usuarios que tienen activado este tipster
        with sqlite3.connect("bot_database.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM user_tipsters WHERE tipster_name = ?", (tipster_name,))
            users = cursor.fetchall()

            for user in users:
                await client.send_photo(user[0], watermarked_image, caption=stats_message)

        # Enviar al canal correspondiente del grupo
        group_name = stats.get('Grupo', None)
        channel_id = channels_dict.get(group_name)
        if channel_id:
            await client.send_photo(channel_id, watermarked_image, caption=stats_message)

        # Enviar al canal de alta efectividad si corresponde
        if efectividad and efectividad > 65 and 'Alta Efectividad' in channels_dict:
            await client.send_photo(channels_dict['Alta Efectividad'], watermarked_image, caption=stats_message)

        os.remove(tmp_file.name)


    @app.on_message((filters.media_group | filters.photo) & filters.create(lambda _, __, m: m.from_user is not None and is_admin(m.from_user.id)))
    async def handle_image_group(client, message):
        # Cargar el archivo Excel
        excel_file = config.excel_path
        tipsters_df, _ = load_tipsters_from_excel(excel_file)
        channels_dict = load_channels_from_excel(excel_file)  # Asegúrate de que esta función cargue los canales correctamente

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

        # Obtener las estadísticas del tipster
        bank_inicial = stats.get('Bank Inicial', None)
        bank_actual = stats.get('Bank Actual', None)
        victorias = stats.get('Victorias', None)
        derrotas = stats.get('Derrotas', None)
        efectividad = stats.get('Efectividad', None)
        racha = stats.get('Dias en racha', None)

        if pd.isna(racha) or not isinstance(racha, (int, float)):
            racha = 0  # Asignar 0 si no es un número válido
        else:
            racha = int(racha)

        racha_emoji = '🌟' * min(racha, 4) + ('🎯' if racha >= 5 else '') if racha else ''

        # Construir el mensaje con solo las estadísticas disponibles
        stats_message = f"Tipster: {category}{semaforo}\n Control de apuestas👇\n"
        if bank_inicial is not None:
            stats_message += f"Bank Inicial 🏦: ${bank_inicial:.2f} 💵\n"
        if bank_actual is not None:
            stats_message += f"Bank Actual 🏦: ${bank_actual:.2f} 💵\n"
        if victorias is not None:
            stats_message += f"Victorias: {victorias} ✅\n"
        if derrotas is not None:
            stats_message += f"Derrotas: {derrotas} ❌\n"
        if efectividad is not None:
            stats_message += f"Efectividad: {efectividad}% 📊\n"
        if racha:
            stats_message += f"Racha: {racha} días {racha_emoji}"

        processed_images = []
        if message.media_group_id:
            for media in media_group:
                if media.photo:
                    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                        photo = await client.download_media(media.photo.file_id, file_name=tmp_file.name)
                        watermarked_image = add_watermark(photo, config.watermark_path, semaforo, racha)
                        processed_images.append(watermarked_image)
                    os.remove(tmp_file.name)
        else:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                photo = await client.download_media(message.photo.file_id, file_name=tmp_file.name)
                processed_images = [add_watermark(photo, config.watermark_path, semaforo, racha)]
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
        channel_id = channels_dict.get(group_name)  # Asegurarse de que obtenga el canal correcto

        if channel_id:
            for img in processed_images:
                await client.send_photo(channel_id, img, caption=stats_message)

        # Enviar al canal de alta efectividad si corresponde
        if efectividad > 65 and 'Alta Efectividad' in channels_dict:
            for img in processed_images:
                await client.send_photo(channels_dict['Alta Efectividad'], img, caption=stats_message)

        if message.media_group_id:
            del client.media_groups_processed[message.media_group_id]



    @app.on_message(filters.channel & filters.chat(config.CANAL_PRIVADO_ID))
    async def handle_channel_images(client, message):
        caption = message.caption
        if not caption:
            await message.reply("No se detectó nombre de tipster en la imagen.")
            return

        tipsters_df, _ = load_tipsters_from_excel(config.excel_path)
        channels_dict = load_channels_from_excel(config.excel_path)

        await process_image_and_send(client, message, caption.strip(), tipsters_df, channels_dict)





