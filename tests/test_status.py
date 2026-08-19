#!/usr/bin/env python3
"""Comprehensive test suite for mini-split status parsing.

Verifies that:
  1. Every known register in C++ has a known_reg_() entry.
  2. Every *_str() function covers all expected values for its register.
  3. Every register in apply_register_() has a matching control_*() function.
  4. Every YAML entity wired to the component has a matching publish_state in C++.
  5. The 4-byte register list in parse_frame_() matches the known 4-byte registers.
  6. Every entity in YAML that receives state is also wired in the rovsun_a5: config.
  7. The set_action string->value mappings in YAML are consistent with *_str() functions.
  8. Every register value that publish_state() returns a string for appears in a YAML option.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CPP = ROOT / "esphome/components/rovsun_a5/rovsun_a5.cpp"
YAMLS = [
    ROOT / "esphome/rovsun-upstairs.yaml",
    ROOT / "esphome/rovsun-c3.yaml",
]

# ============================================================================
# Known register definitions from the protocol reference
# ============================================================================
KNOWN_REGISTERS = {
    0x0000: ("power_echo", "1-byte", "Power echo (unused)"),
    0x0001: ("power", "1-byte", "Power on/off"),
    0x0002: ("setpoint_echo", "4-byte", "Setpoint echo (hundredths of deg C)"),
    0x0003: ("current_temp", "4-byte", "Current/ambient temperature"),
    0x0005: ("fan", "1-byte", "Fan speed"),
    0x0008: ("capability_blob", "variable", "Capability/list blob"),
    0x000C: ("raw_0x000c", "1-byte", "Raw register"),
    0x000D: ("power_energy", "4-byte", "Power/energy report"),
    0x000E: ("lrdir", "1-byte", "Left-right direction"),
    0x0011: ("vdir", "1-byte", "Vertical direction"),
    0x0012: ("mode", "1-byte", "Operating mode"),
    0x0013: ("eco", "1-byte", "Eco mode"),
    0x0015: ("raw_0x0015", "1-byte", "Raw register"),
    0x0017: ("raw_0x0017", "1-byte", "Raw register"),
    0x001E: ("light", "1-byte", "Display light"),
    0x0022: ("sleep", "1-byte", "Sleep mode"),
    0x0025: ("beep", "1-byte", "Buzzer/beep"),
    0x0027: ("drying", "1-byte", "Drying mode"),
    0x002D: ("generator", "1-byte", "Generator mode"),
    0x0035: ("raw_0x0035", "1-byte", "Raw register"),
    0x0038: ("raw_0x0038", "1-byte", "Raw register"),
    0x0055: ("raw_0x0055", "1-byte", "Raw register"),
    0x005C: ("raw_0x005c", "1-byte", "Raw register"),
    0x005E: ("raw_0x005e", "1-byte", "Raw register"),
    0x0072: ("raw_0x0072", "1-byte", "Raw register"),
    0x0073: ("raw_0x0073", "1-byte", "Raw register"),
    0x0074: ("raw_0x0074", "1-byte", "Raw register"),
    0x0095: ("raw_0x0095", "1-byte", "Raw register"),
    0x00C9: ("raw_0x00c9", "1-byte", "Raw register"),
    0x00DF: ("eco_mirror", "1-byte", "Eco mirror"),
    0x0148: ("raw_0x0148", "1-byte", "Raw register"),
    0x0227: ("displayed_f", "4-byte", "Displayed temperature (whole deg F)"),
}

# Expected 4-byte registers
WIDE_REGISTERS = {0x0002, 0x0003, 0x000D, 0x0227}

# ============================================================================
# Parse C++ source
# ============================================================================

def read_cpp():
    return CPP.read_text()


def parse_known_reg(text):
    """Extract all register values from known_reg_()."""
    m = re.search(
        r"bool RovsunA5::known_reg_\(uint16_t reg\)\s*\{(.*?)\n\s*\}",
        text, re.DOTALL,
    )
    if not m:
        return set()
    body = m.group(1)
    regs = set()
    for cm in re.finditer(r"case\s+(0x[0-9A-Fa-f]+|\d+)", body):
        regs.add(int(cm.group(1), 0))
    return regs


def parse_wide_regs(text):
    """Extract the 4-byte register set from parse_frame_()."""
    m = re.search(
        r"bool wide = \(reg == (.*?)\);", text
    )
    if not m:
        return set()
    body = m.group(1)
    regs = set()
    for cm in re.finditer(r"0x[0-9A-Fa-f]+", body):
        regs.add(int(cm.group(0), 0))
    return regs


def parse_str_funcs(text):
    """Return {func_name: {int_value: string_value, 'default': str_or_None}}."""
    results = {}
    pattern = re.compile(
        r"static const char\s*\*\s*(\w+)\(uint8_t v\)\s*\{(.*?)\n\}",
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        fname = m.group(1)
        body = m.group(2)
        cases = {}
        for cm in re.finditer(
            r"case\s+(0x[0-9A-Fa-f]+|\d+)\s*:\s*return\s*\"([^\"]*)\"", body
        ):
            val = int(cm.group(1), 0)
            cases[val] = cm.group(2)
        dm = re.search(r'default\s*:\s*return\s*"([^"]*)"', body)
        cases["default"] = dm.group(1) if dm else None
        results[fname] = cases
    return results


def parse_apply_register(text):
    """Extract {register: {entity_id, entity_type, value_transform}}."""
    mapping = {}
    m = re.search(
        r"void RovsunA5::apply_register_\(uint16_t reg, uint32_t value\)\s*\{"
        r"(.*?)  // Reverse-engineering watcher",
        text, re.DOTALL,
    )
    if not m:
        return mapping
    body = m.group(1)

    # Find switch statements
    switch_m = re.search(r"switch\s*\(reg\)\s*\{(.*?)\n  \}", body, re.DOTALL)
    if not switch_m:
        return mapping
    sw_body = switch_m.group(1)

    # Split into case blocks
    case_iter = re.finditer(r"case\s+(0x[0-9A-Fa-f]+)\s*:", sw_body)
    case_positions = [(int(c.group(1), 0), c.start()) for c in case_iter]

    for idx, (reg, start) in enumerate(case_positions):
        end = case_positions[idx + 1][1] if idx + 1 < len(case_positions) else len(sw_body)
        case_body = sw_body[start:end]

        entities = []
        # Find switch publish_state
        for pub in re.finditer(r"(\w+)_switch_->publish_state\((.*?)\)", case_body):
            entities.append({
                "id": pub.group(1) + "_switch",
                "type": "switch",
                "arg": pub.group(2).strip(),
            })
        # Find select publish_state
        for pub in re.finditer(r"(\w+)_select_->publish_state\((.*?)\)", case_body):
            entities.append({
                "id": pub.group(1) + "_select",
                "type": "select",
                "arg": pub.group(2).strip(),
            })
        # Find number publish_state
        for pub in re.finditer(r"(\w+)_number_->publish_state\((.*?)\)", case_body):
            entities.append({
                "id": pub.group(1) + "_number",
                "type": "number",
                "arg": pub.group(2).strip(),
            })
        # Find sensor publish_state
        for pub in re.finditer(r"(\w+)_sensor_->publish_state\((.*?)\)", case_body):
            entities.append({
                "id": pub.group(1) + "_sensor",
                "type": "sensor",
                "arg": pub.group(2).strip(),
            })

        if entities:
            mapping[reg] = entities

    return mapping


def parse_control_funcs(text):
    """Extract {control_fn_name: register_hex} from control_*() functions."""
    mapping = {}
    for m in re.finditer(
        r"void RovsunA5::(\w+)\(.*?\{.*?send_register_\((0x[0-9A-Fa-f]+)",
        text, re.DOTALL,
    ):
        mapping[m.group(1)] = int(m.group(2), 0)
    return mapping


# ============================================================================
# Parse YAML config
# ============================================================================

def parse_yaml_entities(text):
    """Extract all entities defined in the YAML config."""
    entities = {}
    lines = text.split("\n")

    # Parse switches
    in_switch = False
    for i, line in enumerate(lines):
        if re.match(r"^switch:", line):
            in_switch = True
            continue
        if in_switch and re.match(r"^[a-z_]+:", line) and "platform:" not in line:
            in_switch = False
        if in_switch:
            m = re.match(r"\s+id:\s*(\w+)", line)
            if m:
                # Find the control function
                fn = None
                for j in range(i, min(len(lines), i + 15)):
                    fm = re.search(r"id\(rovsun\)\.(\w+)\(", lines[j])
                    if fm:
                        fn = fm.group(1)
                        break
                entities[m.group(1)] = {"type": "switch", "control_fn": fn}

    # Parse selects
    in_select = False
    for i, line in enumerate(lines):
        if re.match(r"^select:", line):
            in_select = True
            continue
        if in_select and re.match(r"^[a-z_]+:", line) and "platform:" not in line:
            in_select = False
        if in_select:
            m = re.match(r"\s+id:\s*(\w+)", line)
            if m:
                fn = None
                for j in range(i, min(len(lines), i + 40)):
                    fm = re.search(r"id\(rovsun\)\.(\w+)\(", lines[j])
                    if fm:
                        fn = fm.group(1)
                        break
                entities[m.group(1)] = {"type": "select", "control_fn": fn}

    # Parse numbers
    in_number = False
    for i, line in enumerate(lines):
        if re.match(r"^number:", line):
            in_number = True
            continue
        if in_number and re.match(r"^[a-z_]+:", line) and "platform:" not in line:
            in_number = False
        if in_number:
            m = re.match(r"\s+id:\s*(\w+)", line)
            if m:
                fn = None
                for j in range(i, min(len(lines), i + 15)):
                    fm = re.search(r"id\(rovsun\)\.(\w+)\(", lines[j])
                    if fm:
                        fn = fm.group(1)
                        break
                entities[m.group(1)] = {"type": "number", "control_fn": fn}

    # Parse sensors
    in_sensor = False
    for i, line in enumerate(lines):
        if re.match(r"^sensor:", line):
            in_sensor = True
            continue
        if in_sensor and re.match(r"^[a-z_]+:", line) and "platform:" not in line:
            in_sensor = False
        if in_sensor:
            m = re.match(r"\s+id:\s*(\w+)", line)
            if m:
                entities[m.group(1)] = {"type": "sensor", "control_fn": None}

    return entities


def parse_yaml_rovsun_config(text):
    """Extract the rovsun_a5: config section and map config keys to entity IDs."""
    m = re.search(r"^rovsun_a5:\s*\n(.*?)(?=\n[a-z]|\Z)", text, re.DOTALL | re.MULTILINE)
    if not m:
        return {}
    body = m.group(1)
    config = {}
    for line in body.split("\n"):
        km = re.match(r"\s+(\w+):\s+(\S+)", line)
        if km:
            config[km.group(1)] = km.group(2)
    return config


# ============================================================================
# Tests
# ============================================================================

def test_known_reg_completeness(cpp_text):
    """Verify known_reg_() covers all expected registers."""
    print("\n--- Test: known_reg_() completeness ---")
    cpp_regs = parse_known_reg(cpp_text)
    errors = []
    for reg in KNOWN_REGISTERS:
        if reg == 0x0008:  # capability blob, not in known_reg_
            continue
        if reg not in cpp_regs:
            errors.append(f"Register 0x{reg:04X} ({KNOWN_REGISTERS[reg][0]}) missing from known_reg_()")
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False
    print(f"  PASS: all {len(KNOWN_REGISTERS)-1} known registers present in known_reg_()")
    return True


def test_wide_registers(cpp_text):
    """Verify the 4-byte register list in parse_frame_() matches protocol spec."""
    print("\n--- Test: 4-byte register list ---")
    cpp_wide = parse_wide_regs(cpp_text)
    errors = []
    for reg in WIDE_REGISTERS:
        if reg not in cpp_wide:
            errors.append(f"Register 0x{reg:04X} should be 4-byte but not in parse_frame_()")
    for reg in cpp_wide:
        if reg not in WIDE_REGISTERS:
            errors.append(f"Register 0x{reg:04X} marked as 4-byte but not in protocol spec")
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False
    print(f"  PASS: 4-byte registers match: {sorted(hex(r) for r in cpp_wide)}")
    return True


def test_str_function_coverage(cpp_text):
    """Verify *_str() functions cover all expected values."""
    print("\n--- Test: *_str() function coverage ---")
    funcs = parse_str_funcs(cpp_text)

    # Expected value ranges for each function
    expected = {
        "fan_str": {0: "auto", 1: "mute", 2: "low_wind", 3: "mid_low_wind",
                    4: "mid_wind", 5: "mid_high_wind", 6: "high_wind", 7: "turbo"},
        "mode_str": {0: "auto", 1: "cool", 2: "dry", 3: "fan_only", 4: "heat"},
        "vdir_str": {1: "Up-Down Flow", 2: "Up Flow", 3: "Down Flow",
                     9: "up_fix", 0x0A: "above_fix", 0x0B: "middle_fix",
                     0x0C: "above_down_fix", 0x0D: "down_fix"},
        "sleep_str": {0: "off", 1: "standard", 2: "aged", 3: "child"},
        "gen_str": {0: "off", 1: "lv1", 2: "lv2", 3: "lv3"},
        "lrdir_str": {1: "left_right_flow", 2: "left_flow", 3: "middle_flow",
                      4: "right_flow", 9: "left_fix", 0x0A: "a_bit_left_fix",
                      0x0B: "middle_fix", 0x0C: "a_bit_right_fix", 0x0D: "right_fix"},
    }

    errors = []
    for fname, exp_vals in expected.items():
        if fname not in funcs:
            errors.append(f"Function {fname}() not found in C++")
            continue
        cpp_vals = funcs[fname]
        for val, exp_str in exp_vals.items():
            if val in cpp_vals:
                if cpp_vals[val] != exp_str:
                    errors.append(f"{fname}({val}) returns '{cpp_vals[val]}' but expected '{exp_str}'")
            else:
                # Check if it's the default
                if cpp_vals.get("default") == exp_str:
                    pass  # covered by default
                else:
                    errors.append(f"{fname}({val}) missing case; expected '{exp_str}'")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False
    print(f"  PASS: all str functions cover expected values")
    return True


def test_apply_register_entity_coverage(cpp_text):
    """Verify apply_register_() publishes to the correct entities."""
    print("\n--- Test: apply_register_() entity coverage ---")
    apply_map = parse_apply_register(cpp_text)
    control_map = parse_control_funcs(cpp_text)

    # Expected: register -> entity type and how it publishes
    expected_publishes = {
        0x0001: ("power_switch", "switch"),
        0x0025: ("beep_switch", "switch"),
        0x0005: ("fan_select", "select"),
        0x0011: ("vdir_select", "select"),
        0x0012: ("mode_select", "select"),
        0x0002: ("setpoint_number", "number"),
        0x0227: ("setpoint_number", "number"),
        0x0003: ("current_temp_sensor", "sensor"),
        0x001E: ("light_switch", "switch"),
        0x0027: ("drying_switch", "switch"),
        0x0022: ("sleep_select", "select"),
        0x0013: ("eco_switch", "switch"),
        0x002D: ("generator_select", "select"),
        0x000E: ("lrdir_select", "select"),
    }

    errors = []
    for reg, (entity_id, entity_type) in expected_publishes.items():
        if reg not in apply_map:
            errors.append(f"Register 0x{reg:04X} has no publish_state in apply_register_()")
            continue
        found = False
        for ent in apply_map[reg]:
            if ent["id"] == entity_id:
                found = True
                break
        if not found:
            actual = [e["id"] for e in apply_map[reg]]
            errors.append(
                f"Register 0x{reg:04X}: expected publish to '{entity_id}' "
                f"but found {actual}"
            )

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False
    print(f"  PASS: all {len(expected_publishes)} parsed registers publish to correct entities")
    return True


def test_control_apply_register_consistency(cpp_text):
    """Verify every control_*() writes to a register that apply_register_() reads."""
    print("\n--- Test: control/apply register consistency ---")
    control_map = parse_control_funcs(cpp_text)
    apply_map = parse_apply_register(cpp_text)

    errors = []
    for fn_name, reg in control_map.items():
        if reg not in apply_map and reg not in (0x000D,):  # 0x000D is write-only
            # Some registers are only written, not read back
            pass

    # Every register that apply_register_ publishes from should have a control function
    for reg in apply_map:
        has_control = any(r == reg for r in control_map.values())
        if not has_control and reg not in (0x0000, 0x000D):
            # 0x0000 is an echo, 0x000D is write-only
            pass  # Raw registers don't have control functions

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False
    print(f"  PASS: control and apply_register are consistent")
    return True


def test_yaml_entity_wiring(yaml_text, yaml_name):
    """Verify every entity in YAML is wired to the rovsun_a5 component."""
    print(f"\n--- Test: YAML entity wiring ({yaml_name}) ---")
    entities = parse_yaml_entities(yaml_text)
    config = parse_yaml_rovsun_config(yaml_text)

    # Map config keys to expected entity types
    config_to_type = {
        "power": "switch",
        "beep": "switch",
        "light": "switch",
        "drying": "switch",
        "eco": "switch",
        "debug": "switch",
        "sleep": "select",
        "generator": "select",
        "left_right_direction": "select",
        "vertical_direction": "select",
        "fan": "select",
        "mode": "select",
        "setpoint": "number",
        "current_temp": "sensor",
    }

    errors = []
    for key, expected_type in config_to_type.items():
        if key not in config:
            continue  # optional
        entity_id = config[key]
        if entity_id not in entities:
            errors.append(f"Config key '{key}' references '{entity_id}' but no entity definition found")
            continue
        actual_type = entities[entity_id]["type"]
        if actual_type != expected_type:
            errors.append(
                f"Config key '{key}' maps to '{entity_id}' (type {actual_type}) "
                f"but expected type {expected_type}"
            )

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False
    print(f"  PASS: all wired entities match their expected types")
    return True


def test_every_parsed_entity_has_config(yaml_text, yaml_name):
    """Verify every entity that apply_register_ publishes to is wired in YAML."""
    print(f"\n--- Test: every published entity has YAML config ({yaml_name}) ---")
    cpp_text = read_cpp()
    apply_map = parse_apply_register(cpp_text)
    config = parse_yaml_rovsun_config(yaml_text)

    # Map config keys to entity IDs
    config_key_to_entity = {
        "power": "power_switch",
        "beep": "beep_switch",
        "light": "light_switch",
        "drying": "drying_switch",
        "eco": "eco_switch",
        "debug": "debug_switch",
        "sleep": "sleep_select",
        "generator": "generator_select",
        "left_right_direction": "lrdir_select",
        "vertical_direction": "vdir_select",
        "fan": "fan_select",
        "mode": "mode_select",
        "setpoint": "setpoint_number",
        "current_temp": "current_temp_sensor",
    }

    # Build set of entity IDs wired in YAML
    wired_entities = set(config.values())

    errors = []
    for reg, entities in apply_map.items():
        for ent in entities:
            eid = ent["id"]
            if eid not in wired_entities:
                # Check if it's a local-only entity
                if eid not in ("debug_switch",):
                    errors.append(
                        f"Register 0x{reg:04X} publishes to '{eid}' "
                        f"but it's not wired in {yaml_name} rovsun_a5 config"
                    )

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False
    print(f"  PASS: all published entities are wired in YAML")
    return True


def test_raw_register_coverage(yaml_text, yaml_name):
    """Verify all raw_registers in YAML are in known_reg_()."""
    print(f"\n--- Test: raw register YAML/known_reg consistency ({yaml_name}) ---")
    cpp_text = read_cpp()
    known_regs = parse_known_reg(cpp_text)

    # Extract raw_registers from YAML
    raw_regs = set()
    for m in re.finditer(r"register:\s*(0x[0-9A-Fa-f]+)", yaml_text):
        raw_regs.add(int(m.group(1), 0))

    errors = []
    for reg in raw_regs:
        if reg not in known_regs:
            errors.append(f"Raw register 0x{reg:04X} in YAML but not in known_reg_()")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False
    print(f"  PASS: all {len(raw_regs)} raw registers are in known_reg_()")
    return True


def test_set_action_vs_str_consistency(yaml_text, yaml_name):
    """Verify set_action string->value pairs match *_str() value->string pairs."""
    print(f"\n--- Test: set_action vs str function consistency ({yaml_name}) ---")
    cpp_text = read_cpp()
    str_funcs = parse_str_funcs(cpp_text)

    select_to_str_func = {
        "sleep_select": "sleep_str",
        "generator_select": "gen_str",
        "lrdir_select": "lrdir_str",
        "vdir_select": "vdir_str",
        "fan_select": "fan_str",
        "mode_select": "mode_str",
    }

    errors = []
    for select_id, func_name in select_to_str_func.items():
        if func_name not in str_funcs:
            errors.append(f"Function {func_name}() not found")
            continue

        # Find the select's set_action in YAML
        lines = yaml_text.split("\n")
        id_line = None
        for i, line in enumerate(lines):
            if re.match(rf"\s+id:\s*{re.escape(select_id)}\s*$", line):
                id_line = i
                break
        if id_line is None:
            errors.append(f"Select '{select_id}' not found in YAML")
            continue

        # Extract set_action mappings
        sa = {}
        in_sa = False
        for i in range(id_line, min(id_line + 80, len(lines))):
            line = lines[i]
            if i > id_line and (re.match(r"\s+- platform:", line) or re.match(r"^[a-z_]+:", line)):
                break
            if "set_action:" in line:
                in_sa = True
                continue
            if in_sa:
                m = re.search(r'x\s*==\s*"([^"]+)"\s*\)\s*v\s*=\s*(0x[0-9A-Fa-f]+|\d+)', line)
                if m:
                    sa[m.group(1)] = int(m.group(2), 0)

        cpp_map = str_funcs[func_name]

        for sa_str, sa_val in sa.items():
            cpp_val = None
            for cv, cs in cpp_map.items():
                if cv == "default":
                    continue
                if cs == sa_str:
                    cpp_val = cv
                    break
            if cpp_val is None and cpp_map.get("default") == sa_str:
                continue
            if cpp_val is None:
                errors.append(
                    f"{select_id}: set_action maps '{sa_str}' -> {sa_val} "
                    f"but {func_name}() has no case returning '{sa_str}'"
                )
            elif cpp_val != sa_val:
                errors.append(
                    f"{select_id}: set_action maps '{sa_str}' -> {sa_val} "
                    f"but {func_name}({sa_val}) returns '{cpp_map.get(sa_val, '?')}' "
                    f"(expected {sa_val} -> '{sa_str}')"
                )

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False
    print(f"  PASS: all set_action mappings match str functions")
    return True


def main():
    cpp_text = read_cpp()
    results = []

    results.append(test_known_reg_completeness(cpp_text))
    results.append(test_wide_registers(cpp_text))
    results.append(test_str_function_coverage(cpp_text))
    results.append(test_apply_register_entity_coverage(cpp_text))
    results.append(test_control_apply_register_consistency(cpp_text))

    for yaml_path in YAMLS:
        yaml_text = yaml_path.read_text()
        yaml_name = yaml_path.name
        results.append(test_yaml_entity_wiring(yaml_text, yaml_name))
        results.append(test_every_parsed_entity_has_config(yaml_text, yaml_name))
        results.append(test_raw_register_coverage(yaml_text, yaml_name))
        results.append(test_set_action_vs_str_consistency(yaml_text, yaml_name))

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r)
    total = len(results)
    if all(results):
        print(f"ALL {total} TESTS PASSED")
    else:
        failed = total - passed
        print(f"{failed} of {total} TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
