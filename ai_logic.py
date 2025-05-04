import os
from dotenv import load_dotenv
import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions import KernelFunctionFromPrompt
from semantic_kernel.functions import KernelArguments
import json
# from data.menu_data import MENU # Import MENU from the new file location - REMOVED
import semantic_kernel.functions as sk_functions # Use alias to avoid potential conflicts
from src.ai_drive_thru.db_utils import get_menu_items, get_item_quantity, update_item_quantity # Import DB utils
from typing import List, Dict, Any

load_dotenv() # Load environment variables from .env file

# Configure Semantic Kernel
kernel = sk.Kernel()

# Add OpenAI chat completion service
api_key = os.getenv("OPENAI_API_KEY")
org_id = os.getenv("OPENAI_ORG_ID") # Optional: if using OpenAI org ID
service_id = "default" # Can be any name
model_id = "gpt-4o" # Or your preferred model compatible with the prompt

kernel.add_service(
    OpenAIChatCompletion(
        service_id=service_id,
        ai_model_id=model_id,
        api_key=api_key,
        org_id=org_id,
    ),
)

# Define the path to the prompts directory
prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")

# --- Helper Function to Format Menu (Updated for DB data and stock) ---
def format_menu_for_prompt() -> str: # No longer takes menu_data as input
    """Fetches menu items from DB and formats them into a string for the LLM prompt,
       excluding items with quantity 0."""
    menu_items = get_menu_items() # Fetch from DB
    menu_lines = []
    # Group items by name for potential variations (like Soda flavours if we add them later)
    # For now, we assume unique names from the DB schema constraint
    for item in menu_items:
        if item['quantity'] > 0: # Only include items in stock
            # Basic formatting, assuming 'description' isn't needed for the core prompt
            menu_lines.append(f"- {item['name']}: ${item['price']:.2f}")
            # We might need a more complex formatting if variations (like Soda flavors)
            # are stored differently in the DB later.

    if not menu_lines:
        return "Apologies, the menu is currently empty or unavailable."

    return "\n".join(menu_lines)

# --- Helper Function to Format Full Inventory (for Admin) ---
def format_inventory_for_prompt() -> str:
    """Fetches all inventory items from DB and formats them into a string for the LLM prompt,
       including their quantities."""
    inventory_items = get_menu_items() # Fetch all items from DB
    inventory_lines = []
    for item in inventory_items:
        inventory_lines.append(f"- {item['name']}: {item['quantity']} available")

    if not inventory_lines:
        return "Inventory is currently empty."

    return "\n".join(inventory_lines)

# Load the OrderTaker function from its prompty file content
try:
    order_taker_path = os.path.join(prompts_dir, "OrderTaker.prompty")
    # Revert to using from_yaml, loading the file content first
    with open(order_taker_path, 'r') as f:
        order_taker_yaml = f.read()
    order_taker_func = sk_functions.KernelFunctionFromPrompt.from_yaml(order_taker_yaml)

except FileNotFoundError:
    print(f"Error: OrderTaker.prompty not found at {order_taker_path}")
    order_taker_func = None # Set to None to indicate failure
except Exception as e:
    print(f"An unexpected error occurred loading OrderTaker prompt: {e}")
    order_taker_func = None # Set to None to indicate failure

# Load the Confirmer function from its prompty file content
try:
    confirmer_path = os.path.join(prompts_dir, "Confirmer.prompty")
    # Revert to using from_yaml for Confirmer as well
    with open(confirmer_path, 'r') as f:
        confirmer_yaml = f.read()
    confirmer_func = sk_functions.KernelFunctionFromPrompt.from_yaml(confirmer_yaml)

except FileNotFoundError:
    print(f"Error: Confirmer.prompty not found at {confirmer_path}")
    confirmer_func = None
except Exception as e:
    print(f"An unexpected error occurred loading Confirmer prompt: {e}")
    confirmer_func = None

# Load the AdminManager function from its prompty file content
try:
    admin_manager_path = os.path.join(prompts_dir, "AdminManager.prompty")
    with open(admin_manager_path, 'r') as f:
        admin_manager_yaml = f.read()
    admin_manager_func = sk_functions.KernelFunctionFromPrompt.from_yaml(admin_manager_yaml)

except FileNotFoundError:
    print(f"Error: AdminManager.prompty not found at {admin_manager_path}")
    admin_manager_func = None
except Exception as e:
    print(f"An unexpected error occurred loading AdminManager prompt: {e}")
    admin_manager_func = None

