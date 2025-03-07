# Copilot

![Copilot](./poster.png)

> [!NOTE]
> This repository contains an experimental copilot that integrates multiple AI models. Its primary function is a chat interface, with plans to expand its capabilities in the rapidly evolving AI field. **Note that this project is a work in progress—features may be added or removed as the project evolves.**

## To Do

- [ ] ???

## Features

- Web-based chat interface built with React.
- Integration with AI models such as GPT-4, GPT-3, DALL·E, and Whisper.
- Support for file and audio uploads.
- JSON-RPC over WebSocket for asynchronous client-server communication.
- Fully asynchronous server-side code implemented with Python and aiohttp.
- Aggregation of messages from Telegram channels/chats.
- Audio recording and parsing.
- Custom prompt management for chats.

## Project Structure

- `app/`  
  Contains Python backend code.
- `gui/`  
  Contains the frontend source code.
- `configs/`  
  Contains main configs like prompts, profiles and dialogs settings.
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

Edit the environment variables or the configuration file `config.py` to set the following parameters:

- `DEV_MODE`: Set to `True` for development mode (runs backend only).
- `GOOGLE_APP_ID`: Provide your Google App ID if running in Chrome app mode (the copilot currently runs as a Progressive Web App; install it in Chrome and copy the ID from the app settings).
- `UPLOADS_DIR`: Specify the directory for storing uploaded files.
- `HOST_NAME` and `PORT`: Configure the host name and port for the web server.

## Running the Application

Start the app with:

```bash
poetry run python main.py
```
