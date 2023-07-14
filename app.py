import yaml, json, csv
import logging
from flask import Flask, render_template, request
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
app_logger = logging.getLogger("flask_mqtt")
app_logger.name = "mqtt"  # change the logger name
logging.getLogger("werkzeug").setLevel(cfg["WEBSERVER_LOGGING_LEVEL"])
logging.info("app started")
mqttc = Mqtt(app, mqtt_logging=cfg["MQTT_LOGGING"])
contact_list = []
fields = ["nom", "tel_num"]
with open(cfg["CONTACT_FILE"], newline="") as f:
    r = csv.DictReader(f)
    fields = r.fieldnames
    for contact in r:
        contact_list.append(contact)


def get_contact(contact_name):
    for contact in contact_list:
        if contact["nom"] == contact_name:
            break
    if contact["nom"] == "default":
        app_logger.info(
            "contact name '" + contact_name + "' not found using the default number"
        )
    return contact


def add_contcat(name, number):
    contact = get_contact(name)
    if contact["nom"] != "default":
        app_logger.error("contact exist already " + str(contact))
    else:
        with open(cfg["CONTACT_FILE"], newline="", mode="w") as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            contact_list.append({"nom": name, "tel_num": number})
            writer.writerows(contact_list)


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
    num = get_contact(n["Name"])["tel_num"]
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


@mqttc.on_connect()
def on_connect(client, userdata, flags, rc):
    app_logger.info("Connected with result code " + str(rc))
    mqttc.subscribe("/nagios/cmdApp")
    mqttc.subscribe("/nagios/pingApp", 2)
    mqttc.subscribe("/gsm/resp")


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


@app.get("/")
def get_user_list():
    return render_template("index.html", l=contact_list)

@app.post("/update")
def update_contact():
    for i in request.form:
        print(i)
    return 200
