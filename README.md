# AI Drive-Thru POC

A Proof of Concept application demonstrating a Generative AI powered drive-thru order system.

## Features

*   Takes customer orders via voice or text (TBD)
*   Uses OpenAI to process and understand the order
*   Displays the order confirmation

## Setup

1.  Clone the repository.
2.  Create a virtual environment: `python -m venv venv`
3.  Activate the environment: `source venv/bin/activate` (or `venv\Scripts\activate` on Windows)
4.  Install dependencies: `pip install -r requirements.txt`
5.  Set up your OpenAI API key (e.g., as an environment variable `OPENAI_API_KEY`).
6.  Run the Streamlit app: `streamlit run app.py`