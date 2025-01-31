import logging

# Define logging configuration
LOG_CONFIG = {
    'streamjam': logging.INFO,          # Default level
    'streamjam.pubsub': logging.DEBUG,  # PubSub specific level
    'streamjam.server': logging.INFO,   # Server specific level
    'streamjam.service': logging.WARNING,  # Service specific level
    'streamjam.component': logging.INFO,  # Component specific level
}

# Create console handler with formatting
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Handler should allow all levels to pass through
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Configure all loggers based on config
for logger_name, level in LOG_CONFIG.items():
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.addHandler(console_handler)
