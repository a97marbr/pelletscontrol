#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Created 2015-05-17 by Marcus Brohede
# All rights reserved

import sys
import logging
import logging.handlers
import datetime
import subprocess
import time
import json
import RPi.GPIO as GPIO

dt = datetime.datetime.now()
ts = datetime.datetime.timestamp(dt)
print("TS " + str(ts))

CONFIG_FILE = "/tmp/pelletscontrol.json"
config = {"pelletscontrol": {}}
LOGFILE = "/run/user/1000/pelletscontrol.log"

# Setup logging
logger = logging.getLogger('pelletscontrol')
logger.setLevel(logging.DEBUG)
fh = logging.handlers.RotatingFileHandler(
    LOGFILE, maxBytes=10000000, backupCount=5)
fh.setLevel(logging.DEBUG)
# Log error messages to console
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s | %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

# Constants
SID_tank_top = "10.45A892010800"
SID_tank_mid = "10.E0BB92010800"
SID_tank_low = "10.E8B992010800"
TANK_TOP = "/mnt/1wire/"+SID_tank_top+"/temperature"
TANK_MID = "/mnt/1wire/"+SID_tank_mid+"/temperature"
TANK_LOW = "/mnt/1wire/"+SID_tank_low+"/temperature"
# FURNICE = "/mnt/1wire/FC.000000000081/910/out"
# FURNICE = "/tmp/testfile2"
FURNICE_PIN = 12

#GPIO.setmode(GPIO.BOARD)
#GPIO.setup(FURNICE_PIN, GPIO.OUT)
ON = True
OFF = False
LOG_UPDATE_TIME = 10  # In minutes


class Furnice:
    def __init__(self, pin):
        global CONFIG_FILE
        global config
        global logger
        global acc_tank
        self.furnice_pin = pin
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.furnice_pin, GPIO.OUT)
        self.active = False
        self.status = OFF
        self.last_start = 0
        self.last_error = 0

    def start(self):
        try:
            GPIO.output(self.furnice_pin, ON)
            self.last_start = datetime.datetime.now()
            self.active = True
            config['pelletscontrol']['timestamp'] = str(
                datetime.datetime.now())
            config['pelletscontrol']['status'] = 1
            self.writeConfig()                 
            return

        except IOError:
            print("Failed to activate furnice!")
            self.last_error = datetime.datetime.now()
            self.active = False

    def stop(self):
        try:
            GPIO.output(self.furnice_pin, OFF)
            self.active = False
            self.last_start = datetime.datetime.now()

            config['pelletscontrol']['timestamp'] = str(
                datetime.datetime.now())
            config['pelletscontrol']['status'] = 0
            self.writeConfig()            
            return

        except IOError:
            print("Failed to deactivate furnice!")
            self.last_error = datetime.datetime.now()
            self.active = True

    def status(self):
        if (self.active):
            print("Furnace is active.")
            print("   started ===> " + self.last_start)            
        else:
            print("Furnace is idle.")
    def update(self):
        if(self.active == True):
            # Is delta_last30 > 2 degrees
            if(acc_tank.sensors[acc_tank.hi_sensor_id].delta_last30 < 2):
                GPIO.cleanup()
                logger.error("Furnice failed to increase tank temperatur last 30min. Stopping furnice.")
                sys.exit("Furnice failed to increase tank temperatur last 30min. Stopping furnice.")                

            if(acc_tank.sensors[acc_tank.hi_sensor_id].value >= acc_tank.hi_threshold):
                logger.info(acc_tank.sensors[acc_tank.hi_sensor_id].name + " reached target " + str(acc_tank.hi_threshold) + u"\u00B0"+"C.")
                logger.info("Furnice idle " + str(datetime.datetime.now()))
                self.stop()
            # else:
            #     logger.info("Furnice burning")
        else:
            if(acc_tank.sensors[acc_tank.low_sensor_id].value < acc_tank.low_threshold):
                logger.info(acc_tank.sensors[acc_tank.low_sensor_id].name + " dropped below " + str(acc_tank.low_threshold) + u"\u00B0"+"C.")
                logger.info("Furnice activated " + str(datetime.datetime.now()))
                self.start()
            # else:
            #     logger.info("Furnice idle")
    def writeConfig(self):
        try:
            with open(CONFIG_FILE, 'w') as data_file:
                json.dump(config, data_file)
            return
        except IOError:
            print("There was an error writing to ", CONFIG_FILE)

