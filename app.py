import streamlit as st
# We will replace this import later with the kernel service
from ai_logic import get_order_from_text, get_confirmation_message
import json # Add json for parsing AI responses

# --- Menu Data ---
# Centralized menu definition with icons
MENU = {
    "Main Dishes": {
        "Burger": {"price": 5.00, "item_key": "Burger", "icon": "🍔"},
        "Cheeseburger": {"price": 5.50, "item_key": "Cheeseburger", "icon": "🧀"}, # Using cheese emoji for variation
    },
    "Sides": {
        "Fries (Regular)": {"price": 2.50, "item_key": "Fries (Regular)", "icon": "🍟"},
        "Fries (Large)": {"price": 3.50, "item_key": "Fries (Large)", "icon": "🍟"},
    },
    "Drinks": {
        "Coke": {"price": 2.00, "item_key": "Soda", "details": "Coke", "icon": "🥤"},
        "Sprite": {"price": 2.00, "item_key": "Soda", "details": "Sprite", "icon": "🥤"},
        "Lemonade": {"price": 2.00, "item_key": "Soda", "details": "Lemonade", "icon": "🍋"}, # Lemon for lemonade
    },
    "Desserts": {
        "Chocolate Milkshake": {"price": 4.00, "item_key": "Milkshake", "details": "Chocolate", "icon": "🧋"},
        "Vanilla Milkshake": {"price": 4.00, "item_key": "Milkshake", "details": "Vanilla", "icon": "🧋"},
        "Strawberry Milkshake": {"price": 4.00, "item_key": "Milkshake", "details": "Strawberry", "icon": "🧋"},
    }
}

# --- Helper Function to Add Items ---
def add_item_to_order(item_key, details=None):
    """Adds or increments an item in the session state order list."""
    if 'current_order_list' not in st.session_state:
        st.session_state.current_order_list = []

    found = False
    for item in st.session_state.current_order_list:
        # Check if item_key and details match (if details exist)
        if item['item'] == item_key and item.get('details') == details:
            item['quantity'] += 1
            found = True
            break

    if not found:
        new_item = {"item": item_key, "quantity": 1}
        if details:
            new_item["details"] = details
        st.session_state.current_order_list.append(new_item)

# --- Helper Function to Remove Items ---
def remove_item_from_order(item_key, quantity=1, details=None):
    """Removes or decrements an item in the session state order list.

    Args:
        item_key: The key of the item to remove (e.g., 'Burger').
        quantity: The number of items to remove (defaults to 1).
        details: Specific details of the item to remove (e.g., 'Coke' for 'Soda').
    """
    if 'current_order_list' not in st.session_state or not st.session_state.current_order_list:
        return # Nothing to remove

    items_to_remove_indices = []
    found_item = None
    for i, item in enumerate(st.session_state.current_order_list):
        if item['item'] == item_key and item.get('details') == details:
            found_item = item
            # Decrease quantity
            item['quantity'] -= quantity
            # If quantity drops to 0 or below, mark for removal
            if item['quantity'] <= 0:
                items_to_remove_indices.append(i)
            break # Assume only one matching entry per item/detail combo

    # Remove items marked for removal (iterate in reverse to avoid index issues)
    for index in sorted(items_to_remove_indices, reverse=True):
        del st.session_state.current_order_list[index]

    # Return True if the item was found and quantity adjusted/removed, False otherwise
    return found_item is not None

# --- Streamlit App Layout ---
st.set_page_config(layout="wide") # Use wider layout

st.markdown("<h1 style='text-align: center;'>Welcome to the AI Drive-Thru! 🚗💨</h1>", unsafe_allow_html=True)
st.write(" ") # Add some space below title

# --- Initialize Session State ---
if 'messages' not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Welcome! Check out the menu or tell me your order."}]
# Use a list to store order items matching the Confirmer prompt structure
if 'current_order_list' not in st.session_state:
    st.session_state.current_order_list = []


# --- Main Area: Chat and Menu ---
# Adjust column widths - give chat slightly more space e.g., 3:2 ratio
col1, col2 = st.columns([3, 2])

