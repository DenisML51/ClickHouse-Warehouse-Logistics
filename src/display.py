"""Модуль для красивого вывода информации в консоль."""

from typing import Dict, List, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text
from rich import box

from .models import Order, Movement, Warehouse, ActiveOrder
from .graph import WarehouseGraph
from .simulation import SimulationState


console = Console(force_terminal=True)


def print_header(text: str) -> None:
    """Вывести заголовок."""
    console.print()
    console.print(Panel(text, style="bold cyan", box=box.DOUBLE))
    console.print()


def print_test_info(test_data: dict) -> None:
    """Вывести информацию о тесте."""
    table = Table(title=f"Тест #{test_data['test_id']}: {test_data['name']}", box=box.ROUNDED)
    table.add_column("Параметр", style="cyan")
    table.add_column("Значение", style="green")

    table.add_row("Описание", test_data['description'])
    table.add_row("Складов (N)", str(test_data['n_warehouses']))
    table.add_row("Типов товаров (K)", str(test_data['n_types']))
    table.add_row("Всего объектов", f"{test_data['total_objects']:,}")
    table.add_row("Количество заявок", str(len(test_data['orders'])))
    
    # Подсчёт суммы заявок
    total_orders_qty = sum(o.quantity_t for o in test_data['orders'])
    table.add_row("Сумма заявок (K*T)", f"{total_orders_qty:,}")

    console.print(table)


def print_table_preview(table_name: str, columns: List[str], rows: List[Tuple], limit: int = 5) -> None:
    """Вывести превью таблицы."""
    table = Table(title=f"Таблица: {table_name} (первые {limit} строк)", box=box.SIMPLE)

    for col in columns:
        table.add_column(col, style="cyan")

    for row in rows[:limit]:
        table.add_row(*[str(v) for v in row])

    console.print(table)


def print_graph(graph: WarehouseGraph) -> None:
    """Вывести граф в виде дерева."""
    tree = Tree("[bold cyan]Граф складов[/bold cyan]")

    for node in sorted(graph.nodes):
        neighbors = graph.get_neighbors(node)
        branch = tree.add(f"[green]Склад {node}[/green]")
        for neighbor, weight in neighbors:
            branch.add(f"→ Склад {neighbor} (вес: {weight})")

    console.print(tree)


def print_inventory_summary(warehouses: Dict[int, Warehouse]) -> None:
    """Вывести сводку по инвентарю складов."""
    table = Table(title="Инвентарь складов", box=box.ROUNDED)
    table.add_column("Склад", style="cyan")
    table.add_column("Всего товаров", style="green")
    table.add_column("По типам", style="yellow")

    for wh_id in sorted(warehouses.keys()):
        wh = warehouses[wh_id]
        total = wh.get_total_items()
        types_str = ", ".join([f"t{k}:{v}" for k, v in sorted(wh.inventory.items()) if v > 0][:5])
        if len(wh.inventory) > 5:
            types_str += "..."
        table.add_row(f"Склад {wh_id}", str(total), types_str or "-")

    console.print(table)


def print_orders_preview(orders: List[Order], limit: int = 10) -> None:
    """Вывести превью заявок."""
    table = Table(title=f"Лист заявок (первые {limit})", box=box.ROUNDED)
    table.add_column("#", style="cyan")
    table.add_column("Тип K", style="green")
    table.add_column("Кол-во T", style="yellow")
    table.add_column("Склад A", style="magenta")

    for order in orders[:limit]:
        table.add_row(
            str(order.order_id),
            str(order.type_k),
            str(order.quantity_t),
            str(order.warehouse_a)
        )

    if len(orders) > limit:
        table.add_row("...", "...", "...", "...")

    console.print(table)


