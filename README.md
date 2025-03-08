# Copilot

![Copilot](./poster.png)

> [!NOTE]
> This repository contains an experimental copilot that integrates multiple AI models. Its primary function is a chat interface, with plans to expand its capabilities in the rapidly evolving AI field. **Note that this project is a work in progress—features may be added or removed as the project evolves.**

## To do

- [ ] ???

## Features

- Web-based chat interface built with React.
- Integration with AI models such as GPT-4, GPT-3, DALL·E, and Whisper (you can use OpenAI API or OpenRouter).
- Support for file and audio uploads.
- JSON-RPC over WebSocket for asynchronous client-server communication.
- Fully asynchronous server-side code implemented with Python and aiohttp.
- Aggregation of messages from Telegram channels/chats.
- Audio recording and parsing.
- Customizable prompt management for dynamic interactions.

## Installation

Simply run:

```bash
make install
```

This command will install both Python and JavaScript dependencies, build the frontend, and set up a desktop icon.

## Configuration

All configuration files (prompts, profiles, etc.) are located in the `configs/` folder (`demo_configs` is an example of the folder). It’s easy to create your own settings by starting from the example files provided.

## Project structure

- `app/`  
  Contains the Python backend code.
- `gui/`  
  Contains the frontend source code.
- `configs/`  
  Contains configuration files. Use the example files provided as a starting point to create your own prompts and profiles.
- `main.py`  
  The application entry point.
