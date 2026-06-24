from index_graph.viz.atlas_layout import build_atlas_layout, DocNode
from viz_fixtures import simple_atlas


def _by_id(atlas):
    return {d.id: d for d in atlas.docs}


def test_describing_doc_sits_below_its_repo():
    pack, _ = simple_atlas()
    atlas = build_atlas_layout(pack)
    d = _by_id(atlas)["app/README.md"]
    assert d.describes == "app"
    assert d.y > atlas.repo_layout.height       # in the doc region, below the repo graph


def test_cross_cutting_doc_is_a_band_node():
    pack, _ = simple_atlas()
    atlas = build_atlas_layout(pack)
    assert _by_id(atlas)["docs/arch.md"].describes is None


def test_describes_edge_connects_doc_and_repo():
    pack, _ = simple_atlas()
    atlas = build_atlas_layout(pack)
    kinds = {(k.type, k.frm, k.to) for k in atlas.kedges}
    assert ("describes", "app/README.md", "app") in kinds


def test_no_two_doc_nodes_overlap():
    pack, _ = simple_atlas()
    atlas = build_atlas_layout(pack)
    boxes = [(d.x, d.y, d.x + d.w, d.y + d.h) for d in atlas.docs]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ax0, ay0, ax1, ay1 = boxes[i]
            bx0, by0, bx1, by1 = boxes[j]
            assert ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0, "doc nodes overlap"


def test_layout_is_deterministic():
    pack, _ = simple_atlas()
    a, b = build_atlas_layout(pack), build_atlas_layout(pack)
    assert [vars(d) for d in a.docs] == [vars(d) for d in b.docs]
    assert a.width == b.width and a.height == b.height
