import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes
import paho.mqtt.publish as publish

import json
import uuid
import time
import logging

from model import  DeviceData, MeasurementData, Base

from sqlalchemy import func, select, delete, create_engine, and_, exc
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from collections.abc import AsyncGenerator

import requests, hashlib, re
from datetime import datetime
import pytz

from defines import MQTT_SERVER, MQTT_PORT, MQTT_CLIENT_ID, TIMEZONE, WAIT_TIME, MODE, FRITZBOX_URL, USERNAME, PASSWORD, DATABASE, SLEEP_TIME

def dprint(*args, **kwargs):
    if MODE == "DEBUG":
        for arg in args:
            print(arg, end=' ')
        for key, value in kwargs.items():
            print(f"{value}", end=' ')
        print()

def data2db_time(session_factory, time_stamp, device, device_id, device_type, entity, sub_entity, amount, unit, cumulative, mqtt_send=True):
    '''data2db_time handle time based measurements - safe data in databse if not equal to last measurement and send mqtt message'''
    session = session_factory()

    topic = "tele/"+device_type+device_id+"/SENSOR"    

    last_data = session.scalars(select(MeasurementData)
                                .where(and_(MeasurementData.topic == topic, MeasurementData.sub_entity == sub_entity, MeasurementData.time == time_stamp))
                                .order_by(MeasurementData.time.desc())
                                .limit(1)).all()
    
    if last_data and len(last_data) == 1:
        return

    data = MeasurementData(
        id = str(uuid.uuid4()),
        device = device,
        topic = topic,
        entity = device_type+" "+entity if (device_type != "") else entity,
        sub_entity = sub_entity,
        time = time_stamp,
        amount = amount
    )

    if mqtt_send:
        publish.single(
            topic=data.topic, 
            payload=json.dumps({
                "time": data.time, 
                device_type:{
                    "device": data.device,
                    "entity": data.entity,
                    "sub_entity": data.sub_entity,  
                    "amount": data.amount, 
                    "unit": unit
                    }
                }), 
            client_id=MQTT_CLIENT_ID, hostname=MQTT_SERVER, port=MQTT_PORT, keepalive=60, qos=0, retain=False 
        )

    session.add(data)
    session.commit()
    session.close()     


def data2db(session_factory, device, device_id, device_type, entity, sub_entity, amount, unit, cumulative, mqtt_send=True):
    '''data2db handle measurements - save data in databse if not equal to last measurement and send mqtt message'''
    session = session_factory()
    zeitzone = pytz.timezone(TIMEZONE)
    utc_time = datetime.now(zeitzone)

    data = MeasurementData(
        id = str(uuid.uuid4()),
        device = device,
        topic = "tele/"+device_type+device_id+"/SENSOR",
        entity = device_type+" "+entity if (device_type != "") else entity,
        sub_entity = sub_entity,
        time = utc_time.strftime("%Y-%m-%dT%H:%M:%S"),
        amount = amount,
    )

    last_data = session.scalars(select(MeasurementData)
                                .where(and_(MeasurementData.topic == data.topic,MeasurementData.sub_entity == data.sub_entity))
                                .order_by(MeasurementData.time.desc())
                                .limit(2)).all()
    
    if last_data and len(last_data) == 2:
        if  (last_data[0].amount == last_data[1].amount and 
            last_data[1].amount == data.amount):
            
            session.delete(last_data[0])

    if mqtt_send:
        publish.single(
            topic=data.topic, 
            payload=json.dumps({
                "time": data.time, 
                device_type:{
                    "device": data.device,
                    "entity": data.entity,
                    "sub_entity": data.sub_entity,  
                    "amount": data.amount, 
                    "unit": unit
                    }
                }), 
            client_id=MQTT_CLIENT_ID, hostname=MQTT_SERVER, port=MQTT_PORT, keepalive=60, qos=0, retain=False 
        )

    session.add(data)
    session.commit()
    session.close()   

