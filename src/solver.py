"""Алгоритм оптимизации перемещений (Solver)."""

from typing import Dict, List, Optional, Tuple, Set
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
    5. Товары перемещаются пошагово через промежуточные склады.
    """

    def __init__(self, graph: WarehouseGraph, warehouses: Dict[int, Warehouse],
                 all_orders: List[Order], move_times: Dict[int, int] = None):
        self.graph = graph
        self.warehouses = warehouses
        self.all_orders = all_orders
        self.move_times = move_times or {}  # {type_id: move_time}
        
        # Отслеживание активных перемещений: {(target_wh, type_k): (current_wh, quantity)}
        # Нужно для продолжения перемещения товара к цели через промежуточные склады
        self.active_deliveries: Dict[Tuple[int, int], Tuple[int, int]] = {}

    def find_best_move(self, active_orders: List[ActiveOrder], current_step: int) -> Optional[Movement]:
        """
        Найти лучшее действие на текущем шаге.
        
        Логика:
        1. Сначала продолжаем активные доставки (товары в пути к цели).
        2. Смотрим активные заявки (невыполненные).
        3. Для самой "горячей" заявки (самая старая + быстрее доставить) ищем, откуда везти товар.
        4. Если нет активных заявок или всё на месте — смотрим в будущее.
        """
        
        # Сначала проверяем активные доставки - продолжаем перемещение товаров к цели
        move = self._continue_active_delivery(current_step)
        if move:
            return move
        
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
    
    def _continue_active_delivery(self, current_step: int) -> Optional[Movement]:
        """
        Продолжить активную доставку - переместить товар на следующий склад на пути к цели.
        Это гарантирует, что товар дойдёт до цели через промежуточные склады.
        """
        # Очищаем завершённые доставки
        completed = []
        for (target_wh, type_k), (current_wh, qty) in self.active_deliveries.items():
            if current_wh == target_wh:
                completed.append((target_wh, type_k))
        for key in completed:
            del self.active_deliveries[key]
        
        # Продолжаем первую активную доставку
        for (target_wh, type_k), (current_wh, qty) in list(self.active_deliveries.items()):
            if current_wh == target_wh:
                continue  # Уже доставлено
                
            # Проверяем, что товар ещё на текущем складе
            warehouse = self.warehouses.get(current_wh)
            if not warehouse or warehouse.get_quantity(type_k) < qty:
                # Товар уже забрали или переместили - удаляем доставку
                del self.active_deliveries[(target_wh, type_k)]
                continue
            
            # Получаем следующий шаг пути
            next_hop = self.graph.get_next_hop(current_wh, target_wh)
            if next_hop is None:
                del self.active_deliveries[(target_wh, type_k)]
                continue
            
            # Обновляем позицию в активной доставке
            self.active_deliveries[(target_wh, type_k)] = (next_hop, qty)
            
            return Movement(
                step=current_step,
                from_warehouse=current_wh,
                to_warehouse=next_hop,
                type_k=type_k,
                quantity=qty
            )
        
        return None

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
        
        # Проверяем, не идёт ли уже доставка для этой цели
        if (target_wh, type_k) in self.active_deliveries:
            # Уже есть активная доставка, не создаём новую
            return None
        
        # Ищем склады, где есть нужный товар
        warehouses_with_item = []
        for wh_id, wh in self.warehouses.items():
            if wh_id != target_wh and wh.get_quantity(type_k) > 0:
                warehouses_with_item.append(wh_id)
        
        if not warehouses_with_item:
            # Товара нигде нет - невозможно выполнить
            return None
        
        # Находим ближайший склад с товаром
        source_wh, distance = self.graph.find_nearest_with_item(target_wh, warehouses_with_item)
        
        if source_wh is None:
            return None
        
        # Проверяем, что есть путь (граф связный)
        if distance == float('inf'):
            # Нет пути между складами
            return None
        
        source_warehouse = self.warehouses[source_wh]
        available_at_source = source_warehouse.get_quantity(type_k)
        
        # Сколько можем переместить
        qty_to_move = min(to_deliver, available_at_source)
        
        if qty_to_move <= 0:
            return None
        
        # Определяем следующий шаг пути (пошаговое перемещение через промежуточные склады)
        next_hop = self.graph.get_next_hop(source_wh, target_wh)
        
        if next_hop is None:
            # Склады соседние - перемещаем напрямую
            next_hop = target_wh
        
        # Регистрируем активную доставку для отслеживания пути
        # Если это не прямое перемещение (товар идёт через промежуточные склады)
        if next_hop != target_wh:
            self.active_deliveries[(target_wh, type_k)] = (next_hop, qty_to_move)
        
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
    
    def get_total_available(self, type_k: int) -> int:
        """Получить общее количество товара типа k во всей системе."""
        total = 0
        for wh in self.warehouses.values():
            total += wh.get_quantity(type_k)
        return total
    
    def is_order_fulfillable(self, order: Order) -> bool:
        """
        Проверить, может ли заявка быть выполнена в принципе.
        Возвращает False, если товара нужного типа недостаточно во всей системе.
        """
        total_available = self.get_total_available(order.type_k)
        return total_available >= order.quantity_t
    
    def clear_completed_deliveries(self) -> None:
        """Очистить завершённые доставки."""
        completed = []
        for (target_wh, type_k), (current_wh, qty) in self.active_deliveries.items():
            if current_wh == target_wh:
                completed.append((target_wh, type_k))
        for key in completed:
            del self.active_deliveries[key]


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
        
        # Сначала пробуем базовую логику (включая продолжение активных доставок)
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
    
    def _estimate_steps_to_deliver(self, order: Order) -> int:
        """
        Оценить количество шагов, необходимых для доставки товара.
        Используется для приоритезации заявок.
        """
        target_wh = order.warehouse_a
        type_k = order.type_k
        
        # Ищем ближайший склад с товаром
        warehouses_with_item = [
            wh_id for wh_id, wh in self.warehouses.items()
            if wh_id != target_wh and wh.get_quantity(type_k) > 0
        ]
        
        if not warehouses_with_item:
            return float('inf')
        
        _, distance = self.graph.find_nearest_with_item(target_wh, warehouses_with_item)
        return distance

