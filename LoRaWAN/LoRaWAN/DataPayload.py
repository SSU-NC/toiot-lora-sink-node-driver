#
# frm_payload: data(0..N)
#
from .AES_CMAC import AES_CMAC
from Crypto.Cipher import AES
import math

class DataPayload:

    def read(self, mac_payload, payload):
        self.mac_payload = mac_payload
        self.payload = payload

    def create(self, mac_payload, key, args):
        self.mac_payload = mac_payload
        self.set_payload(key, 0x00, args['data'])

    def length(self):
        return len(self.payload)

    def to_raw(self):
        return self.payload

    def set_payload(self, key, direction, data):
        self.payload = self.encrypt_payload(key, direction, data)

    def compute_mic(self, key, direction, mhdr):
        mic = [0x49]
        mic += [0x00, 0x00, 0x00, 0x00]
        mic += [direction]
        print(self.mac_payload.get_fhdr().get_devaddr())
        mic += self.mac_payload.get_fhdr().get_devaddr()
        #print(self.mac_payload.get_fhdr().get_fcnt())
        mic += self.mac_payload.get_fhdr().get_fcnt()
        #Frame Counter upper bytes
        mic += [0x00]
        mic += [0x00]
        
        mic += [0x00]
        mic += [1+self.mac_payload.length()] #len(MHDR|FHDR|FPort|FRMPayload)

        #Add data to it
        #print(format(mhdr.to_raw(), '08b'))
        mic += [mhdr.to_raw()]  #add mhdr
        print("mac_payload: "+str(self.mac_payload.to_raw()))
        mic += self.mac_payload.to_raw() #
        print("before compute MIC: " + str(mic))

        cmac = AES_CMAC()
        print(list(map(int, cmac.encode(bytes(key), bytes(mic))[:])))
        computed_mic = cmac.encode(bytes(key), bytes(mic))[:4]

        print("computed MIC: " + str(list(map(int, computed_mic))))
        return list(map(int, computed_mic))

    def decrypt_payload(self, key, direction, mic):
        k = int(math.ceil(len(self.payload) / 16.0))

        a = []
        for i in range(k):
            a += [0x01]
            a += [0x00, 0x00, 0x00, 0x00]
            a += [direction]
            a += self.mac_payload.get_fhdr().get_devaddr()
            a += self.mac_payload.get_fhdr().get_fcnt()
            a += [0x00] # fcnt 32bit
            a += [0x00] # fcnt 32bit
            a += [0x00]
            a += [i+1]

        cipher = AES.new(bytes(key), AES.MODE_ECB)
        s = cipher.encrypt(bytes(a))

        padded_payload = []
        for i in range(k):
            idx = (i + 1) * 16
            padded_payload += (self.payload[idx - 16:idx] + ([0x00] * 16))[:16]

        payload = []
        for i in range(len(self.payload)):
            payload += [s[i] ^ padded_payload[i]]
        return list(map(int, payload))

    def encrypt_payload(self, key, direction, data):
        k = int(math.ceil(len(data) / 16.0))

        a = []
        for i in range(k):
            a += [0x01]
            a += [0x00, 0x00, 0x00, 0x00]
            a += [direction]
            a += self.mac_payload.get_fhdr().get_devaddr()
            a += self.mac_payload.get_fhdr().get_fcnt()
            a += [0x00] # fcnt 32bit
            a += [0x00] # fcnt 32bit
            a += [0x00]
            a += [i+1]

        cipher = AES.new(bytes(key), AES.MODE_ECB)
        s = cipher.encrypt(bytes(a))

        padded_payload = []
        for i in range(k):
            idx = (i + 1) * 16
            padded_payload += (data[idx - 16:idx] + ([0x00] * 16))[:16]

        payload = []
        for i in range(len(data)):
            payload += [s[i] ^ padded_payload[i]]
        return list(map(int, payload))
