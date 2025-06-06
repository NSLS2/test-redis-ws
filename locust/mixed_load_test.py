from locust import HttpUser, User, between
from writer_load_test import WriterUser
from websocket_load_test import StreamingUser

# Set weights for user distribution
WriterUser.weight = 70  # 70% of users
StreamingUser.weight = 30  # 30% of users

# Alternative: fixed counts
# WriterUser.fixed_count = 20
# StreamingUser.fixed_count = 10