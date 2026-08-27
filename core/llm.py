"""Провайдеры больших языковых моделей для ИИ-поиска.

Поддерживаются два вида сервисов:

  * **GigaChat** (Сбер) — двухшаговая авторизация: по ключу Basic получаем
    временный access_token (живёт 30 минут), им уже ходим в чат.
  * **OpenAI-совместимые** — один ключ, сразу Bearer.

Оба приведены к одному интерфейсу `complete(system, user) -> str | None`,
поэтому ai_search.py не знает, с каким сервисом работает.
"""

from __future__ import annotations

import logging
import ssl
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional

import requests

from config import settings

log = logging.getLogger(__name__)

TIMEOUT = 40

GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


class LLMError(RuntimeError):
    """Ошибка обращения к языковой модели."""


class BaseLLM(ABC):
    """Единый интерфейс языковой модели."""

    name = "base"

    @abstractmethod
    def complete(self, system: str, user: str) -> Optional[str]:
        """Ответ модели или None, если сервис недоступен."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Заданы ли ключи."""

    def check(self) -> tuple[bool, str]:
        """Проверка связи для кнопки в настройках."""
        if not self.is_configured():
            return False, "Ключ не указан"
        try:
            answer = self.complete("Отвечай одним словом.", "Скажи: готово")
        except Exception as exc:
            return False, str(exc)[:200]
        if answer:
            return True, f"Модель отвечает: {answer.strip()[:60]}"
        return False, "Сервис не ответил"


class GigaChatLLM(BaseLLM):
    """GigaChat от Сбера.

    Особенности, из-за которых нужен отдельный класс:
      * авторизация в два шага — ключ Basic меняется на access_token;
      * токен живёт 30 минут, поэтому кэшируется и обновляется заранее;
      * сертификаты подписаны Минцифры и в системном хранилище Windows их
        обычно нет, поэтому проверку TLS можно отключить в настройках.
    """

    name = "gigachat"

    def __init__(self):
        self._session = requests.Session()
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    # ------------------------------------------------------------------ #
    @property
    def credentials(self) -> str:
        return (settings.get("gigachat_credentials") or "").strip()

    @property
    def scope(self) -> str:
        # PERS — физлица, CORP/B2B — организации.
        return settings.get("gigachat_scope") or "GIGACHAT_API_PERS"

    @property
    def model(self) -> str:
        return settings.get("gigachat_model") or "GigaChat"

    @property
    def verify_ssl(self) -> bool:
        return bool(settings.get("gigachat_verify_ssl", False))

    def is_configured(self) -> bool:
        return bool(self.credentials)

    # ------------------------------------------------------------------ #
    def _access_token(self) -> Optional[str]:
        """Действующий токен: из кэша или новый.

        Обновляем за минуту до истечения, чтобы не словить 401 на границе.
        """
        if self._token and time.time() < self._expires_at - 60:
            return self._token

        if not self.credentials:
            return None

        try:
            response = self._session.post(
                GIGACHAT_AUTH_URL,
                headers={
                    "Authorization": f"Basic {self.credentials}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"scope": self.scope},
                timeout=TIMEOUT,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            raise LLMError(f"GigaChat недоступен: {exc}") from exc

        if response.status_code == 401:
            raise LLMError("GigaChat: неверный авторизационный ключ")
        if response.status_code != 200:
            raise LLMError(
                f"GigaChat: авторизация не удалась ({response.status_code})"
            )

        try:
            data = response.json()
            self._token = data["access_token"]
            # expires_at приходит в миллисекундах Unix-времени.
            expires_raw = data.get("expires_at")
            self._expires_at = (
                float(expires_raw) / 1000 if expires_raw else time.time() + 1500
            )
        except (ValueError, KeyError) as exc:
            raise LLMError(f"GigaChat: неожиданный ответ авторизации ({exc})") from exc

        return self._token

    def complete(self, system: str, user: str) -> Optional[str]:
        token = self._access_token()
        if not token:
            return None

        try:
            response = self._session.post(
                GIGACHAT_API_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 600,
                },
                timeout=TIMEOUT,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            raise LLMError(f"GigaChat недоступен: {exc}") from exc

        if response.status_code == 401:
            # Токен мог протухнуть раньше времени — сбрасываем и пробуем ещё раз.
            self._token = None
            self._expires_at = 0.0
            return None
        if response.status_code != 200:
            raise LLMError(f"GigaChat ответил {response.status_code}")

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMError(f"GigaChat: неожиданный формат ответа ({exc})") from exc


class OpenAICompatibleLLM(BaseLLM):
    """Любой сервис с интерфейсом OpenAI /chat/completions."""

    name = "openai"

    def __init__(self):
        self._session = requests.Session()

    @property
    def base_url(self) -> str:
        return (settings.get("ai_base_url") or "").rstrip("/")

    @property
    def api_key(self) -> str:
        return (settings.get("ai_api_key") or "").strip()

    @property
    def model(self) -> str:
        return settings.get("ai_model") or "gpt-4o-mini"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def complete(self, system: str, user: str) -> Optional[str]:
        if not self.is_configured():
            return None
        try:
            response = self._session.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 600,
                },
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise LLMError(f"Сервис недоступен: {exc}") from exc

        if response.status_code == 401:
            raise LLMError("Неверный ключ API")
        if response.status_code != 200:
            raise LLMError(f"Сервис ответил {response.status_code}")

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMError(f"Неожиданный формат ответа ({exc})") from exc


#: Единственные экземпляры — держат кэш токена между запросами.
_GIGACHAT = GigaChatLLM()
_OPENAI = OpenAICompatibleLLM()


def get_llm() -> BaseLLM:
    """Модель согласно настройке ai_provider."""
    provider = (settings.get("ai_provider") or "gigachat").lower()
    return _GIGACHAT if provider == "gigachat" else _OPENAI
