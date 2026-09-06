#!/usr/bin/env python3
"""Render the README's architecture diagrams from checked-in sources.

A diagram exists twice — once per colour scheme — and both copies are derived
from one declarative source, so the picture cannot drift from the words:

  docs/diagrams/src/<n>.json     the source, canonical
  docs/diagrams/<n>-light.svg    generated
  docs/diagrams/<n>-dark.svg     generated

  scripts/render-diagrams.py                    # write every diagram
  scripts/render-diagrams.py --check            # exit 1 on drift, name the file
  scripts/render-diagrams.py --only how-work-moves

Output is deterministic: the same source renders the same bytes, with no
timestamps and no floating-point drift. Editing a generated SVG directly is the
one thing that does not work — the next run overwrites it.

A source is a layered top-to-bottom flow:

  {"title": ..., "description": ..., "direction": "TB", "width": 880,
   "nodes":  [{"id": ..., "label": ..., "sub": ..., "kind": "agent"}],
   "edges":  [{"from": ..., "to": ..., "label": ..., "dashed": true}],
   "groups": [{"label": ..., "kind": "orchestrator", "nodes": [...]}]}

Node kinds carry meaning: `agent` (rounded box), `gate` (hexagon), `human`
(pill), `artifact` (document), `orchestrator` (double-ruled box). Shape and
stroke distinguish them, so the diagram still reads without colour.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAGRAMS = ROOT / "docs" / "diagrams"
SOURCES = DIAGRAMS / "src"

# The plan skill lays its folio diagrams out with the same layered engine. Skills
# stay self-contained and repository tooling may depend on them, never the reverse
# (ADR 0022), so the half the two share — text metrics and layering — is imported
# from there instead of kept as a second copy. The geometry below is not shared:
# this front-end centres a fixed-width canvas, gives every node of a kind one
# width, and routes returns through the side channel its source names.
sys.path.append(str(ROOT / "skills" / "plan" / "scripts"))
from diagrams import (  # noqa: E402 - repository-local renderer
    Diagram,
    DiagramError,
    assign_layers,
    esc,
    num,
    order_within_layers,
    text_width,
    toward,
    wrap,
)

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
KINDS = ("agent", "gate", "human", "artifact", "orchestrator")
KIND_LEGEND = {
    "agent": "agent",
    "gate": "mechanical gate",
    "human": "human gate",
    "artifact": "artifact",
    "orchestrator": "orchestrator",
}

# Two palettes, one per colour scheme. Every fill is paired with the theme's
# single text colour, which keeps label contrast above 4.5:1 on all of them.
THEMES = {
    "light": {
        "text": "#111827",
        "sub": "#3d4657",
        "edge": "#4b5563",
        "muted": "#7b8494",
        "chip": "#ffffff",
        "page": "#ffffff",
        "chipStroke": "#d7dce3",
        "frame": "#8a76d6",
        "frameText": "#4c3a94",
        "fill": {
            "agent": "#e7edfb",
            "gate": "#fdf0d5",
            "human": "#e6f4ea",
            "artifact": "#f1f2f5",
            "orchestrator": "#ece6fb",
        },
        "stroke": {
            "agent": "#2b53a8",
            "gate": "#a2701a",
            "human": "#1f7a45",
            "artifact": "#5a6272",
            "orchestrator": "#5b3fbf",
        },
    },
    "dark": {
        "text": "#e6edf3",
        "sub": "#b9c4d0",
        "edge": "#8b949e",
        "muted": "#6e7681",
        "chip": "#161b22",
        "page": "#0d1117",
        "chipStroke": "#30363d",
        "frame": "#6f5aa8",
        "frameText": "#b392f0",
        "fill": {
            "agent": "#14243f",
            "gate": "#33280e",
            "human": "#102a1b",
            "artifact": "#1b2027",
            "orchestrator": "#241c40",
        },
        "stroke": {
            "agent": "#6ea1ff",
            "gate": "#e3b341",
            "human": "#56d364",
            "artifact": "#9aa4b2",
            "orchestrator": "#b392f0",
        },
    },
}

LABEL_SIZE = 14.0
SUB_SIZE = 11.5
TITLE_SIZE = 16.0
LEGEND_SIZE = 11.5
LABEL_LINE = 17.0
SUB_LINE = 15.0
PAD_X = 20.0
PAD_Y = 8.0
MIN_NODE_W = 150.0
MAX_NODE_W = 430.0
MIN_NODE_H = 40.0
NODE_GAP = 30.0
LAYER_GAP = 28.0
MARGIN_X = 20.0
MARGIN_TOP = 16.0
MARGIN_BOTTOM = 18.0
CORNER = 9.0
FRAME_PAD_X = 16.0
FRAME_PAD_TOP = 30.0
FRAME_PAD_BOTTOM = 14.0
CHANNEL_OFFSET = 26.0
CHANNEL_GAP = 16.0
# Extra width a shape spends on geometry rather than text.
KIND_EXTRA = {
    "agent": 0.0,
    "gate": 24.0,
    "human": 14.0,
    "artifact": 14.0,
    "orchestrator": 8.0,
}


class RenderError(Exception):
    pass


@dataclass
class Node:
    id: str
    label: str
    sub: list[str]
    kind: str
    index: int
    layer: int = 0
    order: float = 0.0
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""
    dashed: bool = False
    side: str = ""
    back: bool = False
    points: list[tuple[float, float]] = field(default_factory=list)
    label_at: tuple[float, float, str] = (0.0, 0.0, "middle")


# --------------------------------------------------------------------- loading


def load(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    where = path.relative_to(ROOT)
    if spec.get("direction", "TB") != "TB":
        raise RenderError(f"{where}: only direction TB is supported")
    for required in ("title", "description", "nodes", "edges"):
        if not spec.get(required):
            raise RenderError(f"{where}: missing {required}")

    nodes: dict[str, Node] = {}
    for index, entry in enumerate(spec["nodes"]):
        if entry["kind"] not in KINDS:
            raise RenderError(f"{where}: unknown kind {entry['kind']!r}")
        if entry["id"] in nodes:
            raise RenderError(f"{where}: duplicate node id {entry['id']!r}")
        limit = MAX_NODE_W - 2 * PAD_X - KIND_EXTRA[entry["kind"]]
        nodes[entry["id"]] = Node(
            id=entry["id"],
            label=entry["label"],
            sub=wrap(entry.get("sub", ""), SUB_SIZE, limit),
            kind=entry["kind"],
            index=index,
        )

    edges = []
    for entry in spec["edges"]:
        for end in ("from", "to"):
            if entry[end] not in nodes:
                raise RenderError(f"{where}: edge {end} {entry[end]!r} is not a node")
        edges.append(
            Edge(
                src=entry["from"],
                dst=entry["to"],
                label=entry.get("label", ""),
                dashed=bool(entry.get("dashed")),
                side=entry.get("side", "right"),
            )
        )

    for group in spec.get("groups", []):
        for member in group["nodes"]:
            if member not in nodes:
                raise RenderError(f"{where}: group member {member!r} is not a node")
        if group.get("kind", "orchestrator") not in KINDS:
            raise RenderError(f"{where}: unknown group kind {group['kind']!r}")

    return {"spec": spec, "nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------- layout


def graph_of(nodes: dict[str, Node], edges: list[Edge]) -> Diagram:
    """The shared layering reads a Diagram. This front-end keeps its own records —
    a node names its `label`, an edge names the `side` its channel runs down — and
    layering touches only the ids, layers, orders, and back-edge marks all three
    have in common."""
    graph = Diagram("TB")
    graph.nodes, graph.edges = nodes, edges  # type: ignore[assignment]
    return graph


def size_nodes(nodes: dict[str, Node]) -> None:
    """One width per kind, so the column has a rhythm instead of a ragged edge."""
    widths: dict[str, float] = dict.fromkeys(KINDS, MIN_NODE_W)
    for node in nodes.values():
        needed = text_width(node.label, LABEL_SIZE, bold=True)
        for line in node.sub:
            needed = max(needed, text_width(line, SUB_SIZE))
        needed += 2 * PAD_X + KIND_EXTRA[node.kind]
        widths[node.kind] = max(widths[node.kind], math.ceil(needed / 2) * 2)
    for node in nodes.values():
        node.w = min(widths[node.kind], MAX_NODE_W)
        block = LABEL_LINE + SUB_LINE * len(node.sub)
        node.h = max(MIN_NODE_H, block + 2 * PAD_Y)


def place(
    spec: dict, nodes: dict[str, Node], layers: list[list[Node]], top: float
) -> float:
    """Centre every layer in the canvas and stack the layers downward."""
    width = float(spec.get("width", 880))
    group_starts = {
        min(nodes[member].layer for member in group["nodes"])
        for group in spec.get("groups", [])
    }
    y = top
    for depth, layer in enumerate(layers):
        if depth:
            y += LAYER_GAP + (FRAME_PAD_TOP - 8 if depth in group_starts else 0)
        height = max(node.h for node in layer)
        total = sum(node.w for node in layer) + NODE_GAP * (len(layer) - 1)
        x = (width - total) / 2
        for node in layer:
            node.x = x
            node.y = y + (height - node.h) / 2
            x += node.w + NODE_GAP
        y += height
    return y


def frames(spec: dict, nodes: dict[str, Node]) -> list[dict]:
    boxes = []
    for group in spec.get("groups", []):
        members = [nodes[member] for member in group["nodes"]]
        left = min(node.x for node in members) - FRAME_PAD_X
        right = max(node.x + node.w for node in members) + FRAME_PAD_X
        top = min(node.y for node in members) - FRAME_PAD_TOP
        bottom = max(node.y + node.h for node in members) + FRAME_PAD_BOTTOM
        boxes.append(
            {
                "label": group["label"],
                "kind": group.get("kind", "orchestrator"),
                "x": left,
                "y": top,
                "w": right - left,
                "h": bottom - top,
            }
        )
    return boxes


# --------------------------------------------------------------------- routing


def route(
    nodes: dict[str, Node], edges: list[Edge], boxes: list[dict], width: float
) -> None:
    """Straight down where the columns line up, one right-angle jog where they
    do not, and a side channel for anything that skips a layer or returns."""
    obstacle_right = max(node.x + node.w for node in nodes.values())
    obstacle_left = min(node.x for node in nodes.values())
    for box in boxes:
        obstacle_right = max(obstacle_right, box["x"] + box["w"])
        obstacle_left = min(obstacle_left, box["x"])
    used = {"left": 0, "right": 0}

    for edge in edges:
        src, dst = nodes[edge.src], nodes[edge.dst]
        span = dst.layer - src.layer
        if span == 1:
            if abs(src.cx - dst.cx) < 0.5:
                edge.points = [(src.cx, src.y + src.h), (dst.cx, dst.y)]
                mid = ((src.y + src.h) + dst.y) / 2
                edge.label_at = (src.cx, mid, "middle")
            else:
                mid = ((src.y + src.h) + dst.y) / 2
                edge.points = [
                    (src.cx, src.y + src.h),
                    (src.cx, mid),
                    (dst.cx, mid),
                    (dst.cx, dst.y),
                ]
                edge.label_at = ((src.cx + dst.cx) / 2, mid, "middle")
            continue

        side = edge.side if edge.side in ("left", "right") else "right"
        channel = (
            obstacle_right + CHANNEL_OFFSET + CHANNEL_GAP * used[side]
            if side == "right"
            else obstacle_left - CHANNEL_OFFSET - CHANNEL_GAP * used[side]
        )
        used[side] += 1
        enter_x = dst.x + dst.w if side == "right" else dst.x
        exit_x = src.x + src.w if side == "right" else src.x
        edge.points = [
            (exit_x, src.cy),
            (channel, src.cy),
            (channel, dst.cy),
            (enter_x, dst.cy),
        ]
        # A channel label sits beside the channel, on whichever side has room.
        room = text_width(edge.label, SUB_SIZE) + 12
        middle = (src.cy + dst.cy) / 2
        if side == "right":
            fits = channel + 9 + room < width
        else:
            fits = channel - 9 - room > 0
        outward = (side == "right") == fits
        edge.label_at = (
            (channel + 9, middle, "start") if outward else (channel - 9, middle, "end")
        )


def path_of(points: list[tuple[float, float]]) -> str:
    """A polyline with rounded corners, drawn as quadratic elbows."""
    parts = [f"M {num(points[0][0])} {num(points[0][1])}"]
    for index in range(1, len(points) - 1):
        before, corner, after = points[index - 1], points[index], points[index + 1]
        radius = min(
            CORNER,
            math.dist(before, corner) / 2,
            math.dist(corner, after) / 2,
        )
        entry = toward(corner, before, radius)
        exit_ = toward(corner, after, radius)
        parts.append(f"L {num(entry[0])} {num(entry[1])}")
        parts.append(
            f"Q {num(corner[0])} {num(corner[1])} {num(exit_[0])} {num(exit_[1])}"
        )
    parts.append(f"L {num(points[-1][0])} {num(points[-1][1])}")
    return " ".join(parts)


# --------------------------------------------------------------------- drawing


def shape(node: Node) -> str:
    # Every measurement scales with the box, so the legend swatches are the same
    # shapes at a smaller size rather than four distorted ones.
    x, y, w, h = node.x, node.y, node.w, node.h
    if node.kind == "gate":
        cut = min(16.0, w * 0.18, h * 0.45)
        points = [
            (x + cut, y),
            (x + w - cut, y),
            (x + w, y + h / 2),
            (x + w - cut, y + h),
            (x + cut, y + h),
            (x, y + h / 2),
        ]
        coords = " ".join(f"{num(px)},{num(py)}" for px, py in points)
        return f'<polygon class="k-{node.kind}" points="{coords}"/>'
    if node.kind == "human":
        return (
            f'<rect class="k-{node.kind}" x="{num(x)}" y="{num(y)}" width="{num(w)}"'
            f' height="{num(h)}" rx="{num(h / 2)}"/>'
        )
    if node.kind == "artifact":
        fold = min(14.0, w * 0.22, h * 0.35)
        outline = (
            f"M {num(x)} {num(y)} L {num(x + w - fold)} {num(y)} L {num(x + w)} {num(y + fold)}"
            f" L {num(x + w)} {num(y + h)} L {num(x)} {num(y + h)} Z"
        )
        crease = (
            f"M {num(x + w - fold)} {num(y)} L {num(x + w - fold)} {num(y + fold)}"
            f" L {num(x + w)} {num(y + fold)}"
        )
        return (
            f'<path class="k-{node.kind}" d="{outline}"/>'
            f'<path class="k-{node.kind} crease" d="{crease}"/>'
        )
    radius = min(10.0, h * 0.28)
    box = (
        f'<rect class="k-{node.kind}" x="{num(x)}" y="{num(y)}" width="{num(w)}"'
        f' height="{num(h)}" rx="{num(radius)}"/>'
    )
    if node.kind == "orchestrator":
        # A second rule inside the border: the orchestrator frames the work.
        inset = min(4.0, h * 0.16)
        box += (
            f'<rect class="k-{node.kind} inner" x="{num(x + inset)}" y="{num(y + inset)}"'
            f' width="{num(w - 2 * inset)}" height="{num(h - 2 * inset)}"'
            f' rx="{num(max(radius - inset, 1))}"/>'
        )
    return box


def node_text(node: Node) -> str:
    block = LABEL_LINE + SUB_LINE * len(node.sub)
    top = node.y + (node.h - block) / 2
    out = [
        f'<text class="label" x="{num(node.cx)}" y="{num(top + 12.5)}">{esc(node.label)}</text>'
    ]
    for index, line in enumerate(node.sub):
        baseline = top + LABEL_LINE + 11 + SUB_LINE * index
        out.append(
            f'<text class="sub" x="{num(node.cx)}" y="{num(baseline)}">{esc(line)}</text>'
        )
    return "".join(out)


def edge_label(edge: Edge) -> str:
    if not edge.label:
        return ""
    x, y, anchor = edge.label_at
    width = text_width(edge.label, SUB_SIZE) + 12
    left = (
        x - width / 2
        if anchor == "middle"
        else (x - 6 if anchor == "start" else x + 6 - width)
    )
    chip = (
        f'<rect class="chip" x="{num(left)}" y="{num(y - 9)}" width="{num(width)}"'
        f' height="18" rx="5"/>'
    )
    return (
        chip
        + f'<text class="edgelabel" text-anchor="{anchor}" x="{num(x)}" y="{num(y + 4)}">'
        + f"{esc(edge.label)}</text>"
    )


def legend(kinds: list[str], x: float, y: float) -> str:
    out = []
    cursor = x
    for kind in kinds:
        swatch = Node(id="", label="", sub=[], kind=kind, index=0)
        swatch.x, swatch.y, swatch.w, swatch.h = cursor, y - 11, 28.0, 14.0
        out.append(shape(swatch))
        out.append(
            f'<text class="legend" text-anchor="start" x="{num(cursor + 32)}" y="{num(y)}">'
            f"{esc(KIND_LEGEND[kind])}</text>"
        )
        cursor += 32 + text_width(KIND_LEGEND[kind], LEGEND_SIZE) + 22
    return "".join(out)


def style(theme: dict) -> str:
    rules = [
        f"text{{font-family:{FONT}}}",
        f".label{{font-size:{num(LABEL_SIZE)}px;font-weight:600;fill:{theme['text']};text-anchor:middle}}",
        f".sub{{font-size:{num(SUB_SIZE)}px;font-style:italic;fill:{theme['sub']};text-anchor:middle}}",
        f".title{{font-size:{num(TITLE_SIZE)}px;font-weight:700;fill:{theme['text']}}}",
        f".legend{{font-size:{num(LEGEND_SIZE)}px;fill:{theme['sub']}}}",
        f".edgelabel{{font-size:{num(SUB_SIZE)}px;fill:{theme['sub']}}}",
        f".chip{{fill:{theme['chip']};stroke:{theme['chipStroke']};stroke-width:1}}",
        f".plate{{fill:{theme['page']}}}",
        f".edge{{fill:none;stroke:{theme['edge']};stroke-width:1.6}}",
        f".edge.dashed{{stroke:{theme['muted']};stroke-dasharray:6 4}}",
        # Dotted, so the grouping frame never reads as one of the dashed edges.
        (
            f".frame{{fill:none;stroke:{theme['frame']};stroke-width:1.4;"
            "stroke-dasharray:1 4;stroke-linecap:round}"
        ),
        f".frametext{{font-size:{num(SUB_SIZE)}px;font-weight:600;fill:{theme['frameText']}}}",
        ".crease{fill:none}",
        ".inner{fill:none;stroke-width:1}",
    ]
    for kind in KINDS:
        rules.append(
            f".k-{kind}{{fill:{theme['fill'][kind]};stroke:{theme['stroke'][kind]};stroke-width:1.6}}"
        )
    return "\n    ".join(rules)


def check_fits(
    spec: dict,
    nodes: dict[str, Node],
    edges: list[Edge],
    boxes: list[dict],
    kinds: list[str],
    width: float,
) -> None:
    """Nothing may leave the canvas. Text width is estimated, so this is the
    guard that turns a too-long label into a build failure rather than a
    clipped word in the README."""
    spans = [
        ("title", MARGIN_X, MARGIN_X + text_width(spec["title"], TITLE_SIZE, bold=True))
    ]
    cursor = MARGIN_X
    for kind in kinds:
        cursor += 32 + text_width(KIND_LEGEND[kind], LEGEND_SIZE) + 22
    spans.append(("legend", MARGIN_X, cursor - 22))
    for node in nodes.values():
        spans.append((f"node {node.id}", node.x, node.x + node.w))
    for box in boxes:
        spans.append(("group", box["x"], box["x"] + box["w"]))
        left = box["x"] + 14
        spans.append(
            ("group label", left, left + text_width(box["label"], SUB_SIZE, bold=True))
        )
    for edge in edges:
        if not edge.label:
            continue
        x, _, anchor = edge.label_at
        room = text_width(edge.label, SUB_SIZE) + 12
        left = (
            x - room / 2
            if anchor == "middle"
            else (x - 6 if anchor == "start" else x + 6 - room)
        )
        spans.append((f"edge {edge.src}->{edge.dst}", left, left + room))
    for what, left, right in spans:
        if left < 2 or right > width - 2:
            raise RenderError(
                f"{spec['title']}: {what} does not fit the {num(width)}px canvas "
                f"({num(left)}..{num(right)}) — shorten the label"
            )


def render(diagram: dict, scheme: str) -> str:
    spec, nodes, edges = diagram["spec"], diagram["nodes"], diagram["edges"]
    theme = THEMES[scheme]
    width = float(spec.get("width", 880))

    graph = graph_of(nodes, edges)
    assign_layers(graph)
    depth = max(node.layer for node in nodes.values())
    layers = [
        sorted(
            (node for node in nodes.values() if node.layer == rank),
            key=lambda node: node.index,
        )
        for rank in range(depth + 1)
    ]
    order_within_layers(graph, layers)
    size_nodes(nodes)

    kinds = [
        kind for kind in KINDS if any(node.kind == kind for node in nodes.values())
    ]
    legend_y = MARGIN_TOP + TITLE_SIZE + 20
    bottom = place(spec, nodes, layers, legend_y + 22)
    boxes = frames(spec, nodes)
    route(nodes, edges, boxes, width)
    check_fits(spec, nodes, edges, boxes, kinds, width)
    height = max([bottom, *(box["y"] + box["h"] for box in boxes)]) + MARGIN_BOTTOM

    body = [
        f'<rect class="frame" x="{num(box["x"])}" y="{num(box["y"])}" width="{num(box["w"])}"'
        f' height="{num(box["h"])}" rx="14"/>'
        for box in boxes
    ]
    for edge in edges:
        classes = "edge dashed" if edge.dashed else "edge"
        marker = "arrow-muted" if edge.dashed else "arrow"
        body.append(
            f'<path class="{classes}" marker-end="url(#{marker})" d="{path_of(edge.points)}"/>'
        )
    for box in boxes:
        # The label sits on the band an incoming edge crosses, so it is painted
        # over that edge on a backing plate rather than struck through by it.
        body.append(
            f'<rect class="plate" x="{num(box["x"] + 8)}" y="{num(box["y"] + 6)}"'
            f' width="{num(text_width(box["label"], SUB_SIZE, bold=True) + 12)}" height="17"/>'
            f'<text class="frametext" x="{num(box["x"] + 14)}" y="{num(box["y"] + 19)}">'
            f"{esc(box['label'])}</text>"
        )
    for node in nodes.values():
        body.append(shape(node) + node_text(node))
    for edge in edges:
        if edge.label:
            body.append(edge_label(edge))

    marker = (
        '<marker id="{name}" markerWidth="10" markerHeight="8" refX="10" refY="4"'
        ' orient="auto" markerUnits="userSpaceOnUse">'
        '<path d="M0,0 L10,4 L0,8 Z" fill="{colour}"/></marker>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {num(width)} {num(height)}"'
        ' width="100%" preserveAspectRatio="xMidYMid meet" role="img"'
        ' aria-labelledby="diagram-title diagram-desc">\n'
        f'  <title id="diagram-title">{esc(spec["title"])}</title>\n'
        f'  <desc id="diagram-desc">{esc(spec["description"])}</desc>\n'
        "  <defs>"
        + marker.format(name="arrow", colour=theme["edge"])
        + marker.format(name="arrow-muted", colour=theme["muted"])
        + "</defs>\n"
        f"  <style>\n    {style(theme)}\n  </style>\n"
        f'  <text class="title" x="{num(MARGIN_X)}" y="{num(MARGIN_TOP + TITLE_SIZE)}">'
        f"{esc(spec['title'])}</text>\n"
        f"  {legend(kinds, MARGIN_X, legend_y)}\n"
        "  " + "\n  ".join(body) + "\n"
        "</svg>\n"
    )


# ------------------------------------------------------------------------ main


def outputs(name: str) -> dict[str, Path]:
    return {scheme: DIAGRAMS / f"{name}-{scheme}.svg" for scheme in THEMES}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report drift, write nothing"
    )
    parser.add_argument("--only", metavar="NAME", help="render one diagram source")
    args = parser.parse_args()

    sources = sorted(SOURCES.glob("*.json"))
    if args.only:
        sources = [path for path in sources if path.stem == args.only]
        if not sources:
            raise RenderError(f"no diagram source named {args.only!r}")
    if not sources:
        raise RenderError(f"no diagram sources in {SOURCES.relative_to(ROOT)}")

    drifted: list[str] = []
    for source in sources:
        for scheme, path in outputs(source.stem).items():
            desired = render(load(source), scheme)
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current == desired:
                continue
            relative = path.relative_to(ROOT)
            if args.check:
                drifted.append(str(relative))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(desired, encoding="utf-8")
                print(f"wrote {relative}")

    if drifted:
        print("diagrams out of date: " + ", ".join(drifted), file=sys.stderr)
        print("run: python3 scripts/render-diagrams.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    # DiagramError is the shared engine's own refusal — the layering invariant.
    except (RenderError, DiagramError) as error:
        print(f"render-diagrams: {error}", file=sys.stderr)
        sys.exit(2)
