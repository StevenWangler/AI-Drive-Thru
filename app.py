import streamlit as st
# We will replace this import later with the kernel service
from ai_logic import get_order_from_text, get_confirmation_message, process_admin_command, run_autonomous_inventory_check
import json # Add json for parsing AI responses
from src.ai_drive_thru.db_utils import get_menu_items, get_item_details, update_item_quantity
from streamlit_mic_recorder import mic_recorder # Import the recorder
import io # For handling audio bytes
from openai import OpenAI # Import OpenAI
import os # For environment variables

# --- Initialize OpenAI Client ---
# Ensure API key is set as an environment variable OPENAI_API_KEY
try:
    client = OpenAI()
    # Test connection (optional, but good practice)
    client.models.list()
except Exception as e:
    st.error(f"Failed to initialize OpenAI client. Ensure OPENAI_API_KEY is set. Error: {e}")
    client = None # Set client to None to prevent further errors

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

# --- Simple View Selection (Admin vs. User) ---
# In a real app, this would be replaced by proper authentication/authorization
view_mode = st.sidebar.radio(
    "Select View",
    ["Order Kiosk", "Admin Panel", "AI Chef"], # <-- Added AI Chef option
    key="view_mode_selector"
)
st.sidebar.divider() # Add a visual separator

# --- Initialize Session State ---
if 'messages' not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Welcome! Check out the menu or tell me your order."}]
# Use a list to store order items matching the Confirmer prompt structure
if 'current_order_list' not in st.session_state:
    st.session_state.current_order_list = []

# Initialize admin chat history if it doesn't exist
if 'admin_messages' not in st.session_state:
    st.session_state.admin_messages = [{"role": "assistant", "content": "Hi Manager! How can I help with the inventory today?"}]

# Initialize AI Chef chat history if it doesn't exist
if 'ai_chef_messages' not in st.session_state:
    st.session_state.ai_chef_messages = [{"role": "assistant", "content": "Ask me about menu ideas, item removals, or other menu optimizations!"}]

