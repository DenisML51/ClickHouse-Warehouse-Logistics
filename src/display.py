"""Модуль для красивого вывода информации в консоль."""

from typing import Dict, List, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text
from rich import box

from .models import Order, Movement, Warehouse, ActiveOrder, CompletedOrderInfo
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

    # Информация о выполненных заявках на этом шаге
    if hasattr(state, 'completed_this_step') and state.completed_this_step:
        completed_table = Table(title="✓ Выполненные заявки на этом шаге", box=box.SIMPLE, style="green")
        completed_table.add_column("Заявка #", style="cyan")
        completed_table.add_column("Тип K", style="yellow")
        completed_table.add_column("Кол-во T", style="magenta")
        completed_table.add_column("Склад A", style="blue")
        completed_table.add_column("Создана", style="dim")
        completed_table.add_column("Выполнена", style="green")
        completed_table.add_column("Ожидание", style="red")
        
        for info in state.completed_this_step:
            completed_table.add_row(
                str(info.order.order_id),
                str(info.order.type_k),
                str(info.order.quantity_t),
                str(info.order.warehouse_a),
                f"шаг {info.created_at_step}",
                f"шаг {info.completed_at_step}",
                f"{info.wait_steps} ходов" if info.wait_steps > 0 else "0 (сразу)"
            )
        
        console.print(completed_table)

    # Информация о перемещении
    if move:
        reason_str = f" (для заявки #{move.reason_order_id})" if move.reason_order_id else ""
        console.print(Panel(
            f"[green]Перемещение:[/green] Склад {move.from_warehouse} → Склад {move.to_warehouse}{reason_str}\n"
            f"Тип товара: {move.type_k}, Количество: {move.quantity}",
            title="Действие",
            box=box.ROUNDED
        ))
    else:
        console.print(Panel("[yellow]Перемещение не требуется[/yellow]", title="Действие", box=box.ROUNDED))

    # Товары в пути
    if hasattr(state, 'in_transit') and state.in_transit:
        transit_table = Table(title="Товары в пути", box=box.SIMPLE)
        transit_table.add_column("Откуда", style="cyan")
        transit_table.add_column("Куда", style="green")
        transit_table.add_column("Тип K", style="yellow")
        transit_table.add_column("Кол-во", style="magenta")
        transit_table.add_column("Прибытие", style="blue")

        for item in state.in_transit[:5]:  # Показываем до 5 товаров в пути
            transit_table.add_row(
                str(item.from_warehouse),
                str(item.to_warehouse),
                str(item.type_k),
                str(item.quantity),
                f"шаг {item.arrival_step}"
            )
        
        if len(state.in_transit) > 5:
            transit_table.add_row("...", "...", "...", "...", "...")

        console.print(transit_table)

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
    in_transit_count = len(state.in_transit) if hasattr(state, 'in_transit') else 0
    console.print(f"[red]Штраф за шаг: {step_penalty}[/red] | [yellow]Общий штраф: {state.total_penalty}[/yellow] | [cyan]В пути: {in_transit_count}[/cyan]")


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
    """Вывести итоговый результат симуляции с полной статистикой."""
    console.print()
    
    # === Статистика по выполненным заявкам ===
    total_wait = 0
    instant_completed = 0
    max_wait = 0
    
    if state.completed_orders:
        for info in state.completed_orders:
            total_wait += info.wait_steps
            if info.wait_steps == 0:
                instant_completed += 1
            if info.wait_steps > max_wait:
                max_wait = info.wait_steps
        avg_wait = total_wait / len(state.completed_orders)
    else:
        avg_wait = 0
    
    # === Время выполнения ===
    exec_time = state.end_time - state.start_time if hasattr(state, 'end_time') and state.end_time > 0 else 0
    
    # === Основной результат ===
    total_orders = len(state.completed_orders) + len(state.active_orders)
    completion_rate = len(state.completed_orders) / total_orders * 100 if total_orders > 0 else 0
    
    result_text = (
        f"[bold green]СИМУЛЯЦИЯ ЗАВЕРШЕНА[/bold green]\n\n"
        f"[cyan]--- Основные показатели ---[/cyan]\n"
        f"Всего шагов: {state.current_step}\n"
        f"Выполнено заявок: {len(state.completed_orders)}/{total_orders} ({completion_rate:.1f}%)\n"
        f"Невыполненных: {len(state.active_orders)}\n"
        f"[bold red]ОБЩИЙ ШТРАФ: {state.total_penalty}[/bold red]\n"
    )
    
    # === Сравнение с теорией ===
    if hasattr(state, 'theoretical_min_penalty'):
        theory_min = state.theoretical_min_penalty
        if theory_min > 0:
            ratio = state.total_penalty / theory_min
            result_text += (
                f"\n[cyan]--- Сравнение с теорией ---[/cyan]\n"
                f"Теоретич. минимум (нижняя граница): {theory_min}\n"
                f"Реальный штраф: {state.total_penalty}\n"
                f"Соотношение: {ratio:.1f}x (чем ближе к 1, тем лучше)\n"
            )
        else:
            result_text += f"\n[green]Теоретич. минимум: 0 (идеальный случай)[/green]\n"
    
    # === Статистика ожидания ===
    if state.completed_orders:
        result_text += (
            f"\n[cyan]--- Статистика ожидания ---[/cyan]\n"
            f"Выполнено сразу (0 ходов): {instant_completed} ({instant_completed/len(state.completed_orders)*100:.1f}%)\n"
            f"Среднее ожидание: {avg_wait:.1f} ходов\n"
            f"Макс. ожидание: {max_wait} ходов\n"
        )
    
    # === Статистика перемещений ===
    total_items = state.total_items_moved if hasattr(state, 'total_items_moved') else 0
    result_text += (
        f"\n[cyan]--- Статистика перемещений ---[/cyan]\n"
        f"Всего операций: {len(state.movements_history)}\n"
        f"Перемещено товаров: {total_items:,}\n"
        f"Стоимость перемещений: {state.total_move_cost:,.2f}\n"
    )
    
    # Распределение по типам
    if hasattr(state, 'moves_by_type') and state.moves_by_type:
        types_str = ", ".join([f"T{k}:{v}" for k, v in sorted(state.moves_by_type.items())[:5]])
        if len(state.moves_by_type) > 5:
            types_str += "..."
        result_text += f"По типам: {types_str}\n"
    
    # === Производительность ===
    if exec_time > 0:
        steps_per_sec = state.current_step / exec_time
        result_text += (
            f"\n[cyan]--- Производительность ---[/cyan]\n"
            f"Время выполнения: {exec_time:.2f} сек\n"
            f"Скорость: {steps_per_sec:.0f} шагов/сек\n"
        )
    
    # === Сложность алгоритма ===
    n_warehouses = len(set(m.from_warehouse for m in state.movements_history) | 
                      set(m.to_warehouse for m in state.movements_history)) if state.movements_history else 0
    n_types = len(state.moves_by_type) if hasattr(state, 'moves_by_type') else 0
    
    result_text += (
        f"\n[cyan]--- Сложность ---[/cyan]\n"
        f"O(S * N * K) где S={state.current_step}, N~{n_warehouses}, K~{n_types}\n"
        f"Эвристический алгоритм (полиномиальное время)\n"
    )
    
    # === Предупреждения ===
    if hasattr(state, 'unfulfillable_orders') and state.unfulfillable_orders:
        result_text += f"\n[red]! Невыполнимых заявок (нет товара): {len(state.unfulfillable_orders)}[/red]\n"
    
    if hasattr(state, 'in_transit') and state.in_transit:
        result_text += f"[yellow]! Товаров в пути: {len(state.in_transit)}[/yellow]\n"
    
    if hasattr(state, 'steps_without_progress') and state.steps_without_progress > 100:
        result_text += f"[yellow]! Шагов без прогресса: {state.steps_without_progress}[/yellow]\n"
    
    # === Оценка эффективности ===
    if completion_rate == 100 and state.total_penalty == 0:
        efficiency = "[bold green]ИДЕАЛЬНО[/bold green] - все заявки выполнены без штрафа"
    elif completion_rate == 100:
        efficiency = "[green]ОТЛИЧНО[/green] - все заявки выполнены"
    elif completion_rate >= 90:
        efficiency = "[yellow]ХОРОШО[/yellow] - большинство заявок выполнено"
    else:
        efficiency = "[red]ТРЕБУЕТ УЛУЧШЕНИЯ[/red]"
    
    result_text += f"\n[bold]Оценка: {efficiency}[/bold]"
    
    console.print(Panel(
        result_text,
        title="ИТОГОВЫЙ ОТЧЁТ",
        style="green" if state.total_penalty == 0 else "cyan",
        box=box.DOUBLE
    ))
    
    # Таблица выполненных заявок
    if state.completed_orders:
        print_completed_orders_table(state.completed_orders)