def connect_fritzbox(userdata):
    '''connect_fritzbox connect to fritzbox - login and get divice data
    [FritzBox forum](https://www.ip-phone-forum.de/threads/aha-http-interface.318229/)    
    '''
    request_payload = {'version': '2'}
    request_result = requests.get(FRITZBOX_URL + "/login_sid.lua", params=request_payload)

    # Daten herausfiltern
    SID = str((request_result.text).split("<SID>")[1].split("</SID>")[0])
    BlockTime = int((request_result.text).split("<BlockTime>")[1].split("</BlockTime>")[0])
    Challenge = str((request_result.text).split("<Challenge>")[1].split("</Challenge>")[0])    

    if SID == '0000000000000000':

        # SID ist 0, daher Response Erzeugen und neu anfordern: Berechnung mit PBKDF2
        Challenge_split = Challenge.split("$")
        #notused = int(Challenge_split[0])
        iter1 = int(Challenge_split[1])
        salt1 = bytes.fromhex(Challenge_split[2])
        iter2 = int(Challenge_split[3])
        salt2 = bytes.fromhex(Challenge_split[4])
        hash1 = hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), salt1, iter1)
        hash2 = hashlib.pbkdf2_hmac("sha256", hash1, salt2, iter2)
        Response = Challenge_split[4] + "$" + hash2.hex()
                
        # Daten erstellen für POST
        request_data = {"username": USERNAME, "response": Response}
                
        # Header erstellen
        request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
                
        # Und Daten anfordern
        request_result = requests.post(FRITZBOX_URL + "/login_sid.lua", data=request_data, headers=request_headers)

        # Zum Debuggen, alles Ausgeben
        dprint (request_result.text)

        SID = str((request_result.text).split("<SID>")[1].split("</SID>")[0])
        BlockTime = int((request_result.text).split("<BlockTime>")[1].split("</BlockTime>")[0])
        Name = str((request_result.text).split("<Name>")[1].split("</Name>")[0])
        Access = int((request_result.text).split("<Access>")[1].split("</Access>")[0])
                
        # Ausgabe der einzelnen Variablen
        dprint ("Challenge:            ",Challenge)
        dprint ("Response:             ",Response)
        dprint ("SID:                  ",SID)
        dprint ("BlockTime:            ",BlockTime)
        dprint ("Name:                 ",Name)
        dprint ("Access:               ",Access)
                
    else:
        # Ausgabe der einzelnen Variablen
        dprint ("SID:                  ",SID)
        dprint ("BlockTime:            ",BlockTime)

    dprint ("------------------------------------------------------------------------")

    request_payload = {'switchcmd': 'getdevicelistinfos', 'sid': SID}
    request_result = requests.get(FRITZBOX_URL + "/webservices/homeautoswitch.lua", params=request_payload)
    request_result_split_array = re.findall("<device (.*?)</device>", request_result.text)

    # Zum Debuggen, alles Ausgeben
    #dprint (request_result.text)

    for i, request_result_split in enumerate(request_result_split_array):
       
        device_ain = str((request_result_split).split('identifier="')[1].split('" id=')[0])
        device_id = int((request_result_split).split('id="')[1].split('" functionbitmask=')[0])
        device_function_bitmask = int((request_result_split).split('functionbitmask="')[1].split('" fwversion=')[0])
        device_firmware = str((request_result_split).split('" fwversion="')[1].split('" manufacturer=')[0])
        device_manufacturer = str((request_result_split).split('manufacturer="')[1].split('" productname=')[0])
        device_product_name = str((request_result_split).split('productname="')[1].split('"><present>')[0])
        device_device_name = str((request_result_split).split("<name>")[1].split("</name>")[0])
        device_present = str((request_result_split).split("<present>")[1].split("</present>")[0])
        device_busy = str((request_result_split).split("<txbusy>")[1].split("</txbusy>")[0])
        
        # Ausgabe der einzelnen Variablen
        dprint ("AIN:                  ",device_ain)
        dprint ("ID:                   ",device_id)
        dprint ("Function bitmask:     ",device_function_bitmask)
        dprint ("Firmware version:     ",device_firmware)
        dprint ("Manufacturer:         ",device_manufacturer)
        dprint ("Product name:         ",device_product_name)
        dprint ("Device name:          ",device_device_name)
        dprint ("Present:              ",device_present)
        dprint ("TX busy:              ",device_busy)    

        dprint ("------------------------------------------------------------------------")

        # nur Heizkoerperregler, Schaltaktor, Taster. Andere Geraete ergaenzen...
        if "<hkr>" in request_result_split:
            device_battery = int((request_result_split).split("<battery>")[1].split("</battery>")[0])
            device_batterylow = str((request_result_split).split("<batterylow>")[1].split("</batterylow>")[0])
            device_temperature_celsius = float((request_result_split).split("<celsius>")[1].split("</celsius>")[0])/10
            device_temperature_offset = float((request_result_split).split("<offset>")[1].split("</offset>")[0])/10
            #Temperatur-Wert in 0,5 °C, Wertebereich: 16 – 56 -> 8 bis 28°C, z.B.: 16 <= 8°C, 17 = 8,5°C...... 56 >= 28°C, 254 = ON , 253 = OFF
            device_hkr_set = float((request_result_split).split("<tsoll>")[1].split("</tsoll>")[0])/2
            device_hkr_is = float((request_result_split).split("<tist>")[1].split("</tist>")[0])/2
            device_hkr_absenk = float((request_result_split).split("<absenk>")[1].split("</absenk>")[0])/2
            device_hkr_komfort = float((request_result_split).split("<komfort>")[1].split("</komfort>")[0])/2
            device_hkr_lock = int((request_result_split).split("<lock>")[1].split("</lock>")[0])
            device_hkr_devicelock = int((request_result_split).split("<devicelock>")[1].split("</devicelock>")[0])
            device_hkr_errorcode = int((request_result_split).split("<errorcode>")[1].split("</errorcode>")[0])
            device_hkr_windowopenactiv = int((request_result_split).split("<windowopenactiv>")[1].split("</windowopenactiv>")[0])
            device_hkr_windowopenactiveendtime = int((request_result_split).split("<windowopenactiveendtime>")[1].split("</windowopenactiveendtime>")[0])
            device_hkr_boostactive = int((request_result_split).split("<boostactive>")[1].split("</boostactive>")[0])
            device_hkr_boostactiveendtime = int((request_result_split).split("<boostactiveendtime>")[1].split("</boostactiveendtime>")[0])
            device_hkr_endperiod = int((request_result_split).split("<endperiod>")[1].split("</endperiod>")[0])
            device_hkr_tchange = int((request_result_split).split("<tchange>")[1].split("</tchange>")[0])
            device_hkr_summeractive = int((request_result_split).split("<summeractive>")[1].split("</summeractive>")[0])
            device_hkr_adaptiveHeatingActive = int((request_result_split).split("<adaptiveHeatingActive>")[1].split("</adaptiveHeatingActive>")[0])
            device_hkr_adaptiveHeatingRunning = int((request_result_split).split("<adaptiveHeatingRunning>")[1].split("</adaptiveHeatingRunning>")[0])
                    
            dprint ("Type:                  HKR")
            dprint ("Battery:              ",device_battery,"%")
            dprint ("Battery low?:         ",device_batterylow)
            dprint ("Temperature:          ",device_temperature_celsius,"°C")
            dprint ("Temperature offset:   ",device_temperature_offset,"°C")
            dprint ("Temperature set:      ",device_hkr_set,"°C")
            dprint ("Temperature is:       ",device_hkr_is,"°C")
            dprint ("Temperature lowering: ",device_hkr_absenk,"°C")
            dprint ("Temperature comfort:  ",device_hkr_komfort,"°C")
            dprint ("HKR lock:             ",device_hkr_lock)
            dprint ("HKR devicelock:       ",device_hkr_devicelock)
            dprint ("HKR error:            ",device_hkr_errorcode)
            dprint ("HKR Window open:      ",device_hkr_windowopenactiv)
            dprint ("HKR Window open timer:",device_hkr_windowopenactiveendtime)
            dprint ("HKR Boost active:     ",device_hkr_boostactive)
            dprint ("HKR Boost time:       ",device_hkr_boostactiveendtime)
            dprint ("HKR endperiod:        ",device_hkr_endperiod)
            dprint ("HKR temp change:      ",device_hkr_tchange)
            dprint ("HKR summer active:    ",device_hkr_summeractive)
            dprint ("HKR adapt heating on: ",device_hkr_adaptiveHeatingActive)
            dprint ("HKR adapt heating run:",device_hkr_adaptiveHeatingRunning)

            session = userdata['session']()
            session.merge(DeviceData(
                device = device_ain,
                sub_entity = "Temperature", 
                device_name = device_device_name, 
                product_name = device_product_name, 
                manufacturer = device_manufacturer, 
                firmware_version = device_firmware,
                unit = "°C",
                cumulative = False
            ))
            session.merge(DeviceData(
                device = device_ain,
                sub_entity = "Battery", 
                device_name = device_device_name, 
                product_name = device_product_name, 
                manufacturer = device_manufacturer, 
                firmware_version = device_firmware,
                unit = "%",
                cumulative = False
            ))            
            session.commit()
            session.close()

            data2db(userdata["session"], device_ain ,str(device_id), "HKR", device_device_name, "Temperature", device_temperature_celsius, "°C", True)
            data2db(userdata["session"], device_ain ,str(device_id), "HKR", device_device_name, "Battery", device_battery, "%", True)

        elif "<button " in request_result_split:
            device_battery = int((request_result_split).split("<battery>")[1].split("</battery>")[0])
            device_batterylow = str((request_result_split).split("<batterylow>")[1].split("</batterylow>")[0])
              
            dprint ("Type:                  Button")
            dprint ("Battery:              ",device_battery,"%")
            dprint ("Battery low?:         ",device_batterylow)


            session = userdata['session']()
            session.merge(DeviceData(
                device = device_ain,
                sub_entity = "Battery", 
                device_name = device_device_name, 
                product_name = device_product_name, 
                manufacturer = device_manufacturer, 
                firmware_version = device_firmware,
                unit = "%",
                cumulative = False
            ))            
            session.commit()
            session.close()

            data2db(userdata["session"], device_ain ,str(device_id), "Button", device_device_name, "Battery", device_battery, "%", True)            

        elif "<switch>" in request_result_split:
            device_switch_state = int((request_result_split).split("<state>")[1].split("</state>")[0])
            device_switch_mode = str((request_result_split).split("<mode>")[1].split("</mode>")[0])
            device_switch_lock = int((request_result_split).split("<lock>")[1].split("</lock>")[0])
            device_switch_devicelock = int((request_result_split).split("<devicelock>")[1].split("</devicelock>")[0])
            device_simpleonoff_state = int((request_result_split).split("<devicelock>")[1].split("</devicelock>")[0])
            device_powermeter_voltage = float((request_result_split).split("<voltage>")[1].split("</voltage>")[0])/1000
            device_powermeter_power = float((request_result_split).split("<power>")[1].split("</power>")[0])/1000
            device_powermeter_energy = float((request_result_split).split("<energy>")[1].split("</energy>")[0])/1000
            device_temperature_celsius = float((request_result_split).split("<celsius>")[1].split("</celsius>")[0])/10
            device_temperature_offset = float((request_result_split).split("<offset>")[1].split("</offset>")[0])/10
            
            dprint ("Type:                  Switch")
            dprint ("Switch state:         ",device_switch_state)
            dprint ("Switch mode:          ",device_switch_mode)
            dprint ("Switch lock:          ",device_switch_lock)
            dprint ("Switch devicelock:    ",device_switch_devicelock)
            dprint ("Simple on/off state:  ",device_simpleonoff_state)
            dprint ("Powermeter voltage:   ",device_powermeter_voltage,"V")
            dprint ("Powermeter power:     ",device_powermeter_power,"W")
            dprint ("Powermeter energy:    ",device_powermeter_energy,"kWh")
            dprint ("Temperature:          ",device_temperature_celsius,"°C")
            dprint ("Temperature offset    ",device_temperature_offset,"°C")

            session = userdata['session']()
            session.merge(DeviceData(
                device = device_ain,
                sub_entity = "Temperature", 
                device_name = device_device_name, 
                product_name = device_product_name, 
                manufacturer = device_manufacturer, 
                firmware_version = device_firmware,
                unit = "°C",
                cumulative = False
            ))
            session.merge(DeviceData(
                device = device_ain,
                sub_entity = "Energy", 
                device_name = device_device_name, 
                product_name = device_product_name, 
                manufacturer = device_manufacturer, 
                firmware_version = device_firmware,
                unit = "kWh",
                cumulative = True
            ))   
            session.merge(DeviceData(
                device = device_ain,
                sub_entity = "Voltage", 
                device_name = device_device_name, 
                product_name = device_product_name, 
                manufacturer = device_manufacturer, 
                firmware_version = device_firmware,
                unit = "V",
                cumulative = False
            ))   
            session.merge(DeviceData(
                device = device_ain,
                sub_entity = "Power", 
                device_name = device_device_name, 
                product_name = device_product_name, 
                manufacturer = device_manufacturer, 
                firmware_version = device_firmware,
                unit = "W",
                cumulative = False
            ))                                    
            session.commit()
            session.close()

            data2db(userdata["session"], device_ain ,str(device_id), "Switch", device_device_name, "Temperature", device_temperature_celsius, "°C", True)
            data2db(userdata["session"], device_ain ,str(device_id), "Switch", device_device_name, "Energy", device_powermeter_energy, "kWh", True)
            data2db(userdata["session"], device_ain ,str(device_id), "Switch", device_device_name, "Voltage", device_powermeter_voltage, "V", True)
            data2db(userdata["session"], device_ain ,str(device_id), "Switch", device_device_name, "Power", device_powermeter_power, "W", True)
       
        elif "FRITZ!Smart Control 350" in request_result_split and "<state>" in request_result_split:
            
            device_control_state = int((request_result_split).split("<state>")[1].split("</state>")[0])
            device_control_lastalertchgtimestamp = int((request_result_split).split("<lastalertchgtimestamp>")[1].split("</lastalertchgtimestamp>")[0])
            date_time = datetime.fromtimestamp(device_control_lastalertchgtimestamp)
          
            dprint ("Type:                  Control")
            dprint ("Control state:        ",device_control_state)
            dprint ("Control last change:  ",date_time.strftime("%Y-%m-%d %H:%M:%S"))

            session = userdata['session']()
            session.merge(DeviceData(
                device = device_ain,
                sub_entity = "State", 
                device_name = device_device_name, 
                product_name = device_product_name, 
                manufacturer = device_manufacturer, 
                firmware_version = device_firmware,
                unit = "",
                cumulative = False
            ))
            session.commit()
            session.close()

            data2db_time(userdata["session"], date_time.strftime("%Y-%m-%dT%H:%M:%S"), device_ain ,str(device_id), "Control", device_device_name, "State", device_control_state, "", True)

        elif "FRITZ!Smart Control 350" in request_result_split and "<battery>" in request_result_split:
            
            device_battery = int((request_result_split).split("<battery>")[1].split("</battery>")[0])
            device_batterylow = str((request_result_split).split("<batterylow>")[1].split("</batterylow>")[0])

            dprint ("Type:                  Control")
            dprint ("Battery:              ",device_battery,"%")
            dprint ("Battery low?:         ",device_batterylow)

            session = userdata['session']()
            session.merge(DeviceData(
                device = device_ain,
                sub_entity = "Battery", 
                device_name = device_device_name, 
                product_name = device_product_name, 
                manufacturer = device_manufacturer, 
                firmware_version = device_firmware,
                unit = "%",
                cumulative = False
            ))            
            session.commit()
            session.close()

            data2db(userdata["session"], device_ain ,str(device_id), "Control", device_device_name, "Battery", device_battery, "%", True)

        else:
            dprint ("Type:                  Unknown")
            dprint ("Result:                ",request_result_split)

        dprint ("------------------------------------------------------------------------")

