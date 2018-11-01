#!/usr/bin/env python3
# Copyright (c) 2018 Kevin Murray <kdmfoss@gmail.com>
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse as ap
import re
import tarfile
import os
import os.path as op
import glob
from tempfile import mkdtemp
from sys import stderr, stdout, stdin
import shutil
from collections import namedtuple

import skimage as ski
import numpy as np
import imageio

def nowarnings(func):
    def wrapped(*args, **kwargs):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return func(*args, **kwargs)
    return wrapped


Image = namedtuple("Image", "filename camname date index ext pixels")

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


@nowarnings
def downsize(img, size=None, scale=None):
    if size is not None and scale is not None:
        raise ValueError("Only one of size or scale can be given")
    elif size is not None:
        img = ski.transform.resize(img, size, anti_aliasing=True, mode="constant", order=3)
    elif scale is not None:
        img = ski.transform.rescale(img, scale, anti_aliasing=True)
    return ski.img_as_ubyte(img)

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


@nowarnings
def gather_images(tarordir, format="jpg"):
    if op.isdir(tarordir):
        files = glob.glob("{base}/*.{ext}".format(base=tarordir, ext=format))
        for file in files:
            try:
                c, d, i, e = filename2dateidx(file)
                pix = imageio.imread(file)
                if e == format:
                    yield Image(file, c, d, i, e, pix)
            except Exception as e:
                print("Skipping", entry.name, ":", str(e), file=stderr)
    else:
        tf = tarfile.TarFile(tarordir)
        for entry in tf:
            try:
                c, d, i, e = filename2dateidx(entry.name)
                pix = imageio.imread(tf.extractfile(entry))
                if e == format:
                    yield Image(entry.name, c, d, i, e, pix)
            except Exception as e:
                print("Skipping", entry.name, ":", str(e), file=stderr)


class CompositeImage(object):
    """Class to piece together composite images

    >>> import numpy as np
    >>> ci = CompositeImage((2, 3), (100, 100))
    >>> ci.image.shape
    (200, 300, 3)
    >>> ci.image.sum()
    0
    >>> ci.set_subimage((1, 1), np.ones((100, 100, 3)))
    >>> ci.image[99, 99, 1]
    0
    >>> ci.image[100, 100, 1]
    1
    >>> ci.image.sum()
    30000
    """
    def __init__(self, dims, subdims):
        self.dims = dims
        self.subdims = subdims
        self.image = np.zeros((dims[0]*subdims[0], dims[1]*subdims[1], 3),
                              dtype=np.uint8)

    def set_subimage(self, pos, image):
        row, col = pos
        top = row * self.subdims[0]
        bottom = top + self.subdims[0]
        left = col * self.subdims[1]
        right = left + self.subdims[1]
        self.image[top:bottom, left:right, ...] = image


def make_composite(input, output, dims, resize, format="jpg",
                   order="colsright", verbose=False):
    superdim = XbyY2XY(dims)
    subdim = XbyY2XY(resize)
    comp = CompositeImage(superdim, subdim)
    print("input:", input)
    print("dimensions:", dims)
    if verbose:
        print("images:")
    n = 0
    try:
        for image in gather_images(input, format=format):
            pos = index2rowcol(image.index, superdim[0], superdim[1], order)
            comp.set_subimage(pos, downsize(image.pixels, size=subdim))
            if verbose:
                print("\t- inserted", image.filename, "at", pos,
                    "pixelsum is", comp.image.sum())
            n += 1
    except KeyboardInterrupt as e:
        print("Terminating early due to Ctrl-C")
    except Exception as e:
        print("Terminating early due to error:", str(e))
    print("num_images:", n)
    imageio.imsave(output, comp.image)


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
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Use verbose output")
    p.add_argument("-o", "--output", type=str, required=True,
                   help="Output image")
    p.add_argument("input", type=str,
                   help="Input tarfile or directory of sub-images")

    args = p.parse_args()
    make_composite(args.input, args.output, args.dims, args.resize, args.format,
                   args.order, args.verbose)


if __name__ == "__main__":
    main()
