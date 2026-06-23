from abc import ABC, abstractmethod
from datetime import date

from sim.models import CardInfo, Order, StorageState


class InboundAlgorithm(ABC):
    """入庫アルゴリズムの基底クラス。"""

    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def assign(
        self,
        cards: list[CardInfo],
        storages: dict[str, StorageState],
    ) -> list[tuple[str, str]]:
        """
        入庫するカードをストレージに割り当てる。

        Returns:
            [(card_id, storage_id), ...]
        """


class OutboundAlgorithm(ABC):
    """出庫アルゴリズムの基底クラス。"""

    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def select(
        self,
        orders: list[Order],
        storages: dict[str, StorageState],
    ) -> list[tuple[Order, str]]:
        """
        注文に対してカードを選択する。

        Returns:
            [(order, card_id), ...]
        """


class StocktakeAlgorithm(ABC):
    """棚卸しアルゴリズムの基底クラス。"""

    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def execute(
        self,
        current_date: date,
        storages: dict[str, StorageState],
    ) -> tuple[list[tuple[str, str]], float]:
        """
        棚卸しを実行する。

        Returns:
            ([(card_id, destination_storage_id), ...], cost_seconds)
        """
