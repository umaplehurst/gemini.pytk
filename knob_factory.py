from abc import ABC, abstractmethod
from typing import Dict, Any, Union

class Knob(ABC):
    @abstractmethod
    def get_name(self) -> str:
        pass

    @abstractmethod
    def get_value(self) -> Any:
        pass

    @abstractmethod
    def set_value(self, value: Any) -> None:
        pass

    @abstractmethod
    def get_ui_component(self) -> Dict[str, Any]:
        pass

class KnobFactory:
    @staticmethod
    def create_knob(knob_type: str, **kwargs) -> Knob:
        if knob_type == "slider":
            return SliderKnob(**kwargs)
        elif knob_type == "dropdown":
            return DropdownKnob(**kwargs)
        elif knob_type == "checkbox":
            return CheckboxKnob(**kwargs)
        else:
            raise ValueError(f"Unknown knob type: {knob_type}")

class SliderKnob(Knob):
    def __init__(self, name: str, min_value: Union[int, float], max_value: Union[int, float], default_value: Union[int, float]):
        self.name = name
        self.min_value = min_value
        self.max_value = max_value
        self.value = default_value
        self.is_integer = isinstance(min_value, int) and isinstance(max_value, int)

    def get_name(self) -> str:
        return self.name

    def get_value(self) -> Union[int, float]:
        return self.value

    def set_value(self, value: Union[int, float]) -> None:
        if self.is_integer:
            value = int(value)
        self.value = max(self.min_value, min(self.max_value, value))

    def get_ui_component(self) -> Dict[str, Any]:
        return {
            "type": "slider",
            "name": self.name,
            "min": self.min_value,
            "max": self.max_value,
            "value": self.value,
            "is_integer": self.is_integer
        }

class DropdownKnob(Knob):
    def __init__(self, name: str, options: list, default_value: Any):
        self.name = name
        self.options = options
        self.value = default_value

    def get_name(self) -> str:
        return self.name

    def get_value(self) -> Any:
        return self.value

    def set_value(self, value: Any) -> None:
        if value in self.options:
            self.value = value

    def get_ui_component(self) -> Dict[str, Any]:
        return {
            "type": "dropdown",
            "name": self.name,
            "options": self.options,
            "value": self.value
        }

class CheckboxKnob(Knob):
    def __init__(self, name: str, default_value: bool):
        self.name = name
        self.value = default_value

    def get_name(self) -> str:
        return self.name

    def get_value(self) -> bool:
        return self.value

    def set_value(self, value: bool) -> None:
        self.value = value

    def get_ui_component(self) -> Dict[str, Any]:
        return {
            "type": "checkbox",
            "name": self.name,
            "value": self.value
        }
