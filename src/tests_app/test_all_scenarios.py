# -*- coding: utf-8 -*-
"""
Тестирование всех 6 сценариев без ClickHouse.
Проверяем:
1. Все ли заявки выполняются
2. Стабильность результатов (штрафы)

Запуск: py -m src.test_all_scenarios
"""

import random
from typing import Dict, List, Tuple
from src.graph import WarehouseGraph
from src.models import Warehouse, Order, Edge, ObjectType
from src.simulation import Simulation

# Константа из tests_generator
TOTAL_OBJECTS = 100_000


class TestDataGenerator:
    """Генератор тестовых данных без зависимости от БД."""
    
    def generate_object_types(self, k: int = 10) -> List[ObjectType]:
        """Генерация K типов объектов."""
        types = []
        for i in range(1, k + 1):
            types.append(ObjectType(
                type_id=i,
                move_time=random.randint(1, 3),
                move_cost=round(random.uniform(10, 100), 2),
                loss_value=round(random.uniform(100, 1000), 2)
            ))
        return types
    
    def generate_chain_graph(self, n: int) -> List[Edge]:
        """Линейный граф."""
        return [Edge(from_id=i, to_id=i + 1, weight=1) for i in range(1, n)]
    
    def generate_star_graph(self, n: int) -> List[Edge]:
        """Граф-звезда."""
        return [Edge(from_id=1, to_id=i, weight=1) for i in range(2, n + 1)]
    
    def generate_ring_graph(self, n: int) -> List[Edge]:
        """Кольцевой граф."""
        edges = [Edge(from_id=i, to_id=i + 1, weight=1) for i in range(1, n)]
        edges.append(Edge(from_id=n, to_id=1, weight=1))
        return edges
    
    def generate_grid_graph(self, rows: int, cols: int) -> List[Edge]:
        """Граф-решётка."""
        edges = []
        for r in range(rows):
            for c in range(cols):
                node = r * cols + c + 1
                if c < cols - 1:
                    edges.append(Edge(from_id=node, to_id=node + 1, weight=1))
                if r < rows - 1:
                    edges.append(Edge(from_id=node, to_id=node + cols, weight=1))
        return edges
    
    def generate_random_connected_graph(self, n: int, extra_edges: int = 5) -> List[Edge]:
        """Случайный связный граф."""
        edges = []
        for i in range(2, n + 1):
            parent = random.randint(1, i - 1)
            edges.append(Edge(from_id=parent, to_id=i, weight=random.randint(1, 3)))
        for _ in range(extra_edges):
            a, b = random.sample(range(1, n + 1), 2)
            edges.append(Edge(from_id=a, to_id=b, weight=random.randint(1, 3)))
        return edges
    
    def distribute_uniform(self, warehouses: int, types: int) -> List[Tuple[int, int, int]]:
        """Равномерное распределение."""
        inventory = []
        total = TOTAL_OBJECTS
        per_slot = total // (warehouses * types)
        remainder = total % (warehouses * types)
        
        for wh in range(1, warehouses + 1):
            for t in range(1, types + 1):
                qty = per_slot + (1 if remainder > 0 else 0)
                if remainder > 0:
                    remainder -= 1
                if qty > 0:
                    inventory.append((wh, t, qty))
        return inventory
    
    def distribute_concentrated(self, warehouses: int, types: int, 
                               concentrate_on: List[int]) -> List[Tuple[int, int, int]]:
        """Концентрация на определённых складах."""
        inventory = []
        total = TOTAL_OBJECTS
        n_concentrated = len(concentrate_on)
        per_wh = total // n_concentrated
        remainder = total % n_concentrated
        
        for i, wh in enumerate(concentrate_on):
            wh_total = per_wh + (1 if i < remainder else 0)
            per_type = wh_total // types
            type_remainder = wh_total % types
            
            for t in range(1, types + 1):
                t_qty = per_type + (1 if t <= type_remainder else 0)
                if t_qty > 0:
                    inventory.append((wh, t, t_qty))
        return inventory
    
    def distribute_sparse(self, warehouses: int, types: int) -> List[Tuple[int, int, int]]:
        """Разреженное распределение."""
        inventory_dict: Dict[Tuple[int, int], int] = {}
        remaining = TOTAL_OBJECTS
        
        while remaining > 0:
            wh = random.randint(1, warehouses)
            t = random.randint(1, types)
            qty = min(random.randint(50, 500), remaining)
            key = (wh, t)
            inventory_dict[key] = inventory_dict.get(key, 0) + qty
            remaining -= qty
        
        return [(wh, t, qty) for (wh, t), qty in inventory_dict.items()]
    
    def generate_orders_from_inventory(self, inventory: List[Tuple[int, int, int]],
                                       target_warehouses: List[int] = None,
                                       min_order_size: int = 100,
                                       max_order_size: int = 2000) -> List[Order]:
        """Генерация заявок на основе инвентаря."""
        type_totals: Dict[int, int] = {}
        for wh, t, qty in inventory:
            type_totals[t] = type_totals.get(t, 0) + qty
        
        all_warehouses = list(set(wh for wh, _, _ in inventory))
        available_warehouses = target_warehouses or all_warehouses
        
        orders = []
        order_id = 1
        remaining_total = TOTAL_OBJECTS
        remaining_by_type = dict(type_totals)
        
        while remaining_total > 0:
            available_types = [t for t, qty in remaining_by_type.items() if qty > 0]
            if not available_types:
                break
            
            t = random.choice(available_types)
            wh = random.choice(available_warehouses)
            max_possible = min(remaining_by_type[t], max_order_size, remaining_total)
            
            if max_possible < min_order_size:
                qty = max_possible
            else:
                qty = random.randint(min(min_order_size, max_possible), max_possible)
            
            if qty > 0:
                orders.append(Order(order_id=order_id, type_k=t, quantity_t=qty, warehouse_a=wh))
                order_id += 1
                remaining_total -= qty
                remaining_by_type[t] -= qty
        
        return orders
    
    def generate_orders_ideal(self, inventory: List[Tuple[int, int, int]]) -> List[Order]:
        """Идеальные заявки (товар уже на нужном складе)."""
        inv_dict: Dict[Tuple[int, int], int] = {}
        for wh, t, qty in inventory:
            key = (wh, t)
            inv_dict[key] = inv_dict.get(key, 0) + qty
        
        orders = []
        order_id = 1
        
        for (wh, t), total_qty in inv_dict.items():
            remaining = total_qty
            while remaining > 0:
                qty = min(remaining, random.randint(500, 2000))
                orders.append(Order(order_id=order_id, type_k=t, quantity_t=qty, warehouse_a=wh))
                order_id += 1
                remaining -= qty
        
        random.shuffle(orders)
        for i, order in enumerate(orders, 1):
            order.order_id = i
        
        return orders
    

    def generate_test_1(self) -> dict:
        """Тест 1: Идеальный случай (штраф = 0)."""
        n_warehouses, n_types = 10, 10
        object_types = self.generate_object_types(n_types)
        edges = self.generate_star_graph(n_warehouses)
        inventory = self.distribute_uniform(n_warehouses, n_types)
        orders = self.generate_orders_ideal(inventory)
        
        return {
            "test_id": 1, "name": "Идеальный случай",
            "description": "Товары уже на нужных складах. Ожидаемый штраф: 0",
            "object_types": object_types, "edges": edges,
            "inventory": inventory, "orders": orders,
            "n_warehouses": n_warehouses, "n_types": n_types, "total_objects": TOTAL_OBJECTS
        }
    
    def generate_test_2(self) -> dict:
        """Тест 2: Линейная магистраль."""
        n_warehouses, n_types = 10, 5
        object_types = self.generate_object_types(n_types)
        edges = self.generate_chain_graph(n_warehouses)
        inventory = self.distribute_concentrated(n_warehouses, n_types, [1])
        orders = self.generate_orders_from_inventory(inventory, [n_warehouses], 500, 3000)
        
        return {
            "test_id": 2, "name": "Линейная магистраль",
            "description": f"Цепочка 1-{n_warehouses}. Товары на складе 1, заявки на складе {n_warehouses}",
            "object_types": object_types, "edges": edges,
            "inventory": inventory, "orders": orders,
            "n_warehouses": n_warehouses, "n_types": n_types, "total_objects": TOTAL_OBJECTS
        }
    
    def generate_test_3(self) -> dict:
        """Тест 3: Центральный хаб."""
        n_warehouses, n_types = 8, 8
        object_types = self.generate_object_types(n_types)
        edges = self.generate_star_graph(n_warehouses)
        peripheral = list(range(2, n_warehouses + 1))
        inventory = self.distribute_concentrated(n_warehouses, n_types, peripheral)
        orders = self.generate_orders_from_inventory(inventory, [1], 500, 2500)
        
        return {
            "test_id": 3, "name": "Центральный хаб",
            "description": "Звезда. Товары на периферии, заявки в центре",
            "object_types": object_types, "edges": edges,
            "inventory": inventory, "orders": orders,
            "n_warehouses": n_warehouses, "n_types": n_types, "total_objects": TOTAL_OBJECTS
        }
    
    def generate_test_4(self) -> dict:
        """Тест 4: Кольцо с разбросом."""
        n_warehouses, n_types = 12, 6
        object_types = self.generate_object_types(n_types)
        edges = self.generate_ring_graph(n_warehouses)
        inventory = self.distribute_sparse(n_warehouses, n_types)
        orders = self.generate_orders_from_inventory(inventory, None, 200, 1500)
        
        return {
            "test_id": 4, "name": "Кольцо с разбросом",
            "description": "Кольцо из 12 складов. Товары разбросаны неравномерно",
            "object_types": object_types, "edges": edges,
            "inventory": inventory, "orders": orders,
            "n_warehouses": n_warehouses, "n_types": n_types, "total_objects": TOTAL_OBJECTS
        }
    
    def generate_test_5(self) -> dict:
        """Тест 5: Сетка с множеством типов."""
        n_warehouses, n_types = 20, 50
        object_types = self.generate_object_types(n_types)
        edges = self.generate_grid_graph(5, 4)
        inventory = self.distribute_uniform(n_warehouses, n_types)
        orders = self.generate_orders_from_inventory(inventory, None, 100, 1000)
        
        return {
            "test_id": 5, "name": "Сетка с множеством типов",
            "description": "Сетка 5x4. 50 типов товаров",
            "object_types": object_types, "edges": edges,
            "inventory": inventory, "orders": orders,
            "n_warehouses": n_warehouses, "n_types": n_types, "total_objects": TOTAL_OBJECTS
        }
    
    def generate_test_6(self) -> dict:
        """Тест 6: Случайный сложный граф."""
        n_warehouses, n_types = 15, 15
        object_types = self.generate_object_types(n_types)
        edges = self.generate_random_connected_graph(n_warehouses, 10)
        concentrated = random.sample(range(1, n_warehouses + 1), 3)
        inventory = self.distribute_concentrated(n_warehouses, n_types, concentrated)
        orders = self.generate_orders_from_inventory(inventory, None, 300, 2000)
        
        return {
            "test_id": 6, "name": "Случайный сложный граф",
            "description": f"15 складов. Товары на складах {concentrated}",
            "object_types": object_types, "edges": edges,
            "inventory": inventory, "orders": orders,
            "n_warehouses": n_warehouses, "n_types": n_types, "total_objects": TOTAL_OBJECTS
        }


