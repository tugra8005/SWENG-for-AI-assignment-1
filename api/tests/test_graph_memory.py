import pytest

from mesveret.graph.memory import InMemoryGraph
from tests.graph_contract import GraphContract


class TestInMemoryGraph(GraphContract):
    @pytest.fixture
    def graph(self):
        return InMemoryGraph()
