"""Flatten PyMuPDF drawing paths in page points, preserving subpath boundaries."""
from __future__ import annotations


def _curve(p0, p1, p2, p3, tol, depth, out):
    ux = 3 * p1[0] - 2 * p0[0] - p3[0]
    uy = 3 * p1[1] - 2 * p0[1] - p3[1]
    vx = 3 * p2[0] - 2 * p3[0] - p0[0]
    vy = 3 * p2[1] - 2 * p3[1] - p0[1]
    if depth >= 15 or max(ux * ux, vx * vx) + max(uy * uy, vy * vy) < 16 * tol * tol:
        out.append(p3)
        return
    ab = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    bc = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    cd = ((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
    abc = ((ab[0] + bc[0]) / 2, (ab[1] + bc[1]) / 2)
    bcd = ((bc[0] + cd[0]) / 2, (bc[1] + cd[1]) / 2)
    mid = ((abc[0] + bcd[0]) / 2, (abc[1] + bcd[1]) / 2)
    _curve(p0, ab, abc, mid, tol, depth + 1, out)
    _curve(mid, bcd, cd, p3, tol, depth + 1, out)


def subpaths(items, tol=0.02):
    result, current = [], []
    for item in items:
        kind = item[0]
        if kind == "l":
            a, b = item[1:3]
            if current and abs(current[-1][0] - a.x) + abs(current[-1][1] - a.y) > 1e-5:
                result.append(current)
                current = []
            if not current:
                current = [(a.x, a.y)]
            current.append((b.x, b.y))
        elif kind == "c":
            p = [(v.x, v.y) for v in item[1:5]]
            if current and abs(current[-1][0] - p[0][0]) + abs(current[-1][1] - p[0][1]) > 1e-5:
                result.append(current)
                current = []
            if not current:
                current = [p[0]]
            _curve(*p, tol, 0, current)
        elif kind in ("re", "qu"):
            if current:
                result.append(current)
                current = []
            q = item[1]
            if kind == "re":
                result.append([(q.x0, q.y0), (q.x1, q.y0), (q.x1, q.y1),
                               (q.x0, q.y1), (q.x0, q.y0)])
            else:
                pts = [(v.x, v.y) for v in (q.ul, q.ur, q.lr, q.ll, q.ul)]
                result.append(pts)
        else:
            raise ValueError(f"unsupported drawing primitive: {kind}")
    if current:
        result.append(current)
    return result


def signed_area(points):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
               in zip(points, points[1:] + points[:1])) / 2


def closed_rings(items, tol=0.02):
    rings = []
    for points in subpaths(items, tol):
        if len(points) < 3:
            continue
        if points[0] != points[-1]:
            points = points + [points[0]]
        if abs(signed_area(points)) > 1e-9:
            rings.append(points)
    return rings