async def get_order_from_text_async(text_input: str) -> dict:
    """Processes the user's text input using Semantic Kernel and OrderTaker prompt.

    Args:
        text_input: The raw text input from the user.

    Returns:
        A dictionary representing the structured order or an error message.
    """
    if not order_taker_func:
         return {"error": "Order Taker function not loaded properly."}
    try:
        # Format the current menu from DB
        formatted_menu = format_menu_for_prompt()

        # Prepare arguments, including the dynamic menu
        # Use the alias for KernelArguments
        arguments = sk_functions.KernelArguments(input=text_input, menu=formatted_menu)

        # Invoke the function loaded from YAML
        result = await kernel.invoke(
             order_taker_func, # Invoke the function object directly
             arguments=arguments
        )

        # The result from a JSON prompt should ideally be a JSON string.
        result_str = str(result)
        print(f"Semantic Kernel Response Content: {result_str}") # Debugging

        # Parse the JSON string result
        try:
            order_data = json.loads(result_str)
            # Add raw response for potential debugging in app.py if needed
            order_data["raw_response"] = result_str

            # --- Post-processing: Stock Check ---
            if "order" in order_data and isinstance(order_data["order"], list):
                validated_order = []
                unavailable_items = []
                items_to_check = order_data["order"] # Get the list of items from the LLM response

                for item_details in items_to_check:
                    item_name = item_details.get("item")
                    item_quantity_requested = item_details.get("quantity", 1) # Assume 1 if not specified

                    if not item_name:
                        print(f"Warning: Order item missing 'item' key: {item_details}")
                        continue # Skip invalid item entries

                    # Check stock in DB
                    available_quantity = get_item_quantity(item_name)

                    if available_quantity is None:
                        print(f"Warning: Item '{item_name}' not found in DB during stock check.")
                        # Decide how to handle - maybe add to unavailable? Or let LLM handle?
                        # For now, let's assume the OrderTaker prompt should only return known items.
                        # If it returns unknown items, maybe it's a hallucination or needs clarification.
                        # Let's add it to unavailable for now.
                        unavailable_items.append({"item": item_name, "reason": "Item not found on menu."})

                    elif available_quantity == 0:
                        print(f"Stock Check: Item '{item_name}' is out of stock.")
                        unavailable_items.append({"item": item_name, "reason": "Out of stock."})

                    elif available_quantity < item_quantity_requested:
                         print(f"Stock Check: Insufficient stock for '{item_name}'. Requested: {item_quantity_requested}, Available: {available_quantity}")
                         # Add to unavailable, maybe suggest ordering the available amount?
                         unavailable_items.append({
                             "item": item_name,
                             "reason": f"Insufficient stock. Only {available_quantity} available."
                         })
                         # Option: Add the available quantity to the order instead?
                         # item_details['quantity'] = available_quantity
                         # validated_order.append(item_details)
                         # For now, just report as unavailable.

                    else:
                        # Item is in stock and quantity is sufficient
                        validated_order.append(item_details)

                # Replace the original order with the validated one
                order_data["order"] = validated_order
                # Add information about unavailable items
                if unavailable_items:
                    order_data["unavailable_items"] = unavailable_items
            # --- End Stock Check ---

            return order_data
        except json.JSONDecodeError as json_e:
            print(f"JSON Decode Error: {json_e}")
            # Try to find JSON within potential ```json ... ``` block if model wraps it
            if "```json" in result_str:
                try:
                    json_block = result_str.split("```json")[1].split("```")[0].strip()
                    order_data = json.loads(json_block)
                    order_data["raw_response"] = result_str # Still include original raw
                    return order_data
                except Exception as inner_e:
                     print(f"Failed to extract/parse JSON block: {inner_e}")
                     return {"error": f"Failed to parse order JSON: {json_e}", "raw_response": result_str}
            else:
                return {"error": f"Failed to parse order JSON: {json_e}", "raw_response": result_str}
        except Exception as e:
            print(f"Error processing kernel result: {e}")
            return {"error": f"An unexpected error occurred: {str(e)}", "raw_response": result_str}

    except Exception as e:
        print(f"Error interacting with Semantic Kernel: {e}")
        return {"error": str(e)}

async def get_confirmation_message_async(order_list: list) -> dict:
    """Generates a confirmation message using Semantic Kernel and Confirmer prompt.

    Args:
        order_list: The current order list (list of dictionaries).

    Returns:
        A dictionary containing the confirmation message or an error.
    """
    if not confirmer_func:
         return {"error": "Confirmer function not loaded properly."}
    try:
        order_json = json.dumps(order_list)
        # Invoke the confirmer function loaded from YAML
        # Use the alias for KernelArguments
        result = await kernel.invoke(confirmer_func, sk_functions.KernelArguments(order_json=order_json))
        confirmation_message = str(result).strip()

        # Basic check if the message seems empty or too short
        if not confirmation_message or len(confirmation_message) < 10:
            print(f"Warning: Confirmation message seems short/empty: {confirmation_message}")
            # Provide a fallback message
            fallback_message = "Okay, just confirming your order. Does everything look right?"
            return {"confirmation": fallback_message, "raw_response": confirmation_message}

        return {"confirmation": confirmation_message, "raw_response": confirmation_message}

    except Exception as e:
        print(f"Error interacting with Semantic Kernel for confirmation: {e}")
        return {"error": str(e)}

