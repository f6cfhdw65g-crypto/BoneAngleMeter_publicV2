import numpy as np
import math
from scipy.optimize import least_squares

def vector_with_two_points(i,j):

    return (j-i)

def normalvector_of_three_points(k,l,m):

    return np.cross((l-k),(l-m))
def normalvector_of_two_vectors(plane_vector_1, plane_vector_2):

    return np.cross(plane_vector_1,plane_vector_2)

def project_vector_to_plane_from_normal(normal, vector):
    normal_component = np.dot(normal, vector)/(np.linalg.norm(normal)**2) * normal
    return (vector - normal_component) # in-plane component

def project_vector_to_plane_from_2_vectors(plane_vector_1, plane_vector_2, vector):
    normal = normalvector_of_two_vectors(plane_vector_1,plane_vector_2)
    return project_vector_to_plane_from_normal(normal, vector)


def angle(u,v):

    c = np.dot(u,v)
    d = np.linalg.norm(u)
    e = np.linalg.norm(v)
    cos_angle = np.clip(c/(d*e), -1.0, 1.0)
    return math.acos(cos_angle)

def angle_in_plane_with_normal(normal, vector_a, vector_b):

    vec_a_proj = project_vector_to_plane_from_normal(normal, vector_a)
    vec_b_proj = project_vector_to_plane_from_normal(normal, vector_b)

    return (angle(vec_a_proj, vec_b_proj)*180/math.pi)

def angle_in_plane_from_two_vectors(plane_vector_1, plane_vector_2, vector_a, vector_b):
    vec_a_proj = project_vector_to_plane_from_2_vectors(plane_vector_1, plane_vector_2, vector_a)
    vec_b_proj = project_vector_to_plane_from_2_vectors(plane_vector_1, plane_vector_2, vector_b)
    normal=np.cross(plane_vector_1,plane_vector_2)

    return (angle(vec_a_proj, vec_b_proj)*180/math.pi)

def fit_sphere(points):
    '''
    Fits a sphere to a set of at least 4 non-coplanar 3D points using least squares and returns
    the fitted (center, radius). Averaging several points sampled on a curved anatomical surface
    this way is more robust against a single mis-placed landmark than relying on one manually
    chosen point (e.g. femur head, femoral condyles), and the fitted sphere can also be drawn in
    the scene so the user can see how well it matches the bone surface.

    Source of the residual formulation: https://github.com/thompson318/scikit-surgery-sphere-fitting/blob/master/sksurgeryspherefitting/algorithms/sphere_fitting.py
    '''
    points = np.asarray(points)

    def _residuals(parameters, values):
        x_centre, y_centre, z_centre, radius = parameters
        distance_from_centre = np.sqrt(np.sum((values - np.array([x_centre, y_centre, z_centre]))**2, axis=1))
        return distance_from_centre - radius

    center0 = np.mean(points, axis=0)
    radius0 = np.linalg.norm(np.amin(points, axis=0) - np.amax(points, axis=0)) / 2.0
    initial_parameters = [center0[0], center0[1], center0[2], radius0]

    fitting_result = least_squares(_residuals, initial_parameters, method="trf", jac="3-point", args=(points,))
    center_x, center_y, center_z, radius = fitting_result.x
    return np.array([center_x, center_y, center_z]), abs(radius)