# --- Display based on selected view ---
if view_mode == "Order Kiosk":
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

        # --- Combine Text and Voice Input Handling ---
        text_input = st.chat_input("Type your order or ask a question...")
        voice_input = None # Placeholder for transcribed voice input

        st.write("Or record your order:")
        # Add the recorder widget
        # key='recorder' helps manage state. format='webm' is supported by Whisper.
        audio_info = mic_recorder(
            start_prompt="🎤 Start Recording",
            stop_prompt="⏹️ Stop Recording",
            key='recorder',
            format='wav',
            just_once=True # Return audio only once after recording
        )

        # Check if audio has been recorded
        if audio_info and client: # Only proceed if recorder returned data AND client is initialized
            audio_bytes = audio_info['bytes']
            # Add a check for empty audio data
            if not audio_bytes:
                st.warning("Received empty audio recording. Please try again.")
            else:
                audio_bio = io.BytesIO(audio_bytes)
                audio_bio.name = 'audio.wav' # Required for OpenAI API

                # Display audio player for debugging/confirmation (optional)
                # st.audio(audio_bytes, format='audio/wav') # Update format if uncommenting

                with st.spinner("Transcribing voice..."):
                    try:
                        transcript = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_bio
                        )
                        voice_input = transcript.text
                        st.success(f"Heard: {voice_input}") # Show transcription
                    except Exception as e:
                        st.error(f"Error transcribing audio: {e}")
                        voice_input = None # Ensure it's None if transcription failed


        # Determine the prompt to process (prioritize voice if available)
        prompt = voice_input if voice_input else text_input

        # Proceed only if there is a valid prompt (from text or voice)
        if prompt:
            # Add user message to state and display (inside container)
            # Use a mic icon if it came from voice
            user_avatar = "🎤" if voice_input else "👤"
            with chat_container:
                 with st.chat_message("user", avatar=user_avatar):
                     st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            # Process the input with AI using the updated ai_logic
            with st.spinner("Processing order..."):
                # Call the refactored function from ai_logic.py
                ai_response = get_order_from_text(prompt) # ai_response is now a dict

            # --- Process AI Response ---
            # Initialize variables
            ai_message_content = "" # Main response message
            stock_message_content = "" # Separate message for stock issues
            update_ui = False # Flag to indicate if we need to update UI state (e.g., sidebar)
            show_error_in_chat = False

            # 1. Check for explicit errors from ai_logic
            if "error" in ai_response:
                error_detail = ai_response.get('error', 'Unknown error from AI logic.')
                # Include raw response if available for debugging
                raw_resp_info = ai_response.get("raw_response", "")
                if raw_resp_info:
                     error_detail += f"\nRaw AI Response:\n```\n{raw_resp_info}\n```"

                ai_message_content = f"An error occurred: {error_detail}"
                show_error_in_chat = True # Will display using st.error later

            else:
                # 2. Check for unavailable items (even if other parts succeeded)
                unavailable_items = ai_response.get("unavailable_items")
                if unavailable_items:
                    stock_messages = []
                    for item_info in unavailable_items:
                        item_name = item_info.get("item", "Unknown item")
                        reason = item_info.get("reason", "unavailable")
                        stock_messages.append(f"{item_name} ({reason})")
                    if stock_messages:
                        stock_message_content = f"Sorry, there were issues with some items: {'; '.join(stock_messages)}."

                # 3. Process the main status and actions
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
                            # Use the actual quantity processed by add/remove functions if needed, but for msg, use requested
                            item_desc = f"{quantity}x {item_key}{detail_str}"

                            if action_type == 'add':
                                # We rely on ai_logic already filtering out items that *cannot* be added at all due to stock.
                                # The add_item_to_order here just updates the UI state.
                                add_item_to_order(item_key, details)
                                items_added.append(item_desc)
                                update_ui = True
                            elif action_type == 'remove':
                                removed = remove_item_from_order(item_key, quantity, details)
                                if removed:
                                    items_removed.append(item_desc)
                                    update_ui = True
                                else:
                                    items_not_found_for_removal.append(item_desc)

                        # Construct confirmation message based on performed actions
                        message_parts = []
                        if items_added:
                            message_parts.append(f"Added {', '.join(items_added)}")
                        if items_removed:
                            message_parts.append(f"Removed {', '.join(items_removed)}")

                        ai_generated_message = ai_response.get("message")
                        if ai_generated_message and (items_added or items_removed):
                            ai_message_content = ai_generated_message
                        elif message_parts:
                            ai_message_content = f"Okay, I've {', '.join(message_parts)}."
                        else:
                            if items_not_found_for_removal:
                                 ai_message_content = f"I tried to remove {', '.join(items_not_found_for_removal)}, but I couldn't find those items in your order."
                            else:
                                 # Success status but no actions? Maybe just acknowledgment. Use AI message if present.
                                 ai_message_content = ai_response.get("message", "Okay.") # Fallback if no message/actions

                    else:
                         # Status is success, but actions list is empty
                         # This might happen if the user asks "Do you have Fries?" and they are in stock.
                         ai_message_content = ai_response.get("message", "Okay, understood.") # Use AI message or a default

                elif status == "clarification":
                    ai_message_content = ai_response.get("message", "Could you please provide more details?") # Use AI message or fallback
                    # Optionally add clarification details if structured differently
                    # e.g., list options if "clarification_options" key exists

                elif status == "not_an_order":
                    ai_message_content = ai_response.get("message", "How can I help you with your order?") # Use AI message or fallback

                # ADDED: Explicit handling for item_unavailable status
                elif status == "item_unavailable":
                    ai_message_content = ai_response.get("message", "Sorry, the requested item is unavailable.") # Use AI message or fallback
                    # Note: The stock_message_content check before this might have already caught specifics
                    # if our db_utils check found it first, but this handles cases where the LLM returns the status directly.

                elif status == "unknown":
                     ai_message_content = "Sorry, I didn't quite understand that. Can you please rephrase?"
                     # Log the raw response if status is unknown for debugging
                     print(f"Unknown status from ai_logic. Raw response: {ai_response.get('raw_response')}")

                else: # Handle any other unexpected statuses
                     ai_message_content = f"Sorry, I encountered an unexpected situation (status: {status})."
                     print(f"Unexpected status '{status}' from ai_logic. Raw response: {ai_response.get('raw_response')}")


            # --- Display Assistant Messages (Stock + Main Response) ---
            with chat_container:
                # Display stock message first if there is one
                if stock_message_content:
                    with st.chat_message("assistant", avatar="ℹ️"): # Info icon for stock notice
                        st.warning(stock_message_content) # Use warning styling for visibility
                    st.session_state.messages.append({"role": "assistant", "content": stock_message_content})

                # Display the main AI response or error message
                if show_error_in_chat:
                    with st.chat_message("assistant", avatar="🚨"): # Use an error avatar
                        st.error(ai_message_content) # Display the detailed error message
                    # Add simplified error to history
                    st.session_state.messages.append({"role": "assistant", "content": f"An error occurred: {ai_response.get('error', 'Unknown error')}"})
                elif ai_message_content: # Only display if there's content (and not already handled by error)
                     with st.chat_message("assistant"):
                         st.markdown(ai_message_content)
                     st.session_state.messages.append({"role": "assistant", "content": ai_message_content})


            # Trigger UI update if order changed
            if update_ui:
                st.rerun()

    with col2:
        st.header("Menu")
        # Fetch menu items from the database
        menu_items_from_db = get_menu_items()

        if not menu_items_from_db:
            st.write("Menu is currently unavailable.")
        else:
            # Display items directly, without categories for now
            for item in menu_items_from_db:
                if item['quantity'] > 0: # Only show items in stock
                    # Use item details from DB
                    item_name = item['name']
                    item_price = item['price']
                    # Add description as tooltip if available
                    item_description = item.get('description', '') # Get description or empty string

                    # Create a unique key for the button
                    button_key = f"add_{item_name}".replace(" ", "_").replace("(", "").replace(")", "")
                    button_label = f"Add {item_name} (${item_price:.2f})"

                    if st.button(button_label, key=button_key, use_container_width=True, help=item_description):
                        # Add item using its name (assuming name is the unique identifier for adding)
                        # If we later need variations (like Soda flavors), this might need adjustment
                        # based on how variations are stored and selected.
                        add_item_to_order(item_name) # Pass item name as the key
                        st.rerun() # Rerun to update the sidebar immediately


    # --- Sidebar: Order Summary ---
    st.sidebar.header("Your Current Order")
    if st.session_state.current_order_list:
        total_price = 0
        for i, item_in_order in enumerate(st.session_state.current_order_list):
            item_name = item_in_order['item']
            item_details_from_db = get_item_details(item_name) # Fetch details from DB

            if item_details_from_db:
                item_price = item_details_from_db['price']
                # If we stored icons in DB, fetch here: item_icon = item_details_from_db.get("icon", " ") + " "
                item_icon = "🍔 " # Placeholder icon, replace if DB has icons

            else:
                # Handle case where item in order list is somehow not in DB (shouldn't happen ideally)
                item_price = 0
                item_icon = "❓ "
                print(f"Warning: Item '{item_name}' from order list not found in DB for price lookup.")


            item_quantity = item_in_order['quantity']
            item_total = item_quantity * item_price
            total_price += item_total

            # Display name logic remains similar, using item_name from order list
            display_name = f"{item_name}{' (' + item_in_order['details'] + ')' if 'details' in item_in_order else ''}"
            st.sidebar.write(f"{item_icon}{item_quantity}x {display_name} (${item_total:.2f})")

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

