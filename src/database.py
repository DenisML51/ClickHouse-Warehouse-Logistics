"""Модуль для работы с ClickHouse."""

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from typing import List, Dict, Tuple, Optional
from .models import ObjectType, Edge, Order, Movement, Penalty, Warehouse


class Database:
    """Класс для работы с ClickHouse."""

    def __init__(self, host: str = "localhost", port: int = 8123, database: str = "logistics"):
        self.host = host
        self.port = port
        self.database = database
        self.client: Optional[Client] = None

    def connect(self) -> bool:
        """Подключиться к ClickHouse."""
        try:
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                database="default"
            )
            # Создаём базу данных если не существует
            self.client.command(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            # Переподключаемся к нужной базе
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                database=self.database
            )
            return True
        except Exception as e:
            print(f"Ошибка подключения к ClickHouse: {e}")
            return False

    def init_schema(self) -> None:
        """Создать все таблицы (DDL)."""
        if not self.client:
            raise RuntimeError("Нет подключения к БД")

        # Таблица типов объектов
        self.client.command("""
            CREATE TABLE IF NOT EXISTS object_types (
                type_id UInt8,
                move_time UInt16,
                move_cost Float32,
                loss_value Float32
            ) ENGINE = MergeTree()
            ORDER BY type_id
        """)

        # Таблица графа складов (рёбра)
        self.client.command("""
            CREATE TABLE IF NOT EXISTS warehouse_graph (
                from_id UInt16,
                to_id UInt16,
                weight UInt16
            ) ENGINE = MergeTree()
            ORDER BY (from_id, to_id)
        """)

        # Таблица начального инвентаря
        self.client.command("""
            CREATE TABLE IF NOT EXISTS initial_inventory (
                warehouse_id UInt16,
                type_k UInt8,
                quantity UInt32
            ) ENGINE = MergeTree()
            ORDER BY (warehouse_id, type_k)
        """)

        # Лист заявок
        self.client.command("""
            CREATE TABLE IF NOT EXISTS order_list (
                order_id UInt32,
                type_k UInt8,
                quantity_t UInt32,
                warehouse_a UInt16
            ) ENGINE = MergeTree()
            ORDER BY order_id
        """)

        # Таблица перемещений (ОТВЕТ)
        self.client.command("""
            CREATE TABLE IF NOT EXISTS movements (
                test_id UInt8,
                step UInt32,
                from_warehouse UInt16,
                to_warehouse UInt16,
                type_k UInt8,
                quantity UInt32
            ) ENGINE = MergeTree()
            ORDER BY (test_id, step)
        """)

        # Таблица штрафов
        self.client.command("""
            CREATE TABLE IF NOT EXISTS penalties (
                test_id UInt8,
                step UInt32,
                order_id UInt32,
                penalty_value UInt32
            ) ENGINE = MergeTree()
            ORDER BY (test_id, step)
        """)

        # Метаданные тестов
        self.client.command("""
            CREATE TABLE IF NOT EXISTS test_metadata (
                test_id UInt8,
                test_name String,
                description String,
                num_warehouses UInt16,
                num_object_types UInt8,
                total_objects UInt32,
                num_orders UInt32
            ) ENGINE = MergeTree()
            ORDER BY test_id
        """)

    def clear_tables(self) -> None:
        """Очистить все таблицы."""
        if not self.client:
            raise RuntimeError("Нет подключения к БД")

        tables = [
            "object_types", "warehouse_graph", "initial_inventory",
            "order_list", "movements", "penalties", "test_metadata"
        ]
        for table in tables:
            self.client.command(f"TRUNCATE TABLE IF EXISTS {table}")

    def insert_object_types(self, types: List[ObjectType]) -> None:
        """Вставить типы объектов."""
        if not self.client or not types:
            return
        data = [[t.type_id, t.move_time, t.move_cost, t.loss_value] for t in types]
        self.client.insert("object_types", data, column_names=["type_id", "move_time", "move_cost", "loss_value"])

    def insert_graph_edges(self, edges: List[Edge]) -> None:
        """Вставить рёбра графа."""
        if not self.client or not edges:
            return
        data = [[e.from_id, e.to_id, e.weight] for e in edges]
        self.client.insert("warehouse_graph", data, column_names=["from_id", "to_id", "weight"])

    def insert_inventory(self, inventory: List[Tuple[int, int, int]]) -> None:
        """Вставить начальный инвентарь: [(warehouse_id, type_k, quantity), ...]."""
        if not self.client or not inventory:
            return
        self.client.insert("initial_inventory", inventory, column_names=["warehouse_id", "type_k", "quantity"])

    def insert_orders(self, orders: List[Order]) -> None:
        """Вставить лист заявок."""
        if not self.client or not orders:
            return
        data = [[o.order_id, o.type_k, o.quantity_t, o.warehouse_a] for o in orders]
        self.client.insert("order_list", data, column_names=["order_id", "type_k", "quantity_t", "warehouse_a"])

    def insert_movements(self, test_id: int, movements: List[Movement]) -> None:
        """Вставить результаты перемещений."""
        if not self.client or not movements:
            return
        data = [[test_id, m.step, m.from_warehouse, m.to_warehouse, m.type_k, m.quantity] for m in movements]
        self.client.insert("movements", data, column_names=["test_id", "step", "from_warehouse", "to_warehouse", "type_k", "quantity"])

    def insert_penalties(self, test_id: int, penalties: List[Penalty]) -> None:
        """Вставить штрафы."""
        if not self.client or not penalties:
            return
        data = [[test_id, p.step, p.order_id, p.penalty_value] for p in penalties]
        self.client.insert("penalties", data, column_names=["test_id", "step", "order_id", "penalty_value"])

    def insert_test_metadata(self, test_id: int, name: str, description: str,
                             num_warehouses: int, num_types: int, total_objects: int, num_orders: int) -> None:
        """Вставить метаданные теста."""
        if not self.client:
            return
        self.client.insert("test_metadata",
                           [[test_id, name, description, num_warehouses, num_types, total_objects, num_orders]],
                           column_names=["test_id", "test_name", "description", "num_warehouses",
                                         "num_object_types", "total_objects", "num_orders"])


    def get_object_types(self) -> List[ObjectType]:
        """Получить все типы объектов."""
        if not self.client:
            return []
        result = self.client.query("SELECT type_id, move_time, move_cost, loss_value FROM object_types")
        return [ObjectType(type_id=r[0], move_time=r[1], move_cost=r[2], loss_value=r[3]) for r in result.result_rows]

    def get_graph_edges(self) -> List[Edge]:
        """Получить все рёбра графа."""
        if not self.client:
            return []
        result = self.client.query("SELECT from_id, to_id, weight FROM warehouse_graph")
        return [Edge(from_id=r[0], to_id=r[1], weight=r[2]) for r in result.result_rows]

    def get_initial_inventory(self) -> List[Tuple[int, int, int]]:
        """Получить начальный инвентарь: [(warehouse_id, type_k, quantity), ...]."""
        if not self.client:
            return []
        result = self.client.query("SELECT warehouse_id, type_k, quantity FROM initial_inventory")
        return [(r[0], r[1], r[2]) for r in result.result_rows]

    def get_orders(self) -> List[Order]:
        """Получить лист заявок."""
        if not self.client:
            return []
        result = self.client.query("SELECT order_id, type_k, quantity_t, warehouse_a FROM order_list ORDER BY order_id")
        return [Order(order_id=r[0], type_k=r[1], quantity_t=r[2], warehouse_a=r[3]) for r in result.result_rows]

    def get_table_preview(self, table_name: str, limit: int = 5) -> Tuple[List[str], List[Tuple]]:
        """Получить превью таблицы (первые N строк)."""
        if not self.client:
            return [], []
        result = self.client.query(f"SELECT * FROM {table_name} LIMIT {limit}")
        return result.column_names, result.result_rows

    def get_total_penalty(self, test_id: int) -> int:
        """Получить общий штраф по тесту."""
        if not self.client:
            return 0
        result = self.client.query(f"SELECT SUM(penalty_value) FROM penalties WHERE test_id = {test_id}")
        val = result.result_rows[0][0] if result.result_rows else 0
        return int(val) if val else 0

    def get_movements_count(self, test_id: int) -> int:
        """Получить количество перемещений по тесту."""
        if not self.client:
            return 0
        result = self.client.query(f"SELECT COUNT() FROM movements WHERE test_id = {test_id}")
        return int(result.result_rows[0][0]) if result.result_rows else 0

