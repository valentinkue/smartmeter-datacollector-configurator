from configparser import ConfigParser
from pathlib import Path

import pytest
from pydantic import ValidationError

import smartmeter_datacollector_configurator.configurator as configurator
from smartmeter_datacollector_configurator.dto import ConfigDto, MeterDto, MeterType


def test_meter_defaults_have_empty_adjustments():
    meter = MeterDto(type=MeterType.LGE450, port="/dev/ttyUSB0")
    assert meter.scale is None
    assert meter.scale_per_obis == {}
    assert meter.unit_per_class == {}
    assert meter.unit_per_obis == {}


def test_write_reader_section_flattens_adjustments(tmp_path: Path):
    cfg = ConfigDto(meters=[MeterDto(
        type=MeterType.LGE450,
        port="/dev/ttyUSB0",
        scale=0.5,
        scale_per_obis={"1.0.3.7.0": 40.0},
        unit_per_class={"W": "kW"},
        unit_per_obis={"1.0.3.7.0": "kvar"},
    )])
    configurator.write_config_from_dto(str(tmp_path), cfg)

    parser = ConfigParser()
    parser.read(tmp_path / configurator.CONFIG_FILE_NAME)
    sec = dict(parser.items("reader0"))
    assert sec["type"] == "lge450"
    assert sec["scale"] == "0.5"
    assert sec["scale.1.0.3.7.0"] == "40.0"
    # configparser lower-cases option names; the datacollector reads them case-insensitively.
    assert sec["unit.w"] == "kW"
    assert sec["unit.1.0.3.7.0"] == "kvar"


def test_round_trip_preserves_adjustments(tmp_path: Path):
    original = ConfigDto(meters=[MeterDto(
        type=MeterType.LGE450,
        port="/dev/ttyUSB0",
        scale=0.5,
        scale_per_obis={"1.0.3.7.0": 40.0},
        unit_per_class={"W": "kW", "Wh": "kWh"},
        unit_per_obis={"1.0.3.7.0": "kvar"},
    )])
    configurator.write_config_from_dto(str(tmp_path), original)
    loaded = configurator.retrieve_config(str(tmp_path))

    meter = loaded.meters[0]
    assert meter.scale == 0.5
    assert meter.scale_per_obis == {"1.0.3.7.0": 40.0}
    assert meter.unit_per_class == {"W": "kW", "Wh": "kWh"}
    assert meter.unit_per_obis == {"1.0.3.7.0": "kvar"}


def test_read_classifies_unit_selectors(tmp_path: Path):
    parser = ConfigParser()
    parser.read_dict({
        "reader0": {
            "type": "lge450",
            "port": "/p",
            "unit.W": "kW",
            "unit.1.0.3.7.0": "kvar",
            "scale.31.7.0": "2",
        },
        "logging": {"default": "INFO"},
    })
    with open(tmp_path / configurator.CONFIG_FILE_NAME, "w", encoding="utf-8") as file:
        parser.write(file, True)

    meter = configurator.retrieve_config(str(tmp_path)).meters[0]
    assert meter.unit_per_class == {"W": "kW"}
    assert meter.unit_per_obis == {"1.0.3.7.0": "kvar"}
    assert meter.scale_per_obis == {"31.7.0": 2.0}


def test_legacy_keys_are_ignored(tmp_path: Path):
    parser = ConfigParser()
    parser.read_dict({
        "reader0": {"type": "lge450", "port": "/p", "baudrate": "2400", "systemtime": "false"},
        "logging": {"default": "INFO"},
    })
    with open(tmp_path / configurator.CONFIG_FILE_NAME, "w", encoding="utf-8") as file:
        parser.write(file, True)

    meter = configurator.retrieve_config(str(tmp_path)).meters[0]
    assert meter.type == MeterType.LGE450
    assert meter.scale is None and meter.unit_per_class == {}


@pytest.mark.parametrize("kwargs", [
    {"scale": 0},
    {"scale_per_obis": {"not-obis": 2.0}},
    {"scale_per_obis": {"1.0.3.7.0": 0}},
    {"unit_per_class": {"banana": "kW"}},
    {"unit_per_class": {"W": "furlong"}},
    {"unit_per_obis": {"9.9.9.9.9": "banana"}},
    {"unit_per_obis": {"not-obis": "kW"}},
])
def test_invalid_adjustments_rejected(kwargs):
    with pytest.raises(ValidationError):
        MeterDto(type=MeterType.LGE450, port="/dev/ttyUSB0", **kwargs)
