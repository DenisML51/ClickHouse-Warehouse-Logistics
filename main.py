"""
Система оптимизации логистики складов на базе ClickHouse.

Точка входа приложения.
Запуск: uv run main.py
"""

import sys
from typing import Dict, List, Optional

from src.database import Database
from src.graph import WarehouseGraph
from src.models import Warehouse, Order, Movement
from src.simulation import Simulation, SimulationState
from src.tests_generator import TestGenerator
from src import display


class Application:
    """Главный класс приложения."""

    def __init__(self):
        self.db: Optional[Database] = None
        self.graph: Optional[WarehouseGraph] = None
        self.warehouses: Dict[int, Warehouse] = {}
        self.orders: List[Order] = []
        self.simulation: Optional[Simulation] = None
        self.current_test: Optional[dict] = None
        self.test_generator: Optional[TestGenerator] = None

    def connect_to_db(self) -> bool:
        """Подключиться к ClickHouse."""
        display.print_header("Подключение к ClickHouse")
        display.console.print("Подключение к localhost:8123...")

        self.db = Database(host="localhost", port=8123, database="logistics")

        if self.db.connect():
            display.print_success("Подключение установлено!")
            self.db.init_schema()
            display.print_success("Схема БД инициализирована.")
            self.test_generator = TestGenerator(self.db)
            return True
        else:
            display.print_error("Не удалось подключиться к ClickHouse.")
            display.print_warning("Убедитесь, что Docker контейнер запущен: docker-compose up -d")
            return False

    def load_test(self, test_id: int) -> bool:
        """Загрузить тест в память и БД."""
        if not self.test_generator:
            display.print_error("Генератор тестов не инициализирован.")
            return False

        display.print_header(f"Загрузка теста #{test_id}")

        # Получаем все тесты
        all_tests = self.test_generator.get_all_tests()

        if test_id < 1 or test_id > len(all_tests):
            display.print_error(f"Тест #{test_id} не найден. Доступны тесты 1-{len(all_tests)}.")
            return False

        test_data = all_tests[test_id - 1]
        self.current_test = test_data

        # Загружаем в БД
        display.console.print("Загрузка данных в ClickHouse...")
        self.test_generator.load_test_to_db(test_data)
        display.print_success("Данные загружены в БД.")

        # Загружаем в память
        self._load_data_to_memory()

        # Валидация теста
        validation = self.test_generator.validate_test(test_data)
        display.console.print(f"\n[bold]Валидация теста:[/bold]")
        display.console.print(f"  Объектов на складах: {validation['total_inventory']:,}")
        display.console.print(f"  Сумма заявок: {validation['total_orders']:,}")
        if validation['all_valid']:
            display.print_success("Тест корректен: 100 000 объектов, сумма заявок = 100 000")
        else:
            display.print_warning("Тест содержит несоответствия!")

        # Выводим информацию о тесте
        display.print_test_info(test_data)

        # Выводим превью таблиц
        self._show_tables_preview()

        return True

    def _load_data_to_memory(self) -> None:
        """Загрузить данные из БД в память для симуляции."""
        if not self.db:
            return

        # Загружаем граф
        edges = self.db.get_graph_edges()
        self.graph = WarehouseGraph()
        self.graph.load_from_edges(edges)

        # Загружаем инвентарь и создаём объекты складов
        inventory = self.db.get_initial_inventory()
        self.warehouses = {}

        # Собираем уникальные склады
        warehouse_ids = set()
        for wh_id, _, _ in inventory:
            warehouse_ids.add(wh_id)
        for node in self.graph.nodes:
            warehouse_ids.add(node)

        # Создаём объекты складов
        for wh_id in warehouse_ids:
            self.warehouses[wh_id] = Warehouse(id=wh_id, name=f"Склад {wh_id}")

        # Заполняем инвентарь
        for wh_id, type_k, qty in inventory:
            if wh_id in self.warehouses:
                self.warehouses[wh_id].add_item(type_k, qty)
                self.warehouses[wh_id].logs.clear()  # Очищаем логи инициализации

        # Загружаем заявки
        self.orders = self.db.get_orders()

        display.print_success(f"Загружено: {len(self.warehouses)} складов, {len(self.orders)} заявок")

    def _show_tables_preview(self) -> None:
        """Показать превью таблиц из БД."""
        if not self.db:
            return

        display.console.print("\n[bold cyan]Превью таблиц ClickHouse:[/bold cyan]\n")

        tables = ["object_types", "warehouse_graph", "initial_inventory", "order_list"]
        for table_name in tables:
            try:
                columns, rows = self.db.get_table_preview(table_name, limit=5)
                if rows:
                    display.print_table_preview(table_name, columns, rows)
            except Exception as e:
                display.print_warning(f"Не удалось загрузить {table_name}: {e}")

    def show_graph(self) -> None:
        """Показать граф складов."""
        if not self.graph:
            display.print_error("Граф не загружен. Сначала загрузите тест.")
            return

        display.print_header("Граф складов")
        display.print_graph(self.graph)

    def show_inventory(self) -> None:
        """Показать инвентарь складов."""
        if not self.warehouses:
            display.print_error("Данные не загружены. Сначала загрузите тест.")
            return

        display.print_header("Инвентарь складов")
        display.print_inventory_summary(self.warehouses)

    def show_orders(self) -> None:
        """Показать лист заявок."""
        if not self.orders:
            display.print_error("Заявки не загружены. Сначала загрузите тест.")
            return

        display.print_header("Лист заявок")
        display.print_orders_preview(self.orders, limit=20)

    def run_simulation_auto(self) -> None:
        """Запустить симуляцию в автоматическом режиме."""
        if not self.graph or not self.warehouses or not self.orders:
            display.print_error("Данные не загружены. Сначала загрузите тест.")
            return

        display.print_header("Автоматический прогон симуляции")

        # Перезагружаем данные для чистой симуляции
        self._load_data_to_memory()

        self.simulation = Simulation(
            graph=self.graph,
            warehouses=self.warehouses,
            orders=self.orders,
            solver_type="predictive"
        )

        display.console.print("Запуск симуляции...\n")

        state = self.simulation.run_auto(max_steps=len(self.orders) + 100)

        # Выводим результат
        display.print_simulation_result(state)

        # Сохраняем результаты в БД
        if self.db and self.current_test:
            test_id = self.current_test["test_id"]
            self.db.insert_movements(test_id, state.movements_history)
            self.db.insert_penalties(test_id, state.penalties_history)
            display.print_success("Результаты сохранены в ClickHouse.")

        # Показываем таблицу перемещений
        if state.movements_history:
            display.print_movements_table(state.movements_history)

    def run_simulation_interactive(self) -> None:
        """Запустить симуляцию в интерактивном режиме."""
        if not self.graph or not self.warehouses or not self.orders:
            display.print_error("Данные не загружены. Сначала загрузите тест.")
            return

        display.print_header("Интерактивный режим симуляции")

        # Перезагружаем данные для чистой симуляции
        self._load_data_to_memory()

        self.simulation = Simulation(
            graph=self.graph,
            warehouses=self.warehouses,
            orders=self.orders,
            solver_type="predictive"
        )

        display.console.print("Управление:")
        display.console.print("  [Enter] - следующий шаг")
        display.console.print("  [l] - показать логи складов")
        display.console.print("  [i] - показать инвентарь")
        display.console.print("  [a] - переключиться в автоматический режим")
        display.console.print("  [q] - остановить симуляцию")
        display.console.print()

        def interactive_callback(state: SimulationState, move: Optional[Movement]) -> bool:
            display.print_step_info(state, move, self.warehouses)

            while True:
                cmd = display.get_input("[Enter/l/i/a/q]: ").strip().lower()

                if cmd == "" or cmd == "n":
                    return True  # Продолжить
                elif cmd == "l":
                    display.print_warehouse_logs(self.warehouses)
                elif cmd == "i":
                    display.print_inventory_summary(self.warehouses)
                elif cmd == "a":
                    display.console.print("\n[yellow]Переключение в автоматический режим...[/yellow]")
                    return True  # Продолжить, но в авто-режиме
                elif cmd == "q":
                    display.console.print("\n[yellow]Симуляция остановлена.[/yellow]")
                    return False  # Остановить
                else:
                    display.print_warning("Неизвестная команда. Используйте Enter, l, i, a или q.")

        state = self.simulation.run_interactive(interactive_callback, max_steps=len(self.orders) + 100)

        # Выводим итоговый результат
        display.print_simulation_result(state)

        # Сохраняем результаты в БД
        if self.db and self.current_test:
            test_id = self.current_test["test_id"]
            self.db.insert_movements(test_id, state.movements_history)
            self.db.insert_penalties(test_id, state.penalties_history)
            display.print_success("Результаты сохранены в ClickHouse.")

    def show_all_tests_info(self) -> None:
        """Показать информацию о всех 6 тестах."""
        if not self.test_generator:
            display.print_error("Генератор тестов не инициализирован.")
            return

        display.print_header("Доступные тесты")

        all_tests = self.test_generator.get_all_tests()
        for test in all_tests:
            display.print_test_info(test)
            display.console.print()

    def main_menu(self) -> None:
        """Главное меню приложения."""
        while True:
            display.print_header("Система оптимизации логистики")

            display.print_menu([
                ("1", "Показать информацию о всех тестах"),
                ("2", "Загрузить тест (1-6)"),
                ("3", "Показать граф складов"),
                ("4", "Показать инвентарь"),
                ("5", "Показать лист заявок"),
                ("6", "Запустить симуляцию (автоматический режим)"),
                ("7", "Запустить симуляцию (интерактивный режим)"),
                ("0", "Выход")
            ])

            choice = display.get_input()

            if choice == "1":
                self.show_all_tests_info()
            elif choice == "2":
                test_id_str = display.get_input("Введите номер теста (1-6): ")
                try:
                    test_id = int(test_id_str)
                    self.load_test(test_id)
                except ValueError:
                    display.print_error("Введите число от 1 до 6.")
            elif choice == "3":
                self.show_graph()
            elif choice == "4":
                self.show_inventory()
            elif choice == "5":
                self.show_orders()
            elif choice == "6":
                self.run_simulation_auto()
            elif choice == "7":
                self.run_simulation_interactive()
            elif choice == "0":
                display.console.print("\n[cyan]До свидания![/cyan]\n")
                break
            else:
                display.print_warning("Неизвестная команда.")


def main():
    """Точка входа."""
    display.print_header("Логистический оптимизатор v1.0")
    display.console.print("[cyan]Курсовой проект по СУБД[/cyan]")
    display.console.print("[dim]ClickHouse + MergeTree + Python[/dim]")
    display.console.print()

    app = Application()

    # Пытаемся подключиться к БД
    if not app.connect_to_db():
        display.console.print()
        display.print_warning("Для запуска ClickHouse выполните:")
        display.console.print("  [green]docker-compose up -d[/green]")
        display.console.print()

        choice = display.get_input("Попробовать ещё раз? (y/n): ")
        if choice.lower() == "y":
            if not app.connect_to_db():
                display.print_error("Не удалось подключиться. Выход.")
                sys.exit(1)
        else:
            sys.exit(0)

    # Запускаем главное меню
    app.main_menu()


if __name__ == "__main__":
    main()

