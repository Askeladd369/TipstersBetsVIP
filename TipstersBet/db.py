import sqlite3
import logging
import pandas as pd

def init_db():
    """Inicializa la base de datos y crea las tablas necesarias si no existen."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        
        # Crear la tabla de usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                approved INTEGER,
                subscription_days INTEGER,
                approved_time TEXT,
                receive_all_alta_efectividad INTEGER DEFAULT 0
            )
        ''')

        # Crear la tabla de categorías
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                semaphore TEXT,
                stars INTEGER,
                main_button TEXT
            )
        ''')

        # Crear la tabla de categorías de usuario
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_categories (
                user_id INTEGER,
                category_name TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (category_name) REFERENCES categories(name),
                PRIMARY KEY (user_id, category_name)
            )
        ''')

        # Crear la tabla para los tipsters activados por los usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_tipsters (
                user_id INTEGER,
                tipster_name TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                PRIMARY KEY (user_id, tipster_name)
            )
        ''')

        # Crear la tabla de códigos de invitación
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invitation_codes (
                code TEXT PRIMARY KEY,
                duration INTEGER,
                used INTEGER
            )
        ''')

        # Crear índices para optimizar las búsquedas
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_categories_user_id ON user_categories(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_tipsters_user_id_tipster_name ON user_tipsters(user_id, tipster_name)')

        conn.commit()

# Funciones relacionadas con los usuarios
def add_user(user_id, first_name, approved, subscription_days, approved_time):
    """Agrega o actualiza un usuario en la base de datos."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO users 
            (user_id, first_name, approved, subscription_days, approved_time) 
            VALUES (?, ?, ?, ?, ?)""",
            (user_id, first_name, approved, subscription_days, approved_time))
        conn.commit()

def get_user(user_id=None):
    """Obtiene la información de un usuario o todos los usuarios si no se especifica un ID."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        if user_id:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        else:
            cursor.execute("SELECT * FROM users")
        return cursor.fetchall()

def update_user_field(user_id, field, value):
    """Actualiza un campo específico de un usuario en la base de datos."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
        conn.commit()

# Funciones relacionadas con las categorías de usuarios
def add_user_category(user_id, category_name):
    """Agrega una categoría a un usuario."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO user_categories (user_id, category_name) VALUES (?, ?)", 
                           (user_id, category_name))
            conn.commit()
        except sqlite3.IntegrityError as e:
            logging.error(f"Error al agregar categoría: {e}")

def remove_user_category(user_id, category_name):
    """Elimina una categoría de un usuario."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_categories WHERE user_id = ? AND category_name = ?", 
                       (user_id, category_name))
        conn.commit()

def get_user_categories(user_id):
    """Obtiene las categorías asociadas a un usuario."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.name FROM user_categories uc 
            JOIN categories c ON uc.category_name = c.name 
            WHERE uc.user_id = ?
        """, (user_id,))
        return [row[0] for row in cursor.fetchall()]

# Funciones relacionadas con las categorías
def add_category(name, semaphore, stars, main_button):
    """Agrega una categoría a la base de datos."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO categories (name, semaphore, stars, main_button) VALUES (?, ?, ?, ?)",
                           (name, semaphore, stars, main_button))
            conn.commit()
        except sqlite3.IntegrityError as e:
            logging.error(f"Error al agregar categoría: {e}")

def get_categories(main_button):
    """Obtiene las categorías (tipsters) para un botón principal específico."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, semaphore, stars FROM categories
            WHERE main_button = ?
        """, (main_button,))
        categories_from_db = cursor.fetchall()

    # Cargar los tipsters desde el Excel
    df = pd.read_excel("C:\\Users\\saidd\\OneDrive\\Escritorio\\Bot de Telegram pruebas\\Bot separado\\excel ejemplo.xlsx")
    categories_from_excel = [
        (row['Tipster'], row['Semaforo'], row['Dias en racha'])
        for _, row in df.iterrows() if row['Categoria'] == main_button
    ]

    # Combinar ambos conjuntos de tipsters y eliminar duplicados basados en el nombre
    combined_categories = list({(name, semaphore, stars) for name, semaphore, stars in categories_from_db + categories_from_excel})

    return combined_categories

def update_category_semaphore(name, semaphore):
    """Actualiza el semáforo de una categoría."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE categories SET semaphore = ? WHERE name = ?", (semaphore, name))
        conn.commit()

def update_category_stars(name, stars):
    """Actualiza las estrellas de una categoría."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE categories SET stars = ? WHERE name = ?", (stars, name))
        conn.commit()

def delete_category(name):
    """Elimina una categoría de la base de datos."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE name = ?", (name,))
        conn.commit()

# Funciones relacionadas con los códigos de invitación
def get_invitation_code(code):
    """Obtiene un código de invitación que no ha sido usado."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invitation_codes WHERE code = ? AND used = 0", (code,))
        return cursor.fetchone()

def mark_invitation_code_as_used(code):
    """Marca un código de invitación como usado."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE invitation_codes SET used = 1 WHERE code = ?", (code,))
        conn.commit()

def create_invitation_code(code, duration):
    """Crea un nuevo código de invitación."""
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO invitation_codes (code, duration, used) VALUES (?, ?, 0)", 
                           (code, duration))
            conn.commit()
        except sqlite3.IntegrityError as e:
            logging.error(f"Error al crear el código de invitación: {e}")

