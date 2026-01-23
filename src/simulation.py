"""Движок симуляции логистики."""

import time
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from .models import Order, Movement, Penalty, Warehouse, ActiveOrder, ObjectType, InTransitItem, CompletedOrderInfo
from .graph import WarehouseGraph
from .solver import Solver, PredictiveSolver


@dataclass
class SimulationState:
    """Состояние симуляции на текущем шаге."""
    current_step: int = 0
    total_penalty: int = 0
    total_move_cost: float = 0.0  # Общая стоимость всех перемещений
    active_orders: List[ActiveOrder] = field(default_factory=list)
    completed_orders: List[CompletedOrderInfo] = field(default_factory=list)  # Детальная информация
    unfulfillable_orders: List[Order] = field(default_factory=list)  # Невыполнимые заявки
    movements_history: List[Movement] = field(default_factory=list)
    penalties_history: List[Penalty] = field(default_factory=list)
    in_transit: List[InTransitItem] = field(default_factory=list)  # Товары в пути
    completed_this_step: List[CompletedOrderInfo] = field(default_factory=list)  # Выполнено на этом шаге
    finished: bool = False
    steps_without_progress: int = 0  # Счётчик шагов без прогресса
    
    # Статистика для анализа эффективности
    start_time: float = 0.0  # Время начала симуляции
    end_time: float = 0.0    # Время окончания
    total_items_moved: int = 0  # Всего перемещено товаров
    moves_by_type: Dict[int, int] = field(default_factory=dict)  # Перемещений по типам
    theoretical_min_penalty: int = 0  # Теоретический минимум штрафа


