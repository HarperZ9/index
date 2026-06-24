import re

from index_graph.viz.charts import render_charts
from viz_fixtures import simple_pack


def test_three_charts_returned():
    charts = render_charts(simple_pack())
    assert set(charts) == {"confidence", "roles", "fanio"}


def test_confidence_counts_sum_to_edge_total():
    charts = render_charts(simple_pack())
    counts = [int(x) for x in re.findall(r'data-count="(\d+)"', charts["confidence"])]
    assert sum(counts) == 4  # four relations in the fixture


def test_roles_chart_counts_each_primary_role_once():
    charts = render_charts(simple_pack())
    assert 'data-label="hub"' in charts["roles"]
    counts = [int(x) for x in re.findall(r'data-count="(\d+)"', charts["roles"])]
    assert sum(counts) == 4  # four internal repos


def test_fanio_lists_top_indegree_repo():
    charts = render_charts(simple_pack())
    assert "core" in charts["fanio"]  # core has the highest salience presence


def test_charts_are_deterministic():
    assert render_charts(simple_pack()) == render_charts(simple_pack())


def test_no_external_excludes_external_edges_from_confidence():
    charts = render_charts(simple_pack(), include_external=False)
    counts = [int(x) for x in re.findall(r'data-count="(\d+)"', charts["confidence"])]
    # simple_pack has 4 relations total (1 external); only 3 internal should be counted
    assert sum(counts) == 3
