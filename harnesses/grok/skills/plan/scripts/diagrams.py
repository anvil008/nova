#!/usr/bin/env python3
"""Lay out and draw the folio's diagrams as deterministic inline SVG.

The folio used to ship a 3.4MB Mermaid bundle and render four `<pre class="mermaid">`
blocks in the browser. It now draws the same four pictures at build time, following
ADR 0010's approach for the README diagrams: Python standard library only, one fixed
float format so a re-render is byte-identical, and shape rather than colour alone
carrying meaning.

Two of the four diagrams come from the sidecar's `architecture.diagramsMermaid`
strings, which stay the authoring format; `parse()` reads the flowchart subset those
sources are allowed to use and refuses anything else by name. The other two are built
directly from the validated issues, with no Mermaid round-trip.

Paint is not baked in. Every fill and stroke comes from a class defined in
`templates/plan.css` against the folio's `--bg-3`/`--line-2`/`--txt`/`--wave-*`
custom properties, so an SVG follows the reader's theme toggle exactly like the rest
of the page.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

LABEL_SIZE = 13.0
SUB_SIZE = 11.0
LABEL_LINE = 16.0
SUB_LINE = 14.0
PAD_X = 14.0
PAD_Y = 9.0
MIN_NODE_W = 110.0
MAX_NODE_W = 200.0
MIN_NODE_H = 38.0
NODE_GAP = 22.0
LAYER_GAP = 46.0
MARGIN = 14.0
CORNER = 8.0
FRAME_PAD = 14.0
FRAME_PAD_TOP = 26.0
CHANNEL_OFFSET = 24.0
CHANNEL_GAP = 16.0
CHIP_PAD = 12.0
# Extra width a shape spends on geometry rather than text.
KIND_EXTRA = {
    "box": 0.0,
    "round": 0.0,
    "stadium": 14.0,
    "subroutine": 12.0,
    "hex": 22.0,
}


class DiagramError(ValueError):
    pass


# ---------------------------------------------------------------- text metrics

NARROW = set("ijltIfr.,:;'`|!()[]{}-·/\\ ")
WIDE = set("mwMW@%—&")


def text_width(text: str, size: float, bold: bool = False) -> float:
    """Approximate a Helvetica-class advance width. No font is embedded, so this
    only has to be a safe over-estimate: too wide leaves air, too narrow clips."""
    units = 0.0
    for char in text:
        if char == " ":
            units += 0.30
        elif char in NARROW:
            units += 0.34
        elif char in WIDE:
            units += 0.92
        elif char.isupper():
            units += 0.70
        elif char.isdigit():
            units += 0.56
        else:
            units += 0.55
    return units * size * (1.06 if bold else 1.0)


def wrap(text: str, size: float, limit: float) -> list[str]:
    """Wrap on spaces, honouring the explicit breaks a label already carries."""
    lines: list[str] = []
    for segment in text.split("\n"):
        segment = segment.strip()
        if not segment:
            continue
        current = ""
        for word in segment.split(" "):
            candidate = f"{current} {word}".strip()
            if current and text_width(candidate, size) > limit:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def num(value: float) -> str:
    """One fixed float format, so a re-render is byte-identical."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ----------------------------------------------------------------------- model


@dataclass
class Node:
    id: str
    text: str
    sub_text: str = ""
    kind: str = "box"
    css: str = ""
    index: int = 0
    lines: list[str] = field(default_factory=list)
    sub: list[str] = field(default_factory=list)
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
    thick: bool = False
    arrow: bool = True
    back: bool = False
    points: list[tuple[float, float]] = field(default_factory=list)
    label_at: tuple[float, float, str] = (0.0, 0.0, "middle")


@dataclass
class Group:
    label: str
    members: list[str]
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0


class Diagram:
    """Nodes, edges, and subgraph frames — whether parsed or built from issues."""

    def __init__(self, direction: str = "TD") -> None:
        if direction not in DIRECTIONS:
            raise DiagramError(f"unsupported flowchart direction {direction!r}")
        self.horizontal, self.reverse = DIRECTIONS[direction]
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.groups: list[Group] = []

    def node(
        self, node_id: str, text: str, kind: str = "box", sub: str = "", css: str = ""
    ) -> Node:
        existing = self.nodes.get(node_id)
        if existing is not None:
            # A later `A[label]` names a node an earlier edge only referenced.
            if text and existing.text == existing.id and text != existing.id:
                existing.text, existing.kind = text, kind
                existing.sub_text = sub or existing.sub_text
            return existing
        node = Node(
            id=node_id,
            text=text,
            sub_text=sub,
            kind=kind,
            css=css,
            index=len(self.nodes),
        )
        self.nodes[node_id] = node
        return node

    def edge(self, src: str, dst: str, **kwargs: object) -> None:
        self.edges.append(Edge(src=src, dst=dst, **kwargs))  # type: ignore[arg-type]

    def group(self, label: str, members: list[str]) -> None:
        self.groups.append(Group(label=label, members=members))