class Simulation:
    """
    Движок симуляции системы логистики.
    
    Правила (из условия задачи):
    1. За 1 ход заказчик забирает со склада A товар типа k количества T.
    2. За 1 действие можно перемещать товары только 1-го типа k.
    3. Если заявку выполнить нельзя — штраф +1 за эту заявку.
    4. Штраф накапливается: если на ходу N висит M невыполненных заявок — штраф +M.
    """

    def __init__(self, graph: WarehouseGraph, warehouses: Dict[int, Warehouse],
                 orders: List[Order], object_types: List[ObjectType] = None,
                 solver_type: str = "predictive"):
        self.graph = graph
        self.warehouses = warehouses
        self.orders = orders
        self.state = SimulationState()
        
        # Словарь стоимостей перемещения по типам товаров
        self.move_costs: Dict[int, float] = {}
        self.move_times: Dict[int, int] = {}
        if object_types:
            for ot in object_types:
                self.move_costs[ot.type_id] = ot.move_cost
                self.move_times[ot.type_id] = ot.move_time
        
        # Создаём решатель
        if solver_type == "predictive":
            self.solver = PredictiveSolver(graph, warehouses, orders, self.move_times)
        else:
            self.solver = Solver(graph, warehouses, orders, self.move_times)

        # Callback для интерактивного режима
        self.step_callback: Optional[Callable[[SimulationState, Optional[Movement]], None]] = None

    def reset(self) -> None:
        """Сбросить симуляцию в начальное состояние."""
        self.state = SimulationState()
    
    def _calculate_theoretical_minimum(self) -> int:
        """
        Вычислить теоретическую нижнюю границу штрафа.
        Это сумма минимальных расстояний для каждой заявки.
        ОЧЕНЬ оптимистичная оценка (реальный оптимум выше).
        """
        # Подсчёт товаров по типам и складам
        stock: Dict[Tuple[int, int], int] = {}
        for wh_id, wh in self.warehouses.items():
            for type_k, qty in wh.inventory.items():
                stock[(wh_id, type_k)] = qty
        
        total_min = 0
        for order in self.orders:
            target_wh = order.warehouse_a
            type_k = order.type_k
            
            # Минимальное расстояние до товара нужного типа
            min_dist = 0
            for (wh, t), qty in stock.items():
                if t == type_k and qty > 0:
                    dist = self.graph.get_distance(wh, target_wh)
                    if dist < float('inf'):
                        min_dist = max(min_dist, dist)  # Консервативная оценка
                        break
            
            total_min += min_dist
        
        return total_min

    def step(self) -> Tuple[int, Optional[Movement]]:
        """
        Выполнить один шаг симуляции.
        
        По условию задачи:
        - За 1 ход заказчик забирает товар со склада (если товар есть)
        - За 1 действие можно перемещать товары только 1-го типа
        - Перемещение занимает время = move_time типа товара * вес ребра
        - Штраф +1 за каждую невыполненную заявку на каждом ходу
        
        Returns:
            (penalty_this_step, movement) - штраф за этот шаг и выполненное действие
        """
        self.state.current_step += 1
        step = self.state.current_step
        
        # Очищаем список выполненных на этом шаге
        self.state.completed_this_step = []
        
        # Запоминаем состояние до шага для отслеживания прогресса
        completed_before = len(self.state.completed_orders)
        
        # 1. Обрабатываем прибытие товаров в пути
        self._process_arrivals(step)
        
        # 2. Добавляем новую заявку из листа (если есть)
        if step <= len(self.orders):
            new_order = self.orders[step - 1]
            self.state.active_orders.append(ActiveOrder(
                order=new_order,
                created_at_step=step
            ))

        # 3. Пытаемся выполнить активные заявки (до перемещения)
        self._try_complete_orders()

        # 4. Проверяем невыполнимые заявки (товара нет в системе)
        self._check_unfulfillable_orders()

        # 5. Получаем лучшее действие от solver'а
        move = self.solver.find_best_move(self.state.active_orders, step, self.state.in_transit)
        
        # 6. Применяем перемещение (создаём товар в пути)
        if move:
            self._apply_movement(move, step)
            self.state.movements_history.append(move)
            # Добавляем стоимость перемещения
            unit_cost = self.move_costs.get(move.type_k, 0.0)
            self.state.total_move_cost += unit_cost * move.quantity
            # Статистика перемещений
            self.state.total_items_moved += move.quantity
            self.state.moves_by_type[move.type_k] = self.state.moves_by_type.get(move.type_k, 0) + 1

        # 7. Снова пытаемся выполнить заявки (после перемещения)
        self._try_complete_orders()

        # 8. Считаем штраф за невыполненные заявки
        step_penalty = len(self.state.active_orders)
        self.state.total_penalty += step_penalty
        
        # Записываем штрафы
        for active in self.state.active_orders:
            active.penalty_accumulated += 1
            self.state.penalties_history.append(Penalty(
                step=step,
                order_id=active.order.order_id,
                penalty_value=1
            ))

        # Callback для интерактивного режима
        if self.step_callback:
            self.step_callback(self.state, move)

        # 9. Отслеживание прогресса (защита от зацикливания)
        # Прогресс = выполнена заявка ИЛИ сделано перемещение ИЛИ товар в пути
        completed_now = len(self.state.completed_orders)
        has_progress = (
            completed_now > completed_before or  # Выполнена заявка
            move is not None or                   # Сделано перемещение
            len(self.state.in_transit) > 0        # Есть товар в пути
        )
        
        if has_progress:
            self.state.steps_without_progress = 0
        else:
            self.state.steps_without_progress += 1

        # 10. Проверяем завершение (все заявки обработаны И нет активных И нет товаров в пути)
        if step >= len(self.orders) and not self.state.active_orders and not self.state.in_transit:
            self.state.finished = True
        
        # Принудительное завершение при зацикливании (>1000 шагов без любого прогресса)
        # Это означает, что solver не может найти решение
        if self.state.steps_without_progress > 1000:
            self.state.finished = True

        return step_penalty, move
    
    def _process_arrivals(self, current_step: int) -> None:
        """
        Обработать прибытие товаров в пути.
        По условию: товары в пути прибывают после истечения времени перемещения.
        """
        remaining_transit = []
        
        for item in self.state.in_transit:
            if item.is_arrived(current_step):
                # Товар прибыл — добавляем на целевой склад
                dest = self.warehouses.get(item.to_warehouse)
                if dest:
                    dest.add_item(item.type_k, item.quantity)
                    dest.logs.append(
                        f"[Шаг {current_step}] Прибыло {item.quantity} шт. типа {item.type_k} "
                        f"со склада {item.from_warehouse}"
                    )
            else:
                # Товар ещё в пути
                remaining_transit.append(item)
        
        self.state.in_transit = remaining_transit
    
    def _apply_movement(self, move: Movement, current_step: int) -> None:
        """
        Применить перемещение: забрать товар со склада-источника и поставить в очередь доставки.
        
        По условию задачи:
        - Время перемещения = move_time типа товара * вес ребра графа
        - Товар находится "в пути" и недоступен до прибытия
        """
        source = self.warehouses.get(move.from_warehouse)
        if not source:
            return
        
        # Забираем товар со склада-источника
        if not source.remove_item(move.type_k, move.quantity):
            return  # Не удалось забрать
        
        source.logs.append(
            f"[Шаг {current_step}] Отправлено {move.quantity} шт. типа {move.type_k} "
            f"на склад {move.to_warehouse}"
        )
        
        # Вычисляем время доставки
        move_time = self.move_times.get(move.type_k, 1)
        edge_weight = self.graph.get_edge_weight(move.from_warehouse, move.to_warehouse)
        transit_time = move_time * edge_weight
        arrival_step = current_step + transit_time
        
        # Создаём запись о товаре в пути
        in_transit = InTransitItem(
            from_warehouse=move.from_warehouse,
            to_warehouse=move.to_warehouse,
            type_k=move.type_k,
            quantity=move.quantity,
            departure_step=current_step,
            arrival_step=arrival_step
        )
        self.state.in_transit.append(in_transit)

    def _try_complete_orders(self) -> None:
        """Попытаться выполнить активные заявки."""
        remaining = []
        
        for active in self.state.active_orders:
            order = active.order
            wh = self.warehouses.get(order.warehouse_a)
            
            if wh and wh.get_quantity(order.type_k) >= order.quantity_t:
                # Заявка может быть выполнена!
                wh.remove_item(order.type_k, order.quantity_t)
                
                # Создаём детальную информацию о выполнении
                completed_info = CompletedOrderInfo(
                    order=order,
                    created_at_step=active.created_at_step,
                    completed_at_step=self.state.current_step,
                    wait_steps=active.penalty_accumulated
                )
                
                self.state.completed_orders.append(completed_info)
                self.state.completed_this_step.append(completed_info)
                
                # Подробный лог на складе
                wh.logs.append(
                    f"[Шаг {self.state.current_step}] ✓ Заявка #{order.order_id} ВЫПОЛНЕНА | "
                    f"Тип: {order.type_k}, Кол-во: {order.quantity_t} | "
                    f"Создана: шаг {active.created_at_step}, Ожидание: {active.penalty_accumulated} ходов"
                )
            else:
                remaining.append(active)
        
        self.state.active_orders = remaining
    
    def _check_unfulfillable_orders(self) -> None:
        """
        Проверить, есть ли заявки, которые невозможно выполнить.
        Если товара нужного типа нет во всей системе (включая товары в пути) - заявка невыполнима.
        """
        remaining = []
        
        for active in self.state.active_orders:
            order = active.order
            
            # Проверяем, есть ли товар в системе (включая товары в пути)
            if self._is_order_fulfillable_with_transit(order):
                remaining.append(active)
            else:
                # Заявка невыполнима - товара нет в системе
                self.state.unfulfillable_orders.append(order)
                # Логируем
                wh = self.warehouses.get(order.warehouse_a)
                if wh:
                    wh.logs.append(f"[Шаг {self.state.current_step}] Заявка #{order.order_id} НЕВЫПОЛНИМА: "
                                  f"товара типа {order.type_k} нет в системе")
        
        self.state.active_orders = remaining
    
    def _is_order_fulfillable_with_transit(self, order: Order) -> bool:
        """
        Проверить, может ли заявка быть выполнена (учитывая товары в пути).
        """
        type_k = order.type_k
        needed = order.quantity_t
        
        # Считаем товар на складах
        total_on_warehouses = sum(
            wh.get_quantity(type_k) for wh in self.warehouses.values()
        )
        
        # Считаем товар в пути
        total_in_transit = sum(
            item.quantity for item in self.state.in_transit if item.type_k == type_k
        )
        
        return (total_on_warehouses + total_in_transit) >= needed

    def run_auto(self, max_steps: int = 1000) -> SimulationState:
        """
        Автоматический прогон симуляции до завершения.
        
        Args:
            max_steps: максимальное количество шагов (защита от бесконечного цикла)
        """
        # Замер времени и расчёт теоретического минимума
        self.state.start_time = time.time()
        self.state.theoretical_min_penalty = self._calculate_theoretical_minimum()
        
        while not self.state.finished and self.state.current_step < max_steps:
            self.step()
            
            # Дополнительная проверка: если все заявки обработаны, нет активных и нет товаров в пути
            if (self.state.current_step >= len(self.orders) 
                and not self.state.active_orders 
                and not self.state.in_transit):
                self.state.finished = True
                break
        
        self.state.end_time = time.time()
        return self.state

    def run_interactive(self, step_callback: Callable[[SimulationState, Optional[Movement]], bool],
                        max_steps: int = 1000) -> SimulationState:
        """
        Интерактивный прогон симуляции.
        
        Args:
            step_callback: функция, вызываемая после каждого шага.
                          Должна вернуть True для продолжения, False для остановки.
            max_steps: максимальное количество шагов
        """
        while not self.state.finished and self.state.current_step < max_steps:
            penalty, move = self.step()
            
            should_continue = step_callback(self.state, move)
            if not should_continue:
                break
            
            if (self.state.current_step >= len(self.orders) 
                and not self.state.active_orders 
                and not self.state.in_transit):
                self.state.finished = True
                break

        return self.state

    def get_warehouse_summary(self) -> Dict[int, dict]:
        """Получить сводку по всем складам."""
        summary = {}
        for wh_id, wh in self.warehouses.items():
            summary[wh_id] = {
                "id": wh_id,
                "name": wh.name,
                "total_items": wh.get_total_items(),
                "inventory": dict(wh.inventory),
                "logs_count": len(wh.logs),
                "last_logs": wh.logs[-3:] if wh.logs else []
            }
        return summary

    def get_statistics(self) -> dict:
        """Получить статистику симуляции."""
        return {
            "current_step": self.state.current_step,
            "total_penalty": self.state.total_penalty,
            "total_move_cost": self.state.total_move_cost,
            "active_orders_count": len(self.state.active_orders),
            "completed_orders_count": len(self.state.completed_orders),
            "unfulfillable_orders_count": len(self.state.unfulfillable_orders),
            "in_transit_count": len(self.state.in_transit),
            "total_movements": len(self.state.movements_history),
            "finished": self.state.finished,
            "steps_without_progress": self.state.steps_without_progress
        }

