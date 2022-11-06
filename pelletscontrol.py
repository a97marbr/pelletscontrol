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

## Constants
SID_tank_top = "10.45A892010800"
SID_tank_mid = "10.E0BB92010800"
SID_tank_low = "10.E8B992010800"
TANK_TOP = "/mnt/1wire/"+SID_tank_top+"/temperature"
TANK_MID = "/mnt/1wire/"+SID_tank_mid+"/temperature"
TANK_LOW = "/mnt/1wire/"+SID_tank_low+"/temperature"
#FURNICE = "/mnt/1wire/FC.000000000081/910/out"
#FURNICE = "/tmp/testfile2"
FURNICE_PIN=12

GPIO.setmode(GPIO.BOARD)
GPIO.setup(FURNICE_PIN, GPIO.OUT)
ON = True
OFF = False
LOG_UPDATE_TIME = 10 #In minutes


class Sensor:
   def __init__(self, n, p) :
      name = n
      self.path = ""
      self.readings = []
      self.value = 0.0
      self.delta = 0.0
      self.last15min = 0
      self.last30min = 0
      self.last45min = 0
      self.last60min = 0
      print("Sensor ["+self.name+"] with path '"+self.path+"' created.")
   @classmethod
   def sense(self) :
      p1 = subprocess.Popen(["cat", self.__name__],  stdout=subprocess.PIPE)
      (output1, err) = p1.communicate()
      new_sensor_value = float(output1)
      self.delta = new_sensor_value - self.value 
      self.value = new_sensor_value
      self.readings.append(self.value)
      if(self.readings.count > 60) :
         self.readings.pop()




## Configuration

#TARGET_TEMP_START=73 ## Vinter inställning
TARGET_TEMP_START=50
TARGET_TEMP_STOP=75
#TARGET_TEMP_STOP=50

CONFIG_FILE = "/tmp/pelletscontrol.json"
config = {"pelletscontrol":{}}
LOGFILE="/run/user/1000/pelletscontrol.log"

tank_top_obj = Sensor("TANK_TOP", TANK_TOP)

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

# Setup logging
logger = logging.getLogger('pelletscontrol')
logger.setLevel(logging.DEBUG)
fh = logging.handlers.RotatingFileHandler(LOGFILE, maxBytes=10000000, backupCount=5)
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

##
## Reads the sensors on ACK tank and logs to LOGFILE
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

   ## Read sensor TOP
   p1 = subprocess.Popen(["cat", TANK_TOP],  stdout=subprocess.PIPE)
   (output1, err) = p1.communicate()
   ACK_TEMP_TOP_LAST=ACK_TEMP_TOP
   ACK_TEMP_TOP = float(output1)

   ## Read sensor MID
   p2 = subprocess.Popen(["cat", TANK_MID],  stdout=subprocess.PIPE)
   (output2, err) = p2.communicate()
   ACK_TEMP_MID_LAST=ACK_TEMP_MID
   ACK_TEMP_MID = float(output2)

   ## Read sensor BOTTOM
   p3 = subprocess.Popen(["cat", TANK_LOW],  stdout=subprocess.PIPE)
   (output3, err) = p3.communicate()
   ACK_TEMP_LOW_LAST=ACK_TEMP_LOW
   ACK_TEMP_LOW = float(output3)
   
   ## Log values
   logger.info("TOP "+ "{0:.1f}".format(ACK_TEMP_TOP) + u"\u00B0"+"C"+", MID "+ "{0:.1f}".format(ACK_TEMP_MID) + u"\u00B0"+"C"+", LOW "+ "{0:.1f}".format(ACK_TEMP_LOW) + u"\u00B0"+"C")
   config['pelletscontrol']['top'] = "{0:.1f}".format(ACK_TEMP_TOP)
   config['pelletscontrol']['mid'] = "{0:.1f}".format(ACK_TEMP_MID)
   config['pelletscontrol']['bottom'] = "{0:.1f}".format(ACK_TEMP_LOW)
   return


##
## Reads the sensors on ACK tank 
##
def readSensors():
   global ACK_TEMP_TOP
   global ACK_TEMP_TOP_LAST
   global ACK_TEMP_MID
   global ACK_TEMP_MID_LAST
   global ACK_TEMP_LOW
   global ACK_TEMP_LOW_LAST

   ## Read sensor TOP
   p1 = subprocess.Popen(["cat", "/mnt/1wire/"+SID_tank_top+"/temperature"],  stdout=subprocess.PIPE)
   (output1, err) = p1.communicate()
   ACK_TEMP_TOP_LAST=ACK_TEMP_TOP
   ACK_TEMP_TOP = float(output1)

   ## Read sensor MID
   p2 = subprocess.Popen(["cat", "/mnt/1wire/"+SID_tank_mid+"/temperature"],  stdout=subprocess.PIPE)
   (output2, err) = p2.communicate()
   ACK_TEMP_MID_LAST=ACK_TEMP_MID
   ACK_TEMP_MID = float(output2)

   ## Read sensor BOTTOM
   p3 = subprocess.Popen(["cat", "/mnt/1wire/"+SID_tank_low+"/temperature"],  stdout=subprocess.PIPE)
   (output3, err) = p3.communicate()
   ACK_TEMP_LOW_LAST=ACK_TEMP_LOW
   ACK_TEMP_LOW = float(output3)
   
   return

