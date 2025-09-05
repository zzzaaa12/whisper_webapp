# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Common Commands

### Development
```bash
# Start the application (development)
python app.py

# Install dependencies
pip install -r requirements.txt

# Install GPU-accelerated version (Windows)
install_gpu.bat

# Install GPU-accelerated version (Linux/Mac)
bash install_gpu.sh

# Run tests
pytest
```

### Configuration Setup
```bash
# Copy example configuration
copy config.example.json config.json  # Windows
cp config.example.json config.json    # Linux/Mac

# Copy example environment file
copy env.example .env  # Windows
cp env.example .env    # Linux/Mac
```

### Client API Usage
```bash
# Send YouTube URL via Python client
python client.py "https://www.youtube.com/watch?v=example"

# Use custom server
python client.py "https://www.youtube.com/watch?v=example" --server http://192.168.1.100:5000
```

## Architecture Overview

### Core Application Structure
- **Flask Web Application**: Main server (`app.py`) with SocketIO for real-time communication
- **Task Queue System**: Asynchronous processing with priority-based queue management (`task_queue.py`)
- **Modular Service Architecture**: Services separated by domain (auth, file management, AI processing)
- **Blueprint-based Routing**: Main routes (`src/routes/main.py`) and API routes (`src/routes/api.py`)

### Key Components

#### Services Layer (`src/services/`)
- **AI Summary Service**: Manages multiple AI providers (OpenAI, Claude, Gemini, DeepSeek, Ollama) with automatic fallback
- **Queue Worker**: Background task processor for YouTube/media transcription
- **Authentication Service**: IP-based blocking, access code verification
- **File Management**: Bookmark, trash, and file validation services
- **Real-time Communication**: SocketIO integration for live updates

#### Utils Layer (`src/utils/`)
- **Path Manager**: Unified path management singleton for all file locations
- **Configuration Manager**: JSON + environment variable configuration with nested key support
- **Logger Manager**: Centralized logging with module-specific loggers
- **File Validation**: Security-focused file handling and sanitization

#### Task Processing
- **Queue-based Architecture**: Priority queue with persistent storage
- **Multi-AI Provider Support**: Automatic failover between AI services
- **Real-time Progress**: SocketIO-based live status updates
- **File Management**: Automatic organization of summaries, subtitles, and uploaded content

### Configuration System
The application uses a hierarchical configuration system:
1. **JSON Configuration** (`config.json`) - Primary configuration source
2. **Environment Variables** - Fallback and development overrides
3. **Path Resolution** - Automatic relative-to-absolute path conversion

Key configuration sections:
- `AI_PROVIDERS`: Multiple AI service configurations with fallback order
- `PATHS`: All file system paths (summaries, subtitles, uploads, etc.)
- `ACCESS_CODE_ALL_PAGE`: Global access control toggle
- `SUBTITLE_EXTRACTION`: YouTube subtitle extraction preferences

### Security Features
- **Access Code Protection**: Global or per-action authentication
- **IP-based Rate Limiting**: Automatic blocking for failed attempts
- **File Validation**: Path traversal protection and file type validation
- **Security Headers**: Comprehensive HTTP security headers
- **SSL Support**: Optional HTTPS with certificate management

### Real-time Communication
- **SocketIO Integration**: Live progress updates and task status
- **Session-based Logging**: Per-client log management with auto-cleanup
- **Task Status Broadcasting**: Real-time queue position and processing updates
- **GPU Status Monitoring**: Live hardware utilization reporting

## Development Guidelines

### File Organization
- Place new services in `src/services/`
- Place utility functions in `src/utils/`
- Use the PathManager singleton for all file path operations
- Follow the existing service pattern with dedicated classes

### Configuration Access
```python
from src.config import get_config

# Access simple values
api_key = get_config("OPENAI_API_KEY")

# Access nested values
downloads_dir = get_config("PATHS.DOWNLOADS_DIR")  # Returns Path object
model = get_config("AI_PROVIDERS.openai.model")
```

### Logging
```python
from src.utils.logger_manager import get_logger_manager

logger_manager = get_logger_manager()
logger_manager.info("Message", "module_name")
```

### Task Queue Integration
```python
from task_queue import get_task_queue

task_queue = get_task_queue()
task_id = task_queue.add_task(
    task_type='youtube',
    data={'url': url},
    priority=5
)
```

### Real-time Updates
```python
from src.services.socketio_instance import emit_log

emit_log("Processing started", "info", task_id)
```

## Important Implementation Details

### AI Provider System
The application supports multiple AI providers with automatic failback. Each provider is configured in `AI_PROVIDERS` with specific models and endpoints. The system automatically tries providers in the configured fallback order if one fails.

### Queue Worker Architecture
The background queue worker runs in a separate thread and processes tasks asynchronously. It handles YouTube video download, Whisper transcription, and AI summarization with progress reporting via SocketIO.

### File Management Strategy
All file operations use the PathManager singleton to ensure consistent path handling. Files are organized into specific directories (summaries, subtitles, uploads, trash) with automatic cleanup and validation.

### Security Model
The application implements defense-in-depth security with IP blocking, access codes, file validation, and secure headers. The security model is designed to prevent common web application vulnerabilities while maintaining usability.
