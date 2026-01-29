"""Pydantic модели данных для системы логистики."""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from dataclasses import dataclass, field


class ObjectType(BaseModel):
    """
    Тип объекта (товара) с его характеристиками.
    
    По условию задачи каждый тип объекта имеет:
    - время перемещения (учитывается при расчёте задержек)
    - стоимость перемещения (учитывается в общих расходах)
    - стоимость при утрате (информационное поле)
    """
    type_id: int = Field(ge=1, lt=100, description="ID типа товара (K < 100)")
    move_time: int = Field(ge=1, description="Время одного перемещения (в ходах) - используется для приоритезации")
    move_cost: float = Field(ge=0, description="Стоимость одного перемещения - учитывается в total_move_cost")
    loss_value: float = Field(ge=0, description="Стоимость товара при утрате - информационное поле")


class Edge(BaseModel):
    """Ребро графа (связь между складами)."""
    from_id: int = Field(ge=1, description="ID склада-источника")
    to_id: int = Field(ge=1, description="ID склада-назначения")
    weight: int = Field(ge=1, default=1, description="Вес ребра (время перемещения)")


class Order(BaseModel):
    """Заявка из листа заявок."""
    order_id: int = Field(ge=1, description="Номер заявки")
    type_k: int = Field(ge=1, lt=100, description="Тип товара K")
    quantity_t: int = Field(ge=1, description="Количество товара T")
    warehouse_a: int = Field(ge=1, description="Номер склада A")


class Movement(BaseModel):
    """Действие перемещения (ответ алгоритма)."""
    step: int = Field(ge=1, description="Номер хода")
    from_warehouse: int = Field(ge=1, description="Откуда везём")
    to_warehouse: int = Field(ge=1, description="Куда везём")
    type_k: int = Field(ge=1, lt=100, description="Тип товара (только один за ход)")
    quantity: int = Field(ge=0, description="Количество перемещаемого товара")


class Penalty(BaseModel):
    """Штраф за невыполненную заявку."""
    step: int = Field(ge=1, description="Номер хода")
    order_id: int = Field(ge=1, description="Номер заявки")
    penalty_value: int = Field(ge=1, description="Размер штрафа")


@dataclass
class Warehouse:
    """Склад с инвентарём и логами."""
    id: int
    name: str
    inventory: Dict[int, int] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)

    def add_item(self, type_k: int, quantity: int) -> None:
        """Добавить товар на склад."""
        self.inventory[type_k] = self.inventory.get(type_k, 0) + quantity
        self.logs.append(f"+{quantity} товара типа {type_k}")

    def remove_item(self, type_k: int, quantity: int) -> bool:
        """Забрать товар со склада. Возвращает True если успешно."""
        current = self.inventory.get(type_k, 0)
        if current >= quantity:
            self.inventory[type_k] = current - quantity
            self.logs.append(f"-{quantity} товара типа {type_k}")
            return True
        return False

    def get_quantity(self, type_k: int) -> int:
        """Получить количество товара типа k на складе."""
        return self.inventory.get(type_k, 0)

    def get_total_items(self) -> int:
        """Общее количество товаров на складе."""
        return sum(self.inventory.values())


@dataclass
class ActiveOrder:
    """Активная (невыполненная) заявка в симуляции."""
    order: Order
    created_at_step: int
    penalty_accumulated: int = 0


@dataclass
class CompletedOrderInfo:
    """Информация о выполненной заявке."""
    order: Order
    created_at_step: int      # На каком шаге заявка появилась
    completed_at_step: int    # На каком шаге выполнена
    wait_steps: int           # Сколько ходов ждала (штраф накопленный)
    
    def __str__(self) -> str:
        return (f"Заявка #{self.order.order_id}: тип {self.order.type_k}, "
                f"кол-во {self.order.quantity_t}, склад {self.order.warehouse_a} | "
                f"создана: шаг {self.created_at_step}, выполнена: шаг {self.completed_at_step}, "
                f"ожидание: {self.wait_steps} ходов")


@dataclass
class InTransitItem:
    """
    Товар в пути между складами.
    
    По условию задачи: у каждого объекта есть время перемещения,
    и перемещение по ребру графа также занимает время (вес ребра).
    Общее время = move_time типа товара * вес ребра.
    """
    from_warehouse: int  # Откуда отправлен
    to_warehouse: int    # Куда направлен
    type_k: int          # Тип товара
    quantity: int        # Количество
    departure_step: int  # Шаг отправления
    arrival_step: int    # Шаг прибытия (когда товар станет доступен)
    
    def is_arrived(self, current_step: int) -> bool:
        """Проверить, прибыл ли товар."""
        return current_step >= self.arrival_step

