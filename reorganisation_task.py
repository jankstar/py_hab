from periodic_task import get_db_sync
from model import DeviceData, MeasurementData, StatisticsData, Base
from sqlalchemy import select, delete, and_
from sqlalchemy.orm import sessionmaker

from defines import TIMEZONE

import logging
import numpy as np
from datetime import datetime
import pytz

def unit_convert(unit):
    if unit == "kWh":
        return "Wh"
    return unit

def reorganisation_task():
    ''' delete redundant measurements for existing database and calculate statistics'''
    zeitzone = pytz.timezone(TIMEZONE)
    utc_time = datetime.now(zeitzone)

    logger = logging.getLogger("py_tas")
    engine = get_db_sync()
    Base.metadata.create_all(engine)    
    Session = sessionmaker(bind=engine)
    session = Session()

#-------------------------------------------------------- 
# delete redundant measurements
    try:
        devices = session.execute(select(DeviceData.device, DeviceData.sub_entity).order_by(DeviceData.device, DeviceData.sub_entity))    
                                
        for device in devices:
            logger.info("reorg: %s %s", device.device, device.sub_entity)
            result = session.scalars(select(MeasurementData)
                                    .where(and_(MeasurementData.device == device.device, MeasurementData.sub_entity == device.sub_entity))
                                    .order_by(MeasurementData.time.desc())).all()

            index = 0
            for row in result:
                if index > 0 and index < (len(result) - 1):
                    if row.amount == result[index-1].amount and row.amount == result[index+1].amount:
                        row.topic = "deleted"
                index += 1

            session.execute(delete(MeasurementData).where(MeasurementData.topic == "deleted"))
    except (KeyboardInterrupt, SystemExit) as e:
        logger.error("Error: %s", e)
    
    session.commit()

