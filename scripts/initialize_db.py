import sqlite3
import os

DB_FILE = "menu.db"

def initialize_database():
    """Creates the SQLite database and the menu_items table if they don't exist."""
    db_path = os.path.join(os.path.dirname(__file__), '..', DB_FILE) # Place DB in root
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity >= 0)
        )
    """)

    print("Database and table initialized successfully.")
    conn.commit()
    conn.close()

def populate_database():
    """Populates the menu_items table with initial data, avoiding duplicates."""
    db_path = os.path.join(os.path.dirname(__file__), '..', DB_FILE) # Place DB in root
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    items = [
        ('Cheeseburger', 'A classic beef patty with cheese, lettuce, and tomato', 5.99, 50),
        ('Veggie Burger', 'A delicious plant-based patty with all the fixings', 6.49, 30),
        ('Fries', 'Crispy golden french fries', 2.99, 100),
        ('Soda', 'Choice of cola, lemon-lime, or orange', 1.99, 80),
        ('Milkshake', 'Chocolate, Vanilla, or Strawberry', 3.49, 40),
        ('Chicken Sandwich', 'Crispy chicken breast sandwich', 6.99, 0), # Example out of stock
        ('Salad', 'Fresh garden salad with choice of dressing', 4.99, 25),
    ]

    added_count = 0
    for item in items:
        try:
            cursor.execute("""
                INSERT INTO menu_items (name, description, price, quantity)
                VALUES (?, ?, ?, ?)
            """, item)
            added_count += 1
        except sqlite3.IntegrityError:
            # Item with this name already exists, skip it
            print(f"Item '{item[0]}' already exists, skipping.")
            pass # Or update if needed: cursor.execute("UPDATE menu_items SET price=?, quantity=? WHERE name=?", (item[2], item[3], item[0]))


    if added_count > 0:
        print(f"Populated database with {added_count} initial items.")
    else:
        print("Database already populated or no new items to add.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    initialize_database()
    populate_database() 