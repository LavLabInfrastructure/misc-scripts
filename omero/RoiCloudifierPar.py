import io
from lavlab.omero_util import (
    getImageAtResolution,
    getDownsampledXYDimensions,
    createPolygon,
    createRoi,
    getLargeRecon,
)
import time


# from lavlab.omero_util import saveObjects
def saveObjects(conn, objects):
    ous = conn.getUpdateService()
    for obj in objects:
        ous.saveAndReturnObject(obj)
    ous.close()


from lavlab.python_util import draw_shapes


class LLabOmeroNamespaceParser:
    """Translates local images to remote OMERO Images"""

    THUMBNAIL_SIZE = (256, 256)

    def __init__(self, conn):
        self.conn = conn

    def findPrimaryRemoteImage(self, details):
        start = time.time()
        """gets remote image based off parsed image details)"""
        project_id, patient_id, slide_id = details
        slide_num = slide_id[0]
        # slide_id from Siren

        # img_obj from llab omero filenaming convention
        print(f"N{patient_id}_S{slide_num}_HE.ome.tiff")
        img = self.conn.getObject(
            "Image", attributes={"name": f"N{patient_id}_S{slide_num}_HE.ome.tiff"}
        )

        if img is not None:
            # thumbnail
            tn = Image.open(io.BytesIO(img.getThumbnail(self.THUMBNAIL_SIZE)))
            print(f"findPrimaryRemoteImage took: {time.time()-start}")
            return tn, img
        print(f"findPrimaryRemoteImage took: {time.time()-start}")
        return None, None

    def extendedRemoteImgSearch(self, details):
        """Find extra image options if possible"""
        start = time.time()
        project_id, patient_id, slide_id = details
        slide_num = slide_id[0]
        # get all images from dataset and match using pattern
        dataset = self.conn.getObject(
            "Dataset", attributes={"name": f"{patient_id}_{project_id.lower()[0]}"}
        )
        rv = []
        for img in dataset.listChildren():
            name = img.getName()
            if re.match(".*_S" + slide_num + ".*", name):
                tn = Image.open(io.BytesIO(img.getThumbnail(self.THUMBNAIL_SIZE)))
                obj = img
                rv.append({"thumbnail": tn, "obj": obj, "name": name})
        print(f"extendedRemoteImgSearch took: {time.time()-start}")
        return rv

    def getRegistrationImage(self, img, details):
        """gets registration img"""
        start = time.time()
        project_id, patient_id, slide_id = details
        slide_num, downsample_factor = slide_id
        lr_obj, lr_img = getLargeRecon(img, downsample_factor)
        os.remove(lr_img.filename)
        print(f"getRegistrationImage took: {time.time()-start}")
        return lr_img

    def createRemoteRois(self, remote_img, remote_img_bin, warped_contours, details):
        """creates and returns omero rois from contours"""
        start = time.time()
        rois = []
        for id, rgb, xy in warped_contours:
            # scale coords back to full res for upload
            xy2 = np.copy(xy)
            for axis in xy2:
                for i, coord in enumerate(axis):
                    axis[i] = coord * int(details[-1][-1])
            # create roi
            polygon = createPolygon(
                xy2, z=0, t=0, comment="Transferred Annotation", rgb=rgb
            )
            rois.append(createRoi(remote_img, [polygon]))

        # remote_bin = np.array(remote_img_bin)
        d_start = time.time()
        _ = draw_shapes(remote_img_bin, warped_contours)
        print(f"drawing shapes took: {time.time()-d_start}")
        # r_tn = Image.fromarray(remote_bin)

        print(f"createRemoteRois took: {time.time()-start}")
        return remote_img_bin.resize(self.THUMBNAIL_SIZE), rois

    def saveRemoteRois(self, rois):
        """uploads/saves the output created by createRemoteRois"""
        start = time.time()
        saveObjects(self.conn, rois)
        print(f"saveRemoteRois took: {time.time()-start}")


import re
import glob
import os.path
import numpy as np
from skimage import measure
from skimage.io import imread
from PIL import Image

from lavlab.python_util import get_color_region_contours

offset = (3, 0, 2)


