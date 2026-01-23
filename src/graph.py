"""Модуль для работы с графом складов и алгоритмом Дейкстры."""

import heapq
from typing import Dict, List, Tuple, Optional, Set
from .models import Edge


class WarehouseGraph:
    """Граф складов с поддержкой поиска кратчайших путей."""

    def __init__(self):
        # Список смежности: {node_id: [(neighbor_id, weight), ...]}
        self.adjacency: Dict[int, List[Tuple[int, int]]] = {}
        self.nodes: Set[int] = set()

    def add_edge(self, from_id: int, to_id: int, weight: int = 1) -> None:
        """Добавить ребро (двустороннее по умолчанию)."""
        if from_id not in self.adjacency:
            self.adjacency[from_id] = []
        if to_id not in self.adjacency:
            self.adjacency[to_id] = []

        self.adjacency[from_id].append((to_id, weight))
        self.adjacency[to_id].append((from_id, weight))

        self.nodes.add(from_id)
        self.nodes.add(to_id)

    def load_from_edges(self, edges: List[Edge]) -> None:
        """Загрузить граф из списка рёбер."""
        self.adjacency.clear()
        self.nodes.clear()

        for edge in edges:
            # Проверяем, не добавлено ли уже это ребро (для двунаправленного графа)
            if (edge.to_id, edge.weight) not in self.adjacency.get(edge.from_id, []):
                self.add_edge(edge.from_id, edge.to_id, edge.weight)

    def dijkstra(self, start: int) -> Tuple[Dict[int, int], Dict[int, Optional[int]]]:
        """
        Алгоритм Дейкстры для поиска кратчайших путей от start до всех вершин.

        Returns:
            distances: {node_id: distance} - расстояния от start
            predecessors: {node_id: prev_node_id} - предшественники для восстановления пути
        """
        distances: Dict[int, int] = {node: float('inf') for node in self.nodes}
        predecessors: Dict[int, Optional[int]] = {node: None for node in self.nodes}
        distances[start] = 0

        # Приоритетная очередь: (distance, node_id)
        pq = [(0, start)]

        while pq:
            current_dist, current = heapq.heappop(pq)

            if current_dist > distances[current]:
                continue

            for neighbor, weight in self.adjacency.get(current, []):
                distance = current_dist + weight

                if distance < distances[neighbor]:
                    distances[neighbor] = distance
                    predecessors[neighbor] = current
                    heapq.heappush(pq, (distance, neighbor))

        return distances, predecessors

    def get_shortest_path(self, start: int, end: int) -> Tuple[List[int], int]:
        """
        Получить кратчайший путь от start до end.

        Returns:
            path: список вершин пути [start, ..., end]
            distance: длина пути (или inf если пути нет)
        """
        distances, predecessors = self.dijkstra(start)

        if distances[end] == float('inf'):
            return [], float('inf')

        # Восстанавливаем путь
        path = []
        current = end
        while current is not None:
            path.append(current)
            current = predecessors[current]

        path.reverse()
        return path, distances[end]

    def get_distance(self, start: int, end: int) -> int:
        """Получить расстояние между двумя вершинами."""
        distances, _ = self.dijkstra(start)
        return distances.get(end, float('inf'))

    def get_neighbors(self, node_id: int) -> List[Tuple[int, int]]:
        """Получить соседей вершины: [(neighbor_id, weight), ...]."""
        return self.adjacency.get(node_id, [])

    def get_all_nodes(self) -> List[int]:
        """Получить все вершины графа."""
        return sorted(list(self.nodes))

    def find_nearest_with_item(self, target: int, warehouses_with_item: List[int]) -> Tuple[Optional[int], int]:
        """
        Найти ближайший склад к target, на котором есть нужный товар.

        Args:
            target: целевой склад (куда нужно доставить)
            warehouses_with_item: список складов, где есть товар

        Returns:
            (warehouse_id, distance) или (None, inf) если не найдено
        """
        if not warehouses_with_item:
            return None, float('inf')

        distances, _ = self.dijkstra(target)

        best_warehouse = None
        best_distance = float('inf')

        for wh_id in warehouses_with_item:
            if wh_id in distances and distances[wh_id] < best_distance:
                best_distance = distances[wh_id]
                best_warehouse = wh_id

        return best_warehouse, best_distance

    def get_next_hop(self, start: int, end: int) -> Optional[int]:
        """
        Получить следующую вершину на кратчайшем пути от start к end.
        Используется для пошагового перемещения.
        """
        if start == end:
            return None

        path, _ = self.get_shortest_path(start, end)
        if len(path) < 2:
            return None

        return path[1]  # Следующая вершина после start

    def get_edge_weight(self, from_id: int, to_id: int) -> int:
        """
        Получить вес ребра между двумя вершинами.
        По условию задачи: вес ребра определяет время перемещения между складами.
        
        Returns:
            Вес ребра или 1 по умолчанию (если ребро не найдено, но склады соседние).
        """
        neighbors = self.adjacency.get(from_id, [])
        for neighbor, weight in neighbors:
            if neighbor == to_id:
                return weight
        return 1  # Значение по умолчанию

    def are_neighbors(self, node1: int, node2: int) -> bool:
        """Проверить, являются ли два склада соседними (связаны ребром)."""
        neighbors = self.adjacency.get(node1, [])
        return any(neighbor == node2 for neighbor, _ in neighbors)