DIRECTIONS = {
    "LR": (True, False),
    "RL": (True, True),
    "TB": (False, False),
    "TD": (False, False),
    "BT": (False, True),
}


# ---------------------------------------------------------------------- parser

HEADER = re.compile(r"^(?:flowchart|graph)(?:\s+([A-Za-z]{2}))?\s*$")
IDENT = re.compile(r"[A-Za-z0-9_]+")
LINKISH = re.compile(r"[-=.<>ox|]+")
BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
# Longest first: `-.->` must win over `-.-`, and `-->` over `---`.
LINKS = {
    "-.->": {"dashed": True},
    "-.-": {"dashed": True, "arrow": False},
    "==>": {"thick": True},
    "===": {"thick": True, "arrow": False},
    "-->": {},
    "---": {"arrow": False},
}
SHAPES = [
    ("([", "])", "stadium"),
    ("[[", "]]", "subroutine"),
    ("{{", "}}", "hex"),
    ("[", "]", "box"),
    ("(", ")", "round"),
    ("{", "}", "hex"),
]
KEYWORDS = (
    "classDef",
    "class",
    "style",
    "linkStyle",
    "click",
    "direction",
)


def _label(raw: str) -> str:
    text = BREAK.sub("\n", raw).strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    return " ".join(part for part in text.split(" ") if part != "") or text


def _term(text: str, pos: int, where: str) -> tuple[str, str, str, int]:
    """Read `id`, `id[label]`, `id([label])`, … starting at `pos`."""
    match = IDENT.match(text, pos)
    if not match:
        raise DiagramError(
            f"{where}: expected a node identifier at {text[pos : pos + 24]!r}"
        )
    node_id = match.group(0)
    pos = match.end()
    for opener, closer, kind in SHAPES:
        if not text.startswith(opener, pos):
            continue
        end = text.find(closer, pos + len(opener))
        if end < 0:
            raise DiagramError(
                f"{where}: node {node_id} opens {opener!r} and never closes it"
            )
        return node_id, _label(text[pos + len(opener) : end]), kind, end + len(closer)
    if text.startswith((">", "(("), pos):
        shape = ">" if text.startswith(">", pos) else "(("
        raise DiagramError(
            f"{where}: unsupported node shape {shape!r} on node {node_id}"
        )
    return node_id, node_id, "box", pos


def _link(text: str, pos: int, where: str) -> tuple[dict, int]:
    for token, style in LINKS.items():
        if text.startswith(token, pos):
            return style, pos + len(token)
    run = LINKISH.match(text, pos)
    found = run.group(0) if run else text[pos : pos + 8].split(" ")[0]
    raise DiagramError(
        f"{where}: unsupported link {found!r} — the folio subset is "
        "-->, ---, -.->, -.-, ==>, ===, and an edge label is written A -->|text| B"
    )


def _statement(
    diagram: Diagram, text: str, where: str, members: list[str] | None
) -> None:
    pos, previous = 0, None
    while True:
        node_id, label, kind, pos = _term(text, pos, where)
        diagram.node(node_id, label, kind)
        if members is not None and node_id not in members:
            members.append(node_id)
        if previous is not None:
            diagram.edge(previous[0], node_id, label=previous[1], **previous[2])
        pos = len(text) - len(text[pos:].lstrip())
        if pos >= len(text):
            return
        style, pos = _link(text, pos, where)
        pos = len(text) - len(text[pos:].lstrip())
        label = ""
        if text.startswith("|", pos):
            end = text.find("|", pos + 1)
            if end < 0:
                raise DiagramError(f"{where}: edge label opens '|' and never closes it")
            label, pos = _label(text[pos + 1 : end]), end + 1
            pos = len(text) - len(text[pos:].lstrip())
        previous = (node_id, label, style)


