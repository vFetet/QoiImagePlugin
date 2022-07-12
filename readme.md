# Pillow QOI Image Plugin

A plugin adding support for QOI image files in Pillow.

See [qoiformat.org](https://qoiformat.org/) for more information on the QOI image format.

## Requirements

- Python v3.x
- Pillow v9.1 or higher

## Features

Open and save qoi image files.

Also, the code implements a streaming encoder and decoder written in pure Python. Hopefully, it can be used as a reference for people interrested in writing their own plugin for Pillow.

## Usage

Copy `QoiImagePlugin.py` in your working directory, and:

```
from PIL import Image
import QoiImagePlugin


# open a .qoi image
im = Image.open('path/to/image.qoi')

# save a .qoi image
im.save('path/to/image', 'qoi')

```

## License

This work is distributed under the terms of the MIT license. See LICENSE.txt for the full license text.