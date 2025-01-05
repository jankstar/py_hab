from dotenv import load_dotenv
import os


# load any available .env into env
load_dotenv()


# load environment variables
FRITZBOX_URL = os.getenv('FRITZBOX_URL',"http://0.0.0.0")
USERNAME = os.getenv('USERNAME', "") 
PASSWORD = os.getenv('PASSWORD', "")
DATABASE = os.getenv('DATABASE','sqlite:///datenbank.db')
MQTT_SERVER = os.getenv('MQTT_SERVER',"0.0.0.0")
MQTT_PORT = int(os.getenv('MQTT_PORT',1883)) #1883
MQTT_CLIENT_ID = os.getenv('MQTT_CLIENT_ID', "TEST") 
SLEEP_TIME = int(os.getenv('SLEEP_TIME',600)) #600
WAIT_TIME = int(os.getenv('WAIT_TIME',10)) #10
TIMEZONE = os.getenv('TIMEZONE', 'Europe/Berlin')
SESSION_SECRET = os.getenv('SESSION_SECRET', 'secret')
FRONTEND_URL = os.getenv('FRONTEND_URL',"http://localhost:8000")
RPYX_PORT = int(os.getenv('RPYX_PORT',8001))
TASMOTA_URL = os.getenv('TASMOTA_URL',"http://0.0.0.0")

DEFAULT_LIMIT = 200
MODE = 'NO_DEBUG' #'DEBUG'