def parse(source: str, where: str) -> Diagram:
    """Read the flowchart subset a plan sidecar may use.

    Anything outside it — a sequence diagram, a `classDef`, a shape the layout
    engine has no drawing for — is named and refused rather than dropped, so a
    diagram never renders as a quietly smaller picture than its author wrote.
    """
    lines = [
        line.split("%%", 1)[0].strip()
        for line in source.replace("\r\n", "\n").split("\n")
    ]
    body = [(number, line) for number, line in enumerate(lines, 1) if line]
    if not body:
        raise DiagramError(f"{where}: diagram source is empty")

    number, header = body[0]
    match = HEADER.match(header)
    if not match:
        keyword = header.split()[0].rstrip(":")
        raise DiagramError(
            f"{where} line {number}: {keyword!r} is not supported — the folio renders "
            "`flowchart`/`graph` sources only"
        )
    direction = (match.group(1) or "TD").upper()
    if direction not in DIRECTIONS:
        raise DiagramError(
            f"{where} line {number}: unsupported direction {direction!r} — use one of "
            + ", ".join(DIRECTIONS)
        )
    diagram = Diagram(direction)

    open_group: tuple[str, list[str]] | None = None
    for number, line in body[1:]:
        place = f"{where} line {number}"
        first = line.split(" ", 1)[0].split("[", 1)[0]
        if first in KEYWORDS:
            raise DiagramError(
                f"{place}: {first!r} is not supported — the folio paints diagrams from "
                "its own theme, so styling directives have no effect"
            )
        if first == "subgraph":
            if open_group is not None:
                raise DiagramError(f"{place}: nested subgraphs are not supported")
            rest = line[len("subgraph") :].strip()
            if not rest:
                raise DiagramError(f"{place}: subgraph needs a title")
            try:
                _, label, _, end = _term(rest, 0, place)
            except DiagramError:
                label, end = rest, len(rest)
            open_group = (_label(label) if end == len(rest) else _label(rest), [])
            continue
        if line == "end":
            if open_group is None:
                raise DiagramError(f"{place}: 'end' without an open subgraph")
            diagram.group(open_group[0], open_group[1])
            open_group = None
            continue
        _statement(diagram, line, place, open_group[1] if open_group else None)

    if open_group is not None:
        raise DiagramError(
            f"{where}: subgraph {open_group[0]!r} is never closed by 'end'"
        )
    if not diagram.nodes:
        raise DiagramError(f"{where}: diagram declares no nodes")
    return diagram


# ---------------------------------------------------------------------- layout


def assign_layers(diagram: Diagram) -> None:
    """Longest-path layering. An edge that closes a cycle — a review loop returning
    to its start — is marked and left out of the ranking, so the loop never drags
    its target down the page."""
    nodes, edges = diagram.nodes, diagram.edges
    outgoing: dict[str, list[Edge]] = {node: [] for node in nodes}
    for edge in edges:
        outgoing[edge.src].append(edge)

    state = dict.fromkeys(nodes, 0)  # 0 unvisited, 1 on the stack, 2 done
    for start in nodes:
        if state[start]:
            continue
        stack = [(start, iter(outgoing[start]))]
        state[start] = 1
        while stack:
            node, pending = stack[-1]
            advanced = False
            for edge in pending:
                if state[edge.dst] == 1:
                    edge.back = True
                elif state[edge.dst] == 0:
                    state[edge.dst] = 1
                    stack.append((edge.dst, iter(outgoing[edge.dst])))
                    advanced = True
                    break
            if not advanced:
                state[node] = 2
                stack.pop()

    forward = [edge for edge in edges if not edge.back]
    incoming = dict.fromkeys(nodes, 0)
    for edge in forward:
        incoming[edge.dst] += 1
    ready = [node for node in nodes if not incoming[node]]
    seen = 0
    while ready:
        node = ready.pop(0)
        seen += 1
        for edge in forward:
            if edge.src != node:
                continue
            nodes[edge.dst].layer = max(nodes[edge.dst].layer, nodes[node].layer + 1)
            incoming[edge.dst] -= 1
            if not incoming[edge.dst]:
                ready.append(edge.dst)
    if seen != len(nodes):
        raise DiagramError(
            "layering did not settle: a cycle escaped back-edge detection"
        )


