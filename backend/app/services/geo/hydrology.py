
from typing import Dict, List, Tuple, Any

class HydrologyService:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height

    def calculate_flow(self, tiles: List[Any]) -> Dict[int, dict]:
        """
        Returns a dict: { tile_id: { 'next_tile_id': int, 'flow': float } }
        """
        tile_map = {(t.x, t.y): t for t in tiles}
        flow_directions = {} 
        
        # 1. Calculate directions
        for tile in tiles:
            # Skip oceans/lakes for flow source, but they can be targets
            # Actually, rivers flow INTO oceans.
            if getattr(tile, 'is_lake', False) or tile.elevation < 0:
                continue
                
            neighbors = self._get_hex_neighbors(tile.x, tile.y)
            lowest_neighbor = None
            min_elev = tile.elevation
            
            for nx, ny in neighbors:
                # Handle wrapping for x
                nx = nx % self.width
                if 0 <= ny < self.height:
                    neighbor = tile_map.get((nx, ny))
                    if neighbor and neighbor.elevation < min_elev:
                        min_elev = neighbor.elevation
                        lowest_neighbor = neighbor
            
            if lowest_neighbor:
                flow_directions[tile.id] = lowest_neighbor.id

        # 2. Accumulate Flux
        # Base flux = humidity * area (assume unit area)
        flux = {t.id: getattr(t, 'humidity', 0.5) for t in tiles}
        
        # Sort by elevation desc
        sorted_tiles = sorted(tiles, key=lambda t: t.elevation, reverse=True)
        
        river_network = {}
        
        for tile in sorted_tiles:
            current_id = getattr(tile, 'id', 0)
            current_flux = flux.get(current_id, 0)
            
            # If significant flow, record it
            # Threshold 2.0 is arbitrary, tune based on humidity range (0-1) and map size
            # If map is large, flux accumulates heavily.
            if current_flux > 2.0 and current_id in flow_directions:
                target_id = flow_directions[current_id]
                river_network[current_id] = {
                    "target_id": target_id,
                    "flux": current_flux
                }
                
                if target_id in flux:
                    flux[target_id] += current_flux

        return river_network

    def _get_hex_neighbors(self, x: int, y: int) -> List[Tuple[int, int]]:
        # Logic matching MapStateManager._neighbor_ids (Column-based offset)
        # Even-q or Odd-q? MapStateManager uses tile.x & 1.
        # If x is odd, use odd_column offsets.
        
        # From MapStateManager:
        # odd_column: (-1,0), (-1,-1), (0,-1), (1,0), (0,1), (-1,1)
        # even_column: (-1,0), (0,-1), (1,-1), (1,0), (1,1), (0,1)
        
        even_column = [
            (-1, 0), (0, -1), (1, -1),
            (1, 0), (1, 1), (0, 1),
        ]
        odd_column = [
            (-1, 0), (-1, -1), (0, -1),
            (1, 0), (0, 1), (-1, 1),
        ]
        
        if x & 1:
            return [(x + dx, y + dy) for dx, dy in odd_column]
        else:
            return [(x + dx, y + dy) for dx, dy in even_column]
