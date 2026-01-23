"""Алгоритм оптимизации перемещений (Solver)."""

from typing import Dict, List, Optional, Tuple
from .models import Order, Movement, Warehouse, ActiveOrder
from .graph import WarehouseGraph


class Solver:
    """
    Алгоритм принятия решений о перемещениях.
    
    Стратегия:
    1. Приоритет — выполнение текущих активных заявок.
    2. Если активная заявка не может быть выполнена — везём товар ближе.
    3. Если текущий ход "свободен" — готовимся к будущим заявкам.
    4. При выборе учитывается время перемещения товара (move_time).
    """

    def __init__(self, graph: WarehouseGraph, warehouses: Dict[int, Warehouse],
                 all_orders: List[Order], move_times: Dict[int, int] = None):
        self.graph = graph
        self.warehouses = warehouses
        self.all_orders = all_orders
        self.move_times = move_times or {}  # {type_id: move_time}
        
        # Кэш: товары "в пути" (ещё не доехали)
        # {(from_wh, to_wh, type_k): quantity}
        self.in_transit: Dict[Tuple[int, int, int], int] = {}

    def find_best_move(self, active_orders: List[ActiveOrder], current_step: int) -> Optional[Movement]:
        """
        Найти лучшее действие на текущем шаге.
        
        Логика:
        1. Смотрим активные заявки (невыполненные).
        2. Для самой "горячей" заявки (самая старая + быстрее доставить) ищем, откуда везти товар.
        3. Если можно двигать — двигаем.
        4. Если нет активных заявок или всё на месте — смотрим в будущее.
        """
        
        # Сортируем активные заявки по приоритету:
        # 1) Старые важнее (больше штраф накопился)
        # 2) При равном возрасте — товары с меньшим move_time (быстрее доставить)
        def order_priority(active: ActiveOrder) -> Tuple[int, int]:
            move_time = self.move_times.get(active.order.type_k, 1)
            return (active.created_at_step, move_time)
        
        sorted_orders = sorted(active_orders, key=order_priority)
        
        for active in sorted_orders:
            move = self._find_move_for_order(active.order, current_step)
            if move:
                return move
        
        # Если нет срочных задач, смотрим вперёд
        return self._find_proactive_move(current_step)

    def _find_move_for_order(self, order: Order, current_step: int) -> Optional[Movement]:
        """Найти перемещение для конкретной заявки."""
        target_wh = order.warehouse_a
        type_k = order.type_k
        needed = order.quantity_t
        
        target_warehouse = self.warehouses.get(target_wh)
        if not target_warehouse:
            return None
        
        # Сколько уже есть на целевом складе?
        available = target_warehouse.get_quantity(type_k)
        
        if available >= needed:
            # Товар уже на месте, заявка может быть выполнена
            return None
        
        # Нужно довезти ещё: needed - available
        to_deliver = needed - available
        
        # Ищем склады, где есть нужный товар
        warehouses_with_item = []
        for wh_id, wh in self.warehouses.items():
            if wh_id != target_wh and wh.get_quantity(type_k) > 0:
                warehouses_with_item.append(wh_id)
        
        if not warehouses_with_item:
            # Товара нигде нет
            return None
        
        # Находим ближайший склад с товаром
        source_wh, distance = self.graph.find_nearest_with_item(target_wh, warehouses_with_item)
        
        if source_wh is None:
            return None
        
        source_warehouse = self.warehouses[source_wh]
        available_at_source = source_warehouse.get_quantity(type_k)
        
        # Сколько можем переместить
        qty_to_move = min(to_deliver, available_at_source)
        
        if qty_to_move <= 0:
            return None
        
        # Определяем следующий шаг пути (пошаговое перемещение)
        next_hop = self.graph.get_next_hop(source_wh, target_wh)
        
        if next_hop is None:
            next_hop = target_wh  # Уже рядом
        
        return Movement(
            step=current_step,
            from_warehouse=source_wh,
            to_warehouse=next_hop,
            type_k=type_k,
            quantity=qty_to_move
        )

    def _find_proactive_move(self, current_step: int) -> Optional[Movement]:
        """
        Проактивное перемещение: готовимся к будущим заявкам.
        Смотрим на заявки, которые ещё не стали активными.
        """
        # Смотрим на ближайшие будущие заявки
        future_orders = [o for o in self.all_orders if o.order_id > current_step]
        
        for order in future_orders[:5]:  # Смотрим на 5 ближайших
            target_wh = order.warehouse_a
            type_k = order.type_k
            needed = order.quantity_t
            
            target_warehouse = self.warehouses.get(target_wh)
            if not target_warehouse:
                continue
            
            available = target_warehouse.get_quantity(type_k)
            
            if available < needed:
                # Можем начать подготовку
                move = self._find_move_for_order(order, current_step)
                if move:
                    return move
        
        return None

    def apply_move(self, move: Movement) -> None:
        """Применить перемещение к состоянию складов."""
        if move.quantity <= 0:
            return
            
        source = self.warehouses.get(move.from_warehouse)
        dest = self.warehouses.get(move.to_warehouse)
        
        if source and dest:
            source.remove_item(move.type_k, move.quantity)
            dest.add_item(move.type_k, move.quantity)


class GreedySolver(Solver):
    """
    Жадный алгоритм: всегда выбирает действие для самой старой невыполненной заявки.
    """
    pass  # Базовая логика уже реализована в Solver


class PredictiveSolver(Solver):
    """
    Предиктивный алгоритм: учитывает будущие заявки при принятии решений.
    Пытается минимизировать будущие штрафы.
    Учитывает move_time для оптимизации порядка перемещений.
    """

    def find_best_move(self, active_orders: List[ActiveOrder], current_step: int) -> Optional[Movement]:
        """
        Улучшенная стратегия: учитываем не только текущие, но и будущие заявки.
        Приоритезируем товары с меньшим move_time для более быстрой доставки.
        """
        
        # Сначала пробуем базовую логику
        base_move = super().find_best_move(active_orders, current_step)
        
        if base_move:
            return base_move
        
        # Если базовая логика ничего не нашла, ищем проактивно
        return self._find_proactive_move(current_step)

    def _estimate_future_demand(self, warehouse_id: int, type_k: int, horizon: int = 10) -> int:
        """Оценить будущий спрос на товар типа k на складе."""
        demand = 0
        for order in self.all_orders:
            if order.warehouse_a == warehouse_id and order.type_k == type_k:
                demand += order.quantity_t
        return demand
    
    def _estimate_delivery_urgency(self, order: Order, current_step: int) -> float:
        """
        Оценить срочность доставки для заявки.
        Учитывает расстояние до товара и время перемещения.
        """
        target_wh = order.warehouse_a
        type_k = order.type_k
        move_time = self.move_times.get(type_k, 1)
        
        # Ищем ближайший склад с товаром
        warehouses_with_item = [
            wh_id for wh_id, wh in self.warehouses.items()
            if wh_id != target_wh and wh.get_quantity(type_k) > 0
        ]
        
        if not warehouses_with_item:
            return float('inf')
        
        _, distance = self.graph.find_nearest_with_item(target_wh, warehouses_with_item)
        
        # Срочность = расстояние * время_перемещения (чем меньше, тем срочнее)
        return distance * move_time