def order_within_layers(diagram: Diagram, layers: list[list[Node]]) -> None:
    """Two barycentre sweeps. On a mostly linear flow this changes nothing; on a
    branch it puts a node beside its predecessors instead of crossing to reach them."""
    nodes = diagram.nodes
    forward = [edge for edge in diagram.edges if not edge.back]
    for layer in layers:
        for position, node in enumerate(layer):
            node.order = position

    for _ in range(2):
        for direction in ("down", "up"):
            sweep = layers[1:] if direction == "down" else layers[-2::-1]
            for layer in sweep:
                for node in layer:
                    if direction == "down":
                        peers = [nodes[e.src] for e in forward if e.dst == node.id]
                    else:
                        peers = [nodes[e.dst] for e in forward if e.src == node.id]
                    if peers:
                        node.order = sum(peer.order for peer in peers) / len(peers)
                layer.sort(key=lambda item: (item.order, item.index))
                for position, node in enumerate(layer):
                    node.order = position


def size_nodes(diagram: Diagram) -> None:
    for node in diagram.nodes.values():
        limit = MAX_NODE_W - 2 * PAD_X - KIND_EXTRA[node.kind]
        node.lines = wrap(node.text, LABEL_SIZE, limit)
        node.sub = wrap(node.sub_text, SUB_SIZE, limit)
        needed = max(
            [text_width(line, LABEL_SIZE, bold=True) for line in node.lines]
            + [text_width(line, SUB_SIZE) for line in node.sub]
            + [0.0]
        )
        needed += 2 * PAD_X + KIND_EXTRA[node.kind]
        node.w = min(max(MIN_NODE_W, math.ceil(needed / 2) * 2), MAX_NODE_W)
        block = LABEL_LINE * len(node.lines) + SUB_LINE * len(node.sub)
        node.h = max(MIN_NODE_H, block + 2 * PAD_Y)


def _main(node: Node, horizontal: bool) -> tuple[float, float]:
    """(start, size) along the axis layers advance on."""
    return (node.x, node.w) if horizontal else (node.y, node.h)


def _cross(node: Node, horizontal: bool) -> tuple[float, float]:
    """(start, size) along the axis a layer spreads on."""
    return (node.y, node.h) if horizontal else (node.x, node.w)


def layer_gaps(diagram: Diagram, layers: list[list[Node]]) -> list[float]:
    """Space before each layer. A left-to-right flow puts its edge labels between
    the columns, so a long label widens exactly the gap it sits in."""
    gaps = [0.0] + [LAYER_GAP] * (len(layers) - 1)
    starts = {
        min(diagram.nodes[m].layer for m in group.members)
        for group in diagram.groups
        if group.members
    }
    ends = {
        max(diagram.nodes[m].layer for m in group.members)
        for group in diagram.groups
        if group.members
    }
    for depth in range(1, len(layers)):
        if depth in starts:
            gaps[depth] += FRAME_PAD_TOP
        if depth - 1 in ends:
            gaps[depth] += FRAME_PAD
    if diagram.horizontal:
        for edge in diagram.edges:
            src, dst = diagram.nodes[edge.src], diagram.nodes[edge.dst]
            if not edge.label or dst.layer - src.layer != 1:
                continue
            needed = text_width(edge.label, SUB_SIZE) + CHIP_PAD + 16
            gaps[dst.layer] = max(gaps[dst.layer], needed)
    return gaps


def place(diagram: Diagram, layers: list[list[Node]]) -> None:
    horizontal = diagram.horizontal
    gaps = layer_gaps(diagram, layers)
    main = 0.0
    for depth, layer in enumerate(layers):
        main += gaps[depth]
        span = max(_main(node, horizontal)[1] for node in layer)
        total = sum(_cross(node, horizontal)[1] for node in layer) + NODE_GAP * (
            len(layer) - 1
        )
        cross = -total / 2
        for node in layer:
            offset = (span - _main(node, horizontal)[1]) / 2
            if horizontal:
                node.x, node.y = main + offset, cross
            else:
                node.y, node.x = main + offset, cross
            cross += _cross(node, horizontal)[1] + NODE_GAP
        main += span


def frames(diagram: Diagram) -> None:
    for group in diagram.groups:
        members = [diagram.nodes[member] for member in group.members]
        if not members:
            continue
        group.x = min(node.x for node in members) - FRAME_PAD
        group.y = min(node.y for node in members) - FRAME_PAD_TOP
        group.w = max(node.x + node.w for node in members) + FRAME_PAD - group.x
        group.h = max(node.y + node.h for node in members) + FRAME_PAD - group.y


