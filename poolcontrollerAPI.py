import sys
import asyncio

import aiohttp
import async_timeout

import datetime

class PoolControllerPlatform:
    """ Main PoolController object """
    def __init__(self, address, username='', password='', connection_timeout=10):
        self.address = address
        if not self.address.endswith('/'):
            self.address += '/'
        
        self.connection_timeout = connection_timeout
        self.username = username
        self.password = password
        self.headers = None
        self.gen_headers()

        self.switches = []
        self.heaters = []
        self.lights = []

        self.update_lock = asyncio.Lock()

    def gen_headers(self):
        # not entirely sure how no-password logins work
        if len(self.username) > 0 or len(self.password) > 0:
            b64d = self.username + ':' + self.password
            import base64
            b64e = base64.b64encode(b64d)
            self.headers = {'Authorization': 'Basic ' + b64e}

    async def request(self, path):
        try:
            async with aiohttp.ClientSession() as websession:
                loop = asyncio.get_event_loop()
                with async_timeout.timeout(self.connection_timeout, loop=loop):
                    print('POOLCONTROLLER API REQUEST: ' + path)
                    response = await websession.get(self.address + path, headers=self.headers)
                    json = await response.json()
                    return json
        except Exception:
            return None

    async def refresh_circuits(self):
        self.switches = []
        self.heaters = []
        self.lights = []
        self.all_circuits = []

        temps_json = await self.request('temp')
        temps_json = temps_json['temperature']

        data = await self.request('circuit')

        for number, circuit_data in data['circuit'].items():
            circuit_function = circuit_data['circuitFunction'].lower()
            
            if circuit_function == 'generic':
                real_circuit = Circuit(str(number), circuit_function, self.request)
                self.switches.append(real_circuit)
                real_circuit.data = circuit_data
                self.all_circuits.append(real_circuit)

            elif circuit_function == 'intellibrite':
                # TODO: add support for light mode changing once poolcontroller #106 is fixed
                real_circuit = Intellibrite(str(number), circuit_function, self.request)
                self.lights.append(real_circuit)
                real_circuit.data = circuit_data
                self.all_circuits.append(real_circuit)

            elif circuit_function == 'spa' or circuit_function == 'pool':
                real_circuit = Heater(str(number), circuit_function, self.request)
                circuit_data['temperature'] = temps_json
                real_circuit.data = circuit_data
                self.heaters.append(real_circuit)
                self.all_circuits.append(real_circuit)

    async def update_data(self):
        print("PC API UPDATE_DATA")
        if self.update_lock.locked():
            print("update_data LOCKED")
            return
        
        async with self.update_lock:
            temps_json = await self.request('temp')
            temps_json = temps_json['temperature']

            data = await self.request('circuit')

            for circuit in self.all_circuits:
                numberf = circuit.number
                cdata = data['circuit'][numberf]

                if circuit.circuit_function == 'spa' or circuit.circuit_function == 'pool':
                    cdata['temperature'] = temps_json
                
                circuit.data = cdata

                # tell circuit to grab updated data from platform
                await circuit.update_from_platform()

# base circuit object that all devices inherit from
class Circuit(object):
    def __init__(self, number, circuit_function, request):
        self.number = number
        self.data = {}
        self.request = request
        
        self.name = None
        self.friendlyName = None
        self.state = None
        self.circuit_function = circuit_function

    async def update_from_platform(self):
        self.name            = self.data['name']
        self.friendlyName    = self.data['friendlyName']
        self.state           = bool(self.data['status'])

        print("circuit update " + self.name)

    async def set_state(self, state):
        rjson = await self.request( 'circuit/' + self.number + '/set/' + str(state) )
        self.state = bool(rjson['value'])

class Intellibrite(Circuit):

    intellibriteModes = {
        'Color Sync': 128,
        'Color Swim': 144,
        'Color Set': 160,
        'Party': 177,
        'Romance': 178,
        'Caribbean': 179,
        'American': 180,
        'Sunset': 181,
        'Royal': 182,
        'Save': 190,
        'Recall': 191,
        'Blue': 193,
        'Green': 194,
        'Red': 195,
        'White': 196,
        'Magenta': 197
}

    def __init__(self, number, circuit_function, request):
        super().__init__(number, circuit_function, request)

        self.current_effect = None

    async def update_from_platform(self):
        await super().update_from_platform()

        self.current_effect = self.data['light']['colorStr']

    async def set_effect(self, effect):
        mode = str(Intellibrite.intellibriteModes[effect])
        await self.request( 'light/mode/' + mode)

    def effect_list(self):
        return list(Intellibrite.intellibriteModes.keys())

class Heater(Circuit):

    operation_modes = {
        'OFF' : 0,
        'Heater': 1,
        'Solar Pref': 2,
        'Solar Only': 3,
        'Idle' : 4 # pump on with no heater
    }

    def __init__(self, number, circuit_function, request):
        super().__init__(number, circuit_function, request)

        self.current_temperature = None
        self.target_temperature  = None
        self.heater_mode         = None
        self.operation_mode      = None

    async def update_from_platform(self):
        await super().update_from_platform()

        temps = self.data['temperature']        

        self.current_temperature = temps[self.circuit_function + 'Temp']
        self.target_temperature  = temps[self.circuit_function + 'SetPoint']
        self.heater_mode         = temps[self.circuit_function + 'HeatModeStr']

        # update operation mode
        if self.state and self.heater_mode == 'OFF':
            self.operation_mode = 'Idle'
        else: self.operation_mode = self.heater_mode

    async def set_target_temperature(self, target_temperature):
        rjson = await self.request( self.circuit_function + "heat/setpoint/" + str(target_temperature) )
        new_target = rjson['value']
        self.target_temperature = new_target

    async def set_heater_mode(self, target_mode):
        desired_mode = Heater.operation_modes[target_mode]
        await self.request( self.circuit_function + 'heat/mode/' + str(desired_mode) )
        self.heater_mode = target_mode

    # set_operation_mode also updates the circuit on/off state
    async def set_operation_mode(self, target_operation):
        if target_operation == 'OFF':
            await self.set_heater_mode(target_operation)
            await self.set_state(0)
        else:
            if target_operation == 'Idle':
                await self.set_heater_mode('OFF')
            else:
                await self.set_heater_mode(target_operation)
            await self.set_state(1)


# if __name__ == "__main__":
#     platform = PoolControllerPlatform('10.0.1.6:3000')

#     loop = asyncio.get_event_loop()
#     loop.run_until_complete( platform.refresh_circuits() )


