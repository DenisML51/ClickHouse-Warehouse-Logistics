# -*- coding: utf-8 -*-
"""
Test script for step-by-step routing through intermediate warehouses.
Run: py -m src.test_routing
"""

from src.graph import WarehouseGraph
from src.models import Warehouse, Order, Edge
from src.solver import Solver, PredictiveSolver
from src.simulation import Simulation


def test_chain_routing():
    """
    Test: goods must pass through intermediate warehouses.
    Graph: 1 - 2 - 3 - 4 - 5 (chain)
    Goods at warehouse 1, order at warehouse 5.
    Expected: goods travel 1 -> 2 -> 3 -> 4 -> 5
    """
    print("=" * 60)
    print("TEST: Movement through intermediate warehouses (chain)")
    print("=" * 60)
    
    # Create chain graph: 1 - 2 - 3 - 4 - 5
    graph = WarehouseGraph()
    edges = [
        Edge(from_id=1, to_id=2, weight=1),
        Edge(from_id=2, to_id=3, weight=1),
        Edge(from_id=3, to_id=4, weight=1),
        Edge(from_id=4, to_id=5, weight=1),
    ]
    graph.load_from_edges(edges)
    
    # Check path
    path, distance = graph.get_shortest_path(1, 5)
    print(f"Path from warehouse 1 to warehouse 5: {path}")
    print(f"Distance: {distance}")
    assert path == [1, 2, 3, 4, 5], f"Expected path [1, 2, 3, 4, 5], got {path}"
    
    # Create warehouses
    warehouses = {
        1: Warehouse(id=1, name="Warehouse 1"),
        2: Warehouse(id=2, name="Warehouse 2"),
        3: Warehouse(id=3, name="Warehouse 3"),
        4: Warehouse(id=4, name="Warehouse 4"),
        5: Warehouse(id=5, name="Warehouse 5"),
    }
    
    # Put 100 items of type 1 at warehouse 1
    warehouses[1].add_item(type_k=1, quantity=100)
    
    # Order: take 50 items of type 1 from warehouse 5
    orders = [Order(order_id=1, type_k=1, quantity_t=50, warehouse_a=5)]
    
    # Create simulation
    sim = Simulation(graph=graph, warehouses=warehouses, orders=orders, solver_type="predictive")
    
    print("\nInitial state:")
    for wh_id, wh in warehouses.items():
        print(f"  Warehouse {wh_id}: {wh.inventory}")
    
    # Run step by step
    print("\nStep-by-step execution:")
    max_steps = 20
    for step_num in range(max_steps):
        penalty, move = sim.step()
        
        if move:
            print(f"  Step {sim.state.current_step}: {move.from_warehouse} -> {move.to_warehouse} "
                  f"(type {move.type_k}, qty {move.quantity})")
        else:
            print(f"  Step {sim.state.current_step}: no movement")
        
        # Show warehouse state
        inv_str = ", ".join([f"WH{wh_id}: {wh.get_quantity(1)}" 
                            for wh_id, wh in sorted(warehouses.items())])
        print(f"    Inventory (type 1): {inv_str}")
        print(f"    Active orders: {len(sim.state.active_orders)}, Penalty: {sim.state.total_penalty}")
        
        if sim.state.finished:
            print("\n[OK] Simulation finished!")
            break
    
    print(f"\nResult:")
    print(f"  Total steps: {sim.state.current_step}")
    print(f"  Completed orders: {len(sim.state.completed_orders)}")
    print(f"  Total penalty: {sim.state.total_penalty}")
    print(f"  Movements: {len(sim.state.movements_history)}")
    
    # Check result
    assert len(sim.state.completed_orders) == 1, "Order should be completed"
    assert warehouses[5].get_quantity(1) >= 0, "Warehouse 5 should have items or 0"
    
    print("\n[OK] TEST PASSED!")
    return True


def test_star_routing():
    """
    Test: star graph with center at warehouse 1.
    Goods at warehouse 5, order at warehouse 3.
    Path: 5 -> 1 -> 3 (through center)
    """
    print("\n" + "=" * 60)
    print("TEST: Movement through central hub (star)")
    print("=" * 60)
    
    # Create star graph: center 1, periphery 2,3,4,5
    graph = WarehouseGraph()
    edges = [
        Edge(from_id=1, to_id=2, weight=1),
        Edge(from_id=1, to_id=3, weight=1),
        Edge(from_id=1, to_id=4, weight=1),
        Edge(from_id=1, to_id=5, weight=1),
    ]
    graph.load_from_edges(edges)
    
    # Check path
    path, distance = graph.get_shortest_path(5, 3)
    print(f"Path from warehouse 5 to warehouse 3: {path}")
    print(f"Distance: {distance}")
    assert path == [5, 1, 3], f"Expected path [5, 1, 3], got {path}"
    
    # Create warehouses
    warehouses = {i: Warehouse(id=i, name=f"Warehouse {i}") for i in range(1, 6)}
    
    # Goods at warehouse 5
    warehouses[5].add_item(type_k=1, quantity=100)
    
    # Order at warehouse 3
    orders = [Order(order_id=1, type_k=1, quantity_t=30, warehouse_a=3)]
    
    # Simulation
    sim = Simulation(graph=graph, warehouses=warehouses, orders=orders, solver_type="predictive")
    
    print("\nStep-by-step execution:")
    for _ in range(10):
        penalty, move = sim.step()
        if move:
            print(f"  Step {sim.state.current_step}: {move.from_warehouse} -> {move.to_warehouse}")
        if sim.state.finished:
            break
    
    print(f"\nResult: penalty = {sim.state.total_penalty}, completed = {len(sim.state.completed_orders)}")
    assert len(sim.state.completed_orders) == 1, "Order should be completed"
    print("[OK] TEST PASSED!")
    return True


