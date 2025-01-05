from defines import TASMOTA_URL

import requests
import logging
import json

from periodic_task import get_db_sync, Base,  data2db
from sqlalchemy.orm import sessionmaker
from model import DeviceData

def tasmota_task():

    logger = logging.getLogger("py_tas")#
    engine = get_db_sync()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

 # Header erstellen
    request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try: 
        request_result = requests.get(TASMOTA_URL + "/cm?cmnd=Status0", headers=request_headers)
    except Exception as e:
        logger.error("Error while getting data by device: " + str(e))
        return
    logger.info(request_result.content.decode("utf-8"))

    if request_result.status_code != 200:
        logger.error("Error while getting data by device: " + str(request_result.status_code))
        return

    data = json.loads(request_result.content.decode("utf-8"))

    if data["StatusSNS"] and data["StatusSNS"]["MT681"]:
        print(data["StatusSNS"])



    device_id = data["Status"]["Topic"]

    data = data["StatusSNS"]
    data2db(Session, 
            data["MT681"]["Meter_id"] or "" , #device
            device_id,                        #device_id
            "",                               #device_type
            "MT681",                          #entity
            "E_in",                           #sub_entity
            data["MT681"]["E_in"],            #amount
            "kWh", True, False)               #unit, cumulative, mqtt_send


    data2db(Session, 
        data["MT681"]["Meter_id"] or "" , #device
        device_id,                        #device_id
        "",                               #device_type
        "MT681",                          #entity
        "Power",                          #sub_entity
        data["MT681"]["Power"],           #amount
        "W", False, False)                #unit, cumulative, mqtt_send
    
    session = Session()   
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
    pass



if __name__ == "__main__":
    tasmota_task()