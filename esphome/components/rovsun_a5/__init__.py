import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, switch, select, number
from esphome.const import CONF_ID

DEPENDENCIES = ["uart"]
MULTI_CONF = False

CONF_UART = "uart_id"
CONF_POWER = "power"
CONF_BEEP = "beep"
CONF_FAN = "fan_mode"
CONF_VDIR = "vertical_direction"
CONF_MODE = "mode"
CONF_SETPOINT = "setpoint"

rovsun_a5_ns = cg.esphome_ns.namespace("rovsun_a5")
RovsunA5 = rovsun_a5_ns.class_("RovsunA5", cg.Component, uart.UARTDevice)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(RovsunA5),
        cv.Required(CONF_UART): cv.use_id(uart.UARTComponent),
        cv.Optional(CONF_POWER): cv.use_id(switch.Switch),
        cv.Optional(CONF_BEEP): cv.use_id(switch.Switch),
        cv.Optional(CONF_FAN): cv.use_id(select.Select),
        cv.Optional(CONF_VDIR): cv.use_id(select.Select),
        cv.Optional(CONF_MODE): cv.use_id(select.Select),
        cv.Optional(CONF_SETPOINT): cv.use_id(number.Number),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)
    if CONF_POWER in config:
        p = await cg.get_variable(config[CONF_POWER])
        cg.add(var.set_power_switch(p))
    if CONF_BEEP in config:
        p = await cg.get_variable(config[CONF_BEEP])
        cg.add(var.set_beep_switch(p))
    if CONF_FAN in config:
        p = await cg.get_variable(config[CONF_FAN])
        cg.add(var.set_fan_select(p))
    if CONF_VDIR in config:
        p = await cg.get_variable(config[CONF_VDIR])
        cg.add(var.set_vdir_select(p))
    if CONF_MODE in config:
        p = await cg.get_variable(config[CONF_MODE])
        cg.add(var.set_mode_select(p))
    if CONF_SETPOINT in config:
        p = await cg.get_variable(config[CONF_SETPOINT])
        cg.add(var.set_setpoint_number(p))