class SirenFileReader:
    """parses paths to single resolution annotated tiff images found on Siren"""

    THUMBNAIL_SIZE = (256, 256)

    FN_GLOB = r"/**/large_recon_*_AN*OT.tif*"
    """all annotated large recons (regardless of spelling lol)"""

    FN_REGEX_CAPTURE = r".*\/([A-Za-z]+)_data\/[12]([0-9]{3})\/.*\/([0-9]+)(?:_incl?|_excl)*\/[A-Za-z]+/large_recon_([0-9]+)_A[N]+OT.*"

    ANNOT_TO_REG = (r"_AN+OT.*", r".tif*")

    GENEROUS = True

    ROI_RGB_VALS = [  # green fails
        (0, 0, 0),
        (5, 1, 4),
        (25, 20, 255),
        (255, 120, 0),
        (255, 16, 0),
        (48, 255, 48),
        (3, 254, 3),
        (50, 255, 50),
        (255, 250, 20),
        (254, 22, 255),
        (252, 27, 207),
        (253, 252, 4),
        (255, 9, 255),
        (33, 255, 255),
    ]

    def parse(self, path):
        """gets project, patient_id, slide_id(slide#, downsample)"""
        project, patient_num, slide_num, downsample_factor = re.search(
            self.FN_REGEX_CAPTURE, path
        ).groups()
        return (
            project.capitalize(),
            patient_num,
            (f"{int(slide_num):02d}", downsample_factor),
        )

    def searchDirectory(self, path):
        """search for annotated large recons recursively"""
        print(path)
        for file in glob.glob(f"{path}{self.FN_GLOB}", recursive=True):
            print(file)
            if not os.path.isfile(file):
                yield
            with Image.open(file) as img:
                print(img.mode)
                yield img.resize(self.THUMBNAIL_SIZE), file

    def getRegistrationImage(self, path: str):
        pattern = re.sub(self.ANNOT_TO_REG[0], self.ANNOT_TO_REG[1], path)
        for file in glob.glob(pattern):
            if os.path.isfile(file):
                return Image.open(file)
        if self.GENEROUS is True:
            print(path)
            return Image.open(path)
        else:
            raise FileNotFoundError

    def getRoiContours(self, path):
        """returns roi contours. generated from thresholded region of interest"""
        start = time.time()
        rv = []
        raw_img = Image.open(path)
        with raw_img.convert("RGB") as img:
            for rgb in self.ROI_RGB_VALS:
                contours = get_color_region_contours(img, rgb)
                if contours:
                    rv.extend(contours)
        raw_img.close()
        print(f"getRoiContours took: {time.time()-start}")
        print(f"found {len(rv)} rois!")
        return rv


from tempfile import TemporaryDirectory
from valis import registration
from valis.serial_rigid import SerialRigidRegistrar
from skimage.io import imsave


class ValisLargeReconRoiRegistrar:
    """Registers single resolution tiff/jpeg/png files. NOT FOR FULL RESOLUTION COREGISTRATION!"""

    registrar = registration.Valis(
        os.devnull, os.devnull, img_list=[], imgs_ordered=True
    )

    def transfer_rois(rois, local_img: Image.Image, remote_img):
        """Coregisters local_img and remote_img, then uses that info to transfer the rois"""
        start = time.time()
        with TemporaryDirectory() as workdir:
            s_start = time.time()
            local = workdir + os.sep + "local.ome.tiff"
            remote = workdir + os.sep + "remote.ome.tiff"
            local_img.save(local)
            remote_img.save(remote)
            # imsave(local, np.array(local_img))
            # imsave(remote, np.array(remote_img))
            # coregister images
            v_start = time.time()
            print(f"save took: {v_start-s_start}")
            ValisLargeReconRoiRegistrar.registrar.__init__(
                workdir,
                workdir + os.sep + "out/",
                reference_img_f="remote.jpeg",
                align_to_reference=True,
            )
            (
                rigid_registrar,
                non_rigid_registrar,
                error_df,
            ) = ValisLargeReconRoiRegistrar.registrar.register()
            print(f"valis took: {time.time()- v_start}")
            annot_obj = ValisLargeReconRoiRegistrar.registrar.get_slide(local)
            ref = ValisLargeReconRoiRegistrar.registrar.get_ref_slide()
            w_start = time.time()
            for i, shape in enumerate(rois):
                id, rgb_val, contour = shape
                # contour = [(y,x) for x,y in contour]
                warped_contour = annot_obj.warp_xy_from_to(contour, ref)
                warped_contour = [tuple(xy) for xy in warped_contour]
                rois[i] = (id, rgb_val, warped_contour)
            print(f"warping took: {time.time() - w_start}")
        print(f"transfer_rois took: {time.time()-start}")
        return rois


import time
import tkinter as tk
import tkinter.font as tkFont
from PIL import ImageTk


