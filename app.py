import yaml, json, csv
import logging
import logging.handlers as handlers
from datetime import datetime
from flask import Flask, render_template, request
from flask_mqtt import Mqtt

app = Flask(__name__)
app.config.from_file("config.yml", load=yaml.full_load)
cfg = app.config
handler = handlers.TimedRotatingFileHandler(
    filename=cfg["LOGGING_FILE"], when="midnight", backupCount=7
)
logging.basicConfig(
    format=cfg["LOGGING_FORMAT"],
    level=cfg["LOGGING_LEVEL"],
    handlers=[handler],
)
gsm_logger = logging.getLogger("gsm")
app_logger = logging.getLogger("flask_mqtt")
app_logger.name = "mqtt"  # change the logger name
logging.getLogger("werkzeug").setLevel(cfg["WEBSERVER_LOGGING_LEVEL"])
logging.info("app started")
mqttc = Mqtt(app, mqtt_logging=cfg["MQTT_LOGGING"])
contact_list = []
fields = [
    "nom",
    "tel_num",
    "notif_options",
    "vocal",
    "jours",
    "temps",
    "intervale_date",
]
default = {
    "nom": "default",
    "tel_num": cfg["CONTACT_DEFAULT_NUMBER"],
    "notif_options": ["DOWN"],
    "vocal": True,
    "jours": [],
    "temps": [],
}


def save_list():
    with open(cfg["CONTACT_FILE"], newline="", mode="w") as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(contact_list)


def load():
    with open(cfg["CONTACT_FILE"], newline="") as f:
        r = csv.DictReader(f)
        for c in r:
            c["notif_options"] = (
                c["notif_options"].strip("][").replace("'", "").split(", ")
            )
            c["jours"] = c["jours"].strip("][").replace("'", "").split(", ")
            c["temps"] = c["temps"].strip("][").replace("'", "").split(", ")
            contact_list.append(c)
        if len(contact_list) == 0:
            app_logger.warning("no contact found adding the default ")
            contact_list.append(default)
        if contact_list[-1]["nom"] != "default":
            app_logger.info(
                "no default contact found at the end of the contact list adding it"
            )
            contact_list.append(default)


def get_contact(contact_name):
    if len(contact_list) == 0:
        load()
    for contact in contact_list:
        if contact["nom"] == contact_name:
            return contact
    app_logger.info(
        "contact name '" + contact_name + "' not found using the default number"
    )
    return contact


def add_contcat(contact):
    with open(cfg["CONTACT_FILE"], newline="", mode="w") as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        contact_list.insert(-1, contact)
        writer.writerows(contact_list)


def handle_gateway_responce(r):
    state = r.split(",")[0]
    if state == "WR":
        gsm_logger.warning(r)
    elif state == "CR":
        gsm_logger.critical(r)
    else:
        gsm_logger.info(r)


def check_time(days, times, intervale):
    now = datetime.now()
    if intervale != "":
        dates = [datetime.strptime(i, "%Y-%m-%d") for i in intervale.split("/")]
        if now < dates[0] or now > dates[1]:
            return False
    try:
        today = now.strftime("%A").upper()
        i = days.index(today)
        start_h, start_m, end_h, end_m = [
            int(k) for j in times[i].split("/") for k in j.split(":")
        ]
        if now.hour < start_h or now.hour > end_h:
            return False
        if now.hour == start_h and now.minute < start_m:
            return False
        if now.hour == end_h and now.minute > end_m:
            return False
        return True
    except ValueError:
        return False


def handel_notification(n):
    contact = get_contact(n["Name"])
    if not (n["State"] in contact["notif_options"]):
        return
    if not check_time(contact["jours"], contact["temps"], contact["intervale_date"]):
        return
    n.pop("Name")
    m = {"Msg": str(n).strip("{}").replace("'", "")}
    m["Num"] = "+216" + contact["tel_num"]
    m["Vocal"] = contact["vocal"]
    mqttc.publish("/gsm/cmd", json.dumps(m).encode("utf-8"))
    # mqttc.publish("/gsm/cmd2", json.dumps(m).replace('"', '\\"').encode("utf-8"))


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
    global contact_list
    contact_list = []
    load()
    return render_template("index.html", l=contact_list)


@app.post("/add")
def add():
    data = request.get_json()
    for c in contact_list:
        if c["nom"] == data["nom"]:
            return "contact name already used", 400
    add_contcat(data)
    return "contact added", 201


@app.post("/update/<contact_name>")
def update(contact_name):
    data = request.get_json()
    if data["nom"] != contact_name:
        for c in contact_list:
            if c["nom"] == data["nom"]:
                return "contact name already used", 400
    contact = get_contact(contact_name)
    for i in contact.keys():
        contact[i] = data[i]
    save_list()
    return "contact updated", 200


@app.delete("/delete/<contact_name>")
def delete(contact_name):
    for c in contact_list:
        if c["nom"] == contact_name:
            break
    contact_list.remove(c)
    save_list()
    return "contact removed", 200
