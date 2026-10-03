"""Generation-based family tree layout with orthogonal connector routing.

Pipeline (per connected component, then routed globally):

1. ranking     - generation rows: parents above children, spouses on one row
2. structure   - families (children grouped by identical visible parent sets),
                 spouse clusters, and dummy slots for links spanning rows
3. ordering    - left-to-right order within rows (barycentric crossing reduction)
4. positioning - x coordinates (isotonic regression with spacing constraints)
5. routing     - right-angle connectors, junctions, tracks and y coordinates
"""

from famtree.layout.engine import compute_layout
from famtree.layout.types import Layout, LayoutConfig

__all__ = ["Layout", "LayoutConfig", "compute_layout"]
