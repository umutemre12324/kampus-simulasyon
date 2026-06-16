# -*- coding: utf-8 -*-
"""
Created on Thu Mar 12 10:30:22 2026
@author: arvasis (Modified for Recycling Bin, Small Items & Slower Fill Rate)
"""

import numpy as np
import heapq
from collections import deque
import math

###############
## KUTUPHANE ##
###############
class TimeLine:
    def __init__(self):
        self.data = {}  
        self.heap = []    

    def add(self, event):
        index = event.time
        if index not in self.data:
            self.data[index] = deque()
            heapq.heappush(self.heap, index)
        self.data[index].append(event)

    def pop(self):
        while self.heap:
            time = self.heap[0]
            if time not in self.data:
                heapq.heappop(self.heap)
                continue
            queue = self.data[time]
            event = queue.popleft()
            if not queue:
                del self.data[time]
                heapq.heappop(self.heap)
            return time, event
        return None, "Koleksiyon tamamen boş!"
    
    def clear(self):
        self.data = {}  
        self.heap = [] 

class SimulationEvent:
    def __init__(self, name, timeLine, time, parameters, procedure):
        self.name = name
        self.procedure = procedure
        self.time = time
        self.timeLine = timeLine
        self.parameters = parameters
        
    def run(self):
        if self.procedure:
            time = self.procedure(self.timeLine, self.time, self.parameters)
        else:
            time = self.time
        return time


# --- GERİ DÖNÜŞÜM EVENTLERİ ---
class TrashThrownEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("TrashThrown", timeLine, time, parameters, procedure)

class TrashFallingEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("TrashFalling", timeLine, time, parameters, procedure)

class TrashHitGroundEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("TrashHitGround", timeLine, time, parameters, procedure)

class EmptyBinEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("EmptyBin", timeLine, time, parameters, procedure)


# --- ÇEVRE VE İNSAN EVENTLERİ ---
class ArrivalEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("Arrival", timeLine, time, parameters, procedure)

class DepartureEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure, agent):
        super().__init__("Departure", timeLine, time, parameters, procedure)
        self.agent = agent 
        
    def run(self):
        if self.procedure:
            time = self.procedure(self.timeLine, self.time, self.parameters, self.agent)
        else:
            time = self.time
        return time

class EnvironmentUpdateEvent(SimulationEvent):
    def __init__(self, timeLine, time, parameters, procedure):
        super().__init__("EnvUpdate", timeLine, time, parameters, procedure)


###################################
## SENSÖR SINIFLARI              ##
###################################
class Sensor:
    def __init__(self, name, tolerance):
        self.name = name
        self.tolerance = tolerance

class UltrasonicSensor(Sensor):
    def __init__(self, tolerance=0.02):
        super().__init__(name="Ultrasonic", tolerance=tolerance)
    def capture(self, true_distance):
        return max(0.0, true_distance + np.random.uniform(-self.tolerance, self.tolerance))

class CO2Sensor(Sensor):
    def __init__(self, tolerance=15.0):
        super().__init__(name="CO2_Sensor", tolerance=tolerance)
    def capture(self, true_co2):
        return max(400.0, true_co2 + np.random.normal(0, self.tolerance))

class TemperatureSensor(Sensor):
    def __init__(self, tolerance=0.3):
        super().__init__(name="Temp_Sensor", tolerance=tolerance)
    def capture(self, true_temp):
        return true_temp + np.random.normal(0, self.tolerance)

class CurrentSensor(Sensor):
    def __init__(self, tolerance=0.05):
        super().__init__(name="Current_Sensor", tolerance=tolerance)
    def capture(self, true_current):
        return max(0.0, true_current + np.random.normal(0, self.tolerance))


###################################
## AJAN (AGENT) SINIFLARI        ##
###################################
class Agent:
    def __init__(self, agent_id):
        self.agent_id = agent_id

