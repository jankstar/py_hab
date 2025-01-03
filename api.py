from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session
from sqlalchemy import func, select, and_

from model import Measurement, MeasurementData, Device, DeviceData, Statistics, StatisticsData
from periodic_task import get_db_session_sync

from defines import DEFAULT_LIMIT

router = APIRouter()

import logging
logger = logging.getLogger("py_tas")

@router.get("/api/devices", response_model=list[Device])
async def get_all_devices(limit: int = DEFAULT_LIMIT, offset: int = 0,db: Session = Depends(get_db_session_sync)):
    '''get_devices get device data from database'''

    try:
        session = db()
        last_data = session.scalars(select(DeviceData)
                                    .order_by(DeviceData.device.asc())
                                    .offset(offset)
                                    .limit(limit)).all()
        session.close()
        result = [Device.model_validate(data) for data in last_data]
    except Exception as e:
        logger.error("Error while getting devices: " + str(e))
        raise HTTPException(status_code=404, detail="No Items found")
    
    return result

@router.get("/api/mesurement/{device}", response_model=list[Measurement])
async def get_measurement_by_device(device: str, limit: int = DEFAULT_LIMIT, offset: int = 0,db: Session = Depends(get_db_session_sync)):
    '''get_measurement get measurement data by device from database'''
    
    try: 
        session = db()
        last_data = session.scalars(select(MeasurementData)
                                    .where(MeasurementData.device == device)
                                    .order_by(MeasurementData.time.desc())
                                    .offset(offset)
                                    .limit(limit)).all()
        session.close()
        result = [Measurement.model_validate(data) for data in last_data]
    except Exception as e:
        logger.error("Error while getting mesurement by device: " + str(e))
        raise HTTPException(status_code=404, detail="No Items found")
    
    return  result

@router.get("/api/mesurement/{device}/{sub_entity}", response_model=list[Measurement])
async def get_measurement_by_device_sub_entity(device: str, sub_entity: str,limit: int = DEFAULT_LIMIT, offset: int = 0, db: Session = Depends(get_db_session_sync)):
    '''get_measurement get measurement data by device and sub_entity from database'''

    try:
        session = db()
        last_data = session.scalars(select(MeasurementData)
                                    .where(and_(MeasurementData.device == device, MeasurementData.sub_entity == sub_entity))
                                    .order_by(MeasurementData.time.desc())
                                    .offset(offset)
                                    .limit(limit)).all()
        session.close()
        result = [Measurement.model_validate(data) for data in last_data]
    except Exception as e:
        logger.error("Error while getting mesurement by device and sub_entity: " + str(e))
        raise HTTPException(status_code=404, detail="No Items found")

    return result

@router.get("/api/statistics/{device}/{sub_entity}/{name}", response_model=list[Statistics])
async def get_statistics_by_device_sub_entity_name(device: str, sub_entity: str,name: str, db: Session = Depends(get_db_session_sync)):
    '''get_statistics get statistics data by device, sub_entity and name from database'''

    try:
        session = db()
        last_data = session.scalars(select(StatisticsData)
                                    .where(and_(StatisticsData.device == device, StatisticsData.sub_entity == sub_entity, StatisticsData.name == name))
                                    .order_by(StatisticsData.sub_key.desc())).all()
        session.close()
        result = [Statistics.model_validate(data) for data in last_data]    
    except Exception as e:
        logger.error("Error while getting statistics by device, sub_entity and name: " + str(e))
        raise HTTPException(status_code=404, detail="No Items found")

    return result

