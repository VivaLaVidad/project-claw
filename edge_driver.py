from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseElement(ABC):
    @property
    @abstractmethod
    def exists(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def click(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_text(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def center(self) -> tuple[int, int]:
        raise NotImplementedError

    @abstractmethod
    def set_text(self, text: str) -> None:
        raise NotImplementedError


class BaseDriver(ABC):
    @abstractmethod
    def click(self, x: float, y: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def send_keys(self, text: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def press(self, *keys: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def screenshot(self, path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def push(self, local_path: str, remote_path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def window_size(self) -> tuple[int, int]:
        raise NotImplementedError

    @abstractmethod
    def xpath(self, query: str) -> BaseElement:
        raise NotImplementedError

    @abstractmethod
    def selector(self, **kwargs: Any) -> BaseElement:
        raise NotImplementedError

    @abstractmethod
    def shell(self, command: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_clipboard(self, text: str) -> None:
        raise NotImplementedError


class U2Element(BaseElement):
    def __init__(self, raw: Any):
        self._raw = raw

    @property
    def exists(self) -> bool:
        return bool(self._raw.exists)

    def click(self) -> None:
        self._raw.click()

    def get_text(self) -> str:
        text = self._raw.get_text()
        return text or ""

    def center(self) -> tuple[int, int]:
        point = self._raw.center()
        return int(point[0]), int(point[1])

    def set_text(self, text: str) -> None:
        self._raw.set_text(text)


class U2Driver(BaseDriver):
    def __init__(self, device: Any):
        self._device = device

    @classmethod
    def connect(cls, device_ip: Optional[str] = None) -> "U2Driver":
        import uiautomator2 as u2

        device = u2.connect(device_ip) if device_ip else u2.connect()
        return cls(device)

    def click(self, x: float, y: float) -> None:
        self._device.click(x, y)

    def send_keys(self, text: str) -> None:
        try:
            self._device.send_keys(text, clear=True)
        except TypeError:
            self._device.send_keys(text)
        except Exception:
            self._device.send_keys(text)

    def press(self, *keys: str) -> None:
        if len(keys) == 1:
            self._device.press(keys[0])
        else:
            self._device.press(*keys)

    def screenshot(self, path: str) -> str:
        self._device.screenshot(path)
        return path

    def push(self, local_path: str, remote_path: str) -> None:
        self._device.push(local_path, remote_path)

    def window_size(self) -> tuple[int, int]:
        size = self._device.window_size()
        return int(size[0]), int(size[1])

    def xpath(self, query: str) -> BaseElement:
        return U2Element(self._device.xpath(query))

    def selector(self, **kwargs: Any) -> BaseElement:
        return U2Element(self._device(**kwargs))

    def shell(self, command: str) -> None:
        self._device.shell(command)

    def set_clipboard(self, text: str) -> None:
        self._device.set_clipboard(text)
