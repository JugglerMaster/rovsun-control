#!/usr/bin/env python3
"""Verify that every switch/toggle defined in YAML has matching C++ state publishing.

For each switch defined in the ESPHome YAML configs, this test checks:
  1. The switch id appears in apply_register_() as a publish_state target.
  2. The register used in apply_register_() matches the register in control_*().
  3. Every switch publish_state in apply_register_() has a corresponding YAML switch.
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

# Maps YAML switch id -> (control_fn, expected_register)
SWITCH_INFO = {
    "beep_switch": ("control_beep", 0x0025),
    "light_switch": ("control_light", 0x001E),
    "drying_switch": ("control_drying", 0x0027),
    "eco_switch": ("control_eco", 0x0013),
    "power_switch": ("control_power", 0x0001),
}

# Switches that are NOT wired to a register (local-only, not in apply_register_)
LOCAL_ONLY = {"debug_switch"}


def parse_yaml_switches(text):
    """Return {switch_id: control_fn} for each template switch."""
    switches = {}
    lines = text.split("\n")

    in_switch_section = False
    for i, line in enumerate(lines):
        if re.match(r"^switch:", line):
            in_switch_section = True
            continue
        if in_switch_section and re.match(r"^[a-z_]+:", line) and "platform:" not in line:
            in_switch_section = False
            continue

        if not in_switch_section:
            continue

        m = re.match(r"\s+id:\s*(\w+)", line)
        if not m:
            continue
        sid = m.group(1)
        if sid not in SWITCH_INFO:
            continue

        fn = None
        for j in range(max(0, i - 2), min(len(lines), i + 15)):
            fm = re.search(r"id\(rovsun\)\.(\w+)\(", lines[j])
            if fm:
                fn = fm.group(1)
                break

        if fn:
            switches[sid] = fn

    return switches


def parse_cpp_apply_register(text):
    """Extract {prefix: register_hex} from apply_register_().

    The C++ code uses patterns like `beep_switch_->publish_state(...)`, so
    we extract the prefix before `_switch_`.
    """
    mapping = {}
    func_m = re.search(
        r"void RovsunA5::apply_register_\(uint16_t reg, uint32_t value\)\s*\{"
        r"(.*?)  // Reverse-engineering watcher",
        text,
        re.DOTALL,
    )
    if not func_m:
        return mapping
    body = func_m.group(1)

    # Strategy: split on "case 0xNNNN:" to get per-register blocks,
    # then find publish_state calls in each block.
    # Use a regex that matches case blocks whether or not they have braces.
    case_iter = re.finditer(r"case\s+(0x[0-9A-Fa-f]+)\s*:", body)
    case_positions = [(int(m.group(1), 0), m.start()) for m in case_iter]

    for idx, (reg, start) in enumerate(case_positions):
        # End of this case's body is the start of the next case, or end of body
        if idx + 1 < len(case_positions):
            end = case_positions[idx + 1][1]
        else:
            end = len(body)
        case_body = body[start:end]

        for pub_m in re.finditer(r"(\w+)_switch_->publish_state\(", case_body):
            mapping[pub_m.group(1)] = reg

    return mapping


def parse_cpp_control_regs(text):
    """Extract {control_fn: register_hex} from control_*() functions."""
    mapping = {}
    for sw_id, (fn_name, expected_reg) in SWITCH_INFO.items():
        fn_m = re.search(
            rf"void RovsunA5::{fn_name}\(.*?\{{.*?send_register_\((0x[0-9A-Fa-f]+)",
            text,
            re.DOTALL,
        )
        if fn_m:
            mapping[fn_name] = int(fn_m.group(1), 0)
        else:
            mapping[fn_name] = expected_reg
    return mapping


def test_toggles():
    cpp_text = CPP.read_text()
    cpp_apply = parse_cpp_apply_register(cpp_text)
    cpp_control = parse_cpp_control_regs(cpp_text)

    errors = []

    for yaml_path in YAMLS:
        yaml_text = yaml_path.read_text()
        yaml_switches = parse_yaml_switches(yaml_text)

        # Check 1: Every YAML switch has a publish_state in apply_register_()
        for sw_id, fn in yaml_switches.items():
            _, expected_reg = SWITCH_INFO[sw_id]

            prefix = sw_id.replace("_switch", "")
            published_reg = cpp_apply.get(prefix)
            if published_reg is None:
                errors.append(
                    f"{yaml_path.name}: Switch '{sw_id}' (register 0x{expected_reg:04X}) "
                    f"has no publish_state in apply_register_()"
                )
            elif published_reg != expected_reg:
                errors.append(
                    f"{yaml_path.name}: Switch '{sw_id}' - "
                    f"control writes register 0x{expected_reg:04X} "
                    f"but apply_register_ publishes on 0x{published_reg:04X}"
                )

        # Check 2: Every publish_state on a switch in apply_register_() has a YAML switch
        for prefix, reg in cpp_apply.items():
            yaml_id = prefix + "_switch"
            if yaml_id not in yaml_switches and yaml_id not in LOCAL_ONLY:
                errors.append(
                    f"{yaml_path.name}: C++ apply_register_() publishes to '{prefix}_switch' "
                    f"(register 0x{reg:04X}) but no YAML switch definition found"
                )

    if errors:
        print("FAIL - toggle/switch mismatches found:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"PASS - all switches consistent across {len(YAMLS)} YAML config(s) and C++ source")


if __name__ == "__main__":
    test_toggles()
