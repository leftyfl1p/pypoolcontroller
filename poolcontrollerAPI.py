import sys
import asyncio

import aiohttp
import async_timeout

import datetime

# CONNECTION_TIMEOUT = 5  # seconds

class PoolControllerPlatform:
    """ Main PoolController object """
    def __init__(self, ip, scan_interval=10, connection_timeout=10, useSecure=False, username=None, password=None):
        self.ip = ip
        self.useSecure = useSecure
        self.address = None
        self.gen_addr()

        self.scan_interval = scan_interval
        self.connection_timeout = connection_timeout
        self.skip_update_wait = False
        self.next_update = None

        self.username = username
        self.password = password
        self.headers = None
        self.gen_headers()

        self.switches = []
        self.thermostats = []
        self.lights = []

        self.update_lock = asyncio.Lock()
 
        # loop = asyncio.get_event_loop()
        # loop.run_until_complete( self.init_circuits() )  
        # self.init_circuits()

    def gen_headers(self):
        # not entirely sure how no-password logins work
        if self.username or self.password:
            b64d = self.username + ':' + self.password
            import base64
            b64e = base64.b64encode(b64d)
            self.headers = {'Authorization': 'Basic ' + b64e}
            

    def gen_addr(self):
        http = 'https' if self.useSecure else 'http'
        addr = http + '://' + self.ip + '/'
        self.address = addr

    async def request(self, path):
        try:
            async with aiohttp.ClientSession() as websession:
                loop = asyncio.get_event_loop()
                with async_timeout.timeout(self.connection_timeout, loop=loop):
                    # print('POOLCONTROLLER API REQUEST: ' + path)
                    response = await websession.get(self.address + path, headers=self.headers)
                    json = await response.json()
                    return json
        except Exception:
            return None

    async def set_skip_update_wait(self, skip=True):
        self.skip_update_wait = skip
        # print('UPDATE WAIT WAS SKIPPED!!!!!!!!!!!!!!!!!!!!')

    async def refresh_circuits(self):
        self.switches = []
        self.thermostats = []
        self.lights = []
        self.all_circuits = []

        temps_json = await self.request('temp')
        temps_json = temps_json['temperature']

        data = await self.request('circuit')

        for number, circuit in data['circuit'].items():
            circuit_function = circuit['circuitFunction'].lower()
            cdata = circuit
            
            if circuit_function == 'generic':
                real_circuit = Circuit(str(number), circuit_function, self.update_data, self.request, self.set_skip_update_wait)
                self.switches.append(real_circuit)
                real_circuit.data = cdata
                self.all_circuits.append(real_circuit)

            elif circuit_function == 'intellibrite':
                # TODO: add support for light mode changing once poolcontroller #106 is fixed
                real_circuit = Circuit(str(number), circuit_function, self.update_data, self.request, self.set_skip_update_wait)
                self.lights.append(real_circuit)
                real_circuit.data = cdata
                self.all_circuits.append(real_circuit)

            elif circuit_function == 'spa' or circuit_function == 'pool':
                real_circuit = Thermostat(str(number), circuit_function, self.update_data, self.request, self.set_skip_update_wait)
                cdata['temperature'] = temps_json
                real_circuit.data = cdata
                self.thermostats.append(real_circuit)
                self.all_circuits.append(real_circuit)

        self.next_update = datetime.datetime.now() + datetime.timedelta(seconds=self.scan_interval)


    async def update_data(self):
        if self.update_lock.locked():
            return
        
        async with self.update_lock:
            if self.next_update > datetime.datetime.now():
                if not self.skip_update_wait:
                    return

            self.skip_update_wait = False

            temps_json = await self.request('temp')
            temps_json = temps_json['temperature']

            data = await self.request('circuit')

            for circuit in self.all_circuits:
                numberf = circuit.number
                cdata = data['circuit'][numberf]

                if circuit.circuit_function == 'spa' or circuit.circuit_function == 'pool':
                    cdata['temperature'] = temps_json
                
                circuit.data = cdata
            self.next_update = datetime.datetime.now() + datetime.timedelta(seconds=self.scan_interval)





class Circuit(object):
    def __init__(self, number, circuit_function, update_data, request, set_skip_update_wait):
        self.number = number
        self.update_data = update_data
        self.data = {}
        self.request = request
        self.set_skip_update_wait = set_skip_update_wait
        
        self.name = None
        self.friendlyName = None
        self.state = None
        self.circuit_function = circuit_function

    async def update(self):
        await self.update_data()

        self.name            = self.data['name']
        self.friendlyName    = self.data['friendlyName']
        self.state           = bool(self.data['status'])

    async def set_state(self, state):
        rjson = await self.request( 'circuit/' + self.number + '/set/' + str(state) )
        self.state = bool(rjson['value'])
        await self.set_skip_update_wait()



                


class Thermostat(Circuit):

    heater_modes = {
        'OFF' : 0,
        'Heater': 1,
        'Solar Pref': 2,
        'Solar Only': 3
    }

    def __init__(self, number, circuit_function, update_data, request, set_skip_update_wait):
        super().__init__(number, circuit_function, update_data, request, set_skip_update_wait)

        self.current_temperature = None
        self.target_temperature  = None
        self.heater_mode         = None

    async def update(self):
        await super().update()

        temps = self.data['temperature']        

        self.current_temperature = temps[self.circuit_function + 'Temp']
        self.target_temperature  = temps[self.circuit_function + 'SetPoint']
        self.heater_mode         = temps[self.circuit_function + 'HeatModeStr']

    async def set_target_temperature(self, target_temperature):
        rjson = await self.request( self.circuit_function + "heat/setpoint/" + str(target_temperature) )
        new_target = rjson['value']
        self.target_temperature = new_target
        await self.set_skip_update_wait()

    async def set_heater_mode(self, target_mode):
        desired_mode = Thermostat.heater_modes[target_mode]
        await self.request( self.circuit_function + 'heat/mode/' + str(desired_mode) )
        self.heater_mode = target_mode
        await self.set_skip_update_wait()

# if __name__ == "__main__":
#     platform = PoolControllerPlatform('10.0.1.6:3000')

#     loop = asyncio.get_event_loop()
#     loop.run_until_complete( platform.refresh_circuits() )


