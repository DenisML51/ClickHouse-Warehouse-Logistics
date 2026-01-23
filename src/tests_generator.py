"""Генератор 6 тестовых сценариев для системы логистики.

По условию задачи:
- Всегда 100 000 объектов K типов (K < 100)
- Сумма всех заявок = 100 000 (все объекты должны быть забраны)
"""

import random
from typing import List, Tuple, Dict
from .models import ObjectType, Edge, Order
from .database import Database


# Константа: общее количество объектов по условию задачи
TOTAL_OBJECTS = 100_000


class TestGenerator:
    """Генератор тестовых данных."""

    def __init__(self, db: Database):
        self.db = db

    def generate_object_types(self, k: int = 10) -> List[ObjectType]:
        """Генерация K типов объектов (K < 100)."""
        if k >= 100:
            raise ValueError("K должно быть < 100 по условию задачи")
        
        types = []
        for i in range(1, k + 1):
            types.append(ObjectType(
                type_id=i,
                move_time=random.randint(1, 3),
                move_cost=round(random.uniform(10, 100), 2),
                loss_value=round(random.uniform(100, 1000), 2)
            ))
        return types

    # ========== ГЕНЕРАТОРЫ ГРАФОВ ==========

    def generate_chain_graph(self, n: int) -> List[Edge]:
        """Генерация линейного графа (цепочка): 1-2-3-...-N."""
        edges = []
        for i in range(1, n):
            edges.append(Edge(from_id=i, to_id=i + 1, weight=1))
        return edges

    def generate_star_graph(self, n: int) -> List[Edge]:
        """Генерация графа-звезды: центр (1) соединён со всеми."""
        edges = []
        for i in range(2, n + 1):
            edges.append(Edge(from_id=1, to_id=i, weight=1))
        return edges

    def generate_ring_graph(self, n: int) -> List[Edge]:
        """Генерация кольцевого графа: 1-2-3-...-N-1."""
        edges = []
        for i in range(1, n):
            edges.append(Edge(from_id=i, to_id=i + 1, weight=1))
        edges.append(Edge(from_id=n, to_id=1, weight=1))
        return edges

    def generate_grid_graph(self, rows: int, cols: int) -> List[Edge]:
        """Генерация графа-решётки (сетки)."""
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
        """Генерация случайного связного графа."""
        edges = []
        # Остовное дерево для связности
        for i in range(2, n + 1):
            parent = random.randint(1, i - 1)
            edges.append(Edge(from_id=parent, to_id=i, weight=random.randint(1, 3)))
        # Дополнительные рёбра
        for _ in range(extra_edges):
            a, b = random.sample(range(1, n + 1), 2)
            edges.append(Edge(from_id=a, to_id=b, weight=random.randint(1, 3)))
        return edges

    # ========== РАСПРЕДЕЛЕНИЕ ОБЪЕКТОВ ==========

    def distribute_objects_uniform(self, warehouses: int, types: int) -> List[Tuple[int, int, int]]:
        """Равномерное распределение 100 000 объектов по складам и типам."""
        inventory = []
        total = TOTAL_OBJECTS
        per_slot = total // (warehouses * types)
        remainder = total % (warehouses * types)

        for wh in range(1, warehouses + 1):
            for t in range(1, types + 1):
                qty = per_slot
                if remainder > 0:
                    qty += 1
                    remainder -= 1
                if qty > 0:
                    inventory.append((wh, t, qty))

        return inventory

    def distribute_objects_concentrated(self, warehouses: int, types: int, 
                                        concentrate_on: List[int]) -> List[Tuple[int, int, int]]:
        """Концентрация 100 000 объектов на определённых складах."""
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

    def distribute_objects_sparse(self, warehouses: int, types: int) -> List[Tuple[int, int, int]]:
        """Разреженное распределение 100 000 объектов (много мелких партий)."""
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

    # ========== ГЕНЕРАЦИЯ ЗАЯВОК (СУММА = 100 000) ==========

    def generate_orders_from_inventory(self, inventory: List[Tuple[int, int, int]],
                                       target_warehouses: List[int] = None,
                                       min_order_size: int = 100,
                                       max_order_size: int = 2000) -> List[Order]:
        """
        Генерация листа заявок на основе инвентаря.
        Сумма всех quantity_t = TOTAL_OBJECTS (100 000).
        
        Args:
            inventory: начальный инвентарь [(wh, type_k, qty), ...]
            target_warehouses: если указано, заявки только на эти склады
            min_order_size, max_order_size: размер заявок
        """
        # Подсчитаем общее количество по типам
        type_totals: Dict[int, int] = {}
        for wh, t, qty in inventory:
            type_totals[t] = type_totals.get(t, 0) + qty

        # Определяем доступные склады
        all_warehouses = list(set(wh for wh, _, _ in inventory))
        if target_warehouses:
            available_warehouses = target_warehouses
        else:
            available_warehouses = all_warehouses

        orders = []
        order_id = 1
        remaining_total = TOTAL_OBJECTS
        remaining_by_type = dict(type_totals)

        while remaining_total > 0:
            # Выбираем тип, у которого ещё остались объекты
            available_types = [t for t, qty in remaining_by_type.items() if qty > 0]
            if not available_types:
                break

            t = random.choice(available_types)
            wh = random.choice(available_warehouses)

            # Размер заявки
            max_possible = min(remaining_by_type[t], max_order_size, remaining_total)
            if max_possible < min_order_size:
                qty = max_possible
            else:
                qty = random.randint(min(min_order_size, max_possible), max_possible)

            if qty > 0:
                orders.append(Order(
                    order_id=order_id,
                    type_k=t,
                    quantity_t=qty,
                    warehouse_a=wh
                ))
                order_id += 1
                remaining_total -= qty
                remaining_by_type[t] -= qty

        return orders

    def generate_orders_ideal(self, inventory: List[Tuple[int, int, int]]) -> List[Order]:
        """
        Генерация заявок для идеального случая (штраф = 0).
        Заявки точно совпадают с тем, что лежит на каждом складе.
        """
        # Группируем инвентарь
        inv_dict: Dict[Tuple[int, int], int] = {}
        for wh, t, qty in inventory:
            key = (wh, t)
            inv_dict[key] = inv_dict.get(key, 0) + qty

        orders = []
        order_id = 1

        for (wh, t), total_qty in inv_dict.items():
            remaining = total_qty
            while remaining > 0:
                # Дробим на заявки по 500-2000 штук
                qty = min(remaining, random.randint(500, 2000))
                orders.append(Order(
                    order_id=order_id,
                    type_k=t,
                    quantity_t=qty,
                    warehouse_a=wh  # Заявка на тот же склад, где лежит товар!
                ))
                order_id += 1
                remaining -= qty

        # Перемешиваем и перенумеровываем
        random.shuffle(orders)
        for i, order in enumerate(orders, 1):
            order.order_id = i

        return orders

    # ========== 6 ТЕСТОВЫХ СЦЕНАРИЕВ ==========

    def generate_test_1(self) -> dict:
        """
        Тест 1: Идеальный случай (Штраф = 0).
        Все 100 000 товаров уже на тех складах, где их будут забирать.
        """
        n_warehouses = 10
        n_types = 10

        object_types = self.generate_object_types(n_types)
        edges = self.generate_star_graph(n_warehouses)
        inventory = self.distribute_objects_uniform(n_warehouses, n_types)
        orders = self.generate_orders_ideal(inventory)

        return {
            "test_id": 1,
            "name": "Идеальный случай",
            "description": f"100 000 объектов уже на нужных складах. Ожидаемый штраф: 0",
            "object_types": object_types,
            "edges": edges,
            "inventory": inventory,
            "orders": orders,
            "n_warehouses": n_warehouses,
            "n_types": n_types,
            "total_objects": TOTAL_OBJECTS
        }

    def generate_test_2(self) -> dict:
        """
        Тест 2: Линейная магистраль.
        100 000 объектов на складе 1, все заявки на склад N.
        """
        n_warehouses = 10
        n_types = 5

        object_types = self.generate_object_types(n_types)
        edges = self.generate_chain_graph(n_warehouses)

        # Все 100 000 на складе 1
        inventory = self.distribute_objects_concentrated(n_warehouses, n_types, [1])

        # Все заявки на дальний склад
        orders = self.generate_orders_from_inventory(
            inventory,
            target_warehouses=[n_warehouses],
            min_order_size=500,
            max_order_size=3000
        )

        return {
            "test_id": 2,
            "name": "Линейная магистраль",
            "description": f"Цепочка 1-{n_warehouses}. 100 000 объектов на складе 1, заявки на складе {n_warehouses}.",
            "object_types": object_types,
            "edges": edges,
            "inventory": inventory,
            "orders": orders,
            "n_warehouses": n_warehouses,
            "n_types": n_types,
            "total_objects": TOTAL_OBJECTS
        }

    def generate_test_3(self) -> dict:
        """
        Тест 3: Центральный хаб (Звезда).
        100 000 объектов на периферии, все заявки в центре.
        """
        n_warehouses = 8
        n_types = 8

        object_types = self.generate_object_types(n_types)
        edges = self.generate_star_graph(n_warehouses)

        # Товары на периферии (склады 2-8)
        peripheral = list(range(2, n_warehouses + 1))
        inventory = self.distribute_objects_concentrated(n_warehouses, n_types, peripheral)

        # Заявки в центре (склад 1)
        orders = self.generate_orders_from_inventory(
            inventory,
            target_warehouses=[1],
            min_order_size=500,
            max_order_size=2500
        )

        return {
            "test_id": 3,
            "name": "Центральный хаб",
            "description": "Звезда. 100 000 объектов на периферии, заявки в центре.",
            "object_types": object_types,
            "edges": edges,
            "inventory": inventory,
            "orders": orders,
            "n_warehouses": n_warehouses,
            "n_types": n_types,
            "total_objects": TOTAL_OBJECTS
        }

    def generate_test_4(self) -> dict:
        """
        Тест 4: Кольцо с разбросанными товарами.
        100 000 объектов распределены неравномерно, заявки со всех складов.
        """
        n_warehouses = 12
        n_types = 6

        object_types = self.generate_object_types(n_types)
        edges = self.generate_ring_graph(n_warehouses)
        inventory = self.distribute_objects_sparse(n_warehouses, n_types)

        # Заявки со всех складов
        orders = self.generate_orders_from_inventory(
            inventory,
            min_order_size=200,
            max_order_size=1500
        )

        return {
            "test_id": 4,
            "name": "Кольцо с разбросом",
            "description": "Кольцо из 12 складов. 100 000 объектов разбросаны неравномерно.",
            "object_types": object_types,
            "edges": edges,
            "inventory": inventory,
            "orders": orders,
            "n_warehouses": n_warehouses,
            "n_types": n_types,
            "total_objects": TOTAL_OBJECTS
        }

    def generate_test_5(self) -> dict:
        """
        Тест 5: Сетка с множеством типов.
        100 000 объектов 50 типов на сетке 5x4.
        """
        n_warehouses = 20
        n_types = 50  # Много типов (но < 100)

        object_types = self.generate_object_types(n_types)
        edges = self.generate_grid_graph(5, 4)  # 5x4 = 20 складов
        inventory = self.distribute_objects_uniform(n_warehouses, n_types)

        orders = self.generate_orders_from_inventory(
            inventory,
            min_order_size=100,
            max_order_size=1000
        )

        return {
            "test_id": 5,
            "name": "Сетка с множеством типов",
            "description": "Сетка 5x4. 100 000 объектов 50 типов.",
            "object_types": object_types,
            "edges": edges,
            "inventory": inventory,
            "orders": orders,
            "n_warehouses": n_warehouses,
            "n_types": n_types,
            "total_objects": TOTAL_OBJECTS
        }

    def generate_test_6(self) -> dict:
        """
        Тест 6: Случайный сложный граф.
        100 000 объектов, случайная топология, концентрация на 3 складах.
        """
        n_warehouses = 15
        n_types = 15

        object_types = self.generate_object_types(n_types)
        edges = self.generate_random_connected_graph(n_warehouses, extra_edges=10)

        # Концентрация на 3 случайных складах
        concentrated_warehouses = random.sample(range(1, n_warehouses + 1), 3)
        inventory = self.distribute_objects_concentrated(n_warehouses, n_types, concentrated_warehouses)

        # Заявки со всех складов
        orders = self.generate_orders_from_inventory(
            inventory,
            min_order_size=300,
            max_order_size=2000
        )

        return {
            "test_id": 6,
            "name": "Случайный сложный граф",
            "description": f"15 складов. 100 000 объектов на складах {concentrated_warehouses}.",
            "object_types": object_types,
            "edges": edges,
            "inventory": inventory,
            "orders": orders,
            "n_warehouses": n_warehouses,
            "n_types": n_types,
            "total_objects": TOTAL_OBJECTS
        }

    # ========== ЗАГРУЗКА В БД ==========

    def load_test_to_db(self, test_data: dict) -> None:
        """Загрузить тест в базу данных."""
        self.db.clear_tables()

        self.db.insert_object_types(test_data["object_types"])
        self.db.insert_graph_edges(test_data["edges"])
        self.db.insert_inventory(test_data["inventory"])
        self.db.insert_orders(test_data["orders"])
        self.db.insert_test_metadata(
            test_id=test_data["test_id"],
            name=test_data["name"],
            description=test_data["description"],
            num_warehouses=test_data["n_warehouses"],
            num_types=test_data["n_types"],
            total_objects=test_data["total_objects"],
            num_orders=len(test_data["orders"])
        )

    def get_all_tests(self) -> List[dict]:
        """Получить все 6 тестов."""
        return [
            self.generate_test_1(),
            self.generate_test_2(),
            self.generate_test_3(),
            self.generate_test_4(),
            self.generate_test_5(),
            self.generate_test_6()
        ]

    def validate_test(self, test_data: dict) -> dict:
        """Проверить корректность теста."""
        inventory = test_data["inventory"]
        orders = test_data["orders"]

        total_inventory = sum(qty for _, _, qty in inventory)
        total_orders = sum(o.quantity_t for o in orders)

        return {
            "test_id": test_data["test_id"],
            "total_inventory": total_inventory,
            "total_orders": total_orders,
            "inventory_valid": total_inventory == TOTAL_OBJECTS,
            "orders_valid": total_orders == TOTAL_OBJECTS,
            "all_valid": total_inventory == TOTAL_OBJECTS and total_orders == TOTAL_OBJECTS
        }
