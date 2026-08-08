import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import climate
from esphome.const import CONF_ID

from esphome.components.rovsun_a5 import (
    RovsunClimate,
    CLIMATE_SCHEMA,
    CONF_ROVSUN_A5_ID,
)

CONFIG_SCHEMA = CLIMATE_SCHEMA


async def to_code(config):
    var = await climate.new_climate(config)
    parent = await cg.get_variable(config[CONF_ROVSUN_A5_ID])
    cg.add(var.set_parent(parent))
    cg.add(parent.set_climate(var))
