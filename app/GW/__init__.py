#!/usr/bin/env python3
from time import sleep
from .SX127x.LoRa import *
from .SX127x.LoRaArgumentParser import LoRaArgumentParser
from .SX127x.board_config import BOARD
from random import randrange
import paho.mqtt.client as mqtt

import getmac

from .setup import args
import GW.LoRaWAN
from .LoRaWAN.MHDR import MHDR
from .LoRaWAN.LoRaMAC import LoRaMAC
from .LoRaWAN.Channel import Channel

BOARD.setup()
parser = LoRaArgumentParser("LoRaWAN receiver")

class LoRaWANrcv(LoRa):
    def __init__(self, verbose = False):
        super(LoRaWANrcv, self).__init__(verbose)
        self.usedDevnonce = set()
        self.rx_deveui = ''
        self.rx_devaddr = ''
        self.accepted_deveui = {}   # key:deveui  | value:devaddr
        self.appskey_dict = {}      # key:devaddr | value:appskey
        self.nwskey_dict = {}       # key:devaddr | value:nwskey
        self.FCntDown_dict={}
        self.FCntUp_dict={}

        # Convert devaddr to node id
        self.devaddr2nodeid = {}    # key:devaddr | value:nodeid
        
        self.set_mode(MODE.SLEEP)
        self.reset_ptr_rx()
        
        # values for mac commands
        self.is_MacCommand = False
        self.commandType = None
        self.AnsCommand_payload = []
    def on_rx_done(self):
        # Initialize values
        self.is_MacCommand = False
        correct_fcnt = False

        print("-------------------------------------RxDone")
        self.clear_irq_flags(RxDone=1)
        payload = self.read_payload(nocheck=True)
        print("".join(format(x, '02x') for x in bytes(payload)))
        lorawan.read(payload)
        
        
        print("mhdr.mversion: "+str(format(lorawan.get_mhdr().get_mversion(), '08b')))
        print("mhdr.mtype: "+str(format(lorawan.get_mhdr().get_mtype(), '08b')))
        print("mic: "+str(lorawan.get_mic()))
        print("valid mic: "+str(lorawan.valid_mic()))

        # If mtype is UPLink-----------------------------------------------------
        if lorawan.get_mhdr().get_mtype() == MHDR.UNCONF_DATA_UP or lorawan.get_mhdr().get_mtype() == MHDR.CONF_DATA_UP:
            self.rx_devaddr = ''
            # Get devaddr and add it to devaddr_list
            rx_devaddr_list = lorawan.get_mac_payload().get_fhdr().get_devaddr()
            for elem in rx_devaddr_list:
                self.rx_devaddr += '{:02X}'.format(elem)
            print("rx_devaddr: ",self.rx_devaddr)
            # Update keys
            if self.rx_devaddr in self.nwskey_dict:
                lorawan.set_nwkey(self.nwskey_dict[self.rx_devaddr])
            if self.rx_devaddr in self.appskey_dict:
                lorawan.set_appkey(self.appskey_dict[self.rx_devaddr])
            # Update is_MacCommand
            self.is_MacCommand = not lorawan.get_mac_payload().get_fport() # Boolean reversal
            print("is_MacCommand: ", self.is_MacCommand)

        #If mtype is JOIN_REQUEST--------------------------------------------------
        elif lorawan.get_mhdr().get_mtype() == MHDR.JOIN_REQUEST:
            print("Got LoRaWAN JOIN_REQUEST")
            
            # Get deveui and give new devaddr to end-device
            for elem in lorawan.get_mac_payload().frm_payload.get_deveui():
                self.rx_deveui += '{:02X}'.format(elem)
            print("rx_deveui: ", self.rx_deveui)

            lorawan.set_appkey(appkey)
            lorawan.set_nwkey(nwskey)
            rx_devnonce = lorawan.get_mac_payload().frm_payload.get_devnonce()
            print("devnonce: ", rx_devnonce)

            # Ignore same devnonce
            if str(rx_devnonce[0])+str(rx_devnonce[1]) in self.usedDevnonce:
                print("Error: Received devnonce has been used already!")
                return
            self.usedDevnonce |= {str(rx_devnonce[0])+str(rx_devnonce[1])}


            # Create JoinAccept Message
            new_devaddr = [0x86,randrange(256),randrange(256),randrange(256)]
            new_devaddr_str = ""
            for elem in new_devaddr:
                new_devaddr_str +='{:02X}'.format(elem)
                
            # Create new devaddr for node
            if self.rx_deveui in self.accepted_deveui:
                while self.accepted_deveui[self.rx_deveui] != new_devaddr_str:
                    new_devaddr = [0x86,randrange(256),randrange(256),randrange(256)]
                    new_devaddr_str=""
                    for elem in new_devaddr:
                        new_devaddr_str +='{:02X}'.format(elem)
                self.accepted_deveui[self.rx_deveui] = new_devaddr_str

            lorawan.create(MHDR.JOIN_ACCEPT, {'appnonce':appnonce, 'netid':netid, 'devaddr':new_devaddr, 'dlsettings':dlsettings, 'rxdelay':rxdelay, 'cflist':cflist})

            new_nwskey = lorawan.derive_nwskey(rx_devnonce)    # Generate new nwskey and set new nwkey
            self.nwskey_dict[new_devaddr_str] = new_nwskey
            new_appskey = lorawan.derive_appskey(rx_devnonce)   # Generate new appskey and set new appkey
            self.appskey_dict[new_devaddr_str] = new_appskey
            self.set_mode(MODE.STDBY)
            self.set_invert_iq(1)
            self.set_invert_iq2(1)
            
            # init FCnt
            self.FCntUp_dict[new_devaddr_str]=0
            self.FCntDown_dict[new_devaddr_str]=0

            print("write:", self.write_payload(lorawan.to_raw()))
            print("packet: ", lorawan.to_raw())
            self.set_dio_mapping([1,0,0,0,0,0])
            sleep(0.1)
            self.set_mode(MODE.TX)



        #If mtype is UPLink---------------------------------------------------------
        elif lorawan.get_mhdr().get_mtype() == MHDR.UNCONF_DATA_UP\
                or lorawan.get_mhdr().get_mtype() == MHDR.CONF_DATA_UP:
            rx_msg = "".join(list(map(chr, lorawan.get_payload()))) # Make message into list
            print("Received message: "+rx_msg)
            #Check FCntUp, If not exist in FCntUp_dict, set FCntUp to 0
            if self.rx_devaddr not in self.FCntUp_dict:
                self.FCntUp_dict[self.rx_devaddr] = 0
            
            if self.is_MacCommand == False:                          # If FRMPayload is not MacCommand, update devaddr2nodeid.
                self.devaddr2nodeid[self.rx_devaddr] = int(rx_msg.split(':')[0].split('/')[1]) # Matching devaddr - nodeid(int)
            
            print("Received Uplink FCnt: ", int.from_bytes(lorawan.get_mac_payload().get_fhdr().get_fcnt(), byteorder='little')\
                    ,"| Local FCntUp value",self.FCntUp_dict[self.rx_devaddr])
            if self.FCntUp_dict[self.rx_devaddr] == int.from_bytes(lorawan.get_mac_payload().get_fhdr().get_fcnt(), byteorder='little'):
                correct_fcnt = True
                self.FCntUp_dict[self.rx_devaddr] += 1
            else:
                print("Duplicated Message?: Got wrong FCnt!")
                correct_fcnt = False


            #If fcnt is correct
            if correct_fcnt == True:
                    pass
            elif int.from_bytes(lorawan.get_mac_payload().get_fhdr().get_fcnt(), \
                     byteorder='little') > self.FCntUp_dict[self.rx_devaddr]:
                self.FCntUp_dict[self.rx_devaddr] = int.from_bytes(lorawan.get_mac_payload().get_fhdr().get_fcnt(), byteorder='little') + 1

            
            # If MacCommand is in FramePayload, handle this MacCommand
            if self.is_MacCommand == True:
                if self.rx_devaddr in self.devaddr2nodeid:      # Important!: Can't handle MacCommand if nodeid was not received before.
                    self.commandType, self.AnsCommand_payload = CID.handle_command_payload(lorawan, self.devaddr2nodeid[self.rx_devaddr], int(rx_msg), mqttclient)
            else:
                # If not MacCommand, MQTT Publish
                mqttclient.publish(rx_msg.split(':')[0], rx_msg.split(':')[1]) # topic: 'data/nodeid', message: 'sensorid,value'



            #If Unconfirmed Uplink, respond to MacCommand or just keep listen
            if lorawan.get_mhdr().get_mtype() == MHDR.UNCONF_DATA_UP:
                if self.is_MacCommand==True and self.commandType == CID.Req: # If received Mac Command is Request, send Ans
                    # Update FCntDown
                    if self.rx_devaddr not in self.FCntDown_dict:
                        self.FCntDown_dict[self.rx_devaddr] = 0
                    lorawan.create(MHDR.UNCONF_DATA_DOWN, {'devaddr':devaddr, 'fcnt':self.FCntDown_dict[self.rx_devaddr],\
                        'fport':0,'data':self.AnsCommand_payload})
                else: # If received Mac Command is Answer, keep listen
                    self.set_mode(MODE.STDBY)
                    self.set_invert_iq(0)
                    self.set_invert_iq2(0)
                    self.reset_ptr_rx()
                    self.set_mode(MODE.RXCONT)
            
            #If Confirmed Uplink, send ACK (+ do MacCommand)
            elif lorawan.get_mhdr().get_mtype() == MHDR.CONF_DATA_UP:
                if self.rx_devaddr not in self.FCntDown_dict:
                    self.FCntDown_dict[self.rx_devaddr] = 0
                lorawan.create(MHDR.UNCONF_DATA_DOWN, {'devaddr':devaddr, 'fcnt':self.FCntDown_dict[self.rx_devaddr], 'ACK':True, 'data':list(map(ord, 'ACK'))})
                
                self.set_invert_iq(1)
                self.set_invert_iq2(1)
                self.write_payload(lorawan.to_raw())
                self.set_dio_mapping([1,0,0,0,0,0])
                sleep(0.1)
                self.set_mode(MODE.TX)

        print("--------------------------------------------\n")
    def on_tx_done(self):
        # Update FCntDown
        if self.rx_devaddr not in self.FCntDown_dict:
            self.FCntDown_dict[self.rx_devaddr] = 0
        self.FCntDown_dict[self.rx_devaddr] += 1
        
        # Set mode to RX
        self.set_mode(MODE.STDBY)
        self.clear_irq_flags(TxDone=1)
        print("======================================>TX_DONE!")
        self.set_dio_mapping([0]*6)
        self.set_invert_iq(0)
        self.set_invert_iq2(0)
        self.reset_ptr_rx()
        self.set_mode(MODE.RXCONT)

    def start(self):
        self.set_invert_iq(0)
        self.set_invert_iq2(0)
        self.reset_ptr_rx()
        self.set_mode(MODE.RXCONT)
        while True:
            sleep(.1)
            
            sys.stdout.flush()
            
