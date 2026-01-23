"""Движок симуляции логистики."""

from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from .models import Order, Movement, Penalty, Warehouse, ActiveOrder
from .graph import WarehouseGraph
from .solver import Solver, PredictiveSolver


@dataclass
class SimulationState:
    """Состояние симуляции на текущем шаге."""
    current_step: int = 0
    total_penalty: int = 0
    active_orders: List[ActiveOrder] = field(default_factory=list)
    completed_orders: List[Order] = field(default_factory=list)
    movements_history: List[Movement] = field(default_factory=list)
    penalties_history: List[Penalty] = field(default_factory=list)
    finished: bool = False


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
                 orders: List[Order], solver_type: str = "predictive"):
        self.graph = graph
        self.warehouses = warehouses
        self.orders = orders
        self.state = SimulationState()
        
        # Создаём решатель
        if solver_type == "predictive":
            self.solver = PredictiveSolver(graph, warehouses, orders)
        else:
            self.solver = Solver(graph, warehouses, orders)

        # Callback для интерактивного режима
        self.step_callback: Optional[Callable[[SimulationState, Optional[Movement]], None]] = None

    def reset(self) -> None:
        """Сбросить симуляцию в начальное состояние."""
        self.state = SimulationState()

    def step(self) -> Tuple[int, Optional[Movement]]:
        """
        Выполнить один шаг симуляции.
        
        Returns:
            (penalty_this_step, movement) - штраф за этот шаг и выполненное действие
        """
        self.state.current_step += 1
        step = self.state.current_step
        
        # 1. Добавляем новую заявку из листа (если есть)
        if step <= len(self.orders):
            new_order = self.orders[step - 1]
            self.state.active_orders.append(ActiveOrder(
                order=new_order,
                created_at_step=step
            ))

        # 2. Пытаемся выполнить активные заявки (до перемещения)
        self._try_complete_orders()

        # 3. Получаем лучшее действие от solver'а
        move = self.solver.find_best_move(self.state.active_orders, step)
        
        # 4. Применяем перемещение
        if move:
            self.solver.apply_move(move)
            self.state.movements_history.append(move)

        # 5. Снова пытаемся выполнить заявки (после перемещения)
        self._try_complete_orders()

        # 6. Считаем штраф за невыполненные заявки
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

        # Проверяем завершение
        if step >= len(self.orders) and not self.state.active_orders:
            self.state.finished = True

        return step_penalty, move

    def _try_complete_orders(self) -> None:
        """Попытаться выполнить активные заявки."""
        remaining = []
        
        for active in self.state.active_orders:
            order = active.order
            wh = self.warehouses.get(order.warehouse_a)
            
            if wh and wh.get_quantity(order.type_k) >= order.quantity_t:
                # Заявка может быть выполнена!
                wh.remove_item(order.type_k, order.quantity_t)
                wh.logs.append(f"[Шаг {self.state.current_step}] Заявка #{order.order_id} выполнена: "
                              f"выдано {order.quantity_t} шт. типа {order.type_k}")
                self.state.completed_orders.append(order)
            else:
                remaining.append(active)
        
        self.state.active_orders = remaining

    def run_auto(self, max_steps: int = 1000) -> SimulationState:
        """
        Автоматический прогон симуляции до завершения.
        
        Args:
            max_steps: максимальное количество шагов (защита от бесконечного цикла)
        """
        while not self.state.finished and self.state.current_step < max_steps:
            self.step()
            
            # Дополнительная проверка: если все заявки обработаны и активных нет
            if self.state.current_step >= len(self.orders) and not self.state.active_orders:
                self.state.finished = True
                break

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
            
            if self.state.current_step >= len(self.orders) and not self.state.active_orders:
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
            "active_orders_count": len(self.state.active_orders),
            "completed_orders_count": len(self.state.completed_orders),
            "total_movements": len(self.state.movements_history),
            "finished": self.state.finished
        }