async def get_db_session_async() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(DATABASE,
                         pool_size=20,
                         max_overflow=30)
    factory = async_sessionmaker(engine)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except exc.SQLAlchemyError as error:
            await session.rollback()
            raise

def get_db_session_sync():
    '''get_db_session    start and get database Session'''
    return sessionmaker(bind=get_db_sync())

def get_db_sync():
    '''get_db_sync    start and get database connection'''
    return create_engine(DATABASE,
                         pool_size=20,
                         max_overflow=30)


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties):
    userdata["logger"].info(f"Connected with result code {reason_code}")
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    #client.subscribe("tele/tasmota_9282F4/SENSOR")
    client.subscribe("tele/+/SENSOR")


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):

    # JSON decodieren
    data = json.loads(msg.payload)
    if "SENSOR" in msg.topic and "MT681" in data:

        device_id = msg.topic.replace("tele/","").replace("/SENSOR","")
        data2db(userdata["session"], 
                data["MT681"]["Meter_id"] or "" , #device
                device_id,                        #device_id
                "",                               #device_type
                "MT681",                          #entity
                "E_in",                           #sub_entity
                data["MT681"]["E_in"],            #amount
                "kWh", True, False)               #unit, cumulative, mqtt_send


        data2db(userdata["session"], 
            data["MT681"]["Meter_id"] or "" , #device
            device_id,                        #device_id
            "",                               #device_type
            "MT681",                          #entity
            "Power",                          #sub_entity
            data["MT681"]["Power"],           #amount
            "W", False, False)                #unit, cumulative, mqtt_send
        
        session = userdata["session"]()   
        session.merge(DeviceData(
            device = data["MT681"]["Meter_id"] or "",
            sub_entity = "E_in",
            device_name = "MT681",
            product_name = device_id,
            manufacturer = "ISKAEMECO",
            firmware_version = "2020",
            unit = "kWh",
            cumulative = True
        ))
        session.merge(DeviceData(
            device = data["MT681"]["Meter_id"] or "",
            sub_entity = "Power",
            device_name = "MT681",
            product_name = device_id,
            manufacturer = "ISKAEMECO",
            firmware_version = "2020",
            unit = "W",
            cumulative = False
        ))        
        session.commit()
        session.close()

    #print(msg.topic+" "+str(msg.payload))
    userdata["logger"].info(msg.topic+" "+str(msg.payload))   