class OccupantAgent(Agent):
    def __init__(self, agent_id, x, y):
        super().__init__(agent_id)
        self.x = x
        self.y = y
        self.co2_emission_rate = 0.03 

    def emit(self, interval):
        return self.co2_emission_rate * interval

class SmartLightAgent(Agent):
    def __init__(self, agent_id, wattage=60.0):
        super().__init__(agent_id)
        self.wattage = wattage
        self.is_on = False

    def consume(self, interval):
        if self.is_on:
            return self.wattage * (interval / 3600.0)
        return 0.0

class VentilationAgent(Agent):
    def __init__(self, agent_id, wattage=1000.0, evacuation_rate=10.0):
        super().__init__(agent_id)
        self.wattage = wattage
        self.evacuation_rate = evacuation_rate 
        self.is_on = False

    def consume(self, interval):
        if self.is_on:
            return self.wattage * (interval / 3600.0)
        return 0.0

    def evacuate(self, interval):
        if self.is_on:
            return self.evacuation_rate * interval
        return 0.0


#############################
## DIŞ FONKSİYON (KAMERA)  ##
#############################
def capture_and_classify():
    print("   [KAMERA] -> captured image (Biri geri dönüşüm kutusuna pet şişe/ambalaj attı, sınıflandırılıyor...)")


###########################
## DEGISKEN & PARAMETRELER##
###########################

smart_lights = [SmartLightAgent(agent_id=f"Light_{i+1}", wattage=60.0) for i in range(4)]
ventilation_system = VentilationAgent(agent_id="HVAC_1", wattage=1000.0, evacuation_rate=10.0)

simParameters = {
    'SimulationDuration': 28800.0,   
    'EnvUpdateInterval': 60.0,       
    
    'TotalArrivalsPlanned': 200,     
    'ArrivalsSoFar': 0,
    'ActiveOccupants': [],           
    'RoomWidth': 8.0,
    'RoomLength': 6.0,
    
    # GERİ DÖNÜŞÜM KUTUSU VE FİZİK
    'BinHeight': 0.8,                # Standart geri dönüşüm kutusu boyutu (80 cm)
    'Gravity': 9.81,             
    'TrashInterval': 0.05,            
    'BinSensor': UltrasonicSensor(tolerance=0.02),
    'StartTime': 0.0,            
    'CurrentTrashInBin': 0,
    'TotalTrashDroppedDay': 0,       
    'TrashThickness': 0.02,          # Pet şişe, kağıt ambalaj gibi atıkların ezilmiş kalınlığı (2 cm)
    'MaxBinCapacity': 40,            # 0.8m / 0.02m = 40 adet atık kapasitesi
    
    'TrueCO2': 400.0,
    'CriticalCO2Level': 1200.0,          
    'SafeCO2Level': 400.0,               
    'BaseTemp': 22.0,                    
    'TempPerPerson': 0.15,               
    'GridVoltage': 220.0,                
    'TotalEnergy_Wh': 0.0,               
    
    'Lights': smart_lights,
    'Ventilation': ventilation_system,
    'CO2Sensor': CO2Sensor(tolerance=5.0),
    'TempSensor': TemperatureSensor(tolerance=0.5),
    'CurrentSensor': CurrentSensor(tolerance=0.05)
}

simParameters['ArrivalRate'] = simParameters['SimulationDuration'] / simParameters['TotalArrivalsPlanned']
simulationTimeLine = TimeLine()

#######################
## MODEL PROSEDÜRLERİ##
#######################

# 1. GERİ DÖNÜŞÜM KUTUSU PROSEDÜRLERİ
def trashThrownProcedure(timeLine, simTime, params):
    if params['CurrentTrashInBin'] >= params['MaxBinCapacity']:
        print(f"   [{simTime:.1f} sn] -> UYARI: Geri dönüşüm kutusu zaten dolu, atılan atık taştı!")
        
    capture_and_classify()
    params['StartTime'] = simTime 
    next_check = simTime + params['TrashInterval']
    timeLine.add(TrashFallingEvent(timeLine, round(next_check, 4), params, trashFallingProcedure))
    return simTime