def test_no_direct_connection():
    """
    Test: no direct connection between warehouses.
    Graph: 1 - 2 - 3
           |       |
           4 - 5 - 6
    Goods at warehouse 1, order at warehouse 6.
    """
    print("\n" + "=" * 60)
    print("TEST: Complex path without direct connection")
    print("=" * 60)
    
    graph = WarehouseGraph()
    edges = [
        Edge(from_id=1, to_id=2, weight=1),
        Edge(from_id=2, to_id=3, weight=1),
        Edge(from_id=1, to_id=4, weight=1),
        Edge(from_id=4, to_id=5, weight=1),
        Edge(from_id=5, to_id=6, weight=1),
        Edge(from_id=3, to_id=6, weight=1),
    ]
    graph.load_from_edges(edges)
    
    path, distance = graph.get_shortest_path(1, 6)
    print(f"Path from warehouse 1 to warehouse 6: {path}")
    print(f"Distance: {distance}")
    
    warehouses = {i: Warehouse(id=i, name=f"Warehouse {i}") for i in range(1, 7)}
    warehouses[1].add_item(type_k=1, quantity=50)
    
    orders = [Order(order_id=1, type_k=1, quantity_t=25, warehouse_a=6)]
    
    sim = Simulation(graph=graph, warehouses=warehouses, orders=orders, solver_type="predictive")
    
    print("\nStep-by-step execution:")
    for _ in range(15):
        penalty, move = sim.step()
        if move:
            print(f"  Step {sim.state.current_step}: {move.from_warehouse} -> {move.to_warehouse}")
        if sim.state.finished:
            break
    
    print(f"\nResult: penalty = {sim.state.total_penalty}, completed = {len(sim.state.completed_orders)}")
    assert len(sim.state.completed_orders) == 1, "Order should be completed"
    print("[OK] TEST PASSED!")
    return True


def test_multiple_orders_same_destination():
    """
    Test: multiple orders to the same warehouse.
    """
    print("\n" + "=" * 60)
    print("TEST: Multiple orders to the same warehouse")
    print("=" * 60)
    
    graph = WarehouseGraph()
    edges = [
        Edge(from_id=1, to_id=2, weight=1),
        Edge(from_id=2, to_id=3, weight=1),
    ]
    graph.load_from_edges(edges)
    
    warehouses = {
        1: Warehouse(id=1, name="Warehouse 1"),
        2: Warehouse(id=2, name="Warehouse 2"),
        3: Warehouse(id=3, name="Warehouse 3"),
    }
    
    # Goods distributed across warehouses 1 and 2
    warehouses[1].add_item(type_k=1, quantity=100)
    warehouses[2].add_item(type_k=2, quantity=100)
    
    # Two orders to warehouse 3
    orders = [
        Order(order_id=1, type_k=1, quantity_t=30, warehouse_a=3),
        Order(order_id=2, type_k=2, quantity_t=40, warehouse_a=3),
    ]
    
    sim = Simulation(graph=graph, warehouses=warehouses, orders=orders, solver_type="predictive")
    
    state = sim.run_auto(max_steps=50)
    
    print(f"Result: penalty = {state.total_penalty}, completed = {len(state.completed_orders)}/{len(orders)}")
    assert len(state.completed_orders) == 2, "Both orders should be completed"
    print("[OK] TEST PASSED!")
    return True


if __name__ == "__main__":
    print("\n>>> RUNNING ROUTING TESTS <<<\n")
    
    all_passed = True
    
    try:
        all_passed &= test_chain_routing()
        all_passed &= test_star_routing()
        all_passed &= test_no_direct_connection()
        all_passed &= test_multiple_orders_same_destination()
        
        print("\n" + "=" * 60)
        if all_passed:
            print("[OK] ALL TESTS PASSED!")
        else:
            print("[FAIL] SOME TESTS FAILED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR]: {e}")
        import traceback
        traceback.print_exc()
