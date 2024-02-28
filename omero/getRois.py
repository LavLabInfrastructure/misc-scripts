import os
import sys
from contextlib import redirect_stdout, contextmanager


@contextmanager
def suppress():
    with open(os.devnull, "w") as null:
        with redirect_stdout(null):
            yield


with suppress():

    import tempfile

    import cv2
    import numpy as np
    from PIL import Image
    from skimage import draw

    from omero.gateway import BlitzGateway
    from omero_model_PolygonI import PolygonI
    from omero_model_EllipseI import EllipseI
    from omero_model_PolygonI import PolygonI
    from omero_model_RectangleI import RectangleI


def uint_to_rgba(uint: int) -> int:
    """
    Return the color as an Integer in RGBA encoding.

    Parameters
    ----------
    int
        Integer encoding rgba value.

    Returns
    -------
    red: int
        Red color val (0-255)
    green: int
        Green color val (0-255)
    blue: int
        Blue color val (0-255)
    alpha: int
        Alpha opacity val (0-255)"""
    if uint < 0:  # convert from signed 32-bit int
        uint = uint + 2**32

    red = (uint >> 24) & 0xFF
    green = (uint >> 16) & 0xFF
    blue = (uint >> 8) & 0xFF
    alpha = uint & 0xFF

    return red, green, blue, alpha


def get_parent_directory():
    """Get the parent directory of the current script.
    Returns:
        str: The parent directory of the current script.
    """
    current_script_path = os.path.abspath(
        sys.argv[0]
    )  # Get the absolute path of the current script
    parent_directory = os.path.dirname(
        current_script_path
    )  # Get the directory of the current script
    return parent_directory


def read_credentials(filename):
    """Read a file containing a username and password.
    Args:
        filename (str): The name of the file to read.
    Returns:
        tuple: A tuple containing the username and password.
    """
    with open(filename, "r") as file:
        lines = file.readlines()
        username = lines[0].strip()  # Remove any leading/trailing whitespace
        password = lines[1].strip()  # Remove any leading/trailing whitespace
    return username, password


def getRois(img, roi_service=None):
    """
    Gathers OMERO RoiI objects.

    Parameters
    ----------
    img: omero.gateway.ImageWrapper
        Omero Image object from conn.getObjects()
    roi_service: omero.RoiService, optional
        Allows roiservice passthrough for performance
    """
    if roi_service is None:
        roi_service = img._conn.getRoiService()
        close_roi = True
    else:
        close_roi = False

    rois = roi_service.findByImage(img.getId(), None, img._conn.SERVICE_OPTS).rois

    if close_roi:
        roi_service.close()

    return rois


def getShapesAsPoints(
    img, point_downsample=4, img_downsample=1, roi_service=None
) -> list[tuple[int, tuple[int, int, int], list[tuple[float, float]]]]:
    """
    Gathers Rectangles, Polygons, and Ellipses as a tuple containing the shapeId, its rgb val, and a tuple of yx points of its bounds.

    Parameters
    ----------
    img: omero.gateway.ImageWrapper
        Omero Image object from conn.getObjects().
    point_downsample: int, Default: 4
        Grabs every nth point for faster computation.
    img_downsample: int, Default: 1
        How much to scale roi points.
    roi_service: omero.RoiService, optional
        Allows roiservice passthrough for performance.

    Returns
    -------
    returns: list[ shape.id, (r,g,b), list[tuple(x,y)] ]
        list of tuples containing a shape's id, rgb value, and a tuple of row and column points
    """

    sizeX = img.getSizeX() / img_downsample
    sizeY = img.getSizeY() / img_downsample
    yx_shape = (sizeY, sizeX)

    shapes = []
    for roi in getRois(img, roi_service):
        points = None
        for shape in roi.copyShapes():
            if type(shape) == RectangleI:
                x = float(shape.getX().getValue()) / img_downsample
                y = float(shape.getY().getValue()) / img_downsample
                w = float(shape.getWidth().getValue()) / img_downsample
                h = float(shape.getHeight().getValue()) / img_downsample
                # points = [(x, y),(x+w, y), (x+w, y+h), (x, y+h), (x, y)]
                points = draw.rectangle_perimeter(
                    (y, x), (y + h, x + w), shape=yx_shape
                )
                points = [
                    (points[1][i], points[0][i]) for i in range(0, len(points[0]))
                ]

            if type(shape) == EllipseI:
                points = draw.ellipse_perimeter(
                    float(shape._y._val / img_downsample),
                    float(shape._x._val / img_downsample),
                    float(shape._radiusY._val / img_downsample),
                    float(shape._radiusX._val / img_downsample),
                    shape=yx_shape,
                )
                points = [
                    (points[1][i], points[0][i]) for i in range(0, len(points[0]))
                ]

            if type(shape) == PolygonI:
                pointStrArr = shape.getPoints()._val.split(" ")
                points = parsePolygonPointString(pointStrArr, img_downsample)
            if points is not None:
                color_val = shape.getStrokeColor()._val
                rgb = uint_to_rgba(color_val)[:-1]  # ignore alpha value for computation
                points = points[::point_downsample]

                shapes.append((shape.getId()._val, rgb, points))

    if not shapes:  # if no shapes in shapes return none
        return None

    # make sure is in correct order
    return sorted(shapes)


def parsePolygonPointString(polyString, img_downsample=1):
    xy = []
    for i in range(0, len(polyString)):
        coordList = polyString[i].split(",")
        xy.append(
            (float(coordList[0]) / img_downsample, float(coordList[1]) / img_downsample)
        )
    if xy:
        points = xy
    return points or None


args = sys.argv
for args in [
    ("_", x)
    # image ids
    for x in (
        262,
        257,
        565,
        566,
        272,
        273,
        275,
        277,
        291,
        305,
        344,
        341,
        343,
        922,
        920,
        921,
        929,
        925,
    )
]:
    # with suppress():
    username, password = read_credentials(
        get_parent_directory() + os.sep + "omero_user.txt"
    )
    img_id = args[1]
    downsample = 10
    workdir = "/Volumes/Siren/Prostate_data/SD_Pathomics"
    skip_upload = False

    if len(args) > 2:
        downsample = int(args[2])

    if len(args) > 3:
        workdir = str(args[3])

    conn = BlitzGateway(username, password, host="lavlab.mcw.edu", secure=True)

    print(conn.connect())

    conn.SERVICE_OPTS.setOmeroGroup("-1")
    img = conn.getObject("image", img_id)
    conn.c.sf.setSecurityContext(img.details.group)
    rgb_mask = np.zeros(
        (
            int(img.getSizeY() / downsample),
            int(img.getSizeX() / downsample),
            img.getSizeC(),
        ),
        dtype=np.uint8,
    )
    rgb_mask[:] = 255
    for id, rgb, xy in getShapesAsPoints(img, img_downsample=downsample):
        yx = np.array(xy, np.int32)  # Ensure the points are of integer type
        yx = yx.reshape((-1, 1, 2))  # Reshape to (-1, 1, 2)
        cv2.fillPoly(rgb_mask, [yx], color=rgb)

    mask = Image.fromarray(rgb_mask)
    path = os.path.join(workdir, img.getName().split(".")[0] + "_annot.jpeg")
    mask.save(path)
    conn.close()