def run_test(test_data: dict, verbose: bool = False) -> dict:
    """Запустить один тест и вернуть результаты."""
    import time
    
    # Создаём граф
    graph = WarehouseGraph()
    graph.load_from_edges(test_data["edges"])
    
    # Создаём склады
    warehouse_ids = set()
    for wh_id, _, _ in test_data["inventory"]:
        warehouse_ids.add(wh_id)
    for node in graph.nodes:
        warehouse_ids.add(node)
    
    warehouses: Dict[int, Warehouse] = {}
    for wh_id in warehouse_ids:
        warehouses[wh_id] = Warehouse(id=wh_id, name=f"Склад {wh_id}")
    
    # Заполняем инвентарь
    for wh_id, type_k, qty in test_data["inventory"]:
        if wh_id in warehouses:
            warehouses[wh_id].add_item(type_k, qty)
            warehouses[wh_id].logs.clear()
    
    # Создаём симуляцию
    sim = Simulation(
        graph=graph,
        warehouses=warehouses,
        orders=test_data["orders"],
        object_types=test_data["object_types"],
        solver_type="predictive"
    )
    
    # Запускаем (увеличиваем max_steps для сложных тестов)
    max_steps = len(test_data["orders"]) * 20 + 1000
    state = sim.run_auto(max_steps=max_steps)
    
    # Собираем результаты
    total_orders = len(test_data["orders"])
    completed = len(state.completed_orders)
    unfulfillable = len(state.unfulfillable_orders) if hasattr(state, 'unfulfillable_orders') else 0
    active = len(state.active_orders)
    
    # Проверяем суммы
    total_inventory = sum(qty for _, _, qty in test_data["inventory"])
    total_orders_qty = sum(o.quantity_t for o in test_data["orders"])
    
    # Расчёт времени выполнения
    exec_time = state.end_time - state.start_time if hasattr(state, 'end_time') else 0
    
    # Статистика ожидания
    if state.completed_orders:
        wait_times = [info.wait_steps for info in state.completed_orders]
        avg_wait = sum(wait_times) / len(wait_times)
        max_wait = max(wait_times)
        instant = sum(1 for w in wait_times if w == 0)
    else:
        avg_wait, max_wait, instant = 0, 0, 0
    
    result = {
        "test_id": test_data["test_id"],
        "name": test_data["name"],
        "total_steps": state.current_step,
        "total_orders": total_orders,
        "completed_orders": completed,
        "active_orders": active,
        "unfulfillable_orders": unfulfillable,
        "total_penalty": state.total_penalty,
        "total_movements": len(state.movements_history),
        "total_inventory": total_inventory,
        "total_orders_qty": total_orders_qty,
        "finished": state.finished,
        "all_completed": (completed + unfulfillable) == total_orders and active == 0,
        "exec_time": exec_time,
        "avg_wait": avg_wait,
        "max_wait": max_wait,
        "instant_completed": instant,
        "theoretical_min": state.theoretical_min_penalty if hasattr(state, 'theoretical_min_penalty') else 0,
        "total_items_moved": state.total_items_moved if hasattr(state, 'total_items_moved') else 0,
    }
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"TEST {test_data['test_id']}: {test_data['name']}")
        print(f"{'='*60}")
        print(f"Description: {test_data['description']}")
        print(f"Warehouses: {test_data['n_warehouses']}, Types: {test_data['n_types']}")
        print(f"Objects: {total_inventory:,}, Orders sum: {total_orders_qty:,}")
        print(f"\nRESULTS:")
        print(f"  Steps: {state.current_step}")
        print(f"  Orders: {completed}/{total_orders} completed")
        print(f"  Movements: {len(state.movements_history)}")
        print(f"  PENALTY: {state.total_penalty}")
        print(f"\nSTATISTICS:")
        print(f"  Exec time: {exec_time:.2f}s")
        print(f"  Avg wait: {avg_wait:.1f} steps")
        print(f"  Max wait: {max_wait} steps")
        print(f"  Instant (0 wait): {instant} ({instant/completed*100:.1f}%)" if completed > 0 else "")
        print(f"  Theoretical min: {result['theoretical_min']}")
        
        if result["all_completed"]:
            print(f"\n  [OK] All orders completed")
        else:
            print(f"\n  [FAIL] {active} orders NOT completed!")
    
    return result