class Reading:
    def __init__(self, value,ts):
        self.value=value
        self.ts=ts
        

class Sensor:
    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.readings = []
        self.value = 0.0
        self.delta = 0.0
        self.delta_last5 = 999.99
        self.delta_last15 = 999.99
        self.delta_last30 = 999.99
        self.delta_last45 = 999.99
        self.delta_last60 = 999.99
        self.avg_last60 = 0.0
        print("Sensor ["+self.name+"] with path '"+self.path+"' created.")

    def update(self):
        p1 = subprocess.Popen(["cat", self.path],  stdout=subprocess.PIPE)
        (output1, err) = p1.communicate()
        new_sensor_value = float(output1)
        self.delta = new_sensor_value - self.value
        self.value = new_sensor_value
        dt = datetime.datetime.now()
        self.readings.append(Reading(new_sensor_value,datetime.datetime.timestamp(dt)))

        if (len(self.readings) >= 5):
            self.delta_last5 = self.value - \
                self.readings[len(self.readings)-5].value
        if (len(self.readings) >= 15):
            self.delta_last15 = self.value - \
                self.readings[len(self.readings)-15].value
        if (len(self.readings) >= 30):
            self.delta_last30 = self.value - \
                self.readings[len(self.readings)-30].value
        if (len(self.readings) >= 45):
            self.delta_last45 = self.value - \
                self.readings[len(self.readings)-45].value
        if (len(self.readings) >= 60):
            self.delta_last60 = self.value - self.readings[0].value

        if (len(self.readings) > 60):
            self.readings.pop(0)
        tmpsum = 0
        for reading in self.readings:
            tmpsum += reading.value
            self.avg_last60 = tmpsum/len(self.readings)