# --------------------------------------------------------------------- routing


def route(diagram: Diagram) -> None:
    """Straight along the flow where the lanes line up, one right-angle jog where
    they do not, and a side channel for anything that skips a layer or returns."""
    horizontal, nodes = diagram.horizontal, diagram.nodes
    frame_lo = [group.y if horizontal else group.x for group in diagram.groups]
    frame_hi = [
        (group.y + group.h) if horizontal else (group.x + group.w)
        for group in diagram.groups
    ]
    cross_hi = max(
        [sum(_cross(node, horizontal)) for node in nodes.values()] + frame_hi
    )
    cross_lo = min(
        [_cross(node, horizontal)[0] for node in nodes.values()] + frame_lo
    )
    used = {"lo": 0, "hi": 0}

    def point(main: float, cross: float) -> tuple[float, float]:
        return (main, cross) if horizontal else (cross, main)

    for edge in diagram.edges:
        src, dst = nodes[edge.src], nodes[edge.dst]
        src_main, src_span = _main(src, horizontal)
        dst_main, dst_span = _main(dst, horizontal)
        src_cross, src_width = _cross(src, horizontal)
        dst_cross, dst_width = _cross(dst, horizontal)
        src_mid, dst_mid = src_cross + src_width / 2, dst_cross + dst_width / 2

        if dst.layer - src.layer == 1:
            middle = ((src_main + src_span) + dst_main) / 2
            if abs(src_mid - dst_mid) < 0.5:
                edge.points = [
                    point(src_main + src_span, src_mid),
                    point(dst_main, dst_mid),
                ]
                edge.label_at = (*point(middle, src_mid), "middle")
            else:
                edge.points = [
                    point(src_main + src_span, src_mid),
                    point(middle, src_mid),
                    point(middle, dst_mid),
                    point(dst_main, dst_mid),
                ]
                edge.label_at = (*point(middle, (src_mid + dst_mid) / 2), "middle")
            continue

        side = "lo" if edge.back or dst.layer <= src.layer else "hi"
        channel = (
            cross_hi + CHANNEL_OFFSET + CHANNEL_GAP * used[side]
            if side == "hi"
            else cross_lo - CHANNEL_OFFSET - CHANNEL_GAP * used[side]
        )
        used[side] += 1
        exit_cross = src_cross + src_width if side == "hi" else src_cross
        enter_cross = dst_cross + dst_width if side == "hi" else dst_cross
        edge.points = [
            point(src_main + src_span / 2, exit_cross),
            point(src_main + src_span / 2, channel),
            point(dst_main + dst_span / 2, channel),
            point(dst_main + dst_span / 2, enter_cross),
        ]
        middle = (src_main + src_span / 2 + dst_main + dst_span / 2) / 2
        offset = 9 if side == "hi" else -9
        edge.label_at = (*point(middle, channel + offset), "middle")


def mirror(diagram: Diagram) -> None:
    """RL and BT are the canonical layout reflected across its own flow axis."""
    horizontal = diagram.horizontal
    for node in diagram.nodes.values():
        if horizontal:
            node.x = -node.x - node.w
        else:
            node.y = -node.y - node.h
    for group in diagram.groups:
        if horizontal:
            group.x = -group.x - group.w
        else:
            group.y = -group.y - group.h
    for edge in diagram.edges:
        edge.points = [(-x, y) if horizontal else (x, -y) for x, y in edge.points]
        x, y, anchor = edge.label_at
        edge.label_at = (-x, y, anchor) if horizontal else (x, -y, anchor)


def normalise(diagram: Diagram) -> tuple[float, float]:
    """Slide everything into positive space and report the canvas it needs."""
    spans_x: list[tuple[float, float]] = []
    spans_y: list[tuple[float, float]] = []
    for node in diagram.nodes.values():
        spans_x.append((node.x, node.x + node.w))
        spans_y.append((node.y, node.y + node.h))
    for group in diagram.groups:
        spans_x.append((group.x, group.x + group.w))
        spans_y.append((group.y, group.y + group.h))
    for edge in diagram.edges:
        for x, y in edge.points:
            spans_x.append((x, x))
            spans_y.append((y, y))
        if edge.label:
            x, y, _ = edge.label_at
            width = text_width(edge.label, SUB_SIZE) + CHIP_PAD
            spans_x.append((x - width / 2, x + width / 2))
            spans_y.append((y - 9, y + 9))

    dx = MARGIN - min(low for low, _ in spans_x)
    dy = MARGIN - min(low for low, _ in spans_y)
    for node in diagram.nodes.values():
        node.x, node.y = node.x + dx, node.y + dy
    for group in diagram.groups:
        group.x, group.y = group.x + dx, group.y + dy
    for edge in diagram.edges:
        edge.points = [(x + dx, y + dy) for x, y in edge.points]
        x, y, anchor = edge.label_at
        edge.label_at = (x + dx, y + dy, anchor)
    width = max(high for _, high in spans_x) + dx + MARGIN
    height = max(high for _, high in spans_y) + dy + MARGIN
    return width, height