def analyze_algorithm():
    """Проанализировать алгоритм на всех тестах."""
    
    print("\n" + "="*70)
    print("ПОЛНОЕ ТЕСТИРОВАНИЕ АЛГОРИТМА НА 6 СЦЕНАРИЯХ")
    print("="*70)
    
    generator = TestDataGenerator()
    
    # Фиксируем seed для воспроизводимости
    random.seed(42)
    
    all_tests = [
        generator.generate_test_1(),
        generator.generate_test_2(),
        generator.generate_test_3(),
        generator.generate_test_4(),
        generator.generate_test_5(),
        generator.generate_test_6(),
    ]
    
    results = []
    for test_data in all_tests:
        result = run_test(test_data, verbose=True)
        results.append(result)
    
    # Итоговая таблица
    print("\n" + "="*90)
    print("SUMMARY TABLE")
    print("="*90)
    print(f"{'Test':<5} {'Name':<20} {'Orders':<8} {'Done':<8} {'Penalty':<10} {'Time':<8} {'AvgWait':<8} {'Status':<8}")
    print("-"*90)
    
    total_penalty = 0
    total_time = 0
    all_passed = True
    
    for r in results:
        status = "OK" if r["all_completed"] else "FAIL"
        if not r["all_completed"]:
            all_passed = False
        total_penalty += r["total_penalty"]
        total_time += r["exec_time"]
        
        print(f"{r['test_id']:<5} {r['name'][:19]:<20} {r['total_orders']:<8} {r['completed_orders']:<8} "
              f"{r['total_penalty']:<10} {r['exec_time']:.2f}s   {r['avg_wait']:.1f}     {status:<8}")
    
    print("-"*90)
    print(f"{'TOTAL':<5} {'':<20} {'':<8} {'':<8} {total_penalty:<10} {total_time:.2f}s")
    print("="*90)
    
    # Эффективность алгоритма
    print("\n" + "="*90)
    print("ALGORITHM EFFICIENCY ANALYSIS")
    print("="*90)
    
    for r in results:
        theory = r["theoretical_min"]
        actual = r["total_penalty"]
        if theory > 0:
            ratio = actual / theory
            efficiency = f"{ratio:.1f}x theoretical minimum"
        elif actual == 0:
            efficiency = "OPTIMAL (0 penalty)"
        else:
            efficiency = f"penalty={actual} (theory=0)"
        
        instant_pct = r["instant_completed"] / r["completed_orders"] * 100 if r["completed_orders"] > 0 else 0
        
        print(f"Test {r['test_id']}: {efficiency}")
        print(f"         Instant completion: {r['instant_completed']}/{r['completed_orders']} ({instant_pct:.0f}%)")
        print(f"         Avg wait: {r['avg_wait']:.1f}, Max wait: {r['max_wait']}")
        print()
    
    # Вывод сложности
    print("="*90)
    print("COMPLEXITY: O(S * N * K) where S=steps, N=warehouses, K=types")
    print("Algorithm type: Greedy heuristic with type rotation (polynomial time)")
    print("="*90)
    
    if all_passed:
        print("\n[OK] ALL TESTS PASSED - all orders completed!")
    else:
        print("\n[FAIL] SOME ORDERS NOT COMPLETED - algorithm needs improvement!")
    
    return results


def test_stability(runs: int = 3):
    """Проверить стабильность результатов на нескольких запусках."""
    
    print("\n" + "="*70)
    print(f"ТЕСТ СТАБИЛЬНОСТИ ({runs} запусков)")
    print("="*70)
    
    generator = TestDataGenerator()
    
    # Тестируем на разных seed'ах
    all_results = []
    
    for run in range(runs):
        random.seed(42 + run)  # Разные seed для разных данных
        
        test_data = generator.generate_test_4()  # Тест 4 - самый сложный (случайный разброс)
        result = run_test(test_data, verbose=False)
        all_results.append(result)
        
        print(f"Запуск {run+1}: Штраф = {result['total_penalty']}, "
              f"Выполнено = {result['completed_orders']}/{result['total_orders']}")
    
    penalties = [r["total_penalty"] for r in all_results]
    print(f"\nШтрафы: {penalties}")
    print(f"Мин: {min(penalties)}, Макс: {max(penalties)}, Разброс: {max(penalties) - min(penalties)}")
    
    return all_results


if __name__ == "__main__":
    results = analyze_algorithm()
    
    # Тест стабильности
    # stability_results = test_stability(runs=3)

