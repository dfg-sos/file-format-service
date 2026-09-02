from api.app import create_app
from config import Settings

settings = Settings()
app = create_app(settings)