def Init_client(cname):
    # callback assignment
    client = mqtt.Client(cname, False) #do not use clean session
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.on_publish = on_publish
    client.on_subscribe = on_subscribe
    client.on_unsubscribe = on_unsubscribe
    client.topic_ack = []
    client.run_flag = False
    client.running_loop = False
    client.subscribe_flag = False
    client.bad_connection_flag = False
    client.connected_flag = False
    client.disconnect_flag = False
    return client

def on_message(client, userdata, message):
    print("[MQTT] Received message: ",str(message.payload.decode("utf-8")),\
            "| topic: ",message.topic," | retained: ",message.retain)
    if message.retain == 1:
        print("[MQTT] This is a retained message..")

def on_publish(client, userdata, result):
    print("[MQTT] Data Published via MQTT..")
    pass

def on_subscribe(client, userdata, mid, granted_qos):
    if mid != 0:
        print("[MQTT] Subscribe Failed..")
def on_unsubscribe(client, userdata, mid):
    print("[MQTT] Successfully unsubscribed..")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.connected_flag=True
        print("[MQTT] Successfully connected..[Returned Code="+str(rc)+"]")
    else:
        print("[MQTT] Bad connection..[Returned Code="+str(rc)+"]")
        client.bad_connection_flag=True

def on_disconnect(client, userdata, rc):
    client.disconnect()
    print("[MQTT] Client disconnected..")
    logging.info("[MQTT] Disconnecting reason: "+str(rc))
    client.connected_flag=False
    client.disconnect_flag=True