def trashFallingProcedure(timeLine, simTime, params):
    t = simTime - params['StartTime']
    distance_fallen = 0.5 * params['Gravity'] * (t ** 2)
    current_height = params['BinHeight'] - distance_fallen
    
    current_trash_level = params['CurrentTrashInBin'] * params['TrashThickness']
    effective_drop_height = params['BinHeight'] - current_trash_level
    
    if effective_drop_height <= 0:
        effective_drop_height = 0.001 
        
    total_falling_time = math.sqrt((2 * effective_drop_height) / params['Gravity'])
    
    if t >= total_falling_time or current_height <= current_trash_level:
        exact_hit_time = params['StartTime'] + total_falling_time
        timeLine.add(TrashHitGroundEvent(timeLine, round(exact_hit_time, 4), params, trashHitGroundProcedure))
        return simTime

    params['BinSensor'].capture(distance_fallen)
    next_check = simTime + params['TrashInterval']
    timeLine.add(TrashFallingEvent(timeLine, round(next_check, 4), params, trashFallingProcedure))
    return simTime

def trashHitGroundProcedure(timeLine, simTime, params):
    params['CurrentTrashInBin'] += 1
    params['TotalTrashDroppedDay'] += 1
    
    current_trash_level = params['CurrentTrashInBin'] * params['TrashThickness']
    
    print(f"   [{simTime:.1f} sn] -> Çöp atıldı. Yığın Yüksekliği: {current_trash_level:.2f}m (Kutudaki: {params['CurrentTrashInBin']}/{params['MaxBinCapacity']})")
    
    if params['CurrentTrashInBin'] >= params['MaxBinCapacity']:
        empty_time = simTime + 10.0
        timeLine.add(EmptyBinEvent(timeLine, round(empty_time, 2), params, emptyBinProcedure))
        
    return simTime

def emptyBinProcedure(timeLine, simTime, params):
    print(f"\n   [{simTime:.1f} sn] -> [GERİ DÖNÜŞÜM GÖREVLİSİ] Kutu boşaltıldı!\n")
    params['CurrentTrashInBin'] = 0
    return simTime


# 2. İNSAN HAREKETLERİ (GELİŞ VE AYRILIŞ)
def arrivalProcedure(timeLine, simTime, params):
    agent_id = f"Person_{params['ArrivalsSoFar'] + 1}"
    x = np.random.uniform(0, params['RoomWidth'])
    y = np.random.uniform(0, params['RoomLength'])
    
    new_occupant = OccupantAgent(agent_id, x, y)
    params['ActiveOccupants'].append(new_occupant)
    
    # %30 ihtimalle geri dönüşüme bir şeyler atma
    if np.random.rand() < 0.30:
        trash_time = simTime + np.random.uniform(2.0, 10.0)
        timeLine.add(TrashThrownEvent(timeLine, round(trash_time, 2), params, trashThrownProcedure))
    
    stay_duration = np.random.uniform(1800, 7200) 
    leave_time = simTime + stay_duration
    if leave_time <= params['SimulationDuration']:
        timeLine.add(DepartureEvent(timeLine, round(leave_time, 2), params, departureProcedure, new_occupant))

    params['ArrivalsSoFar'] += 1
    if params['ArrivalsSoFar'] < params['TotalArrivalsPlanned']:
        next_arrival = simTime + np.random.exponential(params['ArrivalRate'])
        if next_arrival < params['SimulationDuration']:
            timeLine.add(ArrivalEvent(timeLine, round(next_arrival, 2), params, arrivalProcedure))
            
    return simTime

def departureProcedure(timeLine, simTime, params, agent):
    if agent in params['ActiveOccupants']:
        params['ActiveOccupants'].remove(agent)
    return simTime