def print_step_info(state: SimulationState, move: Optional[Movement], warehouses: Dict[int, Warehouse]) -> None:
    """Вывести информацию о текущем шаге."""
    console.print()
    console.rule(f"[bold cyan]Шаг {state.current_step}[/bold cyan]")

    # Информация о перемещении
    if move:
        console.print(Panel(
            f"[green]Перемещение:[/green] Склад {move.from_warehouse} → Склад {move.to_warehouse}\n"
            f"Тип товара: {move.type_k}, Количество: {move.quantity}",
            title="Действие",
            box=box.ROUNDED
        ))
    else:
        console.print(Panel("[yellow]Перемещение не требуется[/yellow]", title="Действие", box=box.ROUNDED))

    # Активные заявки
    if state.active_orders:
        orders_table = Table(title="Активные заявки (невыполненные)", box=box.SIMPLE)
        orders_table.add_column("#", style="cyan")
        orders_table.add_column("Тип K", style="green")
        orders_table.add_column("Кол-во T", style="yellow")
        orders_table.add_column("Склад A", style="magenta")
        orders_table.add_column("Ожидает ходов", style="red")

        for active in state.active_orders:
            orders_table.add_row(
                str(active.order.order_id),
                str(active.order.type_k),
                str(active.order.quantity_t),
                str(active.order.warehouse_a),
                str(active.penalty_accumulated)
            )

        console.print(orders_table)
    else:
        console.print("[green]Все заявки выполнены![/green]")

    # Статистика
    step_penalty = len(state.active_orders)
    console.print(f"[red]Штраф за шаг: {step_penalty}[/red] | [yellow]Общий штраф: {state.total_penalty}[/yellow]")


def print_warehouse_logs(warehouses: Dict[int, Warehouse], last_n: int = 5) -> None:
    """Вывести последние логи складов."""
    console.print()
    console.print("[bold cyan]Логи складов:[/bold cyan]")

    for wh_id in sorted(warehouses.keys()):
        wh = warehouses[wh_id]
        if wh.logs:
            console.print(f"\n[green]Склад {wh_id}:[/green]")
            for log in wh.logs[-last_n:]:
                console.print(f"  • {log}")


def print_simulation_result(state: SimulationState) -> None:
    """Вывести итоговый результат симуляции."""
    console.print()
    console.print(Panel(
        f"[bold]Симуляция завершена![/bold]\n\n"
        f"Всего шагов: {state.current_step}\n"
        f"Выполнено заявок: {len(state.completed_orders)}\n"
        f"Невыполненных заявок: {len(state.active_orders)}\n"
        f"Всего перемещений: {len(state.movements_history)}\n"
        f"[bold red]ОБЩИЙ ШТРАФ: {state.total_penalty}[/bold red]",
        title="Результат",
        style="green" if state.total_penalty == 0 else "yellow",
        box=box.DOUBLE
    ))


def print_movements_table(movements: List[Movement], limit: int = 20) -> None:
    """Вывести таблицу перемещений."""
    table = Table(title=f"Таблица перемещений (первые {limit})", box=box.ROUNDED)
    table.add_column("Шаг", style="cyan")
    table.add_column("Откуда", style="green")
    table.add_column("Куда", style="yellow")
    table.add_column("Тип K", style="magenta")
    table.add_column("Кол-во", style="blue")

    for move in movements[:limit]:
        table.add_row(
            str(move.step),
            str(move.from_warehouse),
            str(move.to_warehouse),
            str(move.type_k),
            str(move.quantity)
        )

    if len(movements) > limit:
        table.add_row("...", "...", "...", "...", "...")

    console.print(table)


def print_menu(options: List[Tuple[str, str]]) -> None:
    """Вывести меню."""
    console.print()
    for key, description in options:
        console.print(f"  [cyan][{key}][/cyan] {description}")
    console.print()


def get_input(prompt: str = "Выберите действие: ") -> str:
    """Получить ввод от пользователя."""
    return console.input(f"[bold yellow]{prompt}[/bold yellow]")


def print_error(message: str) -> None:
    """Вывести сообщение об ошибке."""
    console.print(f"[bold red]Ошибка:[/bold red] {message}")


def print_success(message: str) -> None:
    """Вывести сообщение об успехе."""
    console.print(f"[bold green][OK][/bold green] {message}")


def print_warning(message: str) -> None:
    """Вывести предупреждение."""
    console.print(f"[bold yellow][!][/bold yellow] {message}")