class Tank:
    global logger

    def __init__(self):
        self.sensors = []
        self.low_threshold = 50.0
        self.hi_threshold = 75.0
        self.low_sensor_id = 0
        self.hi_sensor_id = 0
        # logger.info("Furnice starts when ["+self.low_sensor_id+"] has droped below " +
        #             str(self.low_threshold) + u"\u00B0"+"C.")
        # logger.info("Furnice stops when ["+self.hi_sensor_id+"] has reached " +
        #             str(self.hi_threshold) + u"\u00B0"+"C.")

    def set_hi_sensor(self, sname):
        self.hi_sensor_id = sname

    def set_low_sensor(self, sname):
        self.low_sensor_id = sname

    def add_sensor(self, sensor):
        self.sensors.append(sensor)

    def show(self):
        for sensor in self.sensors:
            print(sensor.name + " has temperatur " +
                  str(sensor.value) + u"\u00B0"+"C. " + u"\u0394"+"5 " +
                  str(sensor.delta_last5) + u"\u00B0"+"C, " + u"\u0394"+"15 " +
                  str(sensor.delta_last15) + u"\u00B0"+"C, " + u"\u0394"+"30 " +
                  str(sensor.delta_last30) + u"\u00B0"+"C, " + u"\u0394"+"45 " +
                  str(sensor.delta_last45) + u"\u00B0"+"C, " + u"\u0394"+"60 " +
                  str(sensor.delta_last60) + u"\u00B0"+"C. Rolling mean ("+str(len(sensor.readings))+"): " + str(sensor.avg_last60) + u"\u00B0"+"C.")
            readings_str = "["
            for reading in sensor.readings:
                readings_str += str(reading.value) + " "
            
            readings_str += "]"
            print(readings_str)
            # print(sensor.name + u"\u0394"+"15 " + \
            #       str(sensor.delta_last15) + u"\u00B0"+"C.")
            # print(sensor.name + u"\u0394"+"30 " + \
            #       str(sensor.delta_last30) + u"\u00B0"+"C.")
            # print(sensor.name + u"\u0394"+"45 " + \
            #       str(sensor.delta_last45) + u"\u00B0"+"C.")
            # print(sensor.name + u"\u0394"+"60 " + \
            #       str(sensor.delta_last60) + u"\u00B0"+"C.")
            # print("Rolling mean ("+str(len(sensor.readings))+"): " + str(sensor.avg_last60) + u"\u00B0"+"C.")

    def log(self):
        for sensor in self.sensors:
            logger.info(sensor.name +" "+ "{0:.1f}".format(round(sensor.value,2)) +
                        u"\u00B0"+"C. " + u"\u0394"+"5 " +
                        str(round(sensor.delta_last5, 2)) + u"\u00B0"+"C, " + u"\u0394"+"15 " +
                        str(round(sensor.delta_last15,2)) + u"\u00B0"+"C, " + u"\u0394"+"30 " +
                        str(round(sensor.delta_last30,2)) + u"\u00B0"+"C, " + u"\u0394"+"45 " +
                        str(round(sensor.delta_last45,2)) + u"\u00B0"+"C, " + u"\u0394"+"60 " +
                        str(round(sensor.delta_last60,2)) + u"\u00B0"+"C. Rolling mean ("+str(len(sensor.readings))+"): " + "{0:.1f}".format(round(sensor.avg_last60,2)) + u"\u00B0"+"C.")
            readings_str = "["
            for reading in sensor.readings:
                readings_str += str(reading.value) + " "
            
            readings_str += "]"
            logger.info(readings_str)

    def update(self):
        for sensor in self.sensors:
            sensor.update()

        # Configuration

        # TARGET_TEMP_START=73 ## Vinter inställning
TARGET_TEMP_START = 50
TARGET_TEMP_STOP = 75
# TARGET_TEMP_STOP=50


tank_top_obj = Sensor("TANK_TOP", TANK_TOP)
tank_middle_obj = Sensor("TANK_MID", TANK_MID)
tank_bottom_obj = Sensor("TANK_LOW", TANK_LOW)

acc_tank = Tank()
acc_tank.add_sensor(tank_top_obj)
acc_tank.add_sensor(tank_middle_obj)
acc_tank.add_sensor(tank_bottom_obj)
acc_tank.show()

furnice = Furnice(FURNICE_PIN)

# Variables used
ACK_TEMP_TOP = 0.0
ACK_TEMP_TOP_LAST = 0.0
ACK_TEMP_MID = 0.0
ACK_TEMP_MID_LAST = 0.0
ACK_TEMP_LOW = 0.0
ACK_TEMP_LOW_LAST = 0.0
COUNTER = 0
LAST_CHANGE = -1
SINCE_LAST_CHANGE = 0
ACTIVE_TIME = 0
IDEL_TIME = 0
lastChangeTimestamp = datetime.datetime.now()

##
# Reads the sensors on ACK tank and logs to LOGFILE
##


