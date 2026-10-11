# -*- coding: utf-8 -*-
"""Testy publikacji nastaw z /boiler/config (clamp_value, save_to_broker).

    python tests/test_boiler_config.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb import heating_params, mqttclient
from caveweb.pages.boiler_config import BoilerConfigPage, clamp_value

INT_META = heating_params.SETPOINTS['furnace_temp_setpoint']  # int, 52..72
FLOAT_META = heating_params.SETPOINTS['inside_temp_setpoint']  # float, 15.0..28.0
BOOL_META = heating_params.SETPOINTS['furnace_enable_setpoint']  # bool

# --- clamp_value: typ i zakres z metadanych, nie kosmetyka --------------------

check("bool przechodzi bez zmian typu", clamp_value(BOOL_META, True) is True)
check("bool z liczby (0/1 z pola) też", clamp_value(BOOL_META, 0) is False)

check("int w zakresie zostaje bez zmian", clamp_value(INT_META, 60) == 60)
check("int ponad max przycięty do max (72)", clamp_value(INT_META, 999) == 72)
check("int poniżej min przycięty do min (52)", clamp_value(INT_META, 0) == 52)
check("int zaokrąglony do liczby całkowitej", clamp_value(INT_META, 60.6) == 61)
check("wynik int to naprawdę int, nie float", isinstance(clamp_value(INT_META, 60), int))

check("float w zakresie zostaje bez zmian", clamp_value(FLOAT_META, 21.3) == 21.3)
check("float ponad max przycięty (28.0)", clamp_value(FLOAT_META, 99.0) == 28.0)
check("float poniżej min przycięty (15.0)", clamp_value(FLOAT_META, -5.0) == 15.0)


# --- save_to_broker: publikuje każde pole, przycięte, pomija puste ------------

class FakeClient:
    def __init__(self):
        self.calls = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.calls.append((topic, json.loads(payload), qos, retain))
        return self


class FakeClientFail(FakeClient):
    rc = 4


class FakeInput:
    def __init__(self, value):
        self.value = value


mqttclient._client = FakeClient()
page = BoilerConfigPage()
page.inputs = {name: FakeInput(meta['default']) for name, meta in heating_params.SETPOINTS.items()}
page.inputs['furnace_temp_setpoint'] = FakeInput(999)  # ma zostać przycięte do 72
page.save_to_broker()

calls_by_topic = {topic: payload for topic, payload, qos, retain in mqttclient._client.calls}
check("publikuje po jednym razie na nastawę",
      len(mqttclient._client.calls) == len(heating_params.SETPOINTS))
check("wartość spoza zakresu poszła przycięta, nie 999",
      calls_by_topic[INT_META['topic']] == {'value': 72})
check("qos=0, retained - jak każdy inny publish nastawy w caveweb",
      all(qos == 0 and retain is True for _, _, qos, retain in mqttclient._client.calls))

mqttclient._client = FakeClient()
page = BoilerConfigPage()
page.inputs = {name: FakeInput(meta['default']) for name, meta in heating_params.SETPOINTS.items()}
page.inputs['dhw_temp_setpoint'] = FakeInput(None)  # puste pole - pomijamy, nie wysyłamy None
page.save_to_broker()
check("puste pole pomijane, reszta i tak wysłana",
      len(mqttclient._client.calls) == len(heating_params.SETPOINTS) - 1)

mqttclient._client = FakeClientFail()
page = BoilerConfigPage()
page.inputs = {name: FakeInput(meta['default']) for name, meta in heating_params.SETPOINTS.items()}
page.save_to_broker()  # nie powinno rzucić, mimo samych błędów publikacji

done()
