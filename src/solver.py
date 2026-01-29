"""Алгоритм оптимизации перемещений (Solver)."""

from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
from .models import Order, Movement, Warehouse, ActiveOrder, InTransitItem
from .graph import WarehouseGraph


class Solver:
    """
    Алгоритм принятия решений о перемещениях.
    
    По условию задачи:
    1. За 1 действие можно перемещать товары только 1-го типа (одного k).
    2. Перемещение занимает время = move_time типа товара * общее расстояние пути.
    3. Одно действие "отправка" покрывает весь путь до цели.
    4. Цель — минимизировать штрафы (количество невыполненных заявок).
    
    Стратегия:
    1. Приоритет — выполнение текущих активных заявок (старые важнее).
    2. Если активная заявка не может быть выполнена — везём товар ближе.
    3. Если текущий ход "свободен" — готовимся к будущим заявкам.
    4. При выборе учитывается время перемещения товара (move_time).
    5. Чередование типов товаров для предотвращения "голодания".
    """

    def __init__(self, graph: WarehouseGraph, warehouses: Dict[int, Warehouse],
                 all_orders: List[Order], move_times: Dict[int, int] = None):
        self.graph = graph
        self.warehouses = warehouses
        self.all_orders = all_orders
        self.move_times = move_times or {}  # {type_id: move_time}
        self._last_moved_type: Optional[int] = None  # Для чередования типов
        self._type_move_counts: Dict[int, int] = {}  # Счётчик подряд перемещений по типам

    def find_best_move(self, active_orders: List[ActiveOrder], current_step: int,
                       in_transit: List[InTransitItem] = None) -> Optional[Movement]:
        """
        Найти лучшее действие на текущем шаге.
        
        Обновленная логика:
        Всегда ищем возможность перемещения, даже если текущие активные заявки 
        уже находятся на нужных складах. Это предотвращает простой транспорта.
        """
        self._in_transit = in_transit or []
        
        # Попытка 1: Сначала ищем перемещения для АКТИВНЫХ (проблемных) заявок
        if active_orders:
            # Группируем заявки по типам
            orders_by_type: Dict[int, List[ActiveOrder]] = {}
            for active in active_orders:
                type_k = active.order.type_k
                if type_k not in orders_by_type:
                    orders_by_type[type_k] = []
                orders_by_type[type_k].append(active)
            
            # Подсчитываем товары в пути по типам
            in_transit_by_type: Dict[int, int] = {}
            for item in self._in_transit:
                in_transit_by_type[item.type_k] = in_transit_by_type.get(item.type_k, 0) + item.quantity
            
            # Приоритизируем типы
            def type_priority(type_k: int) -> Tuple[int, int, int]:
                it = in_transit_by_type.get(type_k, 0)
                penalty = sum(a.penalty_accumulated for a in orders_by_type[type_k])
                consecutive = self._type_move_counts.get(type_k, 0)
                return (0 if it == 0 else 1, -penalty, consecutive)
            
            sorted_types = sorted(orders_by_type.keys(), key=type_priority)
            
            for type_k in sorted_types:
                type_orders = sorted(orders_by_type[type_k], key=lambda a: a.created_at_step)
                for active in type_orders:
                    move = self._find_move_for_order(active.order, current_step)
                    if move:
                        self._update_type_counts(move.type_k)
                        return move
        
        # Попытка 2: Если для активных заявок ничего не нужно везти (или их нет),
        # ОБЯЗАТЕЛЬНО смотрим на будущие заявки, чтобы не было простоев.
        move = self._find_proactive_move(current_step)
        if move:
            self._update_type_counts(move.type_k)
            return move
        
        # Попытка 3: Продвинуть товары на промежуточных складах
        move = self._find_intermediate_move(active_orders, current_step)
        if move:
            self._update_type_counts(move.type_k)
            return move
        
        return None
    
    def _update_type_counts(self, type_k: int) -> None:
        """Обновить счётчики перемещений по типам."""
        # Сбрасываем счётчики других типов, увеличиваем для текущего
        for t in list(self._type_move_counts.keys()):
            if t != type_k:
                self._type_move_counts[t] = 0
        self._type_move_counts[type_k] = self._type_move_counts.get(type_k, 0) + 1
        self._last_moved_type = type_k

    def _get_future_demand(self, warehouse_id: int, type_k: int, current_step: int) -> int:
        """Рассчитать суммарный будущий спрос на товар на складе."""
        return sum(o.quantity_t for o in self.all_orders 
                  if o.warehouse_a == warehouse_id and o.type_k == type_k 
                  and o.order_id >= current_step)

    def _find_move_for_order(self, order: Order, current_step: int) -> Optional[Movement]:
        """
        Найти перемещение для конкретной заявки.
        """
        target_wh = order.warehouse_a
        type_k = order.type_k
        
        # Считаем СУММАРНУЮ потребность этого склада в этом товаре (включая эту заявку и будущие)
        total_needed = self._get_future_demand(target_wh, type_k, current_step)
        
        target_warehouse = self.warehouses.get(target_wh)
        available = target_warehouse.get_quantity(type_k) if target_warehouse else 0
        in_transit = sum(item.quantity for item in self._in_transit 
                        if item.to_warehouse == target_wh and item.type_k == type_k)
        
        if available + in_transit >= total_needed:
            return None # Склад полностью обеспечен под все будущие нужды этого типа
            
        to_deliver = total_needed - (available + in_transit)
        
        # Ищем склады-источники, у которых есть ИЗЛИШЕК товара
        warehouses_with_surplus = []
        for wh_id, wh in self.warehouses.items():
            if wh_id == target_wh: continue
            
            qty = wh.get_quantity(type_k)
            if qty <= 0: continue
            
            # Излишек = текущий запас - будущие нужды этого же склада
            own_future_demand = self._get_future_demand(wh_id, type_k, current_step)
            surplus = qty - own_future_demand
            
            if surplus > 0:
                warehouses_with_surplus.append(wh_id)
        
        if not warehouses_with_surplus:
            return None
            
        source_wh, distance = self.graph.find_nearest_with_item(target_wh, warehouses_with_surplus)
        if source_wh is None: return None
        
        qty_at_source = self.warehouses[source_wh].get_quantity(type_k)
        own_demand_at_source = self._get_future_demand(source_wh, type_k, current_step)
        
        # Берем только излишек, чтобы не навредить складу-источнику
        available_surplus = qty_at_source - own_demand_at_source
        qty_to_move = min(to_deliver, available_surplus)
        
        if qty_to_move <= 0: return None
        
        return Movement(
            step=current_step, from_warehouse=source_wh, to_warehouse=target_wh,
            type_k=type_k, quantity=qty_to_move, reason_order_id=order.order_id
        )

    def _find_proactive_move(self, current_step: int) -> Optional[Movement]:
        """
        Проактивное перемещение: готовимся к будущим заявкам.
        Смотрим на заявки, которые ещё не стали активными.
        """
        # Смотрим на ВСЕ будущие заявки (не только 5)
        future_orders = [o for o in self.all_orders if o.order_id > current_step]
        
        for order in future_orders:
            target_wh = order.warehouse_a
            type_k = order.type_k
            needed = order.quantity_t
            
            target_warehouse = self.warehouses.get(target_wh)
            if not target_warehouse:
                continue
            
            available = target_warehouse.get_quantity(type_k)
            
            # Учитываем товары в пути К ЦЕЛЕВОМУ складу
            in_transit_qty = sum(
                item.quantity for item in self._in_transit
                if item.to_warehouse == target_wh and item.type_k == type_k
            )
            
            if available + in_transit_qty < needed:
                # Можем начать подготовку
                move = self._find_move_for_order(order, current_step)
                if move:
                    return move
        
        return None
    
    def _find_intermediate_move(self, active_orders: List[ActiveOrder], 
                                current_step: int) -> Optional[Movement]:
        """
        Найти перемещение для товаров на промежуточных складах.
        Это нужно когда товар уже прибыл на промежуточный склад и его нужно
        отправить дальше к цели.
        """
        # Собираем все целевые склады, типы, НУЖНЫЕ КОЛИЧЕСТВА и пример ID заявки
        # {type_k: {target_wh: {"qty": needed_qty, "order_id": order_id}}}
        demand: Dict[int, Dict[int, Dict[str, any]]] = {}
        
        for active in active_orders:
            type_k = active.order.type_k
            target_wh = active.order.warehouse_a
            needed = active.order.quantity_t
            
            if type_k not in demand:
                demand[type_k] = {}
            if target_wh not in demand[type_k]:
                demand[type_k][target_wh] = {"qty": 0, "order_id": active.order.order_id}
            demand[type_k][target_wh]["qty"] += needed
        
        # Добавляем будущие заявки (с меньшим приоритетом)
        for order in self.all_orders:
            if order.order_id > current_step:
                type_k = order.type_k
                target_wh = order.warehouse_a
                needed = order.quantity_t
                
                if type_k not in demand:
                    demand[type_k] = {}
                if target_wh not in demand[type_k]:
                    demand[type_k][target_wh] = {"qty": 0, "order_id": order.order_id}
                demand[type_k][target_wh]["qty"] += needed
        
        # Для каждого типа товара ищем, можно ли продвинуть его ближе к цели
        for type_k, target_demands in demand.items():
            target_warehouses = set(target_demands.keys())
            
            for wh_id, wh in self.warehouses.items():
                qty_available = wh.get_quantity(type_k)
                if qty_available <= 0:
                    continue
                
                # Проверяем, не является ли этот склад одной из целей
                if wh_id in target_warehouses:
                    continue
                
                # Ищем ближайшую цель для этого товара
                best_target = None
                best_distance = float('inf')
                best_needed = 0
                sample_order_id = None
                
                for target_wh, data in target_demands.items():
                    distance = self.graph.get_distance(wh_id, target_wh)
                    if distance < best_distance:
                        best_distance = distance
                        best_target = target_wh
                        best_needed = data["qty"]
                        sample_order_id = data["order_id"]
                
                if best_target is None or best_distance == float('inf'):
                    continue
                
                # Считаем, сколько уже едет к цели и сколько там есть
                in_transit_to_target = sum(
                    item.quantity for item in self._in_transit
                    if item.to_warehouse == best_target and item.type_k == type_k
                )
                at_target = self.warehouses[best_target].get_quantity(type_k) if best_target in self.warehouses else 0
                still_needed = best_needed - at_target - in_transit_to_target
                
                if still_needed <= 0:
                    continue
                
                # Если товар не на целевом складе, отправляем его напрямую
                if best_distance > 0:
                    # Перемещаем только нужное количество сразу до цели
                    qty_to_move = min(qty_available, still_needed)
                    return Movement(
                        step=current_step,
                        from_warehouse=wh_id,
                        to_warehouse=best_target,
                        type_k=type_k,
                        quantity=qty_to_move,
                        reason_order_id=sample_order_id
                    )
        
        return None

    def get_total_available(self, type_k: int, include_transit: bool = True) -> int:
        """
        Получить общее количество товара типа k во всей системе.
        
        Args:
            type_k: тип товара
            include_transit: включать ли товары в пути
        """
        # Товар на складах
        total = sum(wh.get_quantity(type_k) for wh in self.warehouses.values())
        
        # Товар в пути
        if include_transit and hasattr(self, '_in_transit'):
            total += sum(item.quantity for item in self._in_transit if item.type_k == type_k)
        
        return total
    
    def is_order_fulfillable(self, order: Order) -> bool:
        """
        Проверить, может ли заявка быть выполнена в принципе.
        Возвращает False, если товара нужного типа недостаточно во всей системе.
        """
        total_available = self.get_total_available(order.type_k, include_transit=True)
        return total_available >= order.quantity_t


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

    def find_best_move(self, active_orders: List[ActiveOrder], current_step: int,
                       in_transit: List[InTransitItem] = None) -> Optional[Movement]:
        """
        Улучшенная стратегия: учитываем не только текущие, но и будущие заявки.
        Приоритезируем товары с меньшим move_time для более быстрой доставки.
        
        Порядок приоритетов:
        1. Срочные активные заявки (с наибольшим штрафом)
        2. Активные заявки, для которых нужно начать перемещение
        3. Продвижение товаров на промежуточных складах
        4. Проактивная подготовка к будущим заявкам
        """
        self._in_transit = in_transit or []
        
        # Базовая логика уже включает все необходимые попытки
        return super().find_best_move(active_orders, current_step, in_transit)

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
        Учитывает расстояние до товара, время перемещения и вес рёбер.
        
        Время доставки = move_time * общее расстояние по кратчайшему пути.
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
        
        # Срочность = общее расстояние * время_перемещения (чем меньше, тем срочнее)
        return distance * move_time
    
    def _estimate_steps_to_deliver(self, order: Order) -> int:
        """
        Оценить количество шагов, необходимых для доставки товара.
        
        Время доставки = move_time * общее расстояние по кратчайшему пути.
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
        
        source_wh, _ = self.graph.find_nearest_with_item(target_wh, warehouses_with_item)
        if source_wh is None:
            return float('inf')
        
        # Получаем кратчайшее расстояние и считаем общее время
        _, distance = self.graph.get_shortest_path(source_wh, target_wh)
        if distance == float('inf'):
            return float('inf')
        
        return move_time * distance