def print_completed_orders_table(completed_orders: List, limit: int = 15) -> None:
    """Вывести таблицу выполненных заявок."""
    table = Table(title=f"Выполненные заявки (первые {min(limit, len(completed_orders))} из {len(completed_orders)})", box=box.ROUNDED)
    table.add_column("Заявка #", style="cyan")
    table.add_column("Тип K", style="green")
    table.add_column("Кол-во T", style="yellow")
    table.add_column("Склад A", style="magenta")
    table.add_column("Создана", style="dim")
    table.add_column("Выполнена", style="blue")
    table.add_column("Ожидание", style="red")

    for info in completed_orders[:limit]:
        wait_str = f"{info.wait_steps} ходов" if info.wait_steps > 0 else "[green]сразу[/green]"
        table.add_row(
            str(info.order.order_id),
            str(info.order.type_k),
            str(info.order.quantity_t),
            str(info.order.warehouse_a),
            f"шаг {info.created_at_step}",
            f"шаг {info.completed_at_step}",
            wait_str
        )

    if len(completed_orders) > limit:
        table.add_row("...", "...", "...", "...", "...", "...", "...")

    console.print(table)


def print_movements_table(movements: List[Movement], limit: int = 20) -> None:
    """Вывести таблицу перемещений."""
    table = Table(title=f"Таблица перемещений (первые {limit})", box=box.ROUNDED)
    table.add_column("Шаг", style="cyan")
    table.add_column("Откуда", style="green")
    table.add_column("Куда", style="yellow")
    table.add_column("Тип K", style="magenta")
    table.add_column("Кол-во", style="blue")
    table.add_column("Для заявки #", style="dim")

    for move in movements[:limit]:
        table.add_row(
            str(move.step),
            str(move.from_warehouse),
            str(move.to_warehouse),
            str(move.type_k),
            str(move.quantity),
            str(move.reason_order_id) if move.reason_order_id else "-"
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

