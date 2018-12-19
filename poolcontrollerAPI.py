import sys
import asyncio

import aiohttp
import async_timeout

CONNECTION_TIMEOUT = 10  # seconds

class PoolControllerPlatform:
    """ Main PoolController object """
    def __init__(self, ip, port, useSecure=False, username=None, password=None):
        self.ip = ip
        self.port = port
        self.useSecure = useSecure
        self.address = None
        self.gen_addr()

        self.username = username
        self.password = password
        self.headers = None
        self.gen_headers()

        self.switches = []
        self.thermostats = []
        self.lights = []
 
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
        addr = http + '://' + self.ip + ':' + self.port + '/'
        self.address = addr

    async def request(self, path):
        try:
            async with aiohttp.ClientSession() as websession:
                loop = asyncio.get_event_loop()
                with async_timeout.timeout(CONNECTION_TIMEOUT, loop=loop):
                    response = await websession.get(self.address + path, headers=self.headers)
                    json = await response.json()
                    return json
        except Exception:
            return None

    async def refresh_circuits(self):
        self.switches = []
        self.thermostats = []
        self.lights = []

        temps_json = await self.request('temp')
        temps_json = temps_json['temperature']

        rjson = await self.request('circuit')

        for key, circuit in rjson['circuit'].items():
            number          = str(circuit['number'])
            circuitFunction = circuit['circuitFunction'].lower()

            if circuitFunction == 'generic':
                self.switches.append( Circuit(number, circuitFunction, self.request) )

            elif circuitFunction == 'intellibrite':
                # TODO: add support for light mode changing once poolcontroller #106 is fixed 
                self.lights.append( Circuit(number, circuitFunction, self.request) )

            elif circuitFunction == 'spa' or circuitFunction == 'pool':           
                self.thermostats.append( Thermostat(number, circuitFunction, self.request) )




class Circuit(object):
    def __init__(self, number, circuitFunction, request):
        self.number = number
        self.circuitFunction = circuitFunction
        self.request = request
        
        self.name = None
        self.friendlyName = None
        self.state = None

    async def update(self):

        rjson = await self.request('circuit/' + self.number)

        self.name            = rjson['name']
        self.friendlyName    = rjson['friendlyName']
        self.state           = bool(rjson['status'])
        # print(rjson)
        # self.circuitFunction = rjson['circuitFunction'].lower()


    async def set_state(self, state):

        rjson = await self.request( 'circuit/' + self.number + '/set/' + str(state) )
        self.state = bool(rjson['value'])
        # _LOGGER.warning('set_state current: ' + str(self._state))
        # _LOGGER.warning('set_state response: ' + str(newState))
        # await asyncio.sleep(0.3)


                


class Thermostat(Circuit):

    heater_modes = {
        'OFF' : 0,
        'Heater': 1,
        'Solar Pref': 2,
        'Solar Only': 3
    }

    def __init__(self, number, circuitFunction, request):
        super().__init__(number, circuitFunction, request)

        self.current_temperature = None
        self.target_temperature  = None
        self.heater_mode         = None

    async def update(self):
        await super().update()

        temps_json = await self.request('temp')
        temps_json = temps_json['temperature']

        self.current_temperature = temps_json[self.circuitFunction + 'Temp']
        self.target_temperature  = temps_json[self.circuitFunction + 'SetPoint']
        self.heater_mode         = temps_json[self.circuitFunction + 'HeatModeStr']


    async def set_target_temperature(self, target_temperature):
        rjson = await self.request( self.circuitFunction + "heat/setpoint/" + str(target_temperature) )
        new_target = rjson['value']
        self.target_temperature = new_target

    async def set_heater_mode(self, target_mode):
        desired_mode = Thermostat.heater_modes[target_mode]
        await self.request( self.circuitFunction + 'heat/mode/' + str(desired_mode) )
        self.heater_mode = target_mode

# if __name__ == "__main__":
#     platform = PoolControllerPlatform('10.0.1.6', '3000')

#     loop = asyncio.get_event_loop()
#     loop.run_until_complete( platform.refresh_circuits() )


