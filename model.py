from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import declarative_base
from sqlalchemy import Index, Table, Column, String, Float, Boolean

from typing import Literal

Base = declarative_base()

class MeasurementData(Base):
    '''Measurement as sqlalchemy model'''
    __table__ = Table('measurement_data', Base.metadata,
        Column('id', String, primary_key=True), # key id, we use UUID
        Column('device', String),      # device
        Column('topic', String),       # topic of mqtt
        Column('entity', String),      # sensor
        Column('sub_entity', String),  # sensor sub device
        Column('time', String),        # timestamp of measurement
        Column('amount', Float),       # value of measurement
    )

    __table_args__ = (
            Index('idx_01', 'device', 'sub_entity', 'time'),
        )
    
    def __repr__(self):
        return f"<measurement(topic='{self.topic}', time={self.time}, device={self.device}, amount={self.amount})>"

class Measurement(BaseModel):
    '''Measurement as pydantic model'''
    id: str
    device: str
    topic: str
    entity: str
    sub_entity: str
    time: str
    amount: float

    model_config = ConfigDict(from_attributes=True)

class DeviceData(Base):
    '''Device as sqlalchemy model'''
    __table__ = Table('device_data', Base.metadata,
        Column('device', String, primary_key=True), 
        Column('sub_entity', String, primary_key=True), 
        Column('device_name', String),
        Column('product_name', String),
        Column('manufacturer', String),
        Column('firmware_version', String),
        Column('unit', String),               # unit of measurement
        Column('cumulative', Boolean),        # if measurement is cumulative
    )

    def __repr__(self):
        return f"<device(device={self.device}, device_name={self.device_name}, unit={self.unit})>"

class Device(BaseModel):
    '''Device as pydantic model'''
    device: str
    sub_entity: str
    device_name: str
    product_name: str
    manufacturer: str
    firmware_version: str
    unit: str
    cumulative: bool

    model_config = ConfigDict(from_attributes=True)


class StatisticsData(Base):
    '''Statistics as sqlalchemy model'''
    __table__ = Table('statistics_data', Base.metadata,
        Column('device', String, primary_key=True), 
        Column('sub_entity', String, primary_key=True),
        Column('name', String, primary_key=True), 
        Column('sub_key', String, primary_key=True), 
        Column('unit', String),
        Column('sum_amount', Float),
        Column('count', Float),
        Column('avg_amount', Float),
        Column('median_amount', Float),
        Column('stddev_amount', Float),
        Column('min_amount', Float),
        Column('max_amount', Float), 
        Column('time', String),
    )

    def __repr__(self):
        return f"<device(device={self.device}, device_name={self.sub_entity}, product_name={self.name}, manufacturer={self.sub_key}>"

class Statistics(BaseModel):
    '''Statistics as pydantic model'''
    device: str
    sub_entity: str
    name: Literal['Hour', 'Day', 'Month', 'Year']
    sub_key: str
    unit: str
    sum_amount: float
    count: float
    avg_amount: float
    min_amount: float
    max_amount: float
    time: str

    model_config = ConfigDict(from_attributes=True)