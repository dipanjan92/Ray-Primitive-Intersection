import numba
import numpy as np
import numba

from utils.constants import EPSILON
from utils.vectors import normalize
from typing import Optional


spec = [
    ('min_distance', numba.optional(numba.float64)),
    ('intersected_point', numba.optional(numba.float64[:])),
    ('normal', numba.float64[:])
]


@numba.experimental.jitclass(spec)
class Intersection:
    def __init__(self, min_distance, intersected_point, normal):
        self.min_distance = min_distance
        self.intersected_point = intersected_point
        self.normal = normal


@numba.njit
def triangle_intersect(ray, triangle, EPSILON=1e-6):
    vertex_a = triangle.vertex_1
    vertex_b = triangle.vertex_2
    vertex_c = triangle.vertex_3

    plane_normal = triangle.normal

    ab = vertex_b - vertex_a
    ac = vertex_c - vertex_a

    pvec = np.cross(ray.direction, ac)
    det = np.dot(ab, pvec)

    if abs(det) <= EPSILON:
        return False

    inv_det = 1.0 / det

    tvec = ray.origin - vertex_a

    u = np.dot(tvec, pvec) * inv_det

    if u < 0 or u > 1:
        return False

    qvec = np.cross(tvec, ab)

    v = np.dot(ray.direction, qvec) * inv_det

    if v < 0 or u + v > 1:
        return False

    t = np.dot(ac, qvec) * inv_det

    if t < ray.tmin or t > ray.tmax:
        return False

    ray.tmax = t

    return True

@numba.njit
def __triangle_intersect(ray_origin, ray_end, triangle):
    """
    Based on ray–tetrahedron intersection
    returns the distance from the origin of the ray to the nearest intersection point
    :param ray_origin: origin of the ray
    :param ray_end: pixel on the triangle
    :param vertex_a: first vertex of the triangle
    :param vertex_b: second vertex of the triangle
    :param vertex_c: third vertex of the triangle
    :return: distance from origin to the intersection point, or None
    """
    def signed_tetra_volume(a,b,c,d):
        return np.sign(np.dot(np.cross(b-a,c-a),d-a)/6.0)

    vertex_a = triangle.vertex_1
    vertex_b = triangle.vertex_2
    vertex_c = triangle.vertex_3

    s1 = signed_tetra_volume(ray_origin,vertex_a,vertex_b,vertex_c)
    s2 = signed_tetra_volume(ray_end,vertex_a,vertex_b,vertex_c)

    if s1 != s2:
        s3 = signed_tetra_volume(ray_origin,ray_end,vertex_a,vertex_b)
        s4 = signed_tetra_volume(ray_origin,ray_end,vertex_b,vertex_c)
        s5 = signed_tetra_volume(ray_origin,ray_end,vertex_c,vertex_a)
        if s3 == s4 and s4 == s5:
            n = np.cross(vertex_b-vertex_a,vertex_c-vertex_a)
            t = -np.dot(ray_origin,n-vertex_a) / np.dot(ray_origin,ray_end-ray_origin)
            return t

    return None


@numba.njit
def aabb_intersect(ray_origin, ray_direction, box):
    t_min = 0.0
    t_max = np.inf
    ray_inv_dir = 1/ray_direction
    for i in range(3):
        t1 = (box.min_point[i] - ray_origin[i]) * ray_inv_dir[i]
        t2 = (box.max_point[i] - ray_origin[i]) * ray_inv_dir[i]
        t_min = min(max(t1, t_min), max(t2, t_min))
        t_max = max(min(t1, t_max), min(t2, t_max))
    return t_min<=t_max


@numba.njit
def intersect_bounds(bounds, ray, inv_dir, hit0=None, hit1=None):
    t0 = 0
    t1 = ray.tmax
    for i in range(3):
        t_near = (bounds.min_point[i]-ray.origin[i])*inv_dir[i]
        t_far = (bounds.max_point[i]-ray.origin[i])*inv_dir[i]
        if t_near>t_far:
            t_near, t_far = t_far, t_near
        t_far *= 1+2*gamma(3)
        t0 = t_near if t_near>t0 else t0
        t1 = t_far if t_far<t1 else t1
        if t0>t1:
            return False
    if hit0 is not None:
        hit0=t0
    if hit1 is not None:
        hit1=t1
    return True


@numba.njit
def __intersect_bounds(bounds, ray, inv_dir, dir_is_neg):
    # check for ray intersection against x and y slabs
    tmin = ((bounds.max_point[0] if dir_is_neg[0] else bounds.min_point[0]) - ray.origin[0]) * inv_dir[0]
    tmax = ((bounds.min_point[0] if dir_is_neg[0] else bounds.max_point[0]) - ray.origin[0]) * inv_dir[0]
    tymin = ((bounds.max_point[1] if dir_is_neg[1] else bounds.min_point[1]) - ray.origin[1]) * inv_dir[1]
    tymax = ((bounds.min_point[1] if dir_is_neg[1] else bounds.max_point[1]) - ray.origin[1]) * inv_dir[1]
    if tmin > tymax or tymin > tmax:
        return False
    if tymin > tmin:
        tmin = tymin
    if tymax < tmax:
        tmax = tymax

    # check for ray intersection against z slab
    tzmin = ((bounds.max_point[2] if dir_is_neg[2] else bounds.min_point[2]) - ray.origin[2]) * inv_dir[2]
    tzmax = ((bounds.min_point[2] if dir_is_neg[2] else bounds.max_point[2]) - ray.origin[2]) * inv_dir[2]
    if tmin > tzmax or tzmin > tmax:
        return False
    if tzmin > tmin:
        tmin = tzmin
    if tzmax < tmax:
        tmax = tzmax
    return (tmin < np.inf) and (tmax > EPSILON)


@numba.njit
def create_orthonormal_system(normal):
    if abs(normal[0]) > abs(normal[1]):
        v2 = np.array([-normal[2], 0.0, normal[0]], dtype=np.float64) / np.sqrt(np.array([normal[0] * normal[0] + normal[2] * normal[2]], dtype=np.float64))
    else:
        v2 = np.array([0.0, normal[2], -normal[1]], dtype=np.float64) / np.sqrt(np.array([normal[1] * normal[1] + normal[2] * normal[2]], dtype=np.float64))

    v3 = np.cross(normal, v2)

    return v2, v3


@numba.njit
def max_dimension(v):
    return 0 if v[0] > v[1] and v[0] > v[2] else 1 if v[1] > v[2] else 2


@numba.njit
def permute(point, x, y, z):
    return np.array([point[x], point[y], point[z]])


@numba.njit
def max_component(v):
    return max(v[0], max(v[1], v[2]))


@numba.njit
def get_machine_epsilon():
    return np.finfo(np.float32).eps*0.5

@numba.njit
def gamma(n):
    eps = get_machine_epsilon()
    return (n * eps) / (1 - n * eps)


@numba.njit
def get_UVs():
    return np.array([[0,0], [1,0], [1,1]])