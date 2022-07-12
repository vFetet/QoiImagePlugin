# -*- coding: utf-8 -*-
"""
Quite OK Image format (.qoi)

QOI is a lossless, public-domain image format, aiming for simplicity and speed.

Specifications can be found on https://qoiformat.org/

Copyright 2022 Gaazoh <gahdev@protonmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import struct
from PIL import Image, ImageFile


QOI_MAGIC = b'qoif'
QOI_HEADER_RGB = 3
QOI_HEADER_RGBA = 4
QOI_HEADER_SRGB = 0
QOI_HEADER_LINEAR = 1
QOI_OP_RGB = 0xFE
QOI_OP_RGBA = 0xFF
QOI_OP_INDEX = 0x00
QOI_OP_DIFF = 0x40
QOI_OP_LUMA = 0x80
QOI_OP_RUN = 0xC0
QOI_OP_MASK = 0b11000000
QOI_EOF_MARKER = b'\x00\x00\x00\x00\x00\x00\x00\x01'


def _accept(prefix):
    return prefix[:4] == QOI_MAGIC


def _pixel_hash(pixel):
    r, g, b, a = pixel
    return (r * 3 + g * 5 + b * 7 + a * 11) % 64


class QoiImageFile(ImageFile.ImageFile):
    format = 'qoi'
    format_description = 'qoi format'

    def _open(self):
        self.fp.seek(4)
        self._size = struct.unpack('>II', self.fp.read(8))
        channels = struct.unpack('B', self.fp.read(1))[0]
        # FIXME: save colorspace info to image file somehow?
        # colorspace can be sRGB w/ linear alpha or all linear
        colorspace = struct.unpack('B', self.fp.read(1))[0]
        self.mode = 'RGB' if channels == QOI_HEADER_RGB else 'RGBA'

        self.tile = [('qoi', (0, 0) + self.size, 14, None)]


class QoiDecoder(ImageFile.PyDecoder):

    def __init__(self, mode, *args):
        super().__init__(mode, args)
        self.current_pixel = (0, 0, 0, 255)
        self.cache = [(0, 0, 0, 0) for _ in range(64)]
        self.x = 0
        self.y = 0

    def decode(self, buffer):
        i = 0
        while i + 5 < len(buffer):
            if buffer[i:i+8] == QOI_EOF_MARKER:
                return -1, 0
            tag = buffer[i]
            if tag == QOI_OP_RGBA:
                self.current_pixel = (buffer[i+1],
                                      buffer[i+2],
                                      buffer[i+3],
                                      buffer[i+4])
                i += 5

            elif tag == QOI_OP_RGB:
                self.current_pixel = (buffer[i+1],
                                      buffer[i+2],
                                      buffer[i+3],
                                      self.current_pixel[3])
                i += 4

            elif tag & QOI_OP_MASK == QOI_OP_INDEX:
                self.current_pixel = self.cache[tag & ~QOI_OP_MASK]
                i += 1

            elif tag & QOI_OP_MASK == QOI_OP_DIFF:
                dr = (tag >> 4 & 0b11) - 2
                dg = (tag >> 2 & 0b11) - 2
                db = (tag & 0b11) - 2
                self.current_pixel = ((self.current_pixel[0] + dr) % 256,
                                      (self.current_pixel[1] + dg) % 256,
                                      (self.current_pixel[2] + db) % 256,
                                      self.current_pixel[3])
                i += 1

            elif tag & QOI_OP_MASK == QOI_OP_LUMA:
                dg = (tag & ~QOI_OP_MASK) - 32
                diffs = buffer[i+1]
                dr = (diffs >> 4) - 8 + dg
                db = (diffs & 0b1111) - 8 + dg
                self.current_pixel = ((self.current_pixel[0] + dr) % 256,
                                      (self.current_pixel[1] + dg) % 256,
                                      (self.current_pixel[2] + db) % 256,
                                      self.current_pixel[3])
                i += 2
            elif tag & QOI_OP_MASK == QOI_OP_RUN:
                for _ in range((tag & ~QOI_OP_MASK) + 1):
                    self._set_pixel()
                i += 1
                continue

            self._set_pixel()
            self.cache[_pixel_hash(self.current_pixel)] = self.current_pixel
        return i, 0

    def cleanup(self):
        del(self.cache)
        del(self.current_pixel)
        del(self.x)
        del(self.y)

    def _set_pixel(self):
        if self.im.mode == 'RGBA':
            self.im.putpixel((self.x, self.y),
                             self.current_pixel)
        else:
            self.im.putpixel((self.x, self.y),
                             (self.current_pixel[0],
                              self.current_pixel[1],
                              self.current_pixel[2]))
        self.x += 1
        if self.x >= self.im.size[0]:
            self.y += 1
            self.x = 0


class QoiEncoder(ImageFile.PyEncoder):

    def __init__(self, mode, *args):
        super().__init__(mode, args)
        self.previous_pixel = (0, 0, 0, 255)
        self.cache = [(0, 0, 0, 0) for _ in range(64)]
        self.x = 0
        self.y = 0
        self.run = 0
        self.eof = False

    def encode(self, bufsize):
        buffer = bytearray(bufsize)
        i = 0
        while not self.eof and i + 6 < bufsize:
            pixel = self.im.getpixel((self.x, self.y))
            if len(pixel) == 3:
                pixel = pixel + (255, )
            dr = pixel[0] - self.previous_pixel[0]
            dg = pixel[1] - self.previous_pixel[1]
            db = pixel[2] - self.previous_pixel[2]

            if pixel == self.previous_pixel:
                # run
                self.run += 1
                if self.run > 61:
                    buffer[i] = QOI_OP_RUN | (self.run - 1)
                    self.run = 0
                    i += 1
                self._advance_pixel()
                continue

            if self.run:
                buffer[i] = QOI_OP_RUN | (self.run - 1)
                self.run = 0
                i += 1

            if pixel == self.cache[_pixel_hash(pixel)]:
                # index
                buffer[i] = QOI_OP_INDEX | _pixel_hash(pixel)
                i += 1

            elif (pixel[3] == self.previous_pixel[3]
                  and all((d + 2) % 256 < 4 for d in (dr, dg, db))):
                # diff
                buffer[i] = (QOI_OP_DIFF
                             | (dr + 2) % 256 << 4
                             | (dg + 2) % 256 << 2
                             | (db + 2) % 256)
                i += 1

            elif (pixel[3] == self.previous_pixel[3]
                  and (dg + 32) % 256 < 64
                  and (dr - dg + 8) % 256 < 16
                  and (db - dg + 8) % 256 < 16):
                # luma
                buffer[i] = QOI_OP_LUMA | (dg + 32) % 256
                buffer[i+1] = (dr - dg + 8) % 256 << 4 | (db - dg + 8) % 256
                i += 2

            elif pixel[3] == self.previous_pixel[3]:
                # rgb
                buffer[i:i+4] = (struct.pack('BBBB',
                                             QOI_OP_RGB,
                                             pixel[0],
                                             pixel[1],
                                             pixel[2]))
                i += 4

            else:
                # rgba
                buffer[i:i+5] = (struct.pack('BBBBB',
                                             QOI_OP_RGBA,
                                             pixel[0],
                                             pixel[1],
                                             pixel[2],
                                             pixel[3]))
                i += 5

            self.cache[_pixel_hash(pixel)] = pixel
            self.previous_pixel = pixel
            self._advance_pixel()

        if self.eof and self.run:
            buffer[i] = QOI_OP_RUN | (self.run - 1)
            i += 1

        return i, 1 if self.eof else 0, buffer

    def _advance_pixel(self):
        self.x += 1
        if self.x >= self.im.size[0]:
            self.y += 1
            self.x = 0
        self.eof = self.y >= self.im.size[1]

    def cleanup(self):
        del(self.cache)
        del(self.previous_pixel)
        del(self.x)
        del(self.y)
        del(self.run)
        del(self.eof)


def _save(im, fp, filename, save_all=False):
    if im.mode not in ['RGB', 'RGBA']:
        raise ValueError()
    fp.write(QOI_MAGIC)
    fp.write(struct.pack('>II', im.size[0], im.size[1]))
    fp.write(struct.pack('>B', 4 if im.mode == 'RGBA' else 3))
    # FIXME: pull colorspace info (sRGB w/ linear alpha or all linear)
    # from image object
    fp.write(struct.pack('>B', QOI_HEADER_SRGB))

    im.load()
    if not hasattr(im, "encoderconfig"):
        im.encoderconfig = ()
    bufsize = max(ImageFile.MAXBLOCK, im.size[0] * 4)
    fp.flush()
    encoder = Image._getencoder(im.mode, 'qoi', im.mode, im.encoderconfig)
    try:
        encoder.setimage(im.im, (0, 0) + im.size)
        while True:
            l, s, d = encoder.encode(bufsize)
            fp.write(d[:l])
            if s:
                break
        if s < 0:
            raise OSError(f"encoder error {s} when writing image file")
    finally:
        encoder.cleanup()
    if hasattr(fp, "flush"):
        fp.flush()

    fp.write(QOI_EOF_MARKER)


Image.register_open(QoiImageFile.format, QoiImageFile, _accept)
Image.register_extension(QoiImageFile.format, '.qoi')
Image.register_decoder('qoi', QoiDecoder)
Image.register_encoder('qoi', QoiEncoder)
Image.register_save(QoiImageFile.format, _save)