# Synchronous wrapper for Streamlit compatibility (Streamlit doesn't directly support async)
# This uses asyncio.run which might not be ideal in a long-running server,
# but is often sufficient for Streamlit apps. Consider alternatives if needed.
import asyncio

def get_order_from_text(text_input: str) -> dict:
    return asyncio.run(get_order_from_text_async(text_input))

def get_confirmation_message(order_list: list) -> dict:
    return asyncio.run(get_confirmation_message_async(order_list))

# --- Admin Manager AI Logic ---
async def process_admin_command_async(text_input: str) -> dict:
    """Processes the admin's text command using Semantic Kernel and AdminManager prompt.

    Args:
        text_input: The raw text command from the admin.

    Returns:
        A dictionary containing the AI's response, action taken, and whether a DB update occurred.
    """
    if not admin_manager_func:
        return {"action": "error", "message": "Admin Manager function not loaded properly.", "error_details": "Prompt file missing or invalid."}

    try:
        # Format the current inventory from DB
        formatted_inventory = format_inventory_for_prompt()

        # Prepare arguments
        arguments = sk_functions.KernelArguments(input=text_input, inventory_list=formatted_inventory)

        # Invoke the Admin Manager function
        result = await kernel.invoke(
            admin_manager_func,
            arguments=arguments
        )

        result_str = str(result)
        print(f"Admin Manager SK Response: {result_str}") # Debugging

        # Parse the JSON string result
        try:
            response_data = json.loads(result_str)
            response_data["raw_response"] = result_str # Include raw for debugging
            response_data["update_triggered"] = False # Initialize flag

            # --- Perform Database Update if Action is 'order' ---
            if response_data.get("action") == "order":
                item_name = response_data.get("item_name")
                quantity_str = response_data.get("quantity_ordered")

                if not item_name or quantity_str is None:
                    response_data["action"] = "error"
                    response_data["message"] = "Error: LLM requested an order but did not specify item name or quantity."
                    response_data["error_details"] = "Missing item_name or quantity_ordered in LLM response."
                    print(f"Admin Action Error: Missing item/quantity for order. LLM Response: {result_str}")
                    return response_data # Return early

                try:
                    quantity_ordered = int(quantity_str)
                    if quantity_ordered <= 0:
                         raise ValueError("Quantity must be positive.")

                    # Call the DB update function (use positive value for ordering more)
                    print(f"Attempting to update DB for {item_name} by +{quantity_ordered}")
                    success = update_item_quantity(item_name, quantity_ordered)

                    if success:
                        response_data["update_triggered"] = True
                        # Optionally refine the message based on success, or let the LLM's original message stand
                        # response_data["message"] = f"Successfully ordered {quantity_ordered} of {item_name}. Inventory updated."
                        print(f"DB Update successful for {item_name}")
                    else:
                        # Update failed (db_utils should print details)
                        response_data["action"] = "error"
                        response_data["message"] = f"Failed to update inventory for {item_name}. Check logs for details."
                        response_data["error_details"] = "update_item_quantity returned False."
                        print(f"DB Update failed for {item_name}")

                except (ValueError, TypeError) as e:
                     response_data["action"] = "error"
                     response_data["message"] = f"Error: Invalid quantity '{quantity_str}' specified by LLM for ordering {item_name}."
                     response_data["error_details"] = f"Invalid quantity format: {e}"
                     print(f"Admin Action Error: Invalid quantity '{quantity_str}' for order. LLM Response: {result_str}")

            # --- End Database Update Logic ---

            return response_data

        except json.JSONDecodeError as json_e:
            print(f"Admin Manager JSON Decode Error: {json_e}. Raw: {result_str}")
            # Add basic error structure
            return {"action": "error", "message": "Sorry, I couldn't process that request due to a formatting issue.", "error_details": f"Failed to parse AI response: {json_e}", "raw_response": result_str}
        except Exception as e:
            print(f"Error processing admin kernel result: {e}")
            return {"action": "error", "message": f"An unexpected error occurred: {str(e)}", "error_details": str(e), "raw_response": result_str}

    except Exception as e:
        print(f"Error interacting with Semantic Kernel for admin command: {e}")
        return {"action": "error", "message": f"Failed to reach AI service: {str(e)}", "error_details": str(e)}