# Init
appnonce = [randrange(256), randrange(256), randrange(256)]
netid = [0x00,0x00,0x01] #Type=0, NetID=1
#devaddr = [0x26, 0x01, 0x11, 0x5F]
dlsettings = [0x00]
rxdelay = [0x00]
cflist = []

appkey = [0x15, 0xF6, 0xF4, 0xD4, 0x2A, 0x95, 0xB0, 0x97, 0x53, 0x27, 0xB7, 0xC1, 0x45, 0x6E, 0xC5, 0x45]
nwskey = [0xC3, 0x24, 0x64, 0x98, 0xDE, 0x56, 0x5D, 0x8C, 0x55, 0x88, 0x7C, 0x05, 0x86, 0xF9, 0x82, 0x26]
appskey = [0x15, 0xF6, 0xF4, 0xD4, 0x2A, 0x95, 0xB0, 0x97, 0x53, 0x27, 0xB7, 0xC1, 0x45, 0x6E, 0xC5, 0x45]
#nwskey = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
#appskey = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]




mqttclient = Init_client("lora-GW-" + str(getmac.get_mac_address()))
mqttclient.connect(args.b, args.p)
mqttclient.loop_start()
print("[MQTT] Connecting to broker ", args.b)

lora = LoRaWANrcv(verbose=False)
lora.set_mode(MODE.STDBY)
lora.set_dio_mapping([0] * 6)
lora.set_freq(Channel.get_freq('EU433', 0)) # Set freq: EU433 channel 0
lora.set_pa_config(pa_select=1, max_power=0x0F, output_power=0x0E)
lora.set_spreading_factor(8)
lora.set_sync_word(0x34)
lorawan = LoRaWAN.new(nwskey, appkey)

lora.set_rx_crc(True)
print(lora)
assert(lora.get_agc_auto_on() == 1)
try:
    print("[LoRaWAN] Waiting for incoming LoRaWAN messages\n")
    lora.start()
except KeyboardInterrupt:
    sys.stdout.flush()
    print("\nKeyboardInterrupt")
finally:
    sys.stdout.flush()
    lora.set_mode(MODE.SLEEP)
    BOARD.teardown()