with col1:
    st.header("Order Chat")
    # Add a container for the chat history for potential height control later
    chat_container = st.container(height=500) # Adjust height as needed
    with chat_container:
        # Display prior messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # Get user input via chat
    if prompt := st.chat_input("Type your order or ask a question..."):
        # Add user message to state and display (inside container)
        with chat_container:
             with st.chat_message("user"):
                 st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Process the input with AI using the updated ai_logic
        with st.spinner("Processing..."):
            # Call the refactored function from ai_logic.py
            ai_response = get_order_from_text(prompt) # ai_response is now a dict

        # Process the structured response from ai_logic
        ai_message_content = ""
        update_ui = False # Flag to indicate if we need to update UI state (e.g., sidebar)
        show_error_in_chat = False

        # Check if the AI logic itself returned an error
        if "error" in ai_response:
            error_detail = ai_response.get('error', 'Unknown error from AI logic.')
            # Include raw response if available for debugging
            raw_resp_info = ai_response.get("raw_response", "")
            if raw_resp_info:
                 error_detail += f"\nRaw AI Response:\n```\n{raw_resp_info}\n```"

            ai_message_content = f"An error occurred: {error_detail}"
            # Display technical errors using st.error within the chat message for clarity
            with chat_container:
                with st.chat_message("assistant", avatar="🚨"): # Use an error avatar
                    st.error(ai_message_content)
            # Also add to history, but maybe without the full raw response for brevity
            st.session_state.messages.append({"role": "assistant", "content": f"An error occurred: {ai_response.get('error', 'Unknown error')}"})
            show_error_in_chat = True # Prevent default message display below

        else:
            # If no direct error, process the structured response based on 'status'
            status = ai_response.get("status", "unknown") # Default to 'unknown' if status missing

            if status == "success":
                actions = ai_response.get("actions", [])
                if actions:
                    items_added = []
                    items_removed = []
                    items_not_found_for_removal = []

                    for action_data in actions:
                        action_type = action_data.get('action')
                        item_key = action_data.get('item')
                        details = action_data.get('details')
                        try:
                            quantity = int(action_data.get('quantity', 1))
                        except (ValueError, TypeError):
                            quantity = 1

                        if not item_key or quantity <= 0:
                            continue # Skip invalid actions

                        detail_str = f' ({details})' if details else ''
                        item_desc = f"{quantity}x {item_key}{detail_str}"

                        if action_type == 'add':
                            add_item_to_order(item_key, details)
                            # Note: add_item_to_order increments quantity internally,
                            # so we add the description based on the requested quantity.
                            items_added.append(item_desc)
                            update_ui = True
                        elif action_type == 'remove':
                            removed = remove_item_from_order(item_key, quantity, details)
                            if removed:
                                items_removed.append(item_desc)
                                update_ui = True
                            else:
                                # Track items the AI tried to remove but weren't in the order
                                items_not_found_for_removal.append(item_desc)

                    # Construct confirmation message based on performed actions
                    message_parts = []
                    if items_added:
                        message_parts.append(f"Added {', '.join(items_added)}")
                    if items_removed:
                        message_parts.append(f"Removed {', '.join(items_removed)}")

                    # Use the AI's generated message if available and seems reasonable,
                    # otherwise construct one.
                    ai_generated_message = ai_response.get("message")
                    if ai_generated_message and (items_added or items_removed):
                        ai_message_content = ai_generated_message
                    elif message_parts:
                        ai_message_content = f"Okay, I've {' and '.join(message_parts)}."
                    else:
                        # Handle cases where AI returns success but no valid actions are parsed or performed
                        if items_not_found_for_removal:
                             ai_message_content = f"I tried to remove {', '.join(items_not_found_for_removal)}, but I couldn't find those exact items in your order."
                             update_ui = False # No actual change to the order
                        else:
                             ai_message_content = "I understood the request, but couldn't identify specific actions to perform. Could you please rephrase?"

                else:
                    # Status is success, but actions list is empty
                    ai_message_content = "I understood you, but didn't find specific items in your request to add or remove."

            elif status in ["clarification_needed", "item_unavailable", "not_an_order"]:
                # These statuses should have a 'message' intended for the user
                ai_message_content = ai_response.get("message", f"I received a '{status}' status but no message. Could you please rephrase?")
                # No UI update needed as the order hasn't changed

            elif status == "unknown":
                 ai_message_content = "Sorry, I received an unexpected response structure. Please try again."
                 # Optionally log the raw response for debugging
                 print(f"Unknown status received. Raw response: {ai_response.get('raw_response', ai_response)}")

            else: # Handle any other unexpected status values
                ai_message_content = f"Sorry, I couldn't process that due to an unexpected status: {status}. Please try again."
                # Optionally log the raw response
                print(f"Unexpected status '{status}'. Raw response: {ai_response.get('raw_response', ai_response)}")


        # Display AI response message if content exists and wasn't an error shown above
        # (Errors shown via st.error have show_error_in_chat = True)
        if ai_message_content and not show_error_in_chat:
             st.session_state.messages.append({"role": "assistant", "content": ai_message_content})
             with chat_container:
                  with st.chat_message("assistant"):
                      st.markdown(ai_message_content)

        # Rerun if the order was updated (update_ui=True)
        # or if there's a new message/error to display
        if update_ui or ai_message_content:
            st.rerun()