class TKWindowManager:
    """Manages UI Window/Frames with TK"""

    window = tk.Tk()
    current_frame = tk.Frame(window)
    tk.Label(
        current_frame,
        text="Welcome to ROI Cloudifier!",
        font=tkFont.Font(window, size=32),
    ).pack()
    tk.Label(
        current_frame, text="Starting...", font=tkFont.Font(window, size=32)
    ).pack()

    def update():
        TKWindowManager.window.update_idletasks()
        TKWindowManager.window.update()

    def _returnValue(variable, value):
        variable["status"] = value

    def compare(local_thumbnail, remote_thumbnail, msg="Do These Match?"):
        """Shows two PIL images in a comparison prompt"""
        rv = {"status": None}

        l_tn = ImageTk.PhotoImage(local_thumbnail)
        r_tn = ImageTk.PhotoImage(remote_thumbnail)
        frame = tk.Frame(TKWindowManager.window)
        frame.pack(padx=10, pady=10)

        tk.Label(frame, text=msg).pack(padx=10, pady=10)
        tk.Label(frame, text="Local Image", image=l_tn).pack(
            padx=10, pady=10, side="left"
        )
        tk.Label(frame, text="Remote Image", image=r_tn).pack(
            padx=10, pady=10, side="right"
        )
        tk.Button(
            frame, text="Yes", command=lambda: TKWindowManager._returnValue(rv, True)
        ).pack(padx=20, side="left")
        tk.Button(
            frame, text="No", command=lambda: TKWindowManager._returnValue(rv, False)
        ).pack(padx=20, side="right")

        TKWindowManager.current_frame.destroy()
        TKWindowManager.current_frame = frame

        while rv["status"] is None:
            TKWindowManager.update()
            time.sleep(0.2)
        return rv["status"]

    def ask(message):
        """prompts user with text and yesno buttons"""
        rv = {"status": None}
        frame = tk.Frame(TKWindowManager.window)
        frame.pack(padx=10, pady=10)
        tk.Label(frame, text=message).pack(padx=10, pady=10)
        tk.Button(
            frame, text="Yes", command=lambda: TKWindowManager._returnValue(rv, True)
        ).pack(padx=20, side="left")
        tk.Button(
            frame, text="No", command=lambda: TKWindowManager._returnValue(rv, False)
        ).pack(padx=20, side="right")
        TKWindowManager.current_frame.destroy()
        TKWindowManager.current_frame = frame
        while rv["status"] is None:
            TKWindowManager.update()
            time.sleep(0.2)
        return rv["status"]

    def compare_multichoice(local_thumbnail, options):
        """allows user to choose from a group of image thumbnails"""
        rv = {"status": None}
        frame = tk.Frame(TKWindowManager.window)
        frame.pack(padx=10, pady=10)

        tk.Label(frame, text="Select the matching image").pack(padx=10, pady=10)
        ltn = ImageTk.PhotoImage(local_thumbnail)
        tk.Label(frame, text="Local Image", image=ltn).pack(padx=10, pady=10)
        imgs = []
        for option in options:
            img = ImageTk.PhotoImage(option["thumbnail"])
            imgs.append(img)
            tk.Button(
                frame,
                text="REMOTE: " + option["name"],
                image=img,
                command=lambda: TKWindowManager._returnValue(
                    rv, (option["thumbnail"], option["obj"])
                ),
            ).pack(padx=10, pady=10, side="left")
        tk.Button(
            frame,
            text="None",
            command=lambda: TKWindowManager._returnValue(rv, (None, None)),
        ).pack(padx=20, side="right")
        TKWindowManager.current_frame.destroy()
        TKWindowManager.current_frame = frame
        while rv["status"] is None:
            TKWindowManager.update()
            time.sleep(0.2)
        return rv["status"]

    def status(msg):
        frame = tk.Frame(TKWindowManager.window)
        frame.pack()
        tk.Label(
            frame, text=msg, font=tkFont.Font(TKWindowManager.window, size=32)
        ).pack()
        TKWindowManager.current_frame.destroy()
        TKWindowManager.current_frame = frame
        TKWindowManager.update()


# startup screen
TKWindowManager.current_frame.pack()
TKWindowManager.update()

from queue import Queue
import threading


