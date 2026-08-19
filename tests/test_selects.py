#!/usr/bin/env python3
"""Verify that every select's option strings match between YAML and C++ source.

For each select defined in the ESPHome YAML configs, this test checks:
  1. Every option string in the YAML appears as a return value in the C++ *_str() function.
  2. Every non-empty return value in the C++ *_str() function appears in the YAML options list.
  3. The YAML set_action lambda's string->value mapping is consistent with the C++ function.
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

# Maps YAML select id -> C++ function name
SELECT_MAP = {
    "fan_select": "fan_str",
    "mode_select": "mode_str",
    "vdir_select": "vdir_str",
    "sleep_select": "sleep_str",
    "generator_select": "gen_str",
    "lrdir_select": "lrdir_str",
}


def parse_cpp_str_funcs(text):
    """Return {func_name: {int_value: string_value}} for each *_str() function."""
    results = {}
    pattern = re.compile(
        r"static const char\s*\*\s*(\w+)\(uint8_t v\)\s*\{"
        r"(.*?)\n\}",
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        fname = m.group(1)
        body = m.group(2)
        cases = {}
        # Explicit case statements
        for cm in re.finditer(
            r"case\s+(0x[0-9A-Fa-f]+|\d+)\s*:\s*return\s*\"([^\"]*)\"", body
        ):
            val = int(cm.group(1), 0)
            cases[val] = cm.group(2)
        # default: return "...";
        dm = re.search(r'default\s*:\s*return\s*"([^"]*)"', body)
        if dm:
            cases["default"] = dm.group(1)
        results[fname] = cases
    return results


def parse_yaml_selects(text):
    """Return {select_id: {options: [...], set_action: {str: int}}}."""
    selects = {}
    lines = text.split("\n")

    for sid in SELECT_MAP:
        # Find the line with this select id
        id_line = None
        for i, line in enumerate(lines):
            if re.match(r"\s+id:\s*" + re.escape(sid) + r"\s*$", line):
                id_line = i
                break
        if id_line is None:
            continue

        # Scan forward for options and set_action within this select block
        options = []
        sa = {}
        in_options = False
        in_set_action = False

        for i in range(id_line, min(id_line + 80, len(lines))):
            line = lines[i]

            # Stop at next select block or top-level section
            if i > id_line and (re.match(r"\s+- platform:", line) or re.match(r"^[a-z_]+:", line)):
                break

            if "options:" in line:
                in_options = True
                in_set_action = False
                continue

            if "set_action:" in line:
                in_set_action = True
                in_options = False
                continue

            if in_options:
                m = re.match(r"\s+-\s*[\"']?([^\"'\n,]+)[\"']?\s*$", line)
                if m:
                    options.append(m.group(1).strip())

            if in_set_action:
                m = re.search(r'x\s*==\s*"([^"]+)"\s*\)\s*v\s*=\s*(0x[0-9A-Fa-f]+|\d+)', line)
                if m:
                    sa[m.group(1)] = int(m.group(2), 0)

        selects[sid] = {"options": options, "set_action": sa}
    return selects


def test_selects():
    cpp_text = CPP.read_text()
    cpp_funcs = parse_cpp_str_funcs(cpp_text)

    errors = []

    for yaml_path in YAMLS:
        yaml_text = yaml_path.read_text()
        yaml_selects = parse_yaml_selects(yaml_text)

        for select_id, func_name in SELECT_MAP.items():
            if func_name not in cpp_funcs:
                errors.append(f"{yaml_path.name}: C++ function '{func_name}' not found")
                continue
            if select_id not in yaml_selects:
                errors.append(f"{yaml_path.name}: YAML select '{select_id}' not found")
                continue

            cpp_map = cpp_funcs[func_name]
            yaml_data = yaml_selects[select_id]
            yaml_options = yaml_data["options"]
            yaml_sa = yaml_data["set_action"]

            # Build the set of C++ return values (excluding default)
            cpp_return_values = set()
            default_value = None
            for val, s in cpp_map.items():
                if val == "default":
                    default_value = s
                else:
                    cpp_return_values.add(s)

            # The default value is a valid implicit option (e.g. "auto" for mode_select)
            if default_value:
                cpp_return_values.add(default_value)

            # Check 1: Every YAML option string appears in C++ return values
            for opt in yaml_options:
                if opt not in cpp_return_values:
                    errors.append(
                        f"{yaml_path.name} / {select_id}: "
                        f"YAML option '{opt}' not in C++ {func_name}() return values "
                        f"{sorted(cpp_return_values)}"
                    )

            # Check 2: Every non-empty C++ return value appears in YAML options
            for val, s in cpp_map.items():
                if val == "default":
                    continue  # already checked above
                if s and s not in yaml_options:
                    errors.append(
                        f"{yaml_path.name} / {select_id}: "
                        f"C++ {func_name}({val}) returns '{s}' but not in YAML options {yaml_options}"
                    )

            # Check 3: set_action string->value pairs match C++ value->string pairs
            for sa_str, sa_val in yaml_sa.items():
                cpp_val_for_str = None
                for cv, cs in cpp_map.items():
                    if cv == "default":
                        continue
                    if cs == sa_str:
                        cpp_val_for_str = cv
                        break
                if cpp_val_for_str is None and default_value == sa_str:
                    # This is the default - no explicit case needed
                    continue
                if cpp_val_for_str is None:
                    errors.append(
                        f"{yaml_path.name} / {select_id}: "
                        f"YAML set_action maps '{sa_str}' -> {sa_val} "
                        f"but C++ {func_name} has no case returning '{sa_str}'"
                    )
                elif cpp_val_for_str != sa_val:
                    errors.append(
                        f"{yaml_path.name} / {select_id}: "
                        f"YAML set_action maps '{sa_str}' -> {sa_val} "
                        f"but C++ {func_name}({sa_val}) returns '{cpp_map.get(sa_val, '?')}' "
                        f"(expected {sa_val} -> '{sa_str}')"
                    )

    if errors:
        print("FAIL - select option mismatches found:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"PASS - all selects consistent across {len(YAMLS)} YAML config(s) and C++ source")


if __name__ == "__main__":
    test_selects()
