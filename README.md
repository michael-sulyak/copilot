# Copilot

This repository is for a copilot that uses different AI models, but mostly it works as a chat. Currently, it is not a common solution or an example of something complete. By now, I do not have a final conception of this project and often add and remove different features, investigate something, etc., because the AI sphere is developing very fast. I am just publishing some of my draft scripts that may inspire someone.

## Overview

`Copilot` is designed as an experimental platform to integrate multiple AI models such as GPT modes and DALL·E. The current focus is on creating a chat interface similar to ChatGPT. In the future, it may expand its functionality beyond a simple chat, evolving into a more comprehensive AI-powered assistant.

## Features

- **Chat interface:** A web-based chat interface built with React.
- **Multiple AI models:** Integration with different AI models like GPT-4, GPT-4 mini, GPT-3 mini, and DALL·E.
- **File upload:** Support for file and audio uploads.
- **Real-time communication:** Uses JSON-RPC over WebSocket for asynchronous communication between the client and server.
- **Asynchronous Python:** Fully asynchronous server-side code built with Python and aiohttp.

## Project Structure

TODO: Add info

## Installation

1. **Clone the repository:**

   ```bash
   git clone git@github.com:michael-sulyak/copilot.git
   cd copilot
   ```

2. **Set up a Python virtual environment and install dependencies:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Install frontend dependencies:**

   Navigate to the frontend directory and run:

   ```bash
   npm install
   ```

   after:

   ```bash
   npm build
   ```

## Configuration

Edit envs or the configuration file `config.py` to set the following parameters:

- **DEV_MODE:** Set to `True` during development.
- **GOOGLE_APP_ID:** Provide the Google App ID if using the Chrome app mode.
- **UPLOADS_DIR:** Directory where uploaded files will be stored.
- **HOST_NAME and PORT:** Configure the host name and port for the web server.

## Running the Application

1. **Start the backend server:**

   ```bash
   python main.py
   ```

2. **Start the frontend (if built separately):**

   If you have a separate frontend development server (e.g., using `npm start`), run it accordingly.

3. **Access the app:**

   Open your browser and navigate to `http://localhost:8123/` (or as configured in your `config.py`).

## Future Directions

- Expand beyond the current chat functionality to include additional AI-powered features.
- Explore advanced customization options and further integrations with other AI services.
