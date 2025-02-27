# Copilot

This repository **(will)** contains a copilot that uses various AI models, although it primarily functions as a chat interface. It is currently a work in progress rather than a complete solution. At this stage, I do not have a finalized concept for the project. I frequently add or remove features as I explore new opportunities in the rapidly evolving AI field. I am sharing these draft scripts in the hope of inspiring others.

## Overview

Copilot is designed as an experimental platform that integrates multiple AI models such as GPT variants and DALL·E. The current focus is on creating a chat interface similar to ChatGPT. In the future, its functionality may expand beyond simple chat, evolving into a comprehensive AI-powered assistant.

## To Do

- [ ] Create a plan to move settings to the UI.
- [ ] ???
- [ ] Review the frontend code to remove sensitive information.
- [ ] Publish the frontend code.
- [ ] Review the backend code to remove sensitive information.
- [ ] Publish the backend code.

## Features

- **Chat Interface:** A web-based chat interface built with React.
- **Multiple AI Models:** Integration with various AI models like GPT-4, GPT-3, DALL·E, and Whisper.
- **File Upload:** Support for file and audio uploads.
- **Real-Time Communication:** Uses JSON-RPC over WebSocket for asynchronous communication between the client and server.
- **Asynchronous Python:** Fully asynchronous server-side code built with Python and aiohttp.

## Project Structure

- `app/`  
  Python code.
- `gui/`  
  Frontend source.
- `main.py`  
  Entry point.

## Installation

If you are ready to get started, follow these instructions:

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

   Navigate to the frontend directory `gui` and run:

   ```bash
   npm install
   ```

   Then, build the project:

   ```bash
   npm build
   ```

## Configuration

Edit environment variables or the configuration file `config.py` to set the following parameters:

- **DEV_MODE:** Set to `True` during development.
- **GOOGLE_APP_ID:** Provide the Google App ID if using the Chrome app mode.
- **UPLOADS_DIR:** The directory where uploaded files will be stored.
- **HOST_NAME and PORT:** Configure the host name and port for the web server.

## Running the Application

1. **Start the backend server:**

   ```bash
   python3 main.py
   ```

2. **Start the frontend (if built separately):**

   If you have a separate frontend development server (e.g., using `npm start`), run it accordingly.

3. **Access the App:**

   Open your browser and navigate to `http://localhost:8123/` (or use a different address if configured in `config.py`).

## Future Directions

- Expand beyond the current chat functionality to include additional modern AI capabilities.
- Explore advanced customization options and further integrations with other AI services.
