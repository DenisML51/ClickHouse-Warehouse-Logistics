# -*- coding: utf-8 -*-
"""
Отладка теста 2 (линейная магистраль).
Запуск: py -m src.debug_test2
"""

import random
from typing import Dict
from src.graph import WarehouseGraph
from src.models import Warehouse, Order, Edge, ObjectType
from src.simulation import Simulation
from src.test_all_scenarios import TestDataGenerator, TOTAL_OBJECTS


def debug_test2():
    """Детальный анализ теста 2."""
    
    print("="*70)
    print("DEBUG TEST 2: LINEAR CHAIN")
    print("="*70)
    
    random.seed(42)
    generator = TestDataGenerator()
    test_data = generator.generate_test_2()
    
    inventory = test_data["inventory"]
    orders = test_data["orders"]
    edges = test_data["edges"]
    
    print(f"\nTest configuration:")
    print(f"  Warehouses: {test_data['n_warehouses']}")
    print(f"  Types: {test_data['n_types']}")
    print(f"  Orders: {len(orders)}")
    print(f"  Edges: {len(edges)}")
    
    # Анализ инвентаря
    print(f"\nInventory analysis:")
    inv_by_wh = {}
    for wh, type_k, qty in inventory:
        if wh not in inv_by_wh:
            inv_by_wh[wh] = {}
        inv_by_wh[wh][type_k] = qty
    
    for wh in sorted(inv_by_wh.keys()):
        total = sum(inv_by_wh[wh].values())
        print(f"  Warehouse {wh}: {total:,} items, types: {list(inv_by_wh[wh].keys())}")
    
    # Анализ заявок
    print(f"\nOrders analysis:")
    orders_by_wh = {}
    orders_by_type = {}
    for o in orders:
        orders_by_wh[o.warehouse_a] = orders_by_wh.get(o.warehouse_a, 0) + o.quantity_t
        orders_by_type[o.type_k] = orders_by_type.get(o.type_k, 0) + o.quantity_t
    
    print(f"  Orders by warehouse: {orders_by_wh}")
    print(f"  Orders by type: {orders_by_type}")
    
    # Проверка баланса
    print(f"\nSupply vs Demand by type:")
    supply_by_type = {}
    for wh, type_k, qty in inventory:
        supply_by_type[type_k] = supply_by_type.get(type_k, 0) + qty
    
    all_balanced = True
    for type_k in sorted(set(supply_by_type.keys()) | set(orders_by_type.keys())):
        supply = supply_by_type.get(type_k, 0)
        demand = orders_by_type.get(type_k, 0)
        balance = supply - demand
        status = "OK" if balance >= 0 else "DEFICIT!"
        if balance < 0:
            all_balanced = False
        print(f"  Type {type_k}: supply={supply:,}, demand={demand:,}, balance={balance:,} {status}")
    
    if not all_balanced:
        print("\n[CRITICAL] Supply-demand imbalance detected!")
    
    # Анализ графа
    print(f"\nGraph analysis:")
    graph = WarehouseGraph()
    graph.load_from_edges(edges)
    
    # Расстояние от склада 1 до склада 10
    source_wh = 1
    target_wh = test_data['n_warehouses']
    path, distance = graph.get_shortest_path(source_wh, target_wh)
    print(f"  Path {source_wh} -> {target_wh}: {path}")
    print(f"  Distance: {distance} edges")
    
    # Запуск симуляции
    print(f"\n" + "="*70)
    print("RUNNING SIMULATION")
    print("="*70)
    
    warehouse_ids = set()
    for wh_id, _, _ in inventory:
        warehouse_ids.add(wh_id)
    for node in graph.nodes:
        warehouse_ids.add(node)
    
    warehouses: Dict[int, Warehouse] = {}
    for wh_id in warehouse_ids:
        warehouses[wh_id] = Warehouse(id=wh_id, name=f"Warehouse {wh_id}")
    
    for wh_id, type_k, qty in inventory:
        if wh_id in warehouses:
            warehouses[wh_id].add_item(type_k, qty)
            warehouses[wh_id].logs.clear()
    
    sim = Simulation(
        graph=graph,
        warehouses=warehouses,
        orders=orders,
        object_types=test_data["object_types"],
        solver_type="predictive"
    )
    
    # Запускаем с отслеживанием
    max_steps = 2000
    step_log = []
    
    for step_num in range(max_steps):
        penalty, move = sim.step()
        
        if step_num < 20 or step_num % 50 == 0:
            in_transit = len(sim.state.in_transit)
            active = len(sim.state.active_orders)
            completed = len(sim.state.completed_orders)
            
            if move:
                step_log.append(f"Step {sim.state.current_step}: {move.from_warehouse}->{move.to_warehouse} "
                               f"type={move.type_k} qty={move.quantity} | active={active} completed={completed} transit={in_transit}")
            else:
                step_log.append(f"Step {sim.state.current_step}: NO MOVE | active={active} completed={completed} transit={in_transit}")
        
        if sim.state.finished:
            break
    
    # Вывод первых шагов
    print("\nFirst 20 steps:")
    for log in step_log[:20]:
        print(f"  {log}")
    
    # Итоговый результат
    state = sim.state
    print(f"\n" + "="*70)
    print("FINAL RESULT")
    print("="*70)
    print(f"Steps: {state.current_step}")
    print(f"Completed: {len(state.completed_orders)}/{len(orders)}")
    print(f"Active (not completed): {len(state.active_orders)}")
    print(f"Penalty: {state.total_penalty}")
    print(f"Movements: {len(state.movements_history)}")
    print(f"Steps without progress: {state.steps_without_progress}")
    
    if state.active_orders:
        print(f"\nRemaining active orders (first 10):")
        for ao in state.active_orders[:10]:
            o = ao.order
            # Проверим, есть ли товар этого типа в системе
            total_type = sum(wh.get_quantity(o.type_k) for wh in warehouses.values())
            in_transit_type = sum(item.quantity for item in state.in_transit if item.type_k == o.type_k)
            print(f"  Order #{o.order_id}: type={o.type_k}, need={o.quantity_t}, warehouse={o.warehouse_a}")
            print(f"    In system: {total_type}, In transit: {in_transit_type}")


if __name__ == "__main__":
    debug_test2()