def periodic_task():
    '''
    start mqtt client and save data to database one time
    '''

    logger = logging.getLogger("py_tas")
    engine = get_db_sync()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

   
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,protocol=mqtt.MQTTv5, client_id=MQTT_CLIENT_ID)
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = 3600  # Sets the session runtime to 1 hour

    userdata = {
        'engine': engine,
        'session': Session,
        'logger': logger
    }

    mqttc._userdata = userdata
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message

    try:
          
        mqttc.connect(MQTT_SERVER, MQTT_PORT, 60, clean_start=False, properties=properties)
        mqttc.loop_start()
        time.sleep(WAIT_TIME)  # if mqtt does not buffer, all measurement messages are read from these 10 sec 
        mqttc.disconnect()
        mqttc.loop_stop()
        if (USERNAME != "" and PASSWORD != ""):
            logger.info("Check Fritzbox ...")
            connect_fritzbox(userdata)



    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        mqttc.disconnect()
        mqttc.loop_stop()



def endless_task():
    '''
    start mqtt client and save data to database forever
    '''
    logger = logging.getLogger("py_tas")
    engine = get_db_sync()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

   
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,protocol=mqtt.MQTTv5, client_id=MQTT_CLIENT_ID)
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = 3600  # Setzt die Session-Ablaufzeit auf 1 Stunde

    userdata = {
        'engine': engine,
        'session': Session,
        'logger': logger
    }

    mqttc._userdata = userdata
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message

    try:
        while True:
            
            mqttc.connect(MQTT_SERVER, MQTT_PORT, 60, clean_start=False, properties=properties)
            mqttc.loop_start()
            time.sleep(WAIT_TIME)  # wenn mqtt nicht puffert, werden alle messsagen aus diesen 10 sec gelesen 
            mqttc.disconnect()
            mqttc.loop_stop()
            if (USERNAME != "" and PASSWORD != ""):
                logger.info("Check Fritzbox ...")
                connect_fritzbox(userdata)
            logger.info("Sleeping for "+str(SLEEP_TIME)+" seconds...")
            time.sleep(SLEEP_TIME)


    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        mqttc.disconnect()
        mqttc.loop_stop()


if __name__ == "__main__":
    endless_task()