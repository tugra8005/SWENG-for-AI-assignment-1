import pytest

from mesveret.graph.neo4j_store import Neo4jGraph
from tests.graph_contract import GraphContract

pytestmark = pytest.mark.integration


class TestNeo4jGraph(GraphContract):
    @pytest.fixture
    def graph(self, neo4j_driver):
        return Neo4jGraph(neo4j_driver)
