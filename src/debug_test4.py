# -*- coding: utf-8 -*-
"""
Отладка теста 4 (кольцо с разбросом).
Запуск: py -m src.debug_test4
"""

import random
from typing import Dict, Set
from src.graph import WarehouseGraph
from src.models import Warehouse, Order, Edge, ObjectType
from src.simulation import Simulation
from src.test_all_scenarios import TestDataGenerator, TOTAL_OBJECTS


def debug_test4():
    """Детальный анализ теста 4."""
    
    print("="*70)
    print("ОТЛАДКА ТЕСТА 4: КОЛЬЦО С РАЗБРОСОМ")
    print("="*70)
    
    random.seed(42)
    generator = TestDataGenerator()
    test_data = generator.generate_test_4()
    
    # Анализ данных теста
    inventory = test_data["inventory"]
    orders = test_data["orders"]
    
    # Подсчёт товаров по типам
    supply_by_type: Dict[int, int] = {}
    for wh, type_k, qty in inventory:
        supply_by_type[type_k] = supply_by_type.get(type_k, 0) + qty
    
    # Подсчёт спроса по типам
    demand_by_type: Dict[int, int] = {}
    for order in orders:
        demand_by_type[order.type_k] = demand_by_type.get(order.type_k, 0) + order.quantity_t
    
    print("\n1. БАЛАНС СПРОСА И ПРЕДЛОЖЕНИЯ ПО ТИПАМ:")
    print("-"*50)
    print(f"{'Тип':<5} {'Предложение':<15} {'Спрос':<15} {'Баланс':<15}")
    print("-"*50)
    
    problems = []
    for type_k in sorted(set(supply_by_type.keys()) | set(demand_by_type.keys())):
        supply = supply_by_type.get(type_k, 0)
        demand = demand_by_type.get(type_k, 0)
        balance = supply - demand
        status = "OK" if balance >= 0 else "ДЕФИЦИТ!"
        print(f"{type_k:<5} {supply:<15} {demand:<15} {balance:<15} {status}")
        if balance < 0:
            problems.append((type_k, balance))
    
    if problems:
        print(f"\n[!] КРИТИЧЕСКАЯ ПРОБЛЕМА: Товара не хватает!")
        for type_k, deficit in problems:
            print(f"    Тип {type_k}: дефицит {-deficit} шт.")
    else:
        print("\n[OK] Баланс спроса и предложения в норме")
    
    # Запускаем симуляцию
    print("\n2. ЗАПУСК СИМУЛЯЦИИ:")
    print("-"*50)
    
    graph = WarehouseGraph()
    graph.load_from_edges(test_data["edges"])
    
    warehouse_ids = set()
    for wh_id, _, _ in inventory:
        warehouse_ids.add(wh_id)
    for node in graph.nodes:
        warehouse_ids.add(node)
    
    warehouses: Dict[int, Warehouse] = {}
    for wh_id in warehouse_ids:
        warehouses[wh_id] = Warehouse(id=wh_id, name=f"Склад {wh_id}")
    
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
    
    # Запуск с большим лимитом
    max_steps = 5000
    state = sim.run_auto(max_steps=max_steps)
    
    print(f"Шагов выполнено: {state.current_step}")
    print(f"Выполнено заявок: {len(state.completed_orders)}/{len(orders)}")
    print(f"Активных заявок: {len(state.active_orders)}")
    print(f"Невыполнимых: {len(state.unfulfillable_orders)}")
    print(f"Штраф: {state.total_penalty}")
    print(f"Шагов без прогресса: {state.steps_without_progress}")
    
    # Анализ невыполненных заявок
    if state.active_orders:
        print("\n3. АНАЛИЗ НЕВЫПОЛНЕННЫХ ЗАЯВОК:")
        print("-"*50)
        
        for active in state.active_orders[:10]:
            order = active.order
            type_k = order.type_k
            target_wh = order.warehouse_a
            needed = order.quantity_t
            
            # Сколько товара на целевом складе
            at_target = warehouses[target_wh].get_quantity(type_k) if target_wh in warehouses else 0
            
            # Сколько товара в системе
            total_in_system = sum(wh.get_quantity(type_k) for wh in warehouses.values())
            
            # Сколько в пути
            in_transit = sum(item.quantity for item in state.in_transit if item.type_k == type_k)
            
            print(f"\nЗаявка #{order.order_id}:")
            print(f"  Тип: {type_k}, Кол-во: {needed}, Склад: {target_wh}")
            print(f"  На целевом складе: {at_target}")
            print(f"  Всего в системе (на складах): {total_in_system}")
            print(f"  В пути: {in_transit}")
            print(f"  ИТОГО доступно: {total_in_system + in_transit}")
            
            if total_in_system + in_transit < needed:
                print(f"  [!] НЕВОЗМОЖНО ВЫПОЛНИТЬ - товара НЕТ в системе!")
            elif at_target >= needed:
                print(f"  [?] Странно - товар есть, но заявка не выполнена!")
            else:
                # Ищем, где товар
                locations = []
                for wh_id, wh in warehouses.items():
                    qty = wh.get_quantity(type_k)
                    if qty > 0:
                        dist = graph.get_distance(wh_id, target_wh)
                        locations.append((wh_id, qty, dist))
                
                if locations:
                    print(f"  Товар находится на: {[(w, q, f'dist={d}') for w, q, d in sorted(locations, key=lambda x: x[2])]}")
    
    # Проверка графа
    print("\n4. ПРОВЕРКА СВЯЗНОСТИ ГРАФА:")
    print("-"*50)
    
    # Проверяем, что все склады достижимы друг из друга
    all_connected = True
    for wh1 in warehouse_ids:
        for wh2 in warehouse_ids:
            if wh1 != wh2:
                dist = graph.get_distance(wh1, wh2)
                if dist == float('inf'):
                    print(f"[!] Склад {wh1} и склад {wh2} НЕ СВЯЗАНЫ!")
                    all_connected = False
    
    if all_connected:
        print("[OK] Все склады связаны")


if __name__ == "__main__":
    debug_test4()