class RoiCloudifier:
    """main class"""

    def __init__(
        self,
        local_parser: SirenFileReader,
        remote_parser: LLabOmeroNamespaceParser,
        wm=TKWindowManager,
        registrar=ValisLargeReconRoiRegistrar,
        multichoice_default=False,
    ) -> None:
        self.local_parser = local_parser
        self.remote_parser = remote_parser
        self.image_processing_queue = Queue()
        self.image_processed_queue = Queue()

        self.wm = wm
        self.registrar = registrar
        self.multichoice_default = multichoice_default
        self.succeded = []
        self.failed = []

    def fail(self, local_img_path):
        """registers failure"""
        self.failed.append(local_img_path)

    def success(self, local_img_path):
        """registers success"""
        self.succeded.append(local_img_path)

    def main(self, parent_dir):
        """searches parent dir and translates rois from one image to the remote medium"""

        threading.Thread(target=self._process_images).start()
        for local_tn, local_annot_path in self.local_parser.searchDirectory(parent_dir):
            # first, gather results if available
            while self.image_processed_queue.qsize() > 0:
                (
                    ltn,
                    local_annot_path,
                    rtn,
                    roi_objs,
                ) = self.image_processed_queue.get()
                if self.wm.compare(ltn, rtn, "Did ROIs Translate Properly?") is True:
                    self.remote_parser.saveRemoteRois(roi_objs)
                    self.success(local_annot_path)
                else:
                    self.fail(local_annot_path)
                ltn.close()
                rtn.close()
                self.image_processed_queue.task_done()

            # try to find local registration image. just want thumbnail for now
            local_reg_tn = None
            try:
                with self.local_parser.getRegistrationImage(
                    local_annot_path
                ) as local_reg_img:
                    local_reg_tn = local_reg_img.resize(
                        self.local_parser.THUMBNAIL_SIZE
                    )
            except FileNotFoundError:
                print(
                    "could not find registration image for this annotation. skipping..."
                )
                self.fail(local_annot_path)
                continue

            # get details and use them to give users option(s)
            try:
                details = self.local_parser.parse(local_annot_path)
            except AttributeError:
                print(f"File does not fit the capture groups: {local_annot_path}")
                self.fail(local_annot_path)
                continue

            # find remote image
            if self.multichoice_default is True:
                remote_tn, remote_img_ref = self.wm.compare_multichoice(
                    local_reg_tn, self.remote_parser.extendedRemoteImgSearch(details)
                )
            else:  # if not multichoice, try to get most likely image
                remote_tn, remote_img_ref = self.remote_parser.findPrimaryRemoteImage(
                    details
                )
                # if image is available ask for a match, otherwise definitely not a match
                force_multichoice = False
                if remote_img_ref is not None:
                    matching = self.wm.compare(local_reg_tn, remote_tn)
                else:
                    force_multichoice = True
                # if not a match, ask to do an extended search
                if matching is False:
                    if force_multichoice is False:
                        force_multichoice = self.wm.ask(
                            "Should we do an extended search?"
                        )
                    if force_multichoice is True:
                        remote_tn, remote_img_ref = self.wm.compare_multichoice(
                            local_reg_tn,
                            self.remote_parser.extendedRemoteImgSearch(details),
                        )
                    else:
                        remote_tn, remote_img_ref = None, None

            # if no remote image fail
            if remote_img_ref is None:
                print(
                    f"Could not find a remote copy of {local_annot_path}. skipping..."
                )
                self.fail(local_annot_path)
                continue

            # put successful mapping into queue
            self.image_processing_queue.put(
                (local_tn, local_annot_path, remote_img_ref, details)
            )

    def _process_images(self):
        conn = BlitzGateway(
            "", "", host="", port="", secure=True
        )
        try:
            conn.connect()
            conn.keepAlive()
            while True:
                # Get the next image processing task from the queue
                (
                    local_tn,
                    local_annot_path,
                    remote_img_ref,
                    details,
                ) = self.image_processing_queue.get()

                local_roi_contours = self.local_parser.getRoiContours(local_annot_path)

                with self.local_parser.getRegistrationImage(
                    local_annot_path
                ) as local_reg_img:
                    with self.remote_parser.getRegistrationImage(
                        remote_img_ref, details
                    ) as remote_reg_img:
                        warped_contours = self.registrar.transfer_rois(
                            local_roi_contours, local_reg_img, remote_reg_img
                        )

                        roi_tn, roi_objs = self.remote_parser.createRemoteRois(
                            remote_img_ref, remote_reg_img, warped_contours, details
                        )
                        self.image_processed_queue.put(
                            (
                                local_tn,
                                local_annot_path,
                                roi_tn,
                                roi_objs,
                            )
                        )
                # Mark the task as done
                self.image_processing_queue.task_done()
        finally:
            conn.close()


from omero.gateway import BlitzGateway

if __name__ == "__main__":
    conn = BlitzGateway(
        "", "", host="", port="", secure=True
    )
    try:
        conn.connect()
        conn.keepAlive()
        begin = time.time()
        cloudifier = RoiCloudifier(SirenFileReader(), LLabOmeroNamespaceParser(conn))
        cloudifier.main("/workdir/tempdir/Volumes/Siren/Prostate_data")
        print(f"took {time.time() - begin}")
    finally:
        conn.close()
