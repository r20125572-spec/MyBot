import os

# Base directory where photos are stored
PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "attached_assets")

# BATMANCARDXCHK logo photo
LOGO_PHOTO = os.path.join(PHOTOS_DIR, "photo_5951875596612734741_y_(1)_1783849021979.jpg")


def get_logo_photo():
    """Returns open file object for the BATMANCARDXCHK logo photo."""
    return open(LOGO_PHOTO, "rb")
