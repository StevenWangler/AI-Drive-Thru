import sqlite3
import os
from typing import Optional, Dict, Any, List

DB_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'menu.db') # Assumes db is in root

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # Return rows as dictionary-like objects
    return conn

def get_menu_items() -> List[Dict[str, Any]]:
    """Fetches all items from the menu_items table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, description, price, quantity FROM menu_items")
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items

def get_item_details(item_name: str) -> Optional[Dict[str, Any]]:
    """Fetches details for a specific item by name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, description, price, quantity FROM menu_items WHERE name = ? COLLATE NOCASE", (item_name,))
    item = cursor.fetchone()
    conn.close()
    return dict(item) if item else None

def get_item_quantity(item_name: str) -> Optional[int]:
    """Fetches the current quantity for a specific item by name."""
    item = get_item_details(item_name)
    return item['quantity'] if item else None


def update_item_quantity(item_name: str, quantity_change: int) -> bool:
    """
    Updates the quantity of a specific item.
    Decreases quantity if quantity_change is negative, increases if positive.
    Ensures quantity does not go below zero.
    Returns True if update was successful, False otherwise (e.g., item not found or insufficient stock for decrease).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check current quantity first if decreasing
        if quantity_change < 0:
            cursor.execute("SELECT quantity FROM menu_items WHERE name = ? COLLATE NOCASE", (item_name,))
            current_item = cursor.fetchone()
            if not current_item:
                print(f"Error: Item '{item_name}' not found for quantity update.")
                return False
            if current_item['quantity'] < abs(quantity_change):
                print(f"Error: Insufficient stock for '{item_name}'. Requested: {abs(quantity_change)}, Available: {current_item['quantity']}")
                return False

        # Perform the update
        cursor.execute("""
            UPDATE menu_items
            SET quantity = quantity + ?
            WHERE name = ? COLLATE NOCASE
        """, (quantity_change, item_name))

        if cursor.rowcount == 0:
             # This case should ideally be caught by the check above if quantity_change < 0
             # but handles cases where the item disappears between check and update or item_name is wrong
             print(f"Error: Item '{item_name}' not found during update or no change needed.")
             conn.rollback() # Rollback any potential partial changes if transaction semantics were more complex
             return False


        conn.commit()
        print(f"Successfully updated quantity for '{item_name}' by {quantity_change}.")
        return True
    except sqlite3.Error as e:
        print(f"Database error updating quantity for '{item_name}': {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# Example Usage (can be run directly for testing)
# if __name__ == "__main__":
#     print("--- Full Menu ---")
#     print(get_menu_items())
#     print("\n--- Cheeseburger Details ---")
#     print(get_item_details('Cheeseburger'))
#     print("\n--- Fries Quantity ---")
#     print(get_item_quantity('Fries'))
#     print("\n--- Ordering 2 Cheeseburgers ---")
#     update_item_quantity('Cheeseburger', -2)
#     print(get_item_details('Cheeseburger'))
#     print("\n--- Trying to order 1000 Fries (should fail) ---")
#     update_item_quantity('Fries', -1000)
#     print(get_item_details('Fries'))
#     print("\n--- Adding 10 Fries ---")
#     update_item_quantity('Fries', 10)
#     print(get_item_details('Fries'))
#     print("\n--- Getting quantity of non-existent item ---")
#     print(get_item_quantity('NonExistent'))
#     print("\n--- Updating quantity of non-existent item ---")
#     update_item_quantity('NonExistent', -1) 