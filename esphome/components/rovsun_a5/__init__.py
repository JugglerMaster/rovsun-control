import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, switch, select, number, sensor
from esphome.const import CONF_ID

DEPENDENCIES = ["uart"]
MULTI_CONF = False

CONF_UART = "uart_id"
CONF_POWER = "power"
CONF_BEEP = "beep"
CONF_LIGHT = "light"
CONF_DRYING = "drying"
CONF_SLEEP = "sleep"
CONF_ECO = "eco"
CONF_GENERATOR = "generator"
CONF_LRDIR = "left_right_direction"
CONF_VDIR = "vertical_direction"
CONF_FAN = "fan"
CONF_MODE = "mode"
CONF_SETPOINT = "setpoint"
CONF_CURRENT_TEMP = "current_temp"
CONF_POWER_SENSOR = "power_sensor"
CONF_DEBUG = "debug"
CONF_LOG_RAW = "log_raw"
CONF_RESTORE = "restore_on_power_on"

rovsun_a5_ns = cg.esphome_ns.namespace("rovsun_a5")
RovsunA5 = rovsun_a5_ns.class_("RovsunA5", cg.Component, uart.UARTDevice)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(RovsunA5),
        cv.Required(CONF_UART): cv.use_id(uart.UARTComponent),
        cv.Optional(CONF_POWER): cv.use_id(switch.Switch),
        cv.Optional(CONF_BEEP): cv.use_id(switch.Switch),
        cv.Optional(CONF_LIGHT): cv.use_id(switch.Switch),
        cv.Optional(CONF_DRYING): cv.use_id(switch.Switch),
        cv.Optional(CONF_SLEEP): cv.use_id(select.Select),
        cv.Optional(CONF_ECO): cv.use_id(select.Select),
        cv.Optional(CONF_GENERATOR): cv.use_id(select.Select),
        cv.Optional(CONF_LRDIR): cv.use_id(select.Select),
        cv.Optional(CONF_VDIR): cv.use_id(select.Select),
        cv.Optional(CONF_FAN): cv.use_id(select.Select),
        cv.Optional(CONF_MODE): cv.use_id(select.Select),
        cv.Optional(CONF_SETPOINT): cv.use_id(number.Number),
        cv.Optional(CONF_CURRENT_TEMP): cv.use_id(sensor.Sensor),
        cv.Optional(CONF_POWER_SENSOR): cv.use_id(sensor.Sensor),
        cv.Optional(CONF_DEBUG): cv.use_id(switch.Switch),
        cv.Optional(CONF_LOG_RAW, default=False): cv.boolean,
        cv.Optional(CONF_RESTORE, default=True): cv.boolean,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)
    cg.add(var.set_log_raw(config[CONF_LOG_RAW]))
    cg.add(var.set_restore_on_power_on(config[CONF_RESTORE]))
    if CONF_BEEP in config:
        p = await cg.get_variable(config[CONF_BEEP])
        cg.add(var.set_beep_switch(p))
    if CONF_POWER in config:
        p = await cg.get_variable(config[CONF_POWER])
        cg.add(var.set_power_switch(p))
    if CONF_LIGHT in config:
        p = await cg.get_variable(config[CONF_LIGHT])
        cg.add(var.set_light_switch(p))
    if CONF_DRYING in config:
        p = await cg.get_variable(config[CONF_DRYING])
        cg.add(var.set_drying_switch(p))
    if CONF_SLEEP in config:
        p = await cg.get_variable(config[CONF_SLEEP])
        cg.add(var.set_sleep_select(p))
    if CONF_ECO in config:
        p = await cg.get_variable(config[CONF_ECO])
        cg.add(var.set_eco_select(p))
    if CONF_GENERATOR in config:
        p = await cg.get_variable(config[CONF_GENERATOR])
        cg.add(var.set_generator_select(p))
    if CONF_LRDIR in config:
        p = await cg.get_variable(config[CONF_LRDIR])
        cg.add(var.set_lrdir_select(p))
    if CONF_VDIR in config:
        p = await cg.get_variable(config[CONF_VDIR])
        cg.add(var.set_vdir_select(p))
    if CONF_FAN in config:
        p = await cg.get_variable(config[CONF_FAN])
        cg.add(var.set_fan_select(p))
    if CONF_MODE in config:
        p = await cg.get_variable(config[CONF_MODE])
        cg.add(var.set_mode_select(p))
    if CONF_SETPOINT in config:
        p = await cg.get_variable(config[CONF_SETPOINT])
        cg.add(var.set_setpoint_number(p))
    if CONF_CURRENT_TEMP in config:
        p = await cg.get_variable(config[CONF_CURRENT_TEMP])
        cg.add(var.set_current_temp_sensor(p))
    if CONF_POWER_SENSOR in config:
        p = await cg.get_variable(config[CONF_POWER_SENSOR])
        cg.add(var.set_power_sensor(p))
    if CONF_DEBUG in config:
        p = await cg.get_variable(config[CONF_DEBUG])
        cg.add(var.set_debug_switch(p))