# --------------------------------------------------------------------- drawing


def path_of(points: list[tuple[float, float]]) -> str:
    """A polyline with rounded corners, drawn as quadratic elbows."""
    parts = [f"M {num(points[0][0])} {num(points[0][1])}"]
    for index in range(1, len(points) - 1):
        before, corner, after = points[index - 1], points[index], points[index + 1]
        radius = min(
            CORNER, math.dist(before, corner) / 2, math.dist(corner, after) / 2
        )
        entry = toward(corner, before, radius)
        leave = toward(corner, after, radius)
        parts.append(f"L {num(entry[0])} {num(entry[1])}")
        parts.append(
            f"Q {num(corner[0])} {num(corner[1])} {num(leave[0])} {num(leave[1])}"
        )
    parts.append(f"L {num(points[-1][0])} {num(points[-1][1])}")
    return " ".join(parts)


def toward(
    origin: tuple[float, float], target: tuple[float, float], distance: float
) -> tuple[float, float]:
    length = math.dist(origin, target) or 1.0
    ratio = distance / length
    return (
        origin[0] + (target[0] - origin[0]) * ratio,
        origin[1] + (target[1] - origin[1]) * ratio,
    )


def shape(node: Node) -> str:
    """Shape carries the node kind, so the diagram still reads without colour."""
    x, y, w, h = node.x, node.y, node.w, node.h
    if node.kind == "hex":
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
        return f'<polygon class="d-shape" points="{coords}"/>'
    if node.kind == "stadium":
        radius = h / 2
    elif node.kind == "round":
        radius = min(10.0, h * 0.28)
    else:
        radius = 3.0
    box = (
        f'<rect class="d-shape" x="{num(x)}" y="{num(y)}" width="{num(w)}"'
        f' height="{num(h)}" rx="{num(radius)}"/>'
    )
    if node.kind == "subroutine":
        inset = min(4.0, h * 0.16)
        box += (
            f'<rect class="d-shape d-inner" x="{num(x + inset)}" y="{num(y + inset)}"'
            f' width="{num(w - 2 * inset)}" height="{num(h - 2 * inset)}"'
            f' rx="{num(max(radius - inset, 1))}"/>'
        )
    return box


def node_text(node: Node) -> str:
    block = LABEL_LINE * len(node.lines) + SUB_LINE * len(node.sub)
    top = node.y + (node.h - block) / 2
    out = []
    for index, line in enumerate(node.lines):
        baseline = top + 12 + LABEL_LINE * index
        out.append(
            f'<text class="d-label" x="{num(node.cx)}" y="{num(baseline)}">{esc(line)}</text>'
        )
    for index, line in enumerate(node.sub):
        baseline = top + LABEL_LINE * len(node.lines) + 10.5 + SUB_LINE * index
        out.append(
            f'<text class="d-sub" x="{num(node.cx)}" y="{num(baseline)}">{esc(line)}</text>'
        )
    return "".join(out)


def edge_label(edge: Edge) -> str:
    if not edge.label:
        return ""
    x, y, anchor = edge.label_at
    width = text_width(edge.label, SUB_SIZE) + CHIP_PAD
    return (
        f'<rect class="d-chip" x="{num(x - width / 2)}" y="{num(y - 9)}" width="{num(width)}"'
        ' height="18" rx="5"/>'
        f'<text class="d-edgelabel" text-anchor="{anchor}" x="{num(x)}" y="{num(y + 4)}">'
        f"{esc(edge.label)}</text>"
    )


def naming(node: Node) -> str:
    return f"{node.text} [{node.sub_text}]" if node.sub_text else node.text


