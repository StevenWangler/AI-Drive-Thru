import os
from dotenv import load_dotenv
import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions import KernelFunctionFromPrompt
from semantic_kernel.functions import KernelArguments
import json

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

# Load the OrderTaker function from its prompty file content
try:
    order_taker_path = os.path.join(prompts_dir, "OrderTaker.prompty")
    with open(order_taker_path, 'r') as f:
        order_taker_yaml = f.read()
    # Create function from YAML content
    order_taker_func = KernelFunctionFromPrompt.from_yaml(order_taker_yaml)
    # Optional: Add the function to the kernel's plugins if needed for planners, etc.
    # kernel.plugins.add_functions(
    #    sk.KernelPlugin(name="OrderPlugin", functions=[order_taker_func])
    # )
except FileNotFoundError:
    print(f"Error: OrderTaker.prompty not found at {order_taker_path}")
    order_taker_func = None
except Exception as e:
    print(f"An unexpected error occurred loading OrderTaker prompt: {e}")
    order_taker_func = None

# Load the Confirmer function from its prompty file content
try:
    confirmer_path = os.path.join(prompts_dir, "Confirmer.prompty")
    with open(confirmer_path, 'r') as f:
        confirmer_yaml = f.read()
    # Create function from YAML content
    confirmer_func = KernelFunctionFromPrompt.from_yaml(confirmer_yaml)
    # Optional: Add the function to the kernel's plugins
    # kernel.plugins.add_functions(
    #    sk.KernelPlugin(name="ConfirmPlugin", functions=[confirmer_func])
    # )
except FileNotFoundError:
    print(f"Error: Confirmer.prompty not found at {confirmer_path}")
    confirmer_func = None
except Exception as e:
    print(f"An unexpected error occurred loading Confirmer prompt: {e}")
    confirmer_func = None

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
        # Run the OrderTaker function
        result = await kernel.invoke(order_taker_func, KernelArguments(input=text_input))

        # The result from a JSON prompt should ideally be a JSON string.
        result_str = str(result)
        print(f"Semantic Kernel Response Content: {result_str}") # Debugging

        # Parse the JSON string result
        try:
            order_data = json.loads(result_str)
            # Add raw response for potential debugging in app.py if needed
            order_data["raw_response"] = result_str
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
        result = await kernel.invoke(confirmer_func, KernelArguments(order_json=order_json))
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

# Example usage (for testing):
if __name__ == '__main__':
    test_order = "I'd like two burgers, a large fries, and one coke please."
    # Need to run the async function for testing
    structured_order = asyncio.run(get_order_from_text_async(test_order))
    print(f"Structured Order: {structured_order}")

    test_clarification = "gimme a soda"
    structured_order_clarify = asyncio.run(get_order_from_text_async(test_clarification))
    print(f"Clarification Needed: {structured_order_clarify}")

    test_unavailable = "do you have onion rings?"
    structured_order_unavail = asyncio.run(get_order_from_text_async(test_unavailable))
    print(f"Item Unavailable: {structured_order_unavail}")

    test_not_order = "hello"
    structured_order_not = asyncio.run(get_order_from_text_async(test_not_order))
    print(f"Not an Order: {structured_order_not}")

    # Test Confirmer
    test_order_for_confirm = [
        {"item": "Cheeseburger", "quantity": 2},
        {"item": "Fries (Large)", "quantity": 1},
        {"item": "Soda", "quantity": 1, "details": "Coke"}
    ]
    confirmation_result = get_confirmation_message(test_order_for_confirm)
    print(f"Confirmation Result: {confirmation_result}") 