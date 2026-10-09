"""Network map helpers (no game needed): side bits from edge records, routes over connected pieces."""
import pytest

from sc4_mcp import networks

W, N, E, S = 1, 2, 4, 8


def test_sides_from_edge_bytes():
    assert networks._sides(0x00020002) == W | E          # a road running west-east (live: piece 0x4B00)
    assert networks._sides(0x02000200) == N | S          # a street running north-south
    assert networks._sides(0x08000000) == 0              # only the low 3 bits of a side byte count
    assert networks._side_text(W | E | S) == "WES"


def test_route_needs_both_sides():
    data = {(0, 0): {"road": E}, (1, 0): {"road": W | E | S, "street": S}, (2, 0): {"road": W},
            (1, 1): {"street": N | S}, (1, 2): {"street": N}, (3, 0): {"road": W}}
    assert networks.shortest_path(data, (0, 0), (1, 2)) == [(0, 0), (1, 0), (1, 1), (1, 2)]
    with pytest.raises(networks.NetworkError):                 # (2, 0) does not open east
        networks.shortest_path(data, (0, 0), (3, 0))
    with pytest.raises(networks.NetworkError):                 # streets only: no street on (0, 0)
        networks.shortest_path(data, (0, 0), (1, 2), "street")


def test_power_lines_connect_to_neighbours():
    out = {(5, 5): {"power_line": 0}, (6, 5): {"power_line": 0}, (6, 6): {"power_line": 0, "road": W}}
    networks._power_sides(out)
    assert out[(5, 5)]["power_line"] == E and out[(6, 5)]["power_line"] == W | S and out[(6, 6)]["road"] == W


def test_funding_curve_interpolation():
    from sc4_mcp import services
    fire = [[0, 10], [50, 25], [75, 45], [90, 75], [100, 100], [120, 110]]     # the game's fire curve
    assert services.on_curve(fire, 50) == 25 and services.on_curve(fire, 95) == 87.5
    assert services.on_curve(fire, -5) == 10 and services.on_curve(fire, 200) == 110
