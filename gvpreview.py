#!/usr/bin/env python3
import argparse as ap
import re
import tarfile
import os
import os.path as op
import glob
from tempfile import mkdtemp
from sys import stderr, stdout, stdin
import shutil

import skimage as ski
import numpy as np
import imageio



def XbyY2XY(xbyy):
    """Converts a string like 10x20 into a tuple: (10, 20)

    >>> XbyY2XY("10x20")
    (10, 20)
    >>> XbyY2XY("1X2")
    (1, 2)
    """
    m = re.match(r"(\d+)x(\d+)", xbyy, re.I)
    if m is None:
        raise ValueError(str(xbyy) + " doesn't appear to be in XxY format")
    return (int(m[1]), int(m[2]))

def index2rowcol(index, rows, cols, order):
    """Converts an index to an x and y within a rows by cols grid, filed in order

    Everything is zero-based, and coordinates are from top left (a la matricies)

    >>> index2rowcol(10, 5, 5, "colsright") # first row, 3rd col
    (0, 2)
    >>> index2rowcol(1, 5, 5, "colsright") # 2nd row, first col
    (1, 0)
    >>> index2rowcol(25, 5, 5, "colsright") # past end of matrix
    Traceback (most recent call last):
    ...
    ValueError: index is larger than it should be given rowsXcols
    """
    if index >= rows * cols:
        raise ValueError("index is larger than it should be given rowsXcols")
    order = order.lower()
    index = int(index)
    if order == "colsright":
        return (index % rows, index // rows)
    elif order == "colsleft":
        return (index % rows, index // rows)
        raise NotImplementedError("colsleft not done yet")
    elif order == "rowsdown":
        raise NotImplementedError("rowsdown not done yet")
    elif order == "rowsup":
        raise NotImplementedError("rowsup not done yet")
    else:
        raise ValueError("Bad order")


def load_downsize(pathorfile, size=None, scale=None):
    img = imageio.imread(pathorfile)
    if size is None and scale is None:
        return img
    elif size is not None:
        return ski.transform.resize(img, size, anti_aliasing=True)
    elif scale is not None:
        return ski.transform.rescale(img, scale, anti_aliasing=True)
    else:
        raise ValueError("Only one of size or scale can be given")

def filename2dateidx(path):
    fn = op.basename(path)
    m = re.match(r"(\S+)_(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}(_\d{2})+)_(\d+).(jpg|jpeg|tif|tiff)",
                 fn, re.I)
    if m is None:
        raise ValueError(path  + "  doesn't seem to be in the correct file naming format")
    camname = m[1]
    date = m[2]
    idx = int(m[4]) - 1
    ext = m[5]
    return (camname, date, idx, ext)



def gather_images(tarordir, format="jpg", tmpdir=None):
    if op.isdir(tarordir):
        files = glob.glob("{base}/*.{ext}".format(base=tarordir, ext=format))
        files.sort()
        return files
    else:
        # FIXME work out how to avoid extraction
        import fnmatch
        tf = tarfile.TarFile(tarordir)
        print("extracting", tarordir, "...", file=stderr, flush=True, end=" ")
        tf.extractall(tmpdir)
        print("done", file=stderr)
        return gather_images(tmpdir)


class CompositeImage(object):

    def __init__(self, dims, subdims):
        self.dims = dims
        self.subdims = subdims
        self.image = np.zeros((dims[0]*subdims[0], dims[1]*subdims[1], 3),
                              dtype=np.uint8)

    def set_subimage(self, row, col, image):
        top = row * self.subdims[0]
        bottom = top + self.subdims[0]
        left = col * self.subdims[1]
        right = left + self.subdims[1]
        self.image[top:bottom, left:right, ...] = image

def main():
    p = ap.ArgumentParser(prog="gvpreview")
    p.add_argument("-d", "--dims", type=str, required=True,
                   help="Dimension of super-image, in units of sub-images, ROWSxCOLS")
    p.add_argument("-s", "--resize", type=str, default="200x300",
                   help="Size of each sub-image, ROWSxCOLS")
    p.add_argument("-O", "--order", type=str, default="colsright",
                   choices=["colsright", "colsleft", "rowsdown", "rowsup"],
                   help="Order in which images are taken (cols or rows, left orright)")
    p.add_argument("-f", "--format", type=str, default="jpg",
                   help="File format of input images")
    p.add_argument("-o", "--output", type=str, required=True,
                   help="Output image")
    p.add_argument("input", type=str,
                   help="Input tarfile or directory of sub-images")

    args = p.parse_args()

    tmp = mkdtemp()

    superdim = XbyY2XY(args.dims)
    subdim = XbyY2XY(args.resize)

    comp = CompositeImage(superdim, subdim)
    print("input:", args.input)
    print("dimensions:", args.dims)
    print("images:")
    for image in gather_images(args.input, format=args.format, tmpdir=tmp):
        camname, date, idx, ext = filename2dateidx(image)
        pos = index2rowcol(idx, superdim[0], superdim[1], args.order)
        comp.set_subimage(pos[0], pos[1], load_downsize(image, size=subdim))
        print("\t-", camname, date, "at", pos)
    imageio.imsave(args.output, comp.image)
    shutil.rmtree(tmp)

if __name__ == "__main__":
    main()