elif view_mode == "Admin Panel":
    st.header("Admin Management")

    # --- Restore Stock Display Section ---
    st.subheader("Current Stock Levels")
    try:
        inventory_items = get_menu_items() # Fetch items including quantities
        if inventory_items:
            # Display as a dataframe for a quick overview
            st.dataframe(inventory_items, use_container_width=True)
        else:
            st.warning("No inventory items found or unable to load.")
    except Exception as e:
        st.error(f"Error loading inventory: {e}")
        inventory_items = [] # Ensure list exists even on error
    st.divider()

    # --- Admin Command Section (Existing) ---
    st.subheader("Admin Commands") # Renamed slightly for clarity

    # Display prior admin messages
    admin_chat_container = st.container(height=300) # Adjust height if needed
    with admin_chat_container:
        for message in st.session_state.admin_messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # Admin command input
    if admin_prompt := st.chat_input("Enter admin command (e.g., 'low stock report', 'add 5 burger buns')"):
        st.session_state.admin_messages.append({"role": "user", "content": admin_prompt})
        # Display user message immediately in the container
        with admin_chat_container:
            with st.chat_message("user"):
                st.markdown(admin_prompt)

        with st.spinner("Processing command..."):
            response_data = process_admin_command(admin_prompt)
            response_text = response_data.get("response", "Could not process the command.")

            # Check if inventory might have changed and trigger rerun
            if response_data.get("inventory_updated"): # Assumes process_admin_command returns this flag
                 st.toast("Inventory possibly updated by command.")
                 # Add assistant response *before* rerunning
                 st.session_state.admin_messages.append({"role": "assistant", "content": response_text})
                 st.rerun() # Rerun to refresh stock display
            else:
                 # Add response to state normally if no rerun needed yet
                 st.session_state.admin_messages.append({"role": "assistant", "content": response_text})
                 # Display assistant response immediately without full rerun if no inventory change
                 with admin_chat_container:
                     with st.chat_message("assistant"):
                         st.markdown(response_text)

    # --- AI Chef Section REMOVED from here --- 