#-------------------------------------------------------- 
# calculate statistics hour
    try:
        devices = session.execute(select(DeviceData.device, DeviceData.sub_entity, DeviceData.unit, DeviceData.cumulative).order_by(DeviceData.device, DeviceData.sub_entity))    
    
        for device in devices:
            logger.info("statistics: %s %s",device.device, device.sub_entity)


            steps_hour = [["00", "%T00:%"], ["01", "%T01:%"], ["02", "%T02:%"], ["03", "%T03:%"], ["04", "%T04:%"], ##
                    ["05", "%T05:%"], ["06", "%T06:%"], ["07", "%T07:%"], ["08", "%T08:%"], ["09", "%T09:%"], 
                    ["10", "%T10:%"], ["11", "%T11:%"], ["12", "%T12:%"], ["13", "%T13:%"], ["14", "%T14:%"], ##
                    ["15", "%T15:%"], ["16", "%T16:%"], ["17", "%T17:%"], ["18", "%T18:%"], ["19", "%T19:%"], 
                    ["20", "%T20:%"], ["21", "%T21:%"], ["22", "%T22:%"], ["23", "%T23:%"]]   
            
            steps_month = [["01", "%-01-%T%"], ["02", "%-02-%T%"], ["03", "%-03-%T%"], ["04", "%-04-%T%"], ["05", "%-05-%T%"], 
                        ["06", "%-06-%T%"], ["07", "%-07-%T%"], ["08", "%-08-%T%"], ["09", "%-09-%T%"], ["10", "%-10-%T%"], ["11", "%-11-%T%"], ["12", "%-12-%T%"]]  ##


            steps_day = [{ "name": "Mon", "data": []}, { "name": "Tue", "data": []}, { "name": "Wed", "data": []}, 
                        { "name": "Thu", "data": []}, { "name": "Fri", "data": []}, { "name": "Sat", "data": []}, { "name": "Sun", "data": []}]

            #--------------------------------------------------------
            #hour
            for step in steps_hour:
                result = []
                result = session.scalars(select(MeasurementData)
                                    .where(and_(MeasurementData.device == device.device, MeasurementData.sub_entity == device.sub_entity, MeasurementData.time.like(step[1])))
                                    .order_by(MeasurementData.time.asc())
                                     ).all()
                
                if len(result) <= 1:
                    continue

                result = [[row.amount, row.time] for row in result]

                if device.cumulative == True:
                    # if cumulative data, substract the previous value
                    index = 0
                    while index < (len(result) - 1):
                        result[index][0] = result[index+1][0] - result[index][0]
                        date_object_1 = datetime.strptime(result[index][1], "%Y-%m-%dT%H:%M:%S")
                        date_object_2 = datetime.strptime(result[index+1][1], "%Y-%m-%dT%H:%M:%S")
                        date_diff = date_object_2 - date_object_1
                        date_hour = date_diff.total_seconds() / 3600
                        result[index][0] = result[index][0] * 1000 / date_hour
                        index += 1  

                    result = result[:len(result)-1] #delete last value   

                result = [row[0] for row in result]

                session.merge(StatisticsData(
                    device=device.device, 
                    sub_entity=device.sub_entity, 
                    name="Hour", 
                    sub_key=step[0], 
                    unit=unit_convert(device.unit), 
                    sum_amount=np.sum(result),
                    count=len(result),
                    avg_amount=np.mean(result) if len(result) > 0 else 0,
                    median_amount=np.median(result) if len(result) > 0 else 0,
                    stddev_amount=np.std(result) if len(result) > 0 else 0,
                    min_amount=np.min(result) if len(result) > 0 else 0,
                    max_amount=np.max(result) if len(result) > 0 else 0, 
                    time=utc_time.strftime("%Y-%m-%dT%H:%M:%S")
                    )
                )
        
            session.commit()

            #--------------------------------------------------------
            #month
            for step in steps_month:
                result = []
                result = session.scalars(select(MeasurementData)
                                    .where(and_(MeasurementData.device == device.device, MeasurementData.sub_entity == device.sub_entity, MeasurementData.time.like(step[1])))
                                    .order_by(MeasurementData.time.asc())
                                     ).all()
                
                if len(result) <= 1:
                    continue

                result = [[row.amount, row.time] for row in result]

                if device.cumulative == True:
                    # if cumulative data, substract the previous value
                    index = 0
                    while index < (len(result) - 1):
                        result[index][0] = result[index+1][0] - result[index][0]
                        date_object_1 = datetime.strptime(result[index][1], "%Y-%m-%dT%H:%M:%S")
                        date_object_2 = datetime.strptime(result[index+1][1], "%Y-%m-%dT%H:%M:%S")
                        date_diff = date_object_2 - date_object_1
                        date_hour = date_diff.total_seconds() / 3600
                        result[index][0] = result[index][0] * 1000 / date_hour
                        index += 1  

                    result = result[:len(result)-1] #delete last value   

                result = [row[0] for row in result]

                session.merge(StatisticsData(
                    device=device.device, 
                    sub_entity=device.sub_entity, 
                    name="Month", 
                    sub_key=step[0], 
                    unit=unit_convert(device.unit), 
                    sum_amount=np.sum(result),
                    count=len(result),
                    avg_amount=np.mean(result) if len(result) > 0 else 0,
                    median_amount=np.median(result) if len(result) > 0 else 0,
                    stddev_amount=np.std(result) if len(result) > 0 else 0,
                    min_amount=np.min(result) if len(result) > 0 else 0,
                    max_amount=np.max(result) if len(result) > 0 else 0, 
                    time=utc_time.strftime("%Y-%m-%dT%H:%M:%S")
                    )
                )
        
            session.commit()

            #--------------------------------------------------------
            #day
            result = []
            result = session.scalars(select(MeasurementData)
                                     .where(and_(MeasurementData.device == device.device, MeasurementData.sub_entity == device.sub_entity))
                                     .order_by(MeasurementData.time.asc())
                                     ).all()
            
            if len(result) <= 1:
                continue

            result = [[row.amount, row.time] for row in result]

            if device.cumulative == True:
                # if cumulative data, substract the previous value and calculate per hour
                index = 0
                while index < (len(result) - 1):
                    result[index][0] = result[index+1][0] - result[index][0]
                    date_object_1 = datetime.strptime(result[index][1], "%Y-%m-%dT%H:%M:%S")
                    date_object_2 = datetime.strptime(result[index+1][1], "%Y-%m-%dT%H:%M:%S")
                    date_diff = date_object_2 - date_object_1
                    date_hour = date_diff.total_seconds() / 3600
                    result[index][0] = result[index][0] * 1000 / date_hour
                    index += 1  

                result = result[:len(result)-1] #delete last value            


            for row in result:
                date_object = datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S")
                day = date_object.weekday()
                steps_day[day]["data"].append(row[0])

            for step in steps_day:
                session.merge(StatisticsData(
                    device=device.device, 
                    sub_entity=device.sub_entity, 
                    name="Day", 
                    sub_key=step["name"], 
                    unit=unit_convert(device.unit), 
                    sum_amount=np.sum(step["data"]),
                    count=len(step["data"]),
                    avg_amount=np.mean(step["data"]) if len(step["data"]) > 0 else 0,
                    median_amount=np.median(step["data"]) if len(step["data"]) > 0 else 0,
                    stddev_amount=np.std(step["data"]) if len(step["data"]) > 0 else 0,
                    min_amount=np.min(step["data"]) if len(step["data"]) > 0 else 0,
                    max_amount=np.max(step["data"]) if len(step["data"]) > 0 else 0, 
                    time=utc_time.strftime("%Y-%m-%dT%H:%M:%S")
                    )
                )
            
            session.commit()    

    except (KeyboardInterrupt, SystemExit) as e:
        logger.error("Error: %s", e)

#--------------------------------------------------------
    session.close()





if __name__ == "__main__":
    reorganisation_task()