def readAndLogSensors():
    global config
    global ACK_TEMP_TOP
    global ACK_TEMP_TOP_LAST
    global ACK_TEMP_MID
    global ACK_TEMP_MID_LAST
    global ACK_TEMP_LOW
    global ACK_TEMP_LOW_LAST
    global TANK_TOP
    global TANK_MID
    global TANK_LOW

    # Read sensor TOP
    p1 = subprocess.Popen(["cat", TANK_TOP],  stdout=subprocess.PIPE)
    (output1, err) = p1.communicate()
    ACK_TEMP_TOP_LAST = ACK_TEMP_TOP
    ACK_TEMP_TOP = float(output1)

    # Read sensor MID
    p2 = subprocess.Popen(["cat", TANK_MID],  stdout=subprocess.PIPE)
    (output2, err) = p2.communicate()
    ACK_TEMP_MID_LAST = ACK_TEMP_MID
    ACK_TEMP_MID = float(output2)

    # Read sensor BOTTOM
    p3 = subprocess.Popen(["cat", TANK_LOW],  stdout=subprocess.PIPE)
    (output3, err) = p3.communicate()
    ACK_TEMP_LOW_LAST = ACK_TEMP_LOW
    ACK_TEMP_LOW = float(output3)

    # Log values
    logger.info("TOP " + "{0:.1f}".format(ACK_TEMP_TOP) + u"\u00B0"+"C"+", MID " + "{0:.1f}".format(
        ACK_TEMP_MID) + u"\u00B0"+"C"+", LOW " + "{0:.1f}".format(ACK_TEMP_LOW) + u"\u00B0"+"C")
    config['pelletscontrol']['top'] = "{0:.1f}".format(ACK_TEMP_TOP)
    config['pelletscontrol']['mid'] = "{0:.1f}".format(ACK_TEMP_MID)
    config['pelletscontrol']['bottom'] = "{0:.1f}".format(ACK_TEMP_LOW)
    return


##
# Reads the sensors on ACK tank
##
def readSensors():
    global ACK_TEMP_TOP
    global ACK_TEMP_TOP_LAST
    global ACK_TEMP_MID
    global ACK_TEMP_MID_LAST
    global ACK_TEMP_LOW
    global ACK_TEMP_LOW_LAST

    # Read sensor TOP
    p1 = subprocess.Popen(
        ["cat", "/mnt/1wire/"+SID_tank_top+"/temperature"],  stdout=subprocess.PIPE)
    (output1, err) = p1.communicate()
    ACK_TEMP_TOP_LAST = ACK_TEMP_TOP
    ACK_TEMP_TOP = float(output1)

    # Read sensor MID
    p2 = subprocess.Popen(
        ["cat", "/mnt/1wire/"+SID_tank_mid+"/temperature"],  stdout=subprocess.PIPE)
    (output2, err) = p2.communicate()
    ACK_TEMP_MID_LAST = ACK_TEMP_MID
    ACK_TEMP_MID = float(output2)

    # Read sensor BOTTOM
    p3 = subprocess.Popen(
        ["cat", "/mnt/1wire/"+SID_tank_low+"/temperature"],  stdout=subprocess.PIPE)
    (output3, err) = p3.communicate()
    ACK_TEMP_LOW_LAST = ACK_TEMP_LOW
    ACK_TEMP_LOW = float(output3)

    return

##
# Read the config file
# The config contains burner status and time when this status changed
##


def readConfig():
    global lastChangeTimestamp
    global burnStatus
    global config

    try:
        with open(CONFIG_FILE) as data_file:
            config = json.load(data_file)
    except IOError:
        print("There was an error opening ", CONFIG_FILE)
        # Assume IDLE and start counting from now()
        burnStatus = OFF
        lastChangeTimestamp = datetime.datetime.now()
        config = {"pelletscontrol": {"status": 0,
                                     "timestamp": str(lastChangeTimestamp)}}

    burnStatus = config['pelletscontrol']['status']
    lastChangeTimestamp = datetime.datetime.strptime(
        config['pelletscontrol']['timestamp'], "%Y-%m-%d %H:%M:%S.%f")

    try:
        with open(CONFIG_FILE, 'w') as data_file:
            json.dump(config, data_file)
        print("Status: " +
              ("ON" if config['pelletscontrol']['status'] else "OFF"))
        print("Time: " + config['pelletscontrol']['timestamp'])
        return

    except IOError:
        print("There was an error writing to ", CONFIG_FILE)


def writeConfig():
    try:
        with open(CONFIG_FILE, 'w') as data_file:
            json.dump(config, data_file)
        return
    except IOError:
        print("There was an error writing to ", CONFIG_FILE)


