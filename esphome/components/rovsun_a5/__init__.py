import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, switch, select, number, climate
from esphome.const import CONF_ID

DEPENDENCIES = ["uart"]
MULTI_CONF = False

CONF_UART = "uart_id"
CONF_POWER = "power"
CONF_BEEP = "beep"
CONF_LIGHT = "light"
CONF_DRYING = "drying"
CONF_SLEEP = "sleep"
CONF_GENERATOR = "generator"
CONF_LRDIR = "left_right_direction"
CONF_VDIR = "vertical_direction"
CONF_LOG_RAW = "log_raw"
CONF_RESTORE = "restore_on_power_on"
CONF_ROVSUN_A5_ID = "rovsun_a5_id"

rovsun_a5_ns = cg.esphome_ns.namespace("rovsun_a5")
RovsunA5 = rovsun_a5_ns.class_("RovsunA5", cg.Component, uart.UARTDevice)
RovsunClimate = rovsun_a5_ns.class_("RovsunClimate", climate.Climate)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(RovsunA5),
        cv.Required(CONF_UART): cv.use_id(uart.UARTComponent),
        cv.Optional(CONF_POWER): cv.use_id(switch.Switch),
        cv.Optional(CONF_BEEP): cv.use_id(switch.Switch),
        cv.Optional(CONF_LIGHT): cv.use_id(switch.Switch),
        cv.Optional(CONF_DRYING): cv.use_id(switch.Switch),
        cv.Optional(CONF_SLEEP): cv.use_id(select.Select),
        cv.Optional(CONF_GENERATOR): cv.use_id(select.Select),
        cv.Optional(CONF_LRDIR): cv.use_id(select.Select),
    cv.Optional(CONF_VDIR): cv.use_id(select.Select),
        cv.Optional(CONF_LOG_RAW, default=False): cv.boolean,
        cv.Optional(CONF_RESTORE, default=True): cv.boolean,
    }
).extend(cv.COMPONENT_SCHEMA)

CLIMATE_SCHEMA = climate.climate_schema(RovsunClimate).extend(
    {cv.Required(CONF_ROVSUN_A5_ID): cv.use_id(RovsunA5)}
)


async def to_code(config):
    # The climate platform routes through the same module `to_code`. Detect it
    # by the presence of the parent reference and wire it to the controller.
    if CONF_ROVSUN_A5_ID in config:
        var = await climate.new_climate(config)
        await cg.register_component(var, config)
        parent = await cg.get_variable(config[CONF_ROVSUN_A5_ID])
        cg.add(var.set_parent(parent))
        cg.add(parent.set_climate(var))
        return

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
    if CONF_GENERATOR in config:
        p = await cg.get_variable(config[CONF_GENERATOR])
        cg.add(var.set_generator_select(p))
    if CONF_LRDIR in config:
        p = await cg.get_variable(config[CONF_LRDIR])
        cg.add(var.set_lrdir_select(p))
    if CONF_VDIR in config:
        p = await cg.get_variable(config[CONF_VDIR])
        cg.add(var.set_vdir_select(p))
