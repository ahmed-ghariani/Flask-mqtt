import yaml, json
import logging
from flask import Flask
from flask_mqtt import Mqtt
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
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
app_logger = logging.getLogger("flask_mqtt")
app_logger.name = "mqtt"  # change the logger name
logging.getLogger("werkzeug").setLevel(cfg["WEBSERVER_LOGGING_LEVEL"])
logging.info("app started")
mqttc = Mqtt(app, mqtt_logging=cfg["MQTT_LOGGING"])




@mqttc.on_connect()
def on_connect(client, userdata, flags, rc):
    app_logger.info("Connected with result code " + str(rc))
    mqttc.subscribe("/nagios/cmdApp")
    mqttc.subscribe("/nagios/pingApp",2)
    mqttc.subscribe("/gsm/resp")


def handle_gateway_responce(r):
    state = r.split(",")[0]
    if state == "WR":
        gsm_logger.warning(r)
    elif state == "CR":
        gsm_logger.critical(r)
    else:
        gsm_logger.info(r)


def handel_notification(n):
    if not (n["State"] in ["CRITICAL", "DOWN", "WARNING"]):
        return
    num = "+21694960307"  # get_contact_number(n["Name"])
    name = n.pop("Name")
    m = {"Msg": str(n).replace("{", "").replace("}", "").replace("'", "")}
    n["Name"] = name
    n["Num"] = num
    n["Vocal"] = n["State"] in ["CRITICAL", "DOWN"]
    m["Num"] = "+216" + num
    m["Name"] = name
    m["Vocal"] = n["Vocal"]
    mqttc.publish("/gsm/cmd", json.dumps(n).encode("utf-8"))
    mqttc.publish("/gsm/cmd1", json.dumps(m).encode("utf-8"))
    mqttc.publish("/gsm/cmd2", json.dumps(m).replace('"', '\\"').encode("utf-8"))



@mqttc.on_message()
def on_message(client, userdata, msg):
    t = msg.topic
    if t == "/nagios/pingApp":
        client.publish("/nagios/pongApp", "pong")
    elif t == "/nagios/cmdApp":
        try:
            n = json.loads(msg.payload)
            handel_notification(n)
        except json.decoder.JSONDecodeError:
            app_logger.warning("bad format")
    elif t == "/gsm/resp":
        handle_gateway_responce(msg.payload.decode("utf-8"))
