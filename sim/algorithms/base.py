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
        order_history: list[tuple[date, "Order"]] | None = None,
    ) -> tuple[list[tuple[str, str]], float]:
        """
        棚卸しを実行する。

        Args:
            order_history: (出庫日, Order) のリスト。シミュレーション開始から当日までの出庫履歴。

        Returns:
            ([(card_id, destination_storage_id), ...], cost_seconds)
        """