elif view_mode == "AI Chef": # <-- New view block
    st.header("AI Chef Assistant 🧑‍🍳")

    # Option to view current menu within the Chef section
    with st.expander("View/Hide Current Menu"):
        try:
            # Fetch fresh menu data directly here, ensures it's current for this view
            menu_items_for_chef = get_menu_items()
            if menu_items_for_chef:
                st.dataframe(menu_items_for_chef) # Display as a table/dataframe
            else:
                st.write("Menu is currently empty or could not be loaded.")
        except Exception as e:
            st.error(f"Error loading menu: {e}")
            menu_items_for_chef = [] # Ensure it's an empty list on error

    # Display AI Chef chat history
    chef_chat_container = st.container(height=500) # Adjust height as needed for main panel view
    with chef_chat_container:
        for message in st.session_state.ai_chef_messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # AI Chef chat input
    if chef_prompt := st.chat_input("Chat with the AI Chef about the menu..."):
        # Add user message to chef chat state and display immediately
        st.session_state.ai_chef_messages.append({"role": "user", "content": chef_prompt})
        with chef_chat_container:
            with st.chat_message("user"):
                st.markdown(chef_prompt)

        # --- LLM Interaction ---
        with st.spinner("AI Chef is thinking..."):
            ai_chef_response = "Sorry, I couldn't process that request right now." # Default error message
            if not client:
                ai_chef_response = "Error: OpenAI client not initialized. Please check API key."
                st.error(ai_chef_response)
            else:
                try:
                    # Fetch menu again inside the interaction if necessary, or rely on the one fetched above
                    # Re-fetching ensures latest data if menu could change rapidly, but uses more resources.
                    # Using menu_items_for_chef fetched earlier should be sufficient for most cases.
                    if not menu_items_for_chef and 'menu_items_for_chef' in locals(): # Check if fetch failed earlier
                         menu_string_for_prompt = "Menu data could not be loaded."
                    elif menu_items_for_chef:
                         menu_string_for_prompt = json.dumps(menu_items_for_chef, indent=2)
                    else:
                         menu_string_for_prompt = "The menu is currently empty or could not be loaded."

                    # Define System and User messages
                    system_message = (
                        "You are an AI Chef assistant for a drive-thru restaurant. "
                        "Your goal is to help the manager refine the menu based on creative ideas, potential ingredient availability (represented by quantity in the data), sales trends (if provided), and user requests. "
                        "Be creative but practical for a drive-thru setting. Provide concise and actionable suggestions or answers."
                    )
                    user_message_content = (
                        f"Current Menu Data:\n"
                        f"```json\n{menu_string_for_prompt}\n```\n\n"
                        f"Manager's request: \"{chef_prompt}\"\n\n"
                        f"Based on the current menu and the manager's request, provide suggestions, answer questions, or propose new menu items. "
                        f"Consider item quantities if the request involves availability. Think step-by-step."
                    )

                    messages_for_api = [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message_content}
                    ]

                    # Call OpenAI API
                    completion = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=messages_for_api
                    )
                    ai_chef_response = completion.choices[0].message.content

                except NameError: # Handle case where menu_items_for_chef wasn't defined due to initial load error
                    st.error("Error: Menu data not available for AI Chef context.")
                    ai_chef_response = "Sorry, I cannot process the request without menu data."
                except Exception as e:
                    st.error(f"Error communicating with AI Chef: {e}")
                    ai_chef_response = f"Sorry, an error occurred while contacting the AI Chef: {e}"

        # Display AI Chef's response and add to state
        st.session_state.ai_chef_messages.append({"role": "assistant", "content": ai_chef_response})
        # Rerun to display the new messages in the container immediately
        st.rerun()

# --- Sidebar: Order Summary --- 
# ... (Sidebar code remains unchanged) ...

# --- Run the app check ---
# This check prevents Streamlit from rerunning the entire script unnecessarily on every interaction.
# However, we DO need it to rerun when switching views or updating inventory, so we manage reruns explicitly.
# if __name__ == "__main__": # Standard check if running as script (less relevant for Streamlit directly)
#     pass # Streamlit handles the main loop automatically 