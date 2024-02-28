import omero
from omero import scripts, gateway
from omero.rtypes import wrap, rdouble

            
if __name__ == "__main__":
    client = scripts.client(
        'Transpose ROIs', """Takes ROIs from Image 1 and scales them onto Image 2""",
        scripts.String(
            "Image_1", optional=False, grouping="1",
            description="The filename or id of an Image"
        ),
        scripts.String(
            "Image_2", optional=False, grouping="2",
            description="The filename or id of an Image"
        ),
        version="1",
        authors=["Michael Barrett"],
        institutions=["LaViolette Lab"],
        contact="mjbarrett@mcw.edu",
    )

    try:
        conn = gateway.BlitzGateway(client_obj=client)

        updateService = conn.getUpdateService()
        roiService = conn.getRoiService()

        imageOne = client.getInput("Image_1", unwrap=True)
        imageTwo = client.getInput("Image_2", unwrap=True)

        # if is integer, assume an id, else filename
        try: # parse imageOne
            id=int(imageOne)
            imageOne=conn.getObject("image",imageOne)
        except ValueError:
            imageOne=conn.getObject("image",attributes={"name":imageOne})
        try: # parse imageTwo
            id=int(imageTwo)
            imageTwo=conn.getObject("image",imageTwo)
        except ValueError:
            imageTwo=conn.getObject("image",attributes={"name":imageTwo})

        shapes = []

        result = roiService.findByImage(imageOne.getId(), None)
        scaleFactor = [imageTwo.getSizeX() / imageOne.getSizeX(),
                        imageTwo.getSizeY() / imageOne.getSizeY()]
                        
        for roi in result.rois:
            newRoi=gateway.RoiWrapper(conn,omero.model.RoiI())
            for shape in roi.copyShapes():
                newShape=type(shape)()
                if hasattr(shape, "_x"):
                    newShape.setX(rdouble(shape.getX().getValue() * scaleFactor[0]))
                if hasattr(shape, "_y"):
                    newShape.setY(rdouble(shape.getY().getValue() * scaleFactor[1]))
                    
                if hasattr(shape, "_width"):
                    newShape.setWidth(rdouble(shape.getWidth().getValue() * scaleFactor[0]))
                if hasattr(shape, "_height"):
                    newShape.setHeight(rdouble(shape.getHeight().getValue() * scaleFactor[1]))
                    
                if hasattr(shape, "_radiusX"):
                    newShape.setRadiusX(rdouble(shape.getRadiusX().getValue() * scaleFactor[0]))
                if hasattr(shape, "_radiusY"):
                    newShape.setRadiusY(rdouble(shape.getRadiusY().getValue() * scaleFactor[1]))

                if hasattr(shape, "_points"):
                    pointStrArr = shape.getPoints().getValue().split(" ")
                    rv = ""
                    for pointStr in pointStrArr:
                        coordList=pointStr.split(",")
                        rv+=str(float(coordList[0]) * scaleFactor[0])+ "," +\
                            str(float(coordList[1]) * scaleFactor[1])+ " "
                    newShape.setPoints(wrap(rv))
                
                if hasattr(shape, "fillColor"): newShape.fillColor=shape.fillColor
                if hasattr(shape, "strokeColor"): newShape.strokeColor=shape.strokeColor
                if hasattr(shape, "strokeWidth"): newShape.strokeWidth=shape.strokeWidth

                newRoi.addShape(newShape)
                
            newRoi.setImage(imageTwo._obj)
            updateService.saveAndReturnObject(newRoi._obj)
        client.setOutput("Message", wrap("Success!"))

    except Exception as e:
        print(e)
        client.setOutput("Message", wrap("Failed"))

    finally:
        client.closeSession()