# 3. ÇEVRESEL VE ENERJİ ÖLÇÜM PROSEDÜRÜ
def environmentUpdateProcedure(timeLine, simTime, params):
    num_people = len(params['ActiveOccupants'])
    interval = params['EnvUpdateInterval']
    
    co2_emitted = sum(agent.emit(interval) for agent in params['ActiveOccupants'])
    params['TrueCO2'] += co2_emitted
    
    true_temp = params['BaseTemp'] + (num_people * params['TempPerPerson'])
    
    vent = params['Ventilation']
    if params['TrueCO2'] >= params['CriticalCO2Level']:
        vent.is_on = True
    elif params['TrueCO2'] <= params['SafeCO2Level']:
        vent.is_on = False
        
    if vent.is_on:
        co2_evacuated = vent.evacuate(interval)
        params['TrueCO2'] = max(400.0, params['TrueCO2'] - co2_evacuated)
    
    if num_people == 0:
        active_lights_needed = 0
    else:
        active_lights_needed = min(4, math.ceil(num_people / 10.0))
        
    for i, light in enumerate(params['Lights']):
        light.is_on = (i < active_lights_needed)
        
    lights_energy = sum(light.consume(interval) for light in params['Lights'])
    vent_energy = vent.consume(interval)
    params['TotalEnergy_Wh'] += (lights_energy + vent_energy)
    
    active_power_w = active_lights_needed * 60.0
    if vent.is_on:
        active_power_w += vent.wattage
        
    true_current_a = active_power_w / params['GridVoltage']
    
    measured_current = params['CurrentSensor'].capture(true_current_a)
    measured_co2 = params['CO2Sensor'].capture(params['TrueCO2'])
    measured_temp = params['TempSensor'].capture(true_temp)

    if simTime > 0 and simTime % 3600 == 0:
        saat = int(simTime // 3600)
        vent_status = "AÇIK (Tahliye Ediyor)" if vent.is_on else "KAPALI"
        
        print(f"\n[{saat}. SAAT RAPORU | Zaman: {simTime:.0f}s] ---")
        print(f"  * Odadaki Aktif İnsan: {num_people}")
        print(f"  * Işık Durumu: {active_lights_needed} Işık Açık")
        print(f"  * Havalandırma Durumu: {vent_status}")
        print(f"  * Anlık Akım (Şebeke Çekişi): {measured_current:.3f}A")
        print(f"  * Toplam Enerji Tüketimi: {params['TotalEnergy_Wh']:.2f} Wh")
        print(f"  * Sensörler -> Sıcaklık: {measured_temp:.1f}°C | CO2: {measured_co2:.0f} ppm")
        print("--------------------------------------")
    
    next_update = simTime + interval
    if next_update <= params['SimulationDuration']:
        timeLine.add(EnvironmentUpdateEvent(timeLine, round(next_update, 2), params, environmentUpdateProcedure))
        
    return simTime


######################
## SIMÜLASYON RUN ##
######################

print("--- 8 SAATLİK GERÇEKÇİ FİZİK VE ABM-DES HİBRİT SİMÜLASYONU BAŞLIYOR ---\n")

simulationTimeLine.add(ArrivalEvent(simulationTimeLine, 0.0, simParameters, arrivalProcedure))
simulationTimeLine.add(EnvironmentUpdateEvent(simulationTimeLine, simParameters['EnvUpdateInterval'], simParameters, environmentUpdateProcedure))

# Event Döngüsü
while len(simulationTimeLine.data) > 0:
    time, event = simulationTimeLine.pop()
    event.run()

print("\n--- SİMÜLASYON TAMAMLANDI ---")
print(f"Gün Sonu Geri Dönüşüm Kutusunda Kalan Atık Sayısı: {simParameters['CurrentTrashInBin']}")
print(f"Gün İçinde Atılan TOPLAM Atık Sayısı: {simParameters['TotalTrashDroppedDay']}")
print(f"Gün Sonu Toplam Enerji Tüketimi: {simParameters['TotalEnergy_Wh']:.2f} Wh")