##
## Read the config file 
## The config contains burner status and time when this status changed
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
      config = {"pelletscontrol": {"status": 0, "timestamp": str(lastChangeTimestamp)}}

   burnStatus = config['pelletscontrol']['status']
   lastChangeTimestamp = datetime.datetime.strptime( config['pelletscontrol']['timestamp'], "%Y-%m-%d %H:%M:%S.%f")

   try:
      with open(CONFIG_FILE, 'w') as data_file:
         json.dump(config, data_file)
      print("Status: " + ("ON" if config['pelletscontrol']['status'] else "OFF"))
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
      #with open(FURNICE, 'w') as furnice:
      #   furnice.write(str(burnStatus));
      GPIO.output(FURNICE_PIN, ON)
      return

   except IOError:
      print("There was an error writing to ", FURNICE)
      print("Furnice NOT started!")

def stopFurnice():
   try:
      #with open(FURNICE, 'w') as furnice:
      #   furnice.write(str(burnStatus));
      GPIO.output(FURNICE_PIN, OFF)
      return

   except IOError:
      print("There was an error writing to ", FURNICE)
      print("Furnice NOT stopped!")
   

def setFurnice(str):
   try:
      #with open(FURNICE, 'w') as furnice:
      #   furnice.write(str(burnStatus));
      GPIO.output(FURNICE_PIN, str)
      return

   except IOError:
      print("There was an error writing to ", FURNICE)
      print("Furnice status NOT set!")

try:

   readConfig()

   logger.info("---=== PelletsburnerControl Started ===---");
   logger.info("Furnice has status: "+ ("ON" if config['pelletscontrol']['status'] else "OFF") + ", which was set "+ lastChangeTimestamp.strftime('%Y-%m-%d %H:%M:%S'))
   logger.info("Furnice starts when top of tank has droped below " + str(TARGET_TEMP_START) +  u"\u00B0"+"C.");
   logger.info("Furnice stops when middle of tank has reached " + str(TARGET_TEMP_STOP) +  u"\u00B0"+"C.")

   readAndLogSensors()
   lastLogged = datetime.datetime.now()
   

   print("Setting furnice to: " + ("ON" if config['pelletscontrol']['status'] else "OFF"))
   status = OFF
   if config['pelletscontrol']['status']==1 : status = ON
   setFurnice(status)   ## Set the status at every 60s, this should be removed     
   ## Main loop - Ctrl+C to exit
   while True:
      global counter
   
      ## Get sensor input write to log every 10min 
      elapsed = datetime.datetime.now() - lastLogged
      if elapsed >= datetime.timedelta(minutes=10):
         lastLogged = datetime.datetime.now()
         t = lastLogged - lastChangeTimestamp
         if burnStatus == ON:
            logger.info("Burning for " + str(t))
         else:
            logger.info("Idle for " + str(t))
         readAndLogSensors()
      else:
         readSensors()

      tank_top_obj.sense()
      logger.info("Sensor: "+tank_top_obj.name + " has value: " + tank_top_obj.value +  u"\u00B0"+"C.")
      logger.info("Sensor: "+tank_top_obj.name + " has delta: " + tank_top_obj.delta +  u"\u00B0"+"C.")

      if config['pelletscontrol']['status'] == ON:
         if ACK_TEMP_TOP >= TARGET_TEMP_STOP:
            tchange = datetime.datetime.now()
            tdelta = tchange - lastChangeTimestamp
            logger.info("Total burn time: " + str(tdelta))
            lastChangeTimestamp = tchange

            burnStatus = OFF
            
            ## Write state change to file
            config['pelletscontrol']['timestamp'] = str(lastChangeTimestamp)            
            config['pelletscontrol']['status'] = burnStatus
            writeConfig()

            stopFurnice()            
         
      else:
         if ACK_TEMP_TOP <= TARGET_TEMP_START:
            tchange = datetime.datetime.now()
            tdelta = tchange - lastChangeTimestamp
            logger.info("Total idle time: " + str(tdelta))
            lastChangeTimestamp = tchange

            burnStatus = ON

            config['pelletscontrol']['timestamp'] = str(lastChangeTimestamp)
            config['pelletscontrol']['status'] = burnStatus
            writeConfig()

            startFurnice()

      #setFurnice()   ## Set the status at every 60s, this should be removed     
      time.sleep(60) ## Sleeping 60 seconds until next sensor reading.

except KeyboardInterrupt:
   logger.info("---=== Ctrl-C detected: Shutting down ===---");
   writeConfig()
except IOError:
   print("There was an error writing to", CONFIG_FILE)
   logger.info("---=== Stopped ===---");
   sys.exit()

GPIO.cleanup()
logger.info("---=== Stopped ===---");