def startFurnice():
    try:
        # with open(FURNICE, 'w') as furnice:
        #   furnice.write(str(burnStatus));
        GPIO.output(FURNICE_PIN, ON)
        return

    except IOError:
        print("There was an error writing to ", FURNICE)
        print("Furnice NOT started!")


def stopFurnice():
    try:
        # with open(FURNICE, 'w') as furnice:
        #   furnice.write(str(burnStatus));
        GPIO.output(FURNICE_PIN, OFF)
        return

    except IOError:
        print("There was an error writing to ", FURNICE)
        print("Furnice NOT stopped!")


def setFurnice(str):
    try:
        # with open(FURNICE, 'w') as furnice:
        #   furnice.write(str(burnStatus));
        GPIO.output(FURNICE_PIN, str)
        return

    except IOError:
        print("There was an error writing to ", FURNICE)
        print("Furnice status NOT set!")


try:

    readConfig()

    logger.info("---=== PelletsburnerControl Started ===---")
    logger.info("Furnice has status: " + ("ON" if config['pelletscontrol']['status']
                else "OFF") + ", which was set " + lastChangeTimestamp.strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("Furnice starts when top of tank has droped below " +
                str(TARGET_TEMP_START) + u"\u00B0"+"C.")
    logger.info("Furnice stops when middle of tank has reached " +
                str(TARGET_TEMP_STOP) + u"\u00B0"+"C.")

    readAndLogSensors()
    lastLogged = datetime.datetime.now()

    print("Setting furnice to: " +
          ("ON" if config['pelletscontrol']['status'] else "OFF"))
    status = OFF
    if config['pelletscontrol']['status'] == 1:
        status = ON
        furnice.start()
    else:
        furnice.stop()
    #setFurnice(status)  # Set the status at every 60s, this should be removed
    # Main loop - Ctrl+C to exit
    while True:
        global counter

        # Get sensor input write to log every 10min
        # elapsed = datetime.datetime.now() - lastLogged
        # if elapsed >= datetime.timedelta(minutes=10):
        #     lastLogged = datetime.datetime.now()
        #     t = lastLogged - lastChangeTimestamp            
        #     if burnStatus == ON:
        #         logger.info("Burning for " + str(t))
        #     else:
        #         logger.info("Idle for " + str(t))
        #     readAndLogSensors()
        # else:
        #     readSensors()

        acc_tank.update()
        acc_tank.log()
        furnice.update()

        # if config['pelletscontrol']['status'] == ON:
        #     if ACK_TEMP_TOP >= TARGET_TEMP_STOP:
        #         tchange = datetime.datetime.now()
        #         tdelta = tchange - lastChangeTimestamp
        #         logger.info("Total burn time: " + str(tdelta))
        #         lastChangeTimestamp = tchange

        #         burnStatus = OFF

        #         # Write state change to file
        #         config['pelletscontrol']['timestamp'] = str(
        #             lastChangeTimestamp)
        #         config['pelletscontrol']['status'] = burnStatus
        #         writeConfig()

        #         stopFurnice()

        # else:
        #     if ACK_TEMP_TOP <= TARGET_TEMP_START:
        #         tchange = datetime.datetime.now()
        #         tdelta = tchange - lastChangeTimestamp
        #         logger.info("Total idle time: " + str(tdelta))
        #         lastChangeTimestamp = tchange

        #         burnStatus = ON

        #         config['pelletscontrol']['timestamp'] = str(
        #             lastChangeTimestamp)
        #         config['pelletscontrol']['status'] = burnStatus
        #         writeConfig()

        #         startFurnice()

        # setFurnice()   ## Set the status at every 60s, this should be removed
        time.sleep(60)  # Sleeping 60 seconds until next sensor reading.

except KeyboardInterrupt:
    logger.info("---=== Ctrl-C detected: Shutting down ===---")
    writeConfig()
except IOError:
    print("There was an error writing to", CONFIG_FILE)
    logger.info("---=== Stopped ===---")
    sys.exit()

GPIO.cleanup()
logger.info("---=== Stopped ===---")