with col2:
    st.header("Menu")
    # Use expanders for categories
    for category, items in MENU.items():
        with st.expander(f"**{category}**", expanded=True): # Start expanded
            for name, details in items.items():
                icon = details.get("icon", "") # Get icon, default to empty string
                # Include icon in the button label
                button_label = f"{icon} Add {name} (${details['price']:.2f})"
                button_key = f"add_{category}_{name}".replace(" ", "_").replace("(", "").replace(")", "")
                if st.button(button_label, key=button_key, use_container_width=True):
                    add_item_to_order(details['item_key'], details.get('details'))
                    st.rerun() # Rerun to update the sidebar immediately


# --- Sidebar: Order Summary ---
st.sidebar.header("Your Current Order")
if st.session_state.current_order_list:
    total_price = 0
    for i, item in enumerate(st.session_state.current_order_list):
        item_price = 0
        found_price = False
        for category_items in MENU.values():
            for menu_name, menu_details in category_items.items():
                 if menu_details['item_key'] == item['item'] and menu_details.get('details') == item.get('details'):
                     item_price = menu_details['price']
                     found_price = True
                     break
            if found_price:
                break

        item_total = item['quantity'] * item_price
        total_price += item_total
        # Try to find icon for the sidebar display too
        item_icon = ""
        found_icon = False
        for category_items in MENU.values():
             for menu_name, menu_details in category_items.items():
                 if menu_details['item_key'] == item['item'] and menu_details.get('details') == item.get('details'):
                    item_icon = menu_details.get("icon", " ") + " " # Add space after icon
                    found_icon = True
                    break
             if found_icon:
                break

        display_name = f"{item['item']}{' (' + item['details'] + ')' if 'details' in item else ''}"
        st.sidebar.write(f"{item_icon}{item['quantity']}x {display_name} (${item_total:.2f})") # Add icon here

    st.sidebar.markdown("---") # Add a separator
    st.sidebar.subheader(f"Total: ${total_price:.2f}")
    st.sidebar.markdown("---") # Add a separator

    if st.sidebar.button("Confirm Order", use_container_width=True):
        # 1. Get confirmation message from AI
        with st.spinner("Generating confirmation..."):
            confirmation_response = get_confirmation_message(st.session_state.current_order_list)

        # 2. Display confirmation message (or error) in the chat
        if "error" in confirmation_response:
            error_msg = confirmation_response.get("error", "Could not generate confirmation.")
            st.sidebar.error(f"Error confirming order: {error_msg}") # Show error in sidebar
            # Optionally add to chat history too
            st.session_state.messages.append({"role": "assistant", "content": f"Sorry, there was an error generating the confirmation: {error_msg}"})
            st.rerun() # Rerun to show the message in chat history
        else:
            confirmation_text = confirmation_response.get("confirmation", "Please review your order.")
            # Add AI confirmation message to chat history
            st.session_state.messages.append({"role": "assistant", "content": confirmation_text})

            # 3. Placeholder for actual confirmation logic (e.g., asking user Y/N)
            # For now, we'll just display the confirmation message and proceed
            # TODO: Add user interaction step (e.g., buttons Yes/No in chat or sidebar)

            # 4. Show success animation and message (as before)
            st.balloons()
            st.sidebar.success("Order Confirmed! Proceed to payment.") # Keep simple success message for now

            # 5. Optionally clear order and messages for next customer
            # Clear order after confirmation
            # st.session_state.current_order_list = []
            # st.session_state.messages = [{"role": "assistant", "content": "Order placed! How can I help the next customer?"}]
            # st.rerun()
            # Rerun needed to display the confirmation message added to chat history
            st.rerun()

    if st.sidebar.button("Clear Order", type="secondary", use_container_width=True):
        st.session_state.current_order_list = []
        # Add message to chat history about clearing order
        st.session_state.messages.append({"role": "assistant", "content": "Okay, I've cleared your current order."})
        st.rerun()

else:
    st.sidebar.write("Your order is empty.")
    st.sidebar.markdown("---")

# --- (Placeholder logic we removed - cleanup) ---
# # --- Order Summary (Placeholder) ---
# st.sidebar.header("Your Current Order")
# if st.session_state.current_order: # Old state variable
#     st.sidebar.json(st.session_state.current_order)
# else:
#     st.sidebar.write("Your order is empty.")
#
# # --- Checkout Button (Placeholder) ---
# if st.session_state.current_order: # Old state variable
#     if st.sidebar.button("Confirm Order"):
#         st.balloons()
#         st.sidebar.success("Order Confirmed! Proceed to payment.")
#         # TODO: Add logic to finalize order, clear state etc.

# --- Order Summary (Placeholder) ---
# st.sidebar.header("Your Current Order")
# if st.session_state.current_order:
#     st.sidebar.json(st.session_state.current_order)
# else:
#     st.sidebar.write("Your order is empty.")
#
# # --- Checkout Button (Placeholder) ---
# if st.session_state.current_order:
#     if st.sidebar.button("Confirm Order"):
#         st.balloons()
#         st.sidebar.success("Order Confirmed! Proceed to payment.")
#         # TODO: Add logic to finalize order, clear state etc. 