def describe(diagram: Diagram) -> list[str]:
    """The text equivalent ADR 0004 requires, derived from the same model the
    picture is drawn from so the two cannot drift."""
    nodes = diagram.nodes
    lines = []
    connected: set[str] = set()
    for edge in diagram.edges:
        connected.update((edge.src, edge.dst))
        arrow = "→" if edge.arrow else "—"
        suffix = f" ({edge.label})" if edge.label else ""
        lines.append(f"{naming(nodes[edge.src])} {arrow} {naming(nodes[edge.dst])}{suffix}")
    for node in nodes.values():
        if node.id not in connected:
            lines.append(f"{naming(node)} (stands alone)")
    for group in diagram.groups:
        members = ", ".join(naming(nodes[member]) for member in group.members)
        lines.append(f"{group.label} groups: {members}")
    return lines


ARROW = (
    '<marker id="{name}" markerWidth="10" markerHeight="8" refX="10" refY="4"'
    ' orient="auto" markerUnits="userSpaceOnUse">'
    '<path class="d-arrowhead" d="M0,0 L10,4 L0,8 Z"/></marker>'
)


def svg(diagram: Diagram, dom_id: str, title: str) -> str:
    assign_layers(diagram)
    depth = max(node.layer for node in diagram.nodes.values())
    layers = [
        sorted(
            (node for node in diagram.nodes.values() if node.layer == rank),
            key=lambda node: node.index,
        )
        for rank in range(depth + 1)
    ]
    order_within_layers(diagram, layers)
    size_nodes(diagram)
    place(diagram, layers)
    frames(diagram)
    route(diagram)
    if diagram.reverse:
        mirror(diagram)
    width, height = normalise(diagram)

    body = [
        f'<rect class="d-frame" x="{num(group.x)}" y="{num(group.y)}" width="{num(group.w)}"'
        f' height="{num(group.h)}" rx="12"/>'
        for group in diagram.groups
    ]
    for edge in diagram.edges:
        classes = (
            "d-edge"
            + (" d-dashed" if edge.dashed else "")
            + (" d-thick" if edge.thick else "")
        )
        marker = f' marker-end="url(#{dom_id}-arrow)"' if edge.arrow else ""
        body.append(f'<path class="{classes}"{marker} d="{path_of(edge.points)}"/>')
    for group in diagram.groups:
        # The label sits on the band an incoming edge crosses, so it is painted over
        # that edge on a backing plate rather than struck through by it.
        body.append(
            f'<rect class="d-plate" x="{num(group.x + 8)}" y="{num(group.y + 5)}"'
            f' width="{num(text_width(group.label, SUB_SIZE, bold=True) + 12)}" height="17"/>'
            f'<text class="d-frametext" x="{num(group.x + 14)}" y="{num(group.y + 18)}">'
            f"{esc(group.label)}</text>"
        )
    for node in diagram.nodes.values():
        classes = f"d-node {node.css}" if node.css else "d-node"
        body.append(f'<g class="{classes}">{shape(node)}{node_text(node)}</g>')
    for edge in diagram.edges:
        body.append(edge_label(edge))

    edges = len(diagram.edges)
    summary = (
        f"{len(diagram.nodes)} nodes and {edges} "
        f"relationship{'' if edges == 1 else 's'}; "
        "the same content is listed as text beneath the diagram."
    )
    return (
        f'<svg class="diagram" xmlns="http://www.w3.org/2000/svg" width="{num(width)}"'
        f' height="{num(height)}" viewBox="0 0 {num(width)} {num(height)}"'
        f' style="max-width: {num(width)}px; width: 100%; height: auto" role="img"'
        f' aria-labelledby="{dom_id}-title {dom_id}-desc">'
        f'<title id="{dom_id}-title">{esc(title)}</title>'
        f'<desc id="{dom_id}-desc">{esc(summary)}</desc>'
        f"<defs>{ARROW.format(name=f'{dom_id}-arrow')}</defs>"
        + "".join(body)
        + "</svg>"
    )


def block(diagram: Diagram, dom_id: str, title: str) -> str:
    """The picture plus its text equivalent, ready to drop into the folio."""
    items = "".join(f"<li>{esc(line)}</li>" for line in describe(diagram))
    return (
        f'<div class="diagram-shell">{svg(diagram, dom_id, title)}</div>'
        f'<details class="diagram-text"><summary>{esc(title)} in words</summary>'
        f"<ul>{items}</ul></details>"
    )
