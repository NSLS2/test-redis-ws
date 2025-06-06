import os
from writer_load_test import WriterUser
from websocket_load_test import StreamingUser

# Set weights from environment variables (default to equal distribution)
WriterUser.weight = int(os.getenv('WRITER_WEIGHT', 1))
StreamingUser.weight = int(os.getenv('STREAMING_WEIGHT', 1))