# Synchronous wrapper for Streamlit
def process_admin_command(text_input: str) -> dict:
    return asyncio.run(process_admin_command_async(text_input))

# --- Autonomous Inventory Management Logic ---

# Define thresholds and reorder amounts (could be moved to config later)
LOW_STOCK_THRESHOLD = 10
REORDER_QUANTITY = 50

async def run_autonomous_inventory_check_async() -> List[Dict[str, Any]]:
    """Checks inventory levels and automatically reorders items below threshold.

    Returns:
        A list of dictionaries, where each dictionary represents an item
        that was automatically reordered.
        Example: [{"item_name": "Fries", "ordered_quantity": 50, "new_quantity": 58}]
    """
    print("Running autonomous inventory check...")
    items_reordered = []
    try:
        inventory = get_menu_items() # Fetch current state
        if not inventory:
            print("Autonomous check: No inventory found.")
            return []

        for item in inventory:
            item_name = item['name']
            current_quantity = item['quantity']

            if current_quantity < LOW_STOCK_THRESHOLD:
                print(f"Autonomous check: Item '{item_name}' is low (Qty: {current_quantity}). Threshold: {LOW_STOCK_THRESHOLD}. Ordering {REORDER_QUANTITY}.")
                # Call update_item_quantity to ADD the reorder amount
                success = update_item_quantity(item_name, REORDER_QUANTITY)

                if success:
                    # Fetch the new quantity after the update for reporting
                    new_quantity = get_item_quantity(item_name)
                    items_reordered.append({
                        "item_name": item_name,
                        "ordered_quantity": REORDER_QUANTITY,
                        "new_quantity": new_quantity if new_quantity is not None else (current_quantity + REORDER_QUANTITY) # Estimate if fetch fails
                    })
                    print(f"Autonomous check: Successfully reordered {REORDER_QUANTITY} of '{item_name}'. New quantity: {new_quantity}")
                else:
                    # Log the failure, but don't stop checking other items
                    print(f"Autonomous check: FAILED to reorder '{item_name}'. Check db_utils logs.")
            # else: # Optional: Log items that are okay
                # print(f"Autonomous check: Item '{item_name}' stock is OK (Qty: {current_quantity}).")

    except Exception as e:
        print(f"Autonomous check: An error occurred during the check: {e}")
        # Depending on requirements, you might want to return an error indicator

    if items_reordered:
        print(f"Autonomous check completed. Reordered {len(items_reordered)} items.")
    else:
        print("Autonomous check completed. No items needed reordering.")

    return items_reordered

# Synchronous wrapper for Streamlit
def run_autonomous_inventory_check() -> List[Dict[str, Any]]:
    return asyncio.run(run_autonomous_inventory_check_async())

# Define asynchronous test functions
async def run_tests_async():
    test_order = "I'd like two Cheeseburgers, a large fries, and one coke please."
    structured_order = await get_order_from_text_async(test_order)
    print(f"Structured Order: {structured_order}")

    # Test for out-of-stock item (Chicken Sandwich quantity is 0 in DB)
    test_out_of_stock = "Can I get a Chicken Sandwich and a Salad?"
    structured_order_stock = await get_order_from_text_async(test_out_of_stock)
    print(f"Out of Stock Test: {structured_order_stock}")

    # Test requesting more than available (only 30 Veggie Burgers)
    test_insufficient_stock = "I need 40 Veggie Burgers"
    structured_order_insufficient = await get_order_from_text_async(test_insufficient_stock)
    print(f"Insufficient Stock Test: {structured_order_insufficient}")


    test_clarification = "gimme a soda"
    structured_order_clarify = await get_order_from_text_async(test_clarification)
    print(f"Clarification Needed: {structured_order_clarify}")

    test_unavailable = "do you have onion rings?" # Not on menu
    structured_order_unavail = await get_order_from_text_async(test_unavailable)
    print(f"Item Not on Menu Test: {structured_order_unavail}")

    test_not_order = "hello"
    structured_order_not = await get_order_from_text_async(test_not_order)
    print(f"Not an Order: {structured_order_not}")

    # Test Confirmer
    test_order_for_confirm = [
        {"item": "Cheeseburger", "quantity": 2},
        {"item": "Fries", "quantity": 1}, # Assuming 'Fries' maps correctly
        {"item": "Soda", "quantity": 1, "details": "Coke"} # Assuming details handled okay
    ]
    # Confirmer doesn't need async wrapper if get_confirmation_message is used
    confirmation_result = get_confirmation_message(test_order_for_confirm)
    print(f"Confirmation Result: {confirmation_result}")


# Example usage (for testing):
if __name__ == '__main__':
    # Need to run the async test function
    asyncio.run(run_tests_async()) 