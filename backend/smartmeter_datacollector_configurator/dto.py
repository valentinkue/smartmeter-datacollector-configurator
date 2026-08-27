import re
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field
from pydantic.class_validators import validator

LOGGER_LEVEL = ["DEBUG", "INFO", "WARNING", "ERROR", "FATAL", "CRITICAL"]

# --- scaling / unit adjustment helpers -------------------------------------
# Base units that can be relabelled / converted, mapped to their canonical
# spelling. ``var``/``varh`` are accepted as equivalents of ``VA``/``VAh``.
_UNIT_BASE_ALIASES = {
    "W": "W", "WH": "Wh", "VA": "VA", "VAH": "VAh",
    "VAR": "VA", "VARH": "VAh", "V": "V", "A": "A",
}
# Bare built-in units usable as a per-unit-class selector.
_UNIT_CLASSES = {"W": "W", "WH": "Wh", "VA": "VA", "VAH": "VAh", "V": "V", "A": "A"}
_UNIT_PREFIXES = ("m", "k", "M", "G")


def _obis_groups(value: str):
    return [g for g in re.split(r"\W+", value.strip()) if g != ""]


def is_obis_selector(value: str) -> bool:
    """True if ``value`` looks like an OBIS code (2, 3, 5 or 6 numeric groups)."""
    groups = _obis_groups(value)
    return len(groups) in (2, 3, 5, 6) and all(g.isdigit() for g in groups)


def normalize_unit_class(value: str) -> Optional[str]:
    """Return the canonical built-in unit for a class selector, or ``None``."""
    return _UNIT_CLASSES.get(value.strip().upper())


def is_valid_unit(value: str) -> bool:
    """True if ``value`` is a supported (optionally SI-prefixed) unit."""
    value = value.strip()
    for prefix in _UNIT_PREFIXES:
        if value.startswith(prefix) and value[len(prefix):].upper() in _UNIT_BASE_ALIASES:
            return True
    return value.upper() in _UNIT_BASE_ALIASES


class MeterType(str, Enum):
    LGE450 = "lge450"
    LGE360 = "lge360"
    LGE570 = "lge570"
    ISKRAAM550 = "iskraam550"
    KAMSTRUP_HAN = "kamstrup_han"


class SinkType(str, Enum):
    MQTT = "mqtt"
    MQTT_RLDSP = "mqttrldsp"
    LOGGER = "logger"


class BaseModel(PydanticBaseModel):
    # pylint: disable=too-few-public-methods
    class Config:
        anystr_strip_whitespace = True
        use_enum_values = True


class MeterDto(BaseModel):
    type: MeterType
    port: str
    key: Optional[str] = None
    # Optional adjustments applied on top of the meter's built-in behaviour.
    # `scale`         : global multiplicative factor for every register.
    # `scale_per_obis`: factor per OBIS code (overrides `scale`).
    # `unit_per_class`: target unit per built-in unit (e.g. {"W": "kW"}).
    # `unit_per_obis` : target unit per OBIS code (overrides `unit_per_class`).
    scale: Optional[float] = None
    scale_per_obis: Dict[str, float] = {}
    unit_per_class: Dict[str, str] = {}
    unit_per_obis: Dict[str, str] = {}

    @validator("port")
    @classmethod
    def port_not_empty(cls, val: str):
        if not val.strip():
            raise ValueError("Smart meter port must not be empty.")
        return val.strip()

    @validator("scale")
    @classmethod
    def scale_not_zero(cls, val: Optional[float]):
        if val is not None and val == 0:
            raise ValueError("Scaling factor must not be zero.")
        return val

    @validator("scale_per_obis")
    @classmethod
    def scale_per_obis_valid(cls, val: Dict[str, float]):
        for obis, factor in val.items():
            if not is_obis_selector(obis):
                raise ValueError(f"Invalid OBIS code '{obis}' in scaling.")
            if factor == 0:
                raise ValueError(f"Scaling factor for '{obis}' must not be zero.")
        return val

    @validator("unit_per_class")
    @classmethod
    def unit_per_class_valid(cls, val: Dict[str, str]):
        normalized: Dict[str, str] = {}
        for unit, target in val.items():
            builtin = normalize_unit_class(unit)
            if builtin is None:
                raise ValueError(f"Unknown unit class '{unit}'. Allowed: W, Wh, VA, VAh, V, A.")
            if not is_valid_unit(target):
                raise ValueError(f"Unsupported target unit '{target}'.")
            normalized[builtin] = target.strip()
        return normalized

    @validator("unit_per_obis")
    @classmethod
    def unit_per_obis_valid(cls, val: Dict[str, str]):
        for obis, target in val.items():
            if not is_obis_selector(obis):
                raise ValueError(f"Invalid OBIS code '{obis}' in unit override.")
            if not is_valid_unit(target):
                raise ValueError(f"Unsupported target unit '{target}'.")
        return val


class MqttSinkDto(BaseModel):
    type: Literal[SinkType.MQTT, SinkType.MQTT_RLDSP] = SinkType.MQTT
    host: str
    port: int = 1883
    tls: bool = False
    ca_cert: Optional[str] = None
    check_hostname: bool = True
    password: Optional[str] = None
    username: Optional[str] = None
    topic_group: Optional[str] = None

    @validator("host")
    @classmethod
    def host_not_empty(cls, val: str):
        if not val:
            raise ValueError("MQTT host must not be empty.")
        return val

    @validator("port")
    @classmethod
    def port_valid_range(cls, val: int):
        if val <= 0 or val > 65535:
            raise ValueError(f"Invalid MQTT sink port {val}.")
        return val

    @validator("username")
    @classmethod
    def username_password_exists(cls, val: str, values):
        if val and not values["password"]:
            raise ValueError("No password set for username.")
        return val

    @validator("topic_group")
    @classmethod
    def topic_group_is_alpha_num(cls, val: Optional[str]):
        if val and not val.isalnum():
            raise ValueError("Topic group must be alphanumeric if set.")
        return val


class LoggerSinkDto(BaseModel):
    type: SinkType = Field(default=SinkType.LOGGER, const=True)
    name: str = "DataLogger"

    @validator("name")
    @classmethod
    def name_not_empty(cls, val: str):
        if not val.strip():
            raise ValueError("Name must not be empty.")
        return val.strip()


class ConfigDto(BaseModel):
    log_level: str = "WARNING"
    meters: List[MeterDto] = []
    mqtt_sink: Optional[MqttSinkDto] = None
    logger_sink: Optional[LoggerSinkDto] = None

    @validator("log_level")
    @classmethod
    def log_level_valid(cls, val: str):
        lvl = val.strip().upper()
        if lvl not in LOGGER_LEVEL:
            raise ValueError(f"Invalid logging level '{lvl}'. Must be one of {LOGGER_LEVEL}")
        return lvl


class CredentialsDto(BaseModel):
    password: str

    @validator("password")
    @classmethod
    def password_valid(cls, val: str):
        pwd = val.strip()
        if len(pwd) < 8 or len(pwd) > 30:
            raise ValueError("Invalid password length.")
        return pwd
