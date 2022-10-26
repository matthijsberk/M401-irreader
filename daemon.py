#!/usr/bin/python
#
# ----------------------------------------------------------------------------
# "THE BEER-WARE LICENSE" (Revision 42):
# <phk@FreeBSD.ORG> wrote this file.  As long as you retain this notice you
# can do whatever you want with this stuff. If we meet some day, and you think
# this stuff is worth it, you can buy me a beer in return.   Poul-Henning Kamp
# ----------------------------------------------------------------------------
#
# Created by Matthijs Visser

import datetime
import time
import sys
import signal
import subprocess
import logging
import paho.mqtt.client as paho
import multiprocessing
import yaml
from kamstrup_meter import kamstrup
from mqtt_handler import MqqtHandler
from logging.handlers import TimedRotatingFileHandler
import serial
import json
from time import sleep


log = logging.getLogger("log")
log.setLevel(logging.DEBUG)

handler = TimedRotatingFileHandler('debug.log', when="d", interval=1, backupCount=5)

formatter = logging.Formatter("[%(asctime)s %(filename)s %(funcName)s:%(lineno)4s - %(levelname)s - %(message)s]",
							  "%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
log.addHandler(handler)

with open("config.yaml", "r") as ymlfile:
	cfg = yaml.load(ymlfile, Loader=yaml.BaseLoader)

class KamstrupDaemon(multiprocessing.Process):
	def __init__(self):
		log.info('initializing daemon')

		self.running = True
		self.event_finished = multiprocessing.Event()
		self.receive_queue = multiprocessing.Queue()
		mqtt_cfg = cfg["mqtt"]
		serial_cfg = cfg["serial_device"]
		kamstrup_cfg = cfg["kamstrup"]

		self.poll_interval = kamstrup_cfg["poll_interval"]

		signal.signal(signal.SIGINT, self.signal_handler)

		if (mqtt_cfg["retain"].lower() == "true"):
			retain = True
		else:
			retain = False
		
		if (mqtt_cfg["authentication"].lower() == "true"):
			self.mqtt_handler = MqqtHandler(mqtt_cfg["host"], int(mqtt_cfg["port"]), 
				mqtt_cfg["client"], mqtt_cfg["topic"], retain, int(mqtt_cfg["qos"]), 
				True, mqtt_cfg["username"], mqtt_cfg["password"])
		else:
			self.mqtt_handler = MqqtHandler(mqtt_cfg["host"], int(mqtt_cfg["port"]), 
				mqtt_cfg["client"], mqtt_cfg["topic"], retain, int(mqtt_cfg["qos"]))
		self.mqtt_handler.connect()
		self.mqtt_handler.loop_start()

		mc401 = serial.Serial(port='/dev/ttyUSB1', bytesize=serial.SEVENBITS, parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE, timeout=2)
		mc401.baudrate = 300
		mc401.write(bytes("/#1", 'UTF-8'))
		mc401.flush()
		sleep(1)
		mc401.baudrate = 1200
		mc401.flushInput()
		data = mc401.read(87)

		s = []
		for t in data.split():
  		    try:
    	    s.append(float(t))
  		except ValueError:
   		    pass
		print(s)
		energy = s[0] / 1000
		volume = s[1] / 1000
		temp_1 = s[3] / 100
		temp_2 = s[4] / 100
		temp_diff = s[5] / 100

		MQTT_MSG=json.dumps({"energy": energy, "volume": volume, "temp1": temp_1, "temp2": temp_2, "tempdiff": temp_diff, "flow" : 1});
		print(MQTT_MSG)	

	def signal_handler(self, signal, handler):
		self.running = False
		self.heat_meter.close()
		self.mqtt_handler.loop_stop()
		self.mqtt_handler.disconnect()
		log.info('stopping daemon')
		sys.exit(0)

	def run(self):
		while self.running:
			values = self.heat_meter.run()
			self.mqtt_handler.publish("values", str(values).replace("'", "\""))
			
			log.info("Waiting {} minute(s) for the next meter readout".format(self.poll_interval))
			time.sleep(int(self.poll_interval) * 60)
			
def main():
	daemon = KamstrupDaemon()
	daemon.run()

if  __name__ == '__main__':
	main()
