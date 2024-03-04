import os
import sys
from omero.gateway import BlitzGateway
from contextlib import redirect_stdout, contextmanager
import numpy as np
from lavlab.omero_util import getDownsampledXYDimensions, getImageAtResolution

def getLargeRecon(img, downsample_factor:int = 10):
    """
Checks OMERO for a pregenerated large recon, if none are found, it will generate and upload one.

Parameters
----------
img: omero.gateway.ImageWrapper
    Omero Image object from conn.getObjects().
downsample_factor: int, Default: 10
    Which large recon size to get.

Returns
-------
omero.gateway.AnnotationWrapper
    remote large recon object
str
    local path to large recon
    """
    sizeX = img.getSizeX()
    sizeY = img.getSizeY()
    xy_dim = getDownsampledXYDimensions(img, downsample_factor)
    recon_img = getImageAtResolution(img, xy_dim)
    recon_array = np.array(recon_img)

    return recon_array


@contextmanager
def suppress():
    with open(os.devnull, "w") as null:
        with redirect_stdout(null):
            yield

def get_parent_directory():
    """Get the parent directory of the current script.
    
    Returns:
        str: The parent directory of the current script.
    """
    current_script_path = os.path.abspath(sys.argv[0])  # Get the absolute path of the current script
    parent_directory = os.path.dirname(current_script_path)  # Get the directory of the current script
    return parent_directory

def read_credentials(filename):
    """Read a file containing a username and password.
    
    Args:
        filename (str): The name of the file to read.
    
    Returns:
        tuple: A tuple containing the username and password.
    """
    with open(filename, 'r') as file:
        lines = file.readlines()
        username = lines[0].strip()  # Remove any leading/trailing whitespace
        password = lines[1].strip()  # Remove any leading/trailing whitespace
    
    return username, password

img_id = sys.argv[1]
downsample_factor=10
if len(sys.argv) > 2:
    downsample_factor = int(sys.argv[2])

conn = BlitzGateway('', '', host='lavlab.mcw.edu', secure=True)
print(conn.connect())
conn.SERVICE_OPTS.setOmeroGroup("-1")
img = conn.getObject('image', img_id)
print(img)
y = getLargeRecon(img, downsample_factor)
conn.close()
