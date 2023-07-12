import yaml
import logging
from flask import Flask
from flask_mqtt import Mqtt

app = Flask(__name__)
app.config.from_file("config.yml", load=yaml.full_load)
cfg = app.config
logging.basicConfig(
    filename=cfg["LOGGING_FILE"],
    filemode="a",
    format=cfg["LOGGING_FORMAT"],
    level=cfg["LOGGING_LEVEL"],
)
gsm_logger = logging.getLogger("gsm")
logging.getLogger("flask_mqtt").name = "mqtt"  # change the logger name
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.info("app started")
mqttc = Mqtt(app, mqtt_logging=cfg["MQTT_LOGGING"])
