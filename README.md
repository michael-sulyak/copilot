# Copilot

![Copilot](./poster.png)

> [!NOTE]
> This repository contains an experimental copilot that integrates multiple AI models. Its primary function is a chat interface, with plans to expand its capabilities in the rapidly evolving AI field. **Note that this project is a work in progress—features may be added or removed as the project evolves.**

## To do

- [ ] ???

## Features

- Web-based chat interface built with React.
- Integration with AI models such as GPT-4, GPT-3, DALL·E, and Whisper.
- Support for file and audio uploads.
- JSON-RPC over WebSocket for asynchronous client-server communication.
- Fully asynchronous server-side code implemented with Python and aiohttp.
- Aggregation of messages from Telegram channels/chats.
- Audio recording and parsing.
- Customizable prompt management for dynamic interactions.

## Project structure

- `app/`  
  Contains the Python backend code.
- `gui/`  
  Contains the frontend source code.
- `configs/`  
  Contains configuration files including prompts, profiles, and dialogs settings.
- `main.py`  
  The application entry point.

## Installation

Follow these steps to get started:

1. **Clone the repository:**

   ```bash
   git clone git@github.com:michael-sulyak/copilot.git
   cd copilot
   ```

2. **Install Python dependencies:**

   ```bash
   poetry install
   ```

3. **Install JavaScript dependencies:**

   Navigate to the frontend directory `gui` and install dependencies:

   ```bash
   cd gui
   npm install
   ```

   Then, build the project:

   ```bash
   npm run build
   ```

## Configuration

Edit the environment variables to set the following parameters:

- `DEV_MODE`: Set to `True` for development mode (runs backend only).
- `GOOGLE_APP_ID`: Provide your Google App ID if running in Chrome app mode. The copilot runs as a Progressive Web App, install it in Chrome and copy the ID from the app settings.
- `UPLOADS_DIR`: Specify the directory for storing uploaded files.
- `HOST_NAME` and `PORT`: Configure the host name and port for the web server.

## Chat Configuration Examples

The chat functionality can be tailored by setting up custom prompt and profile configurations. Below are two sample examples that you can modify as needed.

### Example prompt: Text improvement

This sample prompt is designed for a text improvement scenario. It instructs the system to act as an editor that checks and refines the text before publication.

- **File:** `configs/prompts/sample_prompt.yaml`
- **Contents example:**

  ```yaml
  name: "Text Improvement Prompt ({{ short_lang }})"

  versions:
    - lang: "English"
      short_lang: "EN"
    - lang: "Chinese"
      short_lang: "CN"

  prompt: |
    Imagine you are an experienced editor responsible for refining texts in {{ lang }} before they are published. Your task is to:
    1. Correct any spelling and grammatical errors.
    2. Enhance the clarity and readability of the text.
    3. Maintain the original tone and meaning.
    
    Here is the text to review:
    {your_text}
  ```
  
Or without versions:


  ```yaml
  name: "Text Improvement Prompt"

  prompt: |
    Imagine you are an experienced editor responsible for refining texts before they are published. Your task is to:
    1. Correct any spelling and grammatical errors.
    2. Enhance the clarity and readability of the text.
    3. Maintain the original tone and meaning.
    
    Here is the text to review:
    {your_text}
  ```

### Example profile: Standard chat settings

This profile defines default parameters for chat interactions such as creativity level and reasoning depth. It is intended for general-purpose queries.

- **File:** `configs/profiles/sample_profile.yaml`
- **Contents example:**

  ```yaml
  temperature: 0.5
  top_p: 0.5
  reasoning_effort: "medium"
  text: |
      You are a friendly assistant specializing in providing clear and concise answers. Your role is to explain ideas and solve problems in a manner that is both informative and easy to understand. Remember to:
      
      - Use the Metric system and Celsius for any measurements.
      - Format mathematical formulas using LaTeX. For example, express the equation of a line as $y = mx + c$.
      
      How can I help you today?
  ```

- **How to configure:**  
  Modify parameters like `temperature`, `top_p`, and `reasoning_effort` to adjust the chatbot's behavior. Change the `text` field to alter the initial prompt or instructions that the assistant uses for every session.

## Running the Application

Start the app with:

```bash
poetry run python main